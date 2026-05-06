"""Burn-rate calculation and alerting logic.

Implements multi-window burn-rate alerting as described in the Google SRE
Workbook (Chapter 5: Alerting on SLOs). The burn rate is defined as:

    burn_rate = (error_rate_observed / error_rate_allowed)

A burn rate of 1.0 means consuming the error budget at exactly the expected
rate. A burn rate of 14.4 means consuming the entire 30-day budget in 2 hours.

The multi-window approach requires BOTH a short window AND a long window to
be exceeding the burn-rate threshold before firing, which reduces false
positives from brief spikes.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from azure.core.credentials import TokenCredential

from azure_slo_guardian.config import SLO, BurnRateWindow, Objective, parse_duration
from azure_slo_guardian.slo_calculator import SLOCalculator

logger = logging.getLogger(__name__)


@dataclass
class BurnRateAlert:
    """Burn rate alert result."""

    slo_name: str
    window_config: BurnRateWindow
    short_window_burn_rate: float
    long_window_burn_rate: float
    burn_rate_threshold: float
    target: float
    is_alerting: bool
    severity: str
    message: str
    measured_at: datetime
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        result = {
            "slo_name": self.slo_name,
            "consume_budget": self.window_config.consume_budget,
            "short_window": self.window_config.short_window,
            "long_window": self.window_config.long_window,
            "short_window_burn_rate": round(self.short_window_burn_rate, 2),
            "long_window_burn_rate": round(self.long_window_burn_rate, 2),
            "burn_rate_threshold": round(self.burn_rate_threshold, 2),
            "target": self.target,
            "is_alerting": self.is_alerting,
            "severity": self.severity,
            "message": self.message,
            "measured_at": self.measured_at.isoformat(),
        }
        if self.error is not None:
            result["error"] = self.error
        return result


class BurnRateCalculator:
    """Calculate burn-rate alerts following Google SRE Workbook recommendations.

    Multi-window burn-rate alerting detects both fast and slow budget consumption.
    The burn-rate threshold is derived from how quickly you'd exhaust the error
    budget:

        burn_rate_threshold = (objective_window / consume_window)
                            × (consume_budget_pct / 100)

    For example, if consume_budget=2% and the objective is 30d, consuming 2% of
    the budget over 1h means:

        threshold = (30d / 1h) × 0.02 = 720 × 0.02 = 14.4×

    Both the short AND long windows must exceed this threshold to fire.
    """

    def __init__(self, credential: Optional[TokenCredential] = None):
        """Initialize burn rate calculator."""
        self.slo_calculator = SLOCalculator(credential)

    def _compute_burn_rate(self, current_sli: float, target: float) -> float:
        """Compute burn rate from observed SLI and target.

        burn_rate = error_rate_observed / error_rate_allowed
                  = (100 - current_sli) / (100 - target)

        A burn rate of 1.0 means consuming budget at exactly the allowed rate.
        """
        error_budget = 100.0 - target
        if error_budget <= 0:
            return 0.0
        observed_error = 100.0 - current_sli
        return max(0.0, observed_error / error_budget)

    def calculate_burn_rate(
        self,
        slo: SLO,
        window_config: BurnRateWindow,
        end_time: Optional[datetime] = None,
    ) -> BurnRateAlert:
        """Calculate burn rate alert for a specific window configuration.

        Args:
            slo: SLO configuration
            window_config: Burn rate window configuration
            end_time: End time for calculation (default: now)

        Returns:
            BurnRateAlert with alert status
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        objective = slo.objectives[0]
        target = objective.target

        try:
            # Calculate SLI for short and long windows
            short_obj = Objective(target=target, window=window_config.short_window)
            long_obj = Objective(target=target, window=window_config.long_window)

            short_status = self.slo_calculator.calculate_slo(slo, short_obj, end_time)
            long_status = self.slo_calculator.calculate_slo(slo, long_obj, end_time)

            # Compute burn rates for each window
            short_burn_rate = self._compute_burn_rate(short_status.current_sli, target)
            long_burn_rate = self._compute_burn_rate(long_status.current_sli, target)

            # Calculate the burn-rate threshold from the consume_budget config.
            # consume_budget = what % of the total error budget this alert detects.
            # The threshold is how many × faster than normal the budget is being consumed.
            objective_delta = objective.get_window_timedelta()
            long_delta = parse_duration(window_config.long_window)

            # Threshold: if we consume consume_budget% of the budget over the long_window,
            # that's a burn rate of:
            burn_rate_threshold = (
                (window_config.consume_budget / 100.0)
                * (objective_delta.total_seconds() / long_delta.total_seconds())
            )

            # Alert fires when BOTH windows exceed the threshold (multi-window strategy)
            is_alerting = (
                short_burn_rate >= burn_rate_threshold
                and long_burn_rate >= burn_rate_threshold
            )

            logger.debug(
                "Burn rate '%s': short=%.2fx, long=%.2fx, threshold=%.2fx, alerting=%s",
                slo.name, short_burn_rate, long_burn_rate, burn_rate_threshold, is_alerting,
            )

            # Severity based on burn rate intensity
            if burn_rate_threshold >= 14.0:
                severity = "critical"
            elif burn_rate_threshold >= 6.0:
                severity = "high"
            else:
                severity = "warning"

            if is_alerting:
                message = (
                    f"SLO '{slo.name}' burn rate alert: consuming error budget at "
                    f"{long_burn_rate:.1f}x the allowed rate "
                    f"(threshold: {burn_rate_threshold:.1f}x). "
                    f"Short window ({window_config.short_window}): {short_burn_rate:.1f}x, "
                    f"Long window ({window_config.long_window}): {long_burn_rate:.1f}x"
                )
            else:
                message = (
                    f"SLO '{slo.name}' burn rate OK: "
                    f"{long_burn_rate:.1f}x (threshold: {burn_rate_threshold:.1f}x)"
                )

            return BurnRateAlert(
                slo_name=slo.name,
                window_config=window_config,
                short_window_burn_rate=short_burn_rate,
                long_window_burn_rate=long_burn_rate,
                burn_rate_threshold=burn_rate_threshold,
                target=target,
                is_alerting=is_alerting,
                severity=severity,
                message=message,
                measured_at=end_time,
            )

        except Exception as e:
            logger.error("Failed to calculate burn rate for %s: %s", slo.name, e)
            return BurnRateAlert(
                slo_name=slo.name,
                window_config=window_config,
                short_window_burn_rate=0.0,
                long_window_burn_rate=0.0,
                burn_rate_threshold=0.0,
                target=target,
                is_alerting=False,
                severity="unknown",
                message=f"Error calculating burn rate: {e}",
                measured_at=end_time,
                error=str(e),
            )

    def calculate_all_burn_rates(
        self, slo: SLO, end_time: Optional[datetime] = None
    ) -> List[BurnRateAlert]:
        """Calculate all burn rate alerts for an SLO.

        Args:
            slo: SLO configuration
            end_time: End time for calculation (default: now)

        Returns:
            List of BurnRateAlert for all configured windows
        """
        if not slo.alerting or not slo.alerting.enabled:
            return []

        results = []
        for window_config in slo.alerting.windows:
            alert = self.calculate_burn_rate(slo, window_config, end_time)
            results.append(alert)

        return results

"""Burn-rate calculation and alerting logic."""

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
    short_window_sli: float
    long_window_sli: float
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
            "short_window_sli": self.short_window_sli,
            "long_window_sli": self.long_window_sli,
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
    """Calculate burn-rate alerts following Google SRE workbook recommendations.

    Multi-window burn-rate alerting detects both fast and slow budget consumption.
    """

    def __init__(self, credential: Optional[TokenCredential] = None):
        """Initialize burn rate calculator."""
        self.slo_calculator = SLOCalculator(credential)

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

        # Get the primary objective (use first one)
        objective = slo.objectives[0]
        target = objective.target

        # Calculate SLI for short and long windows
        short_delta = parse_duration(window_config.short_window)
        long_delta = parse_duration(window_config.long_window)

        short_start = end_time - short_delta
        long_start = end_time - long_delta

        try:
            # Create temporary objectives for each window
            short_obj = Objective(target=target, window=window_config.short_window)
            long_obj = Objective(target=target, window=window_config.long_window)

            short_status = self.slo_calculator.calculate_slo(slo, short_obj, end_time)
            long_status = self.slo_calculator.calculate_slo(slo, long_obj, end_time)

            short_sli = short_status.current_sli
            long_sli = long_status.current_sli

            # Calculate burn rate
            # Burn rate = (target - actual_sli) / error_budget
            error_budget = 100.0 - target

            # Check if both windows are burning budget faster than acceptable
            # Alert if consuming budget % faster than normal rate
            objective_delta = objective.get_window_timedelta()

            # Expected error rate per window based on consume_budget
            # If we want to consume X% of budget over the objective window,
            # we calculate acceptable error rate for shorter windows
            budget_consumption_rate = window_config.consume_budget / 100.0

            # Calculate acceptable SLI for this consumption rate
            acceptable_error_for_short = error_budget * budget_consumption_rate * (
                short_delta.total_seconds() / objective_delta.total_seconds()
            )
            acceptable_sli_short = 100.0 - acceptable_error_for_short

            acceptable_error_for_long = error_budget * budget_consumption_rate * (
                long_delta.total_seconds() / objective_delta.total_seconds()
            )
            acceptable_sli_long = 100.0 - acceptable_error_for_long

            # Alert if both windows are below acceptable SLI
            is_alerting = short_sli < acceptable_sli_short and long_sli < acceptable_sli_long

            logger.debug(
                "Burn rate '%s': short_sli=%.4f%% (acceptable=%.4f%%), "
                "long_sli=%.4f%% (acceptable=%.4f%%), alerting=%s",
                slo.name, short_sli, acceptable_sli_short,
                long_sli, acceptable_sli_long, is_alerting,
            )

            # Determine severity based on how much budget is being consumed
            severity = "warning"
            if window_config.consume_budget >= 10:
                severity = "critical"
            elif window_config.consume_budget >= 5:
                severity = "high"

            if is_alerting:
                message = (
                    f"SLO '{slo.name}' is burning error budget at {window_config.consume_budget}% "
                    f"rate. Short window ({window_config.short_window}) SLI: {short_sli:.2f}%, "
                    f"Long window ({window_config.long_window}) SLI: {long_sli:.2f}%, "
                    f"Target: {target}%"
                )
            else:
                message = f"SLO '{slo.name}' burn rate is acceptable"

            return BurnRateAlert(
                slo_name=slo.name,
                window_config=window_config,
                short_window_sli=short_sli,
                long_window_sli=long_sli,
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
                short_window_sli=0.0,
                long_window_sli=0.0,
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

"""SLO calculation and error budget tracking."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from azure.core.credentials import TokenCredential

from azure_slo_guardian.config import SLO, Objective, Operator, SLIType
from azure_slo_guardian.query_engine import AzureQueryEngine

logger = logging.getLogger(__name__)


@dataclass
class ErrorBudget:
    """Error budget calculation result."""

    slo_name: str
    target: float
    window: str
    current_sli: float
    error_budget_total: float
    error_budget_remaining: float
    error_budget_consumed_pct: float
    is_exhausted: bool
    measured_at: datetime

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "slo_name": self.slo_name,
            "target": self.target,
            "window": self.window,
            "current_sli": self.current_sli,
            "error_budget_total": self.error_budget_total,
            "error_budget_remaining": self.error_budget_remaining,
            "error_budget_consumed_pct": self.error_budget_consumed_pct,
            "is_exhausted": self.is_exhausted,
            "measured_at": self.measured_at.isoformat(),
        }


@dataclass
class SLOStatus:
    """SLO status for an objective."""

    slo_name: str
    service: str
    description: str
    objective: Objective
    current_sli: float
    is_meeting_slo: bool
    error_budget: ErrorBudget
    measured_at: datetime
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "slo_name": self.slo_name,
            "service": self.service,
            "description": self.description,
            "target": self.objective.target,
            "window": self.objective.window,
            "current_sli": self.current_sli,
            "is_meeting_slo": self.is_meeting_slo,
            "error_budget": self.error_budget.to_dict(),
            "measured_at": self.measured_at.isoformat(),
            "error": self.error,
        }


class SLOCalculator:
    """Calculate SLO compliance and error budgets."""

    def __init__(self, credential: Optional[TokenCredential] = None):
        """Initialize SLO calculator.

        Args:
            credential: Azure credential for queries.
        """
        self.query_engine = AzureQueryEngine(credential)

    def calculate_slo(
        self,
        slo: SLO,
        objective: Objective,
        end_time: Optional[datetime] = None,
    ) -> SLOStatus:
        """Calculate SLO status for a specific objective.

        Args:
            slo: SLO configuration
            objective: Specific objective to evaluate
            end_time: End time for evaluation (default: now)

        Returns:
            SLOStatus with current status and error budget
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        # Calculate time window
        window_delta = objective.get_window_timedelta()
        start_time = end_time - window_delta

        # Calculate SLI based on type
        try:
            logger.debug(
                "Calculating SLO '%s' (type=%s, target=%.2f%%, window=%s)",
                slo.name, slo.sli.type.value, objective.target, objective.window,
            )

            if slo.sli.type in (SLIType.AVAILABILITY, SLIType.CUSTOM):
                current_sli = self._calculate_ratio_sli(slo, start_time, end_time)
            elif slo.sli.type == SLIType.LATENCY:
                current_sli = self._calculate_threshold_sli(slo, start_time, end_time)
            else:
                raise ValueError(f"Unsupported SLI type: {slo.sli.type}")

            # Calculate error budget
            error_budget = self._calculate_error_budget(
                slo.name, objective, current_sli, end_time
            )

            is_meeting_slo = current_sli >= objective.target
            logger.info(
                "SLO '%s': sli=%.4f%%, target=%.2f%%, meeting=%s, budget_consumed=%.1f%%",
                slo.name, current_sli, objective.target, is_meeting_slo,
                error_budget.error_budget_consumed_pct,
            )

            return SLOStatus(
                slo_name=slo.name,
                service=slo.service,
                description=slo.description,
                objective=objective,
                current_sli=current_sli,
                is_meeting_slo=is_meeting_slo,
                error_budget=error_budget,
                measured_at=end_time,
            )

        except Exception as e:
            logger.error(f"Failed to calculate SLO for {slo.name}: {e}")
            # Return error status with 0 SLI
            error_budget = ErrorBudget(
                slo_name=slo.name,
                target=objective.target,
                window=objective.window,
                current_sli=0.0,
                error_budget_total=100.0 - objective.target,
                error_budget_remaining=0.0,
                error_budget_consumed_pct=100.0,
                is_exhausted=True,
                measured_at=end_time,
            )

            return SLOStatus(
                slo_name=slo.name,
                service=slo.service,
                description=slo.description,
                objective=objective,
                current_sli=0.0,
                is_meeting_slo=False,
                error_budget=error_budget,
                measured_at=end_time,
                error=str(e),
            )

    def _calculate_ratio_sli(
        self, slo: SLO, start_time: datetime, end_time: datetime
    ) -> float:
        """Calculate ratio-based SLI (e.g., availability, success rate)."""
        good_count, total_count, error = self.query_engine.execute_ratio_queries(
            slo.sli, start_time, end_time
        )

        if error:
            raise RuntimeError(error)

        if total_count == 0:
            logger.warning(
                "SLO '%s': total_count is 0 for window %s to %s. "
                "This may indicate missing instrumentation or no traffic. "
                "Returning 100%% SLI per SRE best practice.",
                slo.name,
                start_time.isoformat(),
                end_time.isoformat(),
            )
            return 100.0

        ratio = good_count / total_count
        sli = ratio * 100.0
        logger.info(
            "SLO '%s' ratio SLI: good=%s, total=%s, sli=%.4f%%",
            slo.name, good_count, total_count, sli,
        )
        return sli

    def _calculate_threshold_sli(
        self, slo: SLO, start_time: datetime, end_time: datetime
    ) -> float:
        """Calculate threshold-based SLI (e.g., latency under threshold).

        For ratio-based latency SLIs (good_query + total_query provided),
        delegates to _calculate_ratio_sli. Otherwise uses the single query
        approach to get a scalar measurement.
        """
        # If good_query and total_query are available, treat as ratio SLI
        if slo.sli.good_query and slo.sli.total_query:
            return self._calculate_ratio_sli(slo, start_time, end_time)

        measured_value, error = self.query_engine.execute_threshold_query(
            slo.sli, start_time, end_time
        )

        if error:
            raise RuntimeError(error)

        # Check if value meets threshold
        threshold = slo.sli.threshold
        operator = slo.sli.operator

        meets_threshold = False
        if operator == Operator.LT:
            meets_threshold = measured_value < threshold
        elif operator == Operator.LTE:
            meets_threshold = measured_value <= threshold
        elif operator == Operator.GT:
            meets_threshold = measured_value > threshold
        elif operator == Operator.GTE:
            meets_threshold = measured_value >= threshold

        return 100.0 if meets_threshold else 0.0

    def _calculate_error_budget(
        self,
        slo_name: str,
        objective: Objective,
        current_sli: float,
        measured_at: datetime,
    ) -> ErrorBudget:
        """Calculate error budget from SLI and objective.

        Error budget = (100 - target) - (100 - current_sli)
                     = current_sli - target
        """
        # Total error budget is the allowed error percentage
        error_budget_total = 100.0 - objective.target

        # Current error is how much we're below the SLI
        current_error = 100.0 - current_sli

        # Remaining budget
        error_budget_remaining = error_budget_total - current_error

        # Percentage consumed (can exceed 100% to show overburn)
        if error_budget_total > 0:
            error_budget_consumed_pct = (current_error / error_budget_total) * 100.0
        else:
            error_budget_consumed_pct = 0.0 if current_error == 0 else 100.0

        # Only clamp the floor at 0% (allow >100% to show overburn)
        error_budget_consumed_pct = max(0.0, error_budget_consumed_pct)

        is_exhausted = error_budget_remaining <= 0

        return ErrorBudget(
            slo_name=slo_name,
            target=objective.target,
            window=objective.window,
            current_sli=current_sli,
            error_budget_total=error_budget_total,
            error_budget_remaining=error_budget_remaining,
            error_budget_consumed_pct=error_budget_consumed_pct,
            is_exhausted=is_exhausted,
            measured_at=measured_at,
        )

    def calculate_all_slos(
        self, slos: list[SLO], end_time: Optional[datetime] = None
    ) -> list[SLOStatus]:
        """Calculate status for all SLOs and their objectives.

        Args:
            slos: List of SLO configurations
            end_time: End time for evaluation (default: now)

        Returns:
            List of SLOStatus for all SLO objectives
        """
        results = []
        for slo in slos:
            for objective in slo.objectives:
                status = self.calculate_slo(slo, objective, end_time)
                results.append(status)
        return results

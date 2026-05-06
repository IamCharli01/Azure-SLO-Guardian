"""Unit tests for SLO calculator."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from azure_slo_guardian.config import (
    Objective,
    Operator,
    QueryType,
    SLIConfig,
    SLIType,
    SLO,
)
from azure_slo_guardian.slo_calculator import ErrorBudget, SLOCalculator, SLOStatus


class TestErrorBudget:
    """Test ErrorBudget dataclass."""

    def test_error_budget_to_dict(self):
        now = datetime.utcnow()
        budget = ErrorBudget(
            slo_name="test",
            target=99.9,
            window="30d",
            current_sli=99.95,
            error_budget_total=0.1,
            error_budget_remaining=0.05,
            error_budget_consumed_pct=50.0,
            is_exhausted=False,
            measured_at=now,
        )

        result = budget.to_dict()
        assert result["slo_name"] == "test"
        assert result["target"] == 99.9
        assert result["is_exhausted"] is False


class TestSLOCalculator:
    """Test SLO calculator."""

    def test_calculate_error_budget_meeting_slo(self):
        calculator = SLOCalculator()
        objective = Objective(target=99.9, window="30d")

        budget = calculator._calculate_error_budget(
            "test-slo", objective, current_sli=99.95, measured_at=datetime.utcnow()
        )

        assert budget.target == 99.9
        assert budget.current_sli == 99.95
        assert budget.error_budget_total == pytest.approx(0.1)
        assert budget.error_budget_remaining > 0
        assert not budget.is_exhausted
        assert budget.error_budget_consumed_pct < 100

    def test_calculate_error_budget_not_meeting_slo(self):
        calculator = SLOCalculator()
        objective = Objective(target=99.9, window="30d")

        budget = calculator._calculate_error_budget(
            "test-slo", objective, current_sli=99.8, measured_at=datetime.utcnow()
        )

        assert budget.current_sli == 99.8
        assert budget.error_budget_remaining < 0
        assert budget.is_exhausted
        # Consumed pct now unclamped — shows actual overburn
        assert budget.error_budget_consumed_pct == pytest.approx(200.0, rel=1e-3)

    def test_calculate_error_budget_exhausted(self):
        calculator = SLOCalculator()
        objective = Objective(target=99.9, window="30d")

        budget = calculator._calculate_error_budget(
            "test-slo", objective, current_sli=99.0, measured_at=datetime.utcnow()
        )

        assert budget.current_sli == 99.0
        # Total budget is 0.1%, but we're at 1.0% error (100 - 99.0)
        # So consumed percentage is 1000% (unclamped to show overburn)
        assert budget.is_exhausted
        assert budget.error_budget_consumed_pct == pytest.approx(1000.0, rel=1e-3)

    def test_calculate_error_budget_perfect_sli(self):
        calculator = SLOCalculator()
        objective = Objective(target=99.9, window="30d")

        budget = calculator._calculate_error_budget(
            "test-slo", objective, current_sli=100.0, measured_at=datetime.utcnow()
        )

        assert budget.current_sli == 100.0
        assert budget.error_budget_remaining == budget.error_budget_total
        assert not budget.is_exhausted
        assert budget.error_budget_consumed_pct == 0.0

    def test_calculate_error_budget_100_target(self):
        """Edge case: 100% target means zero error budget."""
        calculator = SLOCalculator()
        objective = Objective(target=100.0, window="7d")
        budget = calculator._calculate_error_budget(
            "strict", objective, current_sli=100.0, measured_at=datetime.utcnow()
        )
        assert budget.error_budget_total == 0.0
        assert budget.error_budget_consumed_pct == 0.0


# ---------------------------------------------------------------------------
# SLO Status
# ---------------------------------------------------------------------------


class TestSLOStatus:
    """Test SLOStatus dataclass."""

    def test_to_dict(self):
        now = datetime.now(timezone.utc)
        obj = Objective(target=99.9, window="30d")
        status = SLOStatus(
            slo_name="s",
            service="svc",
            description="d",
            objective=obj,
            current_sli=99.95,
            is_meeting_slo=True,
            error_budget=ErrorBudget(
                slo_name="s", target=99.9, window="30d",
                current_sli=99.95, error_budget_total=0.1,
                error_budget_remaining=0.05,
                error_budget_consumed_pct=50.0,
                is_exhausted=False, measured_at=now,
            ),
            measured_at=now,
        )
        d = status.to_dict()
        assert d["slo_name"] == "s"
        assert d["is_meeting_slo"] is True
        assert d["error"] is None
        assert "error_budget" in d

    def test_to_dict_with_error(self):
        now = datetime.now(timezone.utc)
        obj = Objective(target=99.9, window="30d")
        status = SLOStatus(
            slo_name="s", service="svc", description="d",
            objective=obj, current_sli=0.0, is_meeting_slo=False,
            error_budget=ErrorBudget(
                slo_name="s", target=99.9, window="30d",
                current_sli=0.0, error_budget_total=0.1,
                error_budget_remaining=-99.9,
                error_budget_consumed_pct=100.0,
                is_exhausted=True, measured_at=now,
            ),
            measured_at=now, error="query failed",
        )
        d = status.to_dict()
        assert d["error"] == "query failed"


# ---------------------------------------------------------------------------
# End-to-end calculator with mocked query engine
# ---------------------------------------------------------------------------


def _make_slo(sli_type=SLIType.AVAILABILITY) -> SLO:
    if sli_type == SLIType.LATENCY:
        sli = SLIConfig(
            type=SLIType.LATENCY,
            query_type=QueryType.APPLICATION_INSIGHTS,
            workspace_id="ws",
            query="requests | summarize percentile(duration, 95)",
            threshold=500,
            operator=Operator.LTE,
        )
    else:
        sli = SLIConfig(
            type=sli_type,
            query_type=QueryType.APPLICATION_INSIGHTS,
            workspace_id="ws",
            good_query="good",
            total_query="total",
        )
    return SLO(
        name="test",
        description="Test",
        service="svc",
        sli=sli,
        objectives=[Objective(target=99.9, window="30d")],
    )


class TestCalculateSLO:
    """Test calculate_slo with mocked query engine."""

    def test_availability_ratio(self):
        calc = SLOCalculator()
        with patch.object(
            calc.query_engine, "execute_ratio_queries",
            return_value=(950.0, 1000.0, None),
        ):
            status = calc.calculate_slo(
                _make_slo(), Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == pytest.approx(95.0)
        assert not status.is_meeting_slo
        assert status.error is None

    def test_availability_no_events(self):
        calc = SLOCalculator()
        with patch.object(
            calc.query_engine, "execute_ratio_queries",
            return_value=(0.0, 0.0, None),
        ):
            status = calc.calculate_slo(
                _make_slo(), Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == 100.0
        assert status.is_meeting_slo

    def test_latency_meets_threshold(self):
        calc = SLOCalculator()
        with patch.object(
            calc.query_engine, "execute_threshold_query",
            return_value=(300.0, None),
        ):
            status = calc.calculate_slo(
                _make_slo(SLIType.LATENCY), Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == 100.0
        assert status.is_meeting_slo

    def test_latency_exceeds_threshold(self):
        calc = SLOCalculator()
        with patch.object(
            calc.query_engine, "execute_threshold_query",
            return_value=(600.0, None),
        ):
            status = calc.calculate_slo(
                _make_slo(SLIType.LATENCY), Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == 0.0
        assert not status.is_meeting_slo

    def test_query_error_returns_error_status(self):
        calc = SLOCalculator()
        with patch.object(
            calc.query_engine, "execute_ratio_queries",
            return_value=(None, None, "connection refused"),
        ):
            status = calc.calculate_slo(
                _make_slo(), Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == 0.0
        assert not status.is_meeting_slo
        assert status.error is not None
        assert status.error_budget.is_exhausted

    def test_calculate_all_slos(self):
        calc = SLOCalculator()
        slo = _make_slo()
        slo.objectives = [
            Objective(target=99.9, window="30d"),
            Objective(target=99.5, window="7d"),
        ]
        with patch.object(
            calc.query_engine, "execute_ratio_queries",
            return_value=(999.0, 1000.0, None),
        ):
            results = calc.calculate_all_slos([slo])
        assert len(results) == 2
        assert results[0].objective.window == "30d"
        assert results[1].objective.window == "7d"


class TestErrorBudgetOverburn:
    """Test that error_budget_consumed_pct shows values > 100% for overburned budgets."""

    def test_200_percent_overburn(self):
        calc = SLOCalculator()
        objective = Objective(target=99.9, window="30d")
        budget = calc._calculate_error_budget(
            "test-slo", objective, current_sli=99.8, measured_at=datetime.utcnow()
        )
        # 0.2% error vs 0.1% budget = 200% consumed
        assert budget.error_budget_consumed_pct == pytest.approx(200.0, rel=1e-3)
        assert budget.is_exhausted

    def test_severe_overburn(self):
        calc = SLOCalculator()
        objective = Objective(target=99.9, window="30d")
        budget = calc._calculate_error_budget(
            "test-slo", objective, current_sli=90.0, measured_at=datetime.utcnow()
        )
        # 10% error vs 0.1% budget = 10,000% consumed
        assert budget.error_budget_consumed_pct > 100.0
        assert budget.is_exhausted

    def test_floor_at_zero(self):
        calc = SLOCalculator()
        objective = Objective(target=99.9, window="30d")
        budget = calc._calculate_error_budget(
            "test-slo", objective, current_sli=100.0, measured_at=datetime.utcnow()
        )
        assert budget.error_budget_consumed_pct == 0.0
        assert not budget.is_exhausted


class TestZeroEventsWarning:
    """Test that zero-events edge case logs a warning."""

    def test_zero_total_count_logs_warning(self, caplog):
        import logging
        calc = SLOCalculator()
        slo = _make_slo()
        with patch.object(
            calc.query_engine, "execute_ratio_queries",
            return_value=(0.0, 0.0, None),
        ), caplog.at_level(logging.WARNING, logger="azure_slo_guardian.slo_calculator"):
            status = calc.calculate_slo(
                slo, Objective(target=99.9, window="7d"),
                end_time=datetime.now(timezone.utc),
            )
        assert status.current_sli == 100.0
        assert any("total_count is 0" in msg for msg in caplog.messages)

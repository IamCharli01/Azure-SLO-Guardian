"""Unit tests for burn-rate calculator."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from azure_slo_guardian.burn_rate import BurnRateAlert, BurnRateCalculator
from azure_slo_guardian.config import (
    AlertingConfig,
    BurnRateWindow,
    Objective,
    QueryType,
    SLIConfig,
    SLIType,
    SLO,
)
from azure_slo_guardian.slo_calculator import ErrorBudget, SLOStatus


def _make_slo(alerting: AlertingConfig | None = None) -> SLO:
    """Create a test SLO with alerting config."""
    if alerting is None:
        alerting = AlertingConfig(
            enabled=True,
            windows=[
                BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
                BurnRateWindow(consume_budget=5.0, short_window="30m", long_window="6h"),
            ],
        )
    return SLO(
        name="test-slo",
        description="Test",
        service="test-service",
        sli=SLIConfig(
            type=SLIType.AVAILABILITY,
            query_type=QueryType.APPLICATION_INSIGHTS,
            workspace_id="test-ws",
            good_query="good",
            total_query="total",
        ),
        objectives=[Objective(target=99.9, window="30d")],
        alerting=alerting,
    )


def _mock_slo_status(sli: float, target: float, end_time: datetime) -> SLOStatus:
    """Create a mock SLOStatus for a given SLI value."""
    error_budget_total = 100.0 - target
    current_error = 100.0 - sli
    remaining = error_budget_total - current_error
    consumed = max(0.0, min(100.0, (current_error / error_budget_total) * 100.0))
    return SLOStatus(
        slo_name="test-slo",
        service="test-service",
        description="Test",
        objective=Objective(target=target, window="30d"),
        current_sli=sli,
        is_meeting_slo=sli >= target,
        error_budget=ErrorBudget(
            slo_name="test-slo",
            target=target,
            window="30d",
            current_sli=sli,
            error_budget_total=error_budget_total,
            error_budget_remaining=remaining,
            error_budget_consumed_pct=consumed,
            is_exhausted=remaining <= 0,
            measured_at=end_time,
        ),
        measured_at=end_time,
    )


class TestBurnRateAlert:
    """Test BurnRateAlert dataclass."""

    def test_to_dict(self):
        now = datetime.now(timezone.utc)
        window = BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h")
        alert = BurnRateAlert(
            slo_name="test",
            window_config=window,
            short_window_burn_rate=5.0,
            long_window_burn_rate=4.5,
            burn_rate_threshold=14.4,
            target=99.9,
            is_alerting=False,
            severity="critical",
            message="test message",
            measured_at=now,
        )
        d = alert.to_dict()
        assert d["slo_name"] == "test"
        assert d["is_alerting"] is False
        assert d["severity"] == "critical"
        assert d["short_window_burn_rate"] == 5.0
        assert d["long_window_burn_rate"] == 4.5
        assert d["burn_rate_threshold"] == 14.4


class TestBurnRateCalculator:
    """Test BurnRateCalculator."""

    def test_calculate_all_burn_rates_disabled(self):
        slo = _make_slo(alerting=AlertingConfig(enabled=False))
        calc = BurnRateCalculator()
        assert calc.calculate_all_burn_rates(slo) == []

    def test_calculate_all_burn_rates_no_alerting(self):
        slo = _make_slo()
        slo.alerting = None
        calc = BurnRateCalculator()
        assert calc.calculate_all_burn_rates(slo) == []

    @patch.object(BurnRateCalculator, "calculate_burn_rate")
    def test_calculate_all_burn_rates_returns_per_window(self, mock_calc):
        slo = _make_slo()
        now = datetime.now(timezone.utc)
        mock_calc.return_value = BurnRateAlert(
            slo_name="test-slo",
            window_config=slo.alerting.windows[0],
            short_window_burn_rate=0.5,
            long_window_burn_rate=0.5,
            burn_rate_threshold=14.4,
            target=99.9,
            is_alerting=False,
            severity="warning",
            message="OK",
            measured_at=now,
        )
        results = calc = BurnRateCalculator()
        results = calc.calculate_all_burn_rates(slo, now)
        assert len(results) == 2
        assert mock_calc.call_count == 2

    def test_calculate_burn_rate_healthy(self):
        """When SLI is well above target, no alert should fire."""
        slo = _make_slo()
        now = datetime.now(timezone.utc)
        calc = BurnRateCalculator()

        # Mock the underlying SLO calculator to return perfect SLIs
        with patch.object(
            calc.slo_calculator, "calculate_slo",
            side_effect=lambda s, obj, et: _mock_slo_status(100.0, obj.target, et),
        ):
            alert = calc.calculate_burn_rate(slo, slo.alerting.windows[0], now)

        assert not alert.is_alerting
        assert "OK" in alert.message

    def test_calculate_burn_rate_alerting(self):
        """When SLI is very low in both windows, alert should fire."""
        slo = _make_slo()
        now = datetime.now(timezone.utc)
        calc = BurnRateCalculator()

        # Mock terrible SLI in both windows
        with patch.object(
            calc.slo_calculator, "calculate_slo",
            side_effect=lambda s, obj, et: _mock_slo_status(90.0, obj.target, et),
        ):
            alert = calc.calculate_burn_rate(slo, slo.alerting.windows[0], now)

        assert alert.is_alerting
        assert "burn rate alert" in alert.message

    def test_calculate_burn_rate_error_returns_error_state(self):
        """When the calculator throws, return an error (not a false alert)."""
        slo = _make_slo()
        now = datetime.now(timezone.utc)
        calc = BurnRateCalculator()

        with patch.object(
            calc.slo_calculator, "calculate_slo",
            side_effect=RuntimeError("connection failed"),
        ):
            alert = calc.calculate_burn_rate(slo, slo.alerting.windows[0], now)

        assert not alert.is_alerting
        assert alert.severity == "unknown"
        assert alert.error == "connection failed"
        assert "Error calculating burn rate" in alert.message

    def test_severity_levels(self):
        """Test severity is assigned based on burn_rate_threshold derived from config."""
        slo = _make_slo()
        now = datetime.now(timezone.utc)
        calc = BurnRateCalculator()

        # burn_rate_threshold = (consume_budget/100) * (objective_window / long_window)
        # 2% over 1h with 30d objective → 0.02 * 720 = 14.4 → critical (>=14)
        # 5% over 6h with 30d objective → 0.05 * 120 = 6.0 → high (>=6)
        # 10% over 6h with 30d objective → 0.10 * 120 = 12.0 → high (>=6, <14)
        windows = [
            (BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"), "critical"),
            (BurnRateWindow(consume_budget=5.0, short_window="30m", long_window="6h"), "high"),
            (BurnRateWindow(consume_budget=10.0, short_window="1h", long_window="6h"), "high"),
        ]

        for window, expected_severity in windows:
            with patch.object(
                calc.slo_calculator, "calculate_slo",
                side_effect=lambda s, obj, et: _mock_slo_status(99.99, obj.target, et),
            ):
                alert = calc.calculate_burn_rate(slo, window, now)
            assert alert.severity == expected_severity, (
                f"Expected {expected_severity} for consume_budget={window.consume_budget}, "
                f"got {alert.severity} (threshold={alert.burn_rate_threshold:.1f})"
            )


class TestBurnRateAlertErrorField:
    """Test the error field on BurnRateAlert."""

    def test_error_field_in_to_dict_when_set(self):
        alert = BurnRateAlert(
            slo_name="test-slo",
            window_config=BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
            short_window_burn_rate=0.0,
            long_window_burn_rate=0.0,
            burn_rate_threshold=0.0,
            target=99.9,
            is_alerting=False,
            severity="unknown",
            message="Error",
            measured_at=datetime.now(timezone.utc),
            error="query failed",
        )
        d = alert.to_dict()
        assert d["error"] == "query failed"
        assert not d["is_alerting"]

    def test_error_field_absent_in_to_dict_when_none(self):
        alert = BurnRateAlert(
            slo_name="test-slo",
            window_config=BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
            short_window_burn_rate=0.5,
            long_window_burn_rate=0.4,
            burn_rate_threshold=14.4,
            target=99.9,
            is_alerting=False,
            severity="warning",
            message="OK",
            measured_at=datetime.now(timezone.utc),
        )
        d = alert.to_dict()
        assert "error" not in d

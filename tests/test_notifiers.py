"""Unit tests for webhook notifier."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from azure_slo_guardian.burn_rate import BurnRateAlert
from azure_slo_guardian.config import BurnRateWindow, Objective
from azure_slo_guardian.notifiers.webhook import (
    WebhookFormat,
    WebhookResult,
    _build_alert_payload,
    _build_status_payload,
    notify_burn_rate_alerts,
    notify_slo_status,
)
from azure_slo_guardian.slo_calculator import ErrorBudget, SLOStatus


def _slo_status(meeting: bool = True) -> SLOStatus:
    now = datetime.now(timezone.utc)
    sli = 99.95 if meeting else 99.5
    target = 99.9
    eb_total = 100.0 - target
    current_error = 100.0 - sli
    return SLOStatus(
        slo_name="test-slo",
        service="svc",
        description="Test",
        objective=Objective(target=target, window="30d"),
        current_sli=sli,
        is_meeting_slo=meeting,
        error_budget=ErrorBudget(
            slo_name="test-slo", target=target, window="30d",
            current_sli=sli, error_budget_total=eb_total,
            error_budget_remaining=eb_total - current_error,
            error_budget_consumed_pct=max(0.0, min(100.0, (current_error / eb_total) * 100.0)),
            is_exhausted=(eb_total - current_error) <= 0,
            measured_at=now,
        ),
        measured_at=now,
    )


def _alert(alerting: bool = True) -> BurnRateAlert:
    return BurnRateAlert(
        slo_name="test-slo",
        window_config=BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
        short_window_sli=90.0 if alerting else 99.95,
        long_window_sli=90.0 if alerting else 99.95,
        target=99.9,
        is_alerting=alerting,
        severity="critical" if alerting else "warning",
        message="burning budget" if alerting else "ok",
        measured_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


class TestBuildStatusPayload:
    def test_generic(self):
        payload = _build_status_payload([_slo_status()], WebhookFormat.GENERIC)
        assert payload["event"] == "slo_status"
        assert payload["total"] == 1
        assert payload["passing"] == 1

    def test_slack(self):
        payload = _build_status_payload([_slo_status(False)], WebhookFormat.SLACK)
        assert "blocks" in payload
        assert "breaching" in payload["blocks"][0]["text"]["text"]

    def test_slack_all_passing(self):
        payload = _build_status_payload([_slo_status(True)], WebhookFormat.SLACK)
        assert "passing" in payload["blocks"][0]["text"]["text"].lower()

    def test_teams(self):
        payload = _build_status_payload([_slo_status()], WebhookFormat.TEAMS)
        assert payload["@type"] == "MessageCard"
        assert len(payload["sections"][0]["facts"]) == 1


class TestBuildAlertPayload:
    def test_generic(self):
        payload = _build_alert_payload([_alert()], WebhookFormat.GENERIC)
        assert payload["event"] == "burn_rate_alert"
        assert payload["alert_count"] == 1

    def test_slack(self):
        payload = _build_alert_payload([_alert()], WebhookFormat.SLACK)
        assert "blocks" in payload

    def test_teams(self):
        payload = _build_alert_payload([_alert()], WebhookFormat.TEAMS)
        assert payload["@type"] == "MessageCard"
        assert "FF0000" in payload["themeColor"]


# ---------------------------------------------------------------------------
# Notification functions
# ---------------------------------------------------------------------------


class TestNotifySLOStatus:
    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = notify_slo_status("https://example.com/hook", [_slo_status()])
        assert result.success
        assert result.status_code == 200
        mock_post.assert_called_once()

    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_failure(self, mock_post):
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        mock_post.return_value = mock_resp
        result = notify_slo_status("https://example.com/hook", [_slo_status()])
        assert not result.success
        # After retry exhaustion, error is a RetryError string (not the status code)
        assert result.error is not None

    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        result = notify_slo_status("https://example.com/hook", [_slo_status()])
        assert not result.success
        assert "Connection refused" in result.error


class TestNotifyBurnRateAlerts:
    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_firing_alert_sends(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = notify_burn_rate_alerts("https://example.com/hook", [_alert(True)])
        assert result.success
        mock_post.assert_called_once()

    def test_no_firing_alerts_skips(self):
        """When no alerts are firing, no HTTP call should be made."""
        result = notify_burn_rate_alerts("https://example.com/hook", [_alert(False)])
        assert result.success
        assert result.status_code is None  # No HTTP call made

    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_slack_format(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = notify_burn_rate_alerts(
            "https://example.com/hook", [_alert(True)], fmt=WebhookFormat.SLACK,
        )
        assert result.success
        # Verify the payload sent was Slack-formatted
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "blocks" in payload


class TestWebhookResult:
    def test_fields(self):
        r = WebhookResult(url="https://x.com", success=True, status_code=200)
        assert r.url == "https://x.com"
        assert r.success
        assert r.error is None


class TestPayloadTruncation:
    """Test that large payloads are truncated for Slack/Teams."""

    def test_slack_status_payload_truncated(self):
        from azure_slo_guardian.notifiers.webhook import MAX_PAYLOAD_ITEMS
        # Create more SLOs than the limit, all failing
        many_results = [_slo_status(meeting=False) for _ in range(MAX_PAYLOAD_ITEMS + 10)]
        payload = _build_status_payload(many_results, WebhookFormat.SLACK)
        blocks = payload["blocks"]
        # Should have header + MAX_PAYLOAD_ITEMS failing + 1 truncation notice
        assert len(blocks) <= MAX_PAYLOAD_ITEMS + 2
        assert any("truncated" in b["text"]["text"] for b in blocks if "text" in b and isinstance(b["text"], dict))

    def test_slack_alert_payload_truncated(self):
        from azure_slo_guardian.notifiers.webhook import MAX_PAYLOAD_ITEMS
        many_alerts = [_alert(True) for _ in range(MAX_PAYLOAD_ITEMS + 10)]
        payload = _build_alert_payload(many_alerts, WebhookFormat.SLACK)
        blocks = payload["blocks"]
        assert len(blocks) <= MAX_PAYLOAD_ITEMS + 2
        assert any("truncated" in b["text"]["text"] for b in blocks if "text" in b and isinstance(b["text"], dict))

    def test_small_payload_not_truncated(self):
        results = [_slo_status(meeting=False) for _ in range(3)]
        payload = _build_status_payload(results, WebhookFormat.SLACK)
        blocks = payload["blocks"]
        assert not any("truncated" in str(b) for b in blocks)


class TestWebhookRetry:
    """Test that webhooks retry on transient failures."""

    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_retries_on_500_then_succeeds(self, mock_post):
        fail_resp = MagicMock(status_code=500, text="Internal Server Error")
        ok_resp = MagicMock(status_code=200, text="OK")
        mock_post.side_effect = [fail_resp, ok_resp]
        result = notify_slo_status("https://example.com/hook", [_slo_status()])
        assert result.success
        assert mock_post.call_count == 2

    @patch("azure_slo_guardian.notifiers.webhook.requests.post")
    def test_no_retry_on_400(self, mock_post):
        """400 errors are not retried (client error, not transient)."""
        resp = MagicMock(status_code=400, text="Bad Request")
        mock_post.return_value = resp
        result = notify_slo_status("https://example.com/hook", [_slo_status()])
        assert not result.success
        assert result.status_code == 400
        mock_post.assert_called_once()

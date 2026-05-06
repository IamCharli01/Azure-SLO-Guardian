"""Webhook notifier for SLO alerts.

Sends SLO status and burn-rate alerts to external systems via HTTP
webhooks. Supports generic JSON payloads compatible with Slack
incoming webhooks, Microsoft Teams connectors, and custom endpoints.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from azure_slo_guardian.burn_rate import BurnRateAlert
from azure_slo_guardian.slo_calculator import SLOStatus

logger = logging.getLogger(__name__)

# Maximum number of SLO items to include in a single webhook payload
# to stay within Slack/Teams size limits
MAX_PAYLOAD_ITEMS = 25


class WebhookFormat(str, Enum):
    """Supported webhook payload formats."""

    GENERIC = "generic"
    SLACK = "slack"
    TEAMS = "teams"


@dataclass
class WebhookResult:
    """Result of a webhook notification."""

    url: str
    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


def notify_slo_status(
    url: str,
    results: List[SLOStatus],
    fmt: WebhookFormat = WebhookFormat.GENERIC,
    timeout: int = 10,
) -> WebhookResult:
    """Send SLO status results to a webhook URL.

    Args:
        url: Webhook URL.
        results: SLO status results to send.
        fmt: Payload format.
        timeout: HTTP timeout in seconds.

    Returns:
        WebhookResult indicating success or failure.
    """
    try:
        payload = _build_status_payload(results, fmt)
        return _post(url, payload, timeout)
    except Exception as e:
        logger.error(f"Failed to send SLO status webhook: {e}")
        return WebhookResult(url=url, success=False, error=str(e))


def notify_burn_rate_alerts(
    url: str,
    alerts: List[BurnRateAlert],
    fmt: WebhookFormat = WebhookFormat.GENERIC,
    timeout: int = 10,
) -> WebhookResult:
    """Send burn-rate alerts to a webhook URL.

    Only sends when at least one alert is firing.

    Args:
        url: Webhook URL.
        alerts: Burn-rate alert results.
        fmt: Payload format.
        timeout: HTTP timeout in seconds.

    Returns:
        WebhookResult indicating success or failure.
    """
    firing = [a for a in alerts if a.is_alerting]
    if not firing:
        return WebhookResult(url=url, success=True, status_code=None, error=None)

    try:
        payload = _build_alert_payload(firing, fmt)
        return _post(url, payload, timeout)
    except Exception as e:
        logger.error(f"Failed to send burn-rate webhook: {e}")
        return WebhookResult(url=url, success=False, error=str(e))


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _build_status_payload(
    results: List[SLOStatus], fmt: WebhookFormat
) -> Dict[str, Any]:
    failing = [r for r in results if not r.is_meeting_slo]
    passing = [r for r in results if r.is_meeting_slo]
    truncated = len(results) > MAX_PAYLOAD_ITEMS

    if fmt == WebhookFormat.SLACK:
        blocks = []
        header = (
            f":white_check_mark: All {len(results)} SLOs passing"
            if not failing
            else f":red_circle: {len(failing)}/{len(results)} SLO(s) breaching target"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": header}})
        for r in failing[:MAX_PAYLOAD_ITEMS]:
            budget = 100.0 - r.error_budget.error_budget_consumed_pct
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{r.slo_name}* (`{r.service}`)\n"
                        f"SLI: {r.current_sli:.2f}% | Target: {r.objective.target}% "
                        f"| Budget: {budget:.1f}%"
                    ),
                },
            })
        if truncated:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"_... and {len(results) - MAX_PAYLOAD_ITEMS} more SLOs (truncated)_"},
            })
        return {"blocks": blocks}

    elif fmt == WebhookFormat.TEAMS:
        facts = []
        for r in results:
            status = "✅ PASS" if r.is_meeting_slo else "🔴 FAIL"
            facts.append({"name": r.slo_name, "value": f"{r.current_sli:.2f}% — {status}"})
        return {
            "@type": "MessageCard",
            "themeColor": "00FF00" if not failing else "FF0000",
            "summary": f"SLO Report: {len(failing)} breaching" if failing else "SLO Report: All passing",
            "sections": [
                {
                    "activityTitle": "Azure SLO Guardian Report",
                    "facts": facts,
                }
            ],
        }

    else:  # GENERIC
        return {
            "event": "slo_status",
            "total": len(results),
            "passing": len(passing),
            "failing": len(failing),
            "results": [r.to_dict() for r in results],
        }


def _build_alert_payload(
    alerts: List[BurnRateAlert], fmt: WebhookFormat
) -> Dict[str, Any]:
    truncated = len(alerts) > MAX_PAYLOAD_ITEMS

    if fmt == WebhookFormat.SLACK:
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":fire: *{len(alerts)} burn-rate alert(s) firing*",
                },
            }
        ]
        for a in alerts[:MAX_PAYLOAD_ITEMS]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• *{a.slo_name}* [{a.severity.upper()}]: {a.message}",
                },
            })
        if truncated:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"_... and {len(alerts) - MAX_PAYLOAD_ITEMS} more alerts (truncated)_"},
            })
        return {"blocks": blocks}

    elif fmt == WebhookFormat.TEAMS:
        facts = [{"name": a.slo_name, "value": a.message} for a in alerts]
        return {
            "@type": "MessageCard",
            "themeColor": "FF0000",
            "summary": f"{len(alerts)} burn-rate alert(s) firing",
            "sections": [
                {
                    "activityTitle": "Azure SLO Guardian — Burn-Rate Alerts",
                    "facts": facts,
                }
            ],
        }

    else:  # GENERIC
        return {
            "event": "burn_rate_alert",
            "alert_count": len(alerts),
            "alerts": [a.to_dict() for a in alerts],
        }


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _should_retry_response(result: WebhookResult) -> bool:
    """Return True if the webhook response indicates a retryable failure."""
    if result.success:
        return False
    return result.status_code is not None and (
        result.status_code == 429 or result.status_code >= 500
    )


def _post(url: str, payload: Dict[str, Any], timeout: int) -> WebhookResult:
    """POST JSON payload to a URL with retry on transient failures."""

    @retry(
        retry=(
            retry_if_exception_type((requests.ConnectionError, requests.Timeout))
            | retry_if_result(_should_retry_response)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _do_post() -> WebhookResult:
        resp = requests.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        success = 200 <= resp.status_code < 300
        if not success:
            logger.warning(
                "Webhook returned %d: %s", resp.status_code, resp.text[:200]
            )
        return WebhookResult(
            url=url, success=success, status_code=resp.status_code
        )

    try:
        return _do_post()
    except Exception as e:
        logger.error("Webhook POST failed after retries: %s", e)
        return WebhookResult(url=url, success=False, error=str(e))

"""Notifier modules."""

from azure_slo_guardian.notifiers.webhook import (
    WebhookFormat,
    WebhookResult,
    notify_burn_rate_alerts,
    notify_slo_status,
)

__all__ = [
    "WebhookFormat",
    "WebhookResult",
    "notify_burn_rate_alerts",
    "notify_slo_status",
]

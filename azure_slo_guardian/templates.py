"""Pre-built SLO templates for Azure App Service workloads.

Templates eliminate the need for users to write KQL queries. They provide
ready-made SLI definitions for common Azure App Service types:
  - Web App (app-service-availability, app-service-latency)
  - Function App (function-app-availability, function-app-errors)
  - Logic App (logic-app-success-rate, logic-app-latency)

Each template uses a ``{app_name}`` placeholder that is resolved at config
load time from the ``service`` field (or an explicit ``app_name`` override).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Characters allowed in Azure resource names (alphanumeric, hyphens, underscores, dots)
_SAFE_APP_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _sanitize_app_name(app_name: str) -> str:
    """Validate and sanitize app_name before substituting into KQL queries.

    Prevents KQL injection by rejecting names containing KQL operators
    or characters that could alter query semantics.

    Raises:
        ValueError: If app_name contains unsafe characters.
    """
    if not app_name:
        raise ValueError("app_name cannot be empty")
    if len(app_name) > 260:
        raise ValueError(f"app_name too long ({len(app_name)} chars, max 260)")
    if not _SAFE_APP_NAME_RE.match(app_name):
        raise ValueError(
            f"app_name '{app_name}' contains invalid characters. "
            "Only alphanumeric, hyphens, underscores, and dots are allowed."
        )
    return app_name


@dataclass(frozen=True)
class TemplateDefinition:
    """A reusable SLO template with pre-built KQL queries."""

    name: str
    display_name: str
    description: str
    app_type: str  # "web_app", "function_app", "logic_app"
    sli_type: str  # "availability" or "latency"
    default_target: float
    default_window: str

    # Ratio-based (availability / success)
    good_query: Optional[str] = None
    total_query: Optional[str] = None

    # Threshold-based (latency)
    query: Optional[str] = None
    threshold: Optional[float] = None
    operator: Optional[str] = None

    # Default alerting windows
    alerting_windows: List[Dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KQL query fragments — use {app_name} as the placeholder
# ---------------------------------------------------------------------------

# --- Web App (App Service) ------------------------------------------------

_WEBAPP_AVAIL_GOOD = """\
AppServiceHTTPLogs
| where CsHost contains "{app_name}"
| where ScStatus < 500
| count
"""

_WEBAPP_AVAIL_TOTAL = """\
AppServiceHTTPLogs
| where CsHost contains "{app_name}"
| count
"""

_WEBAPP_LATENCY = """\
AppServiceHTTPLogs
| where CsHost contains "{app_name}"
| summarize p95_ms = percentile(TimeTaken, 95)
"""

# --- Function App ---------------------------------------------------------

_FUNCAPP_AVAIL_GOOD = """\
AppRequests
| where AppRoleName contains "{app_name}"
| where Success == true
| count
"""

_FUNCAPP_AVAIL_TOTAL = """\
AppRequests
| where AppRoleName contains "{app_name}"
| count
"""

_FUNCAPP_ERRORS = """\
AppExceptions
| where AppRoleName contains "{app_name}"
| summarize error_count = count()
"""

_FUNCAPP_ERRORS_TOTAL = """\
AppRequests
| where AppRoleName contains "{app_name}"
| summarize total_count = count()
"""

# --- Logic App ------------------------------------------------------------

_LOGICAPP_SUCCESS_GOOD = """\
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.LOGIC"
| where resource_workflowName_s contains "{app_name}"
| where status_s == "Succeeded"
| count
"""

_LOGICAPP_SUCCESS_TOTAL = """\
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.LOGIC"
| where resource_workflowName_s contains "{app_name}"
| where status_s in ("Succeeded", "Failed")
| count
"""

_LOGICAPP_LATENCY = """\
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.LOGIC"
| where resource_workflowName_s contains "{app_name}"
| where status_s in ("Succeeded", "Failed")
| extend duration_ms = datetime_diff('millisecond', endTime_t, startTime_t)
| summarize p95_ms = percentile(duration_ms, 95)
"""

# ---------------------------------------------------------------------------
# Default burn-rate windows (sensible defaults for non-SRE users)
# ---------------------------------------------------------------------------
_DEFAULT_ALERT_WINDOWS = [
    {"consume_budget": 2.0, "short_window": "5m", "long_window": "1h"},
    {"consume_budget": 5.0, "short_window": "30m", "long_window": "6h"},
]

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES: Dict[str, TemplateDefinition] = {}


def _register(t: TemplateDefinition) -> None:
    TEMPLATES[t.name] = t


# Web App templates
_register(TemplateDefinition(
    name="app-service-availability",
    display_name="App Service — Availability",
    description="Tracks HTTP 5xx error rate for an Azure Web App",
    app_type="web_app",
    sli_type="availability",
    default_target=99.9,
    default_window="30d",
    good_query=_WEBAPP_AVAIL_GOOD,
    total_query=_WEBAPP_AVAIL_TOTAL,
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))

_register(TemplateDefinition(
    name="app-service-latency",
    display_name="App Service — Latency (p95)",
    description="95th-percentile response time for an Azure Web App",
    app_type="web_app",
    sli_type="latency",
    default_target=99.5,
    default_window="7d",
    query=_WEBAPP_LATENCY,
    threshold=1000.0,  # 1 second
    operator="lte",
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))

# Function App templates
_register(TemplateDefinition(
    name="function-app-availability",
    display_name="Function App — Availability",
    description="Tracks request success rate for an Azure Function App",
    app_type="function_app",
    sli_type="availability",
    default_target=99.9,
    default_window="30d",
    good_query=_FUNCAPP_AVAIL_GOOD,
    total_query=_FUNCAPP_AVAIL_TOTAL,
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))

_register(TemplateDefinition(
    name="function-app-errors",
    display_name="Function App — Error Rate",
    description="Tracks exception-to-request ratio for an Azure Function App",
    app_type="function_app",
    sli_type="availability",
    default_target=99.9,
    default_window="30d",
    good_query="""\
AppRequests
| where AppRoleName contains "{app_name}"
| summarize good = countif(Success == true)
| project good
""",
    total_query=_FUNCAPP_AVAIL_TOTAL,
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))

# Logic App templates
_register(TemplateDefinition(
    name="logic-app-success-rate",
    display_name="Logic App — Workflow Success Rate",
    description="Tracks workflow run success rate for an Azure Logic App",
    app_type="logic_app",
    sli_type="availability",
    default_target=99.5,
    default_window="30d",
    good_query=_LOGICAPP_SUCCESS_GOOD,
    total_query=_LOGICAPP_SUCCESS_TOTAL,
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))

_register(TemplateDefinition(
    name="logic-app-latency",
    display_name="Logic App — Workflow Latency (p95)",
    description="95th-percentile workflow duration for an Azure Logic App",
    app_type="logic_app",
    sli_type="latency",
    default_target=99.0,
    default_window="7d",
    query=_LOGICAPP_LATENCY,
    threshold=30000.0,  # 30 seconds
    operator="lte",
    alerting_windows=_DEFAULT_ALERT_WINDOWS,
))


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def list_templates() -> List[TemplateDefinition]:
    """Return all registered templates."""
    return list(TEMPLATES.values())


def get_template(name: str) -> Optional[TemplateDefinition]:
    """Look up a template by name.  Returns ``None`` if not found."""
    return TEMPLATES.get(name)


def get_templates_for_app_type(app_type: str) -> List[TemplateDefinition]:
    """Return templates matching the given app type (web_app, function_app, logic_app)."""
    return [t for t in TEMPLATES.values() if t.app_type == app_type]


def resolve_template(
    template_name: str,
    app_name: str,
    workspace_id: str,
    *,
    target: Optional[float] = None,
    window: Optional[str] = None,
    threshold: Optional[float] = None,
) -> Dict:
    """Expand a template into a full SLO dict ready for ``SLO.model_validate()``.

    Parameters
    ----------
    template_name:
        Registered template name, e.g. ``"app-service-availability"``.
    app_name:
        Azure resource name used to filter queries (substituted for ``{app_name}``).
    workspace_id:
        Log Analytics workspace ID (or env-var reference like ``${LOG_ANALYTICS_WORKSPACE_ID}``).
    target:
        Override the template's default target percentage.
    window:
        Override the template's default window (e.g. ``"7d"``).
    threshold:
        Override latency threshold in milliseconds (latency templates only).

    Returns
    -------
    dict
        A dictionary that can be passed to ``SLO.model_validate()``.
    """
    tmpl = get_template(template_name)
    if tmpl is None:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(
            f"Unknown template '{template_name}'. Available templates: {available}"
        )

    safe_app_name = _sanitize_app_name(app_name)
    effective_target = target if target is not None else tmpl.default_target
    effective_window = window if window is not None else tmpl.default_window

    sli: Dict = {
        "type": tmpl.sli_type,
        "query_type": "log_analytics",
        "workspace_id": workspace_id,
    }

    if tmpl.sli_type == "availability":
        sli["good_query"] = tmpl.good_query.replace("{app_name}", safe_app_name)
        sli["total_query"] = tmpl.total_query.replace("{app_name}", safe_app_name)
    elif tmpl.sli_type == "latency":
        sli["query"] = tmpl.query.replace("{app_name}", safe_app_name)
        sli["threshold"] = threshold if threshold is not None else tmpl.threshold
        sli["operator"] = tmpl.operator

    slo_dict: Dict = {
        "name": f"{safe_app_name}-{tmpl.sli_type}",
        "description": f"{tmpl.display_name} for {safe_app_name}",
        "service": safe_app_name,
        "sli": sli,
        "objectives": [{"target": effective_target, "window": effective_window}],
    }

    if tmpl.alerting_windows:
        slo_dict["alerting"] = {
            "enabled": True,
            "windows": tmpl.alerting_windows,
        }

    return slo_dict

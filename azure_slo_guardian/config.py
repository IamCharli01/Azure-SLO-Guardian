"""Configuration models for Azure SLO Guardian."""

from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator


class QueryType(str, Enum):
    """Supported Azure query types."""

    APPLICATION_INSIGHTS = "application_insights"
    LOG_ANALYTICS = "log_analytics"
    AZURE_MONITOR = "azure_monitor"


class SLIType(str, Enum):
    """Supported SLI types."""

    AVAILABILITY = "availability"
    LATENCY = "latency"
    CUSTOM = "custom"


class Operator(str, Enum):
    """Comparison operators for threshold-based SLIs."""

    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class BurnRateWindow(BaseModel):
    """Burn rate alert window configuration."""

    consume_budget: float = Field(..., description="Percentage of budget to consume")
    short_window: str = Field(..., description="Short window duration (e.g., '5m', '1h')")
    long_window: str = Field(..., description="Long window duration (e.g., '1h', '6h')")

    @field_validator("consume_budget")
    @classmethod
    def validate_consume_budget(cls, v: float) -> float:
        """Validate consume_budget is between 0 and 100."""
        if not 0 < v <= 100:
            raise ValueError("consume_budget must be between 0 and 100")
        return v


class AlertingConfig(BaseModel):
    """Alerting configuration for SLO."""

    enabled: bool = Field(default=True, description="Enable burn-rate alerting")
    windows: List[BurnRateWindow] = Field(
        default_factory=lambda: [
            BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
            BurnRateWindow(consume_budget=5.0, short_window="30m", long_window="6h"),
        ],
        description="Multi-window burn-rate configurations",
    )


class SLIConfig(BaseModel):
    """SLI configuration."""

    type: SLIType = Field(..., description="SLI type")
    query_type: QueryType = Field(..., description="Azure query type")
    workspace_id: str = Field(..., description="Azure workspace/resource ID")
    connection_id: Optional[str] = Field(
        default=None, description="Azure Monitor connection ID"
    )

    # For ratio-based SLIs (availability, success rate)
    good_query: Optional[str] = Field(default=None, description="KQL query for good events")
    total_query: Optional[str] = Field(default=None, description="KQL query for total events")

    # For threshold-based SLIs (latency)
    query: Optional[str] = Field(default=None, description="KQL query returning values")
    threshold: Optional[float] = Field(default=None, description="Threshold value")
    operator: Optional[Operator] = Field(default=None, description="Comparison operator")

    @field_validator("workspace_id", "connection_id")
    @classmethod
    def expand_env_vars(cls, v: Optional[str]) -> Optional[str]:
        """Expand environment variables in configuration."""
        if v is None:
            return v
        import os
        import re as _re

        # Only expand explicitly referenced ${VAR} patterns
        def _replace_env(match: _re.Match) -> str:
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set"
                )
            return value

        return _re.sub(r"\$\{([^}]+)}", _replace_env, v)

    def model_post_init(self, __context: Any) -> None:
        """Validate SLI configuration after initialization."""
        if self.type in (SLIType.AVAILABILITY, SLIType.CUSTOM):
            if not self.good_query or not self.total_query:
                raise ValueError(
                    f"SLI type '{self.type}' requires both good_query and total_query"
                )
        elif self.type == SLIType.LATENCY:
            if not self.query or self.threshold is None or not self.operator:
                raise ValueError(
                    f"SLI type '{self.type}' requires query, threshold, and operator"
                )


class Objective(BaseModel):
    """SLO objective configuration."""

    target: float = Field(..., description="SLO target percentage (e.g., 99.9)")
    window: str = Field(..., description="Time window (e.g., '30d', '7d', '24h')")

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: float) -> float:
        """Validate target is between 0 and 100."""
        if not 0 < v <= 100:
            raise ValueError("target must be between 0 and 100")
        return v

    def get_window_timedelta(self) -> timedelta:
        """Convert window string to timedelta."""
        return parse_duration(self.window)


class SLO(BaseModel):
    """Service Level Objective configuration."""

    name: str = Field(..., description="Unique SLO identifier")
    description: str = Field(..., description="Human-readable description")
    service: str = Field(..., description="Service name")
    sli: SLIConfig = Field(..., description="SLI configuration")
    objectives: List[Objective] = Field(..., description="SLO objectives")
    alerting: Optional[AlertingConfig] = Field(
        default=None, description="Alerting configuration"
    )

    @field_validator("objectives")
    @classmethod
    def validate_objectives(cls, v: List[Objective]) -> List[Objective]:
        """Validate at least one objective exists."""
        if not v:
            raise ValueError("At least one objective must be defined")
        return v


class SLOConfig(BaseModel):
    """Root SLO configuration."""

    slos: List[SLO] = Field(..., description="List of SLO definitions")

    @field_validator("slos")
    @classmethod
    def validate_unique_names(cls, v: List[SLO]) -> List[SLO]:
        """Validate SLO names are unique."""
        names = [slo.name for slo in v]
        if len(names) != len(set(names)):
            raise ValueError("SLO names must be unique")
        return v

    def get_slo(self, name: str) -> Optional[SLO]:
        """Get SLO by name."""
        for slo in self.slos:
            if slo.name == name:
                return slo
        return None


def parse_duration(duration: str) -> timedelta:
    """Parse duration string to timedelta.

    Supports formats like: 1h, 30m, 7d, 24h, 1w
    """
    duration = duration.strip().lower()
    if not duration:
        raise ValueError("Duration cannot be empty")

    # Extract number and unit
    import re

    match = re.match(r"^(\d+(?:\.\d+)?)\s*([smhdw])$", duration)
    if not match:
        raise ValueError(
            f"Invalid duration format: {duration}. Expected format like '1h', '30m', '7d'"
        )

    value, unit = match.groups()
    value = float(value)

    units = {
        "s": timedelta(seconds=value),
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
        "w": timedelta(weeks=value),
    }

    return units[unit]


def _expand_template_entries(data: Dict) -> Dict:
    """Expand template-based SLO entries into full SLO definitions.

    If an entry in ``slos`` contains a ``template`` key, it is resolved via
    :func:`azure_slo_guardian.templates.resolve_template` and merged back
    into the list.  Entries that already have an ``sli`` key are left
    untouched.
    """
    from azure_slo_guardian.templates import resolve_template

    if "slos" not in data:
        return data

    expanded: List[Dict] = []
    for entry in data["slos"]:
        if "template" in entry:
            tmpl_name = entry["template"]
            app_name = entry.get("app_name") or entry.get("service", "")
            workspace_id = entry.get("workspace_id", "")
            target = entry.get("target")
            window = entry.get("window")
            threshold = entry.get("threshold")

            resolved = resolve_template(
                tmpl_name,
                app_name,
                workspace_id,
                target=target,
                window=window,
                threshold=threshold,
            )
            # Allow explicit overrides (name, description, alerting, etc.)
            if "name" in entry:
                resolved["name"] = entry["name"]
            if "description" in entry:
                resolved["description"] = entry["description"]
            if "alerting" in entry:
                resolved["alerting"] = entry["alerting"]
            expanded.append(resolved)
        else:
            expanded.append(entry)

    data["slos"] = expanded
    return data


def load_config(config_path: Union[str, Path]) -> SLOConfig:
    """Load and validate SLO configuration from YAML file.

    Supports two SLO formats:

    **Full format** (existing) — you provide ``sli``, ``objectives``, etc::

        slos:
          - name: my-slo
            sli: { type: availability, ... }
            objectives: [{ target: 99.9, window: 30d }]

    **Template format** (simplified) — pick a preset, provide your app name::

        slos:
          - template: app-service-availability
            app_name: my-web-app
            workspace_id: "${LOG_ANALYTICS_WORKSPACE_ID}"
            target: 99.9   # optional override
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        raise ValueError(
            f"Configuration file is empty or invalid: {config_path}. "
            "Expected a YAML file with a top-level 'slos' key."
        )

    data = _expand_template_entries(data)

    return SLOConfig(**data)


def validate_config(config_path: Union[str, Path]) -> tuple[bool, Optional[str]]:
    """Validate SLO configuration file.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        load_config(config_path)
        return True, None
    except Exception as e:
        return False, str(e)

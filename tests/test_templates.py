"""Unit tests for the templates module and template-based config loading."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from azure_slo_guardian.templates import (
    TEMPLATES,
    get_template,
    get_templates_for_app_type,
    list_templates,
    resolve_template,
)


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_all_templates_registered(self):
        names = [t.name for t in list_templates()]
        assert "app-service-availability" in names
        assert "app-service-latency" in names
        assert "function-app-availability" in names
        assert "function-app-errors" in names
        assert "logic-app-success-rate" in names
        assert "logic-app-latency" in names

    def test_get_template_found(self):
        t = get_template("app-service-availability")
        assert t is not None
        assert t.sli_type == "availability"

    def test_get_template_not_found(self):
        assert get_template("nonexistent") is None

    def test_templates_for_web_app(self):
        result = get_templates_for_app_type("web_app")
        assert len(result) == 2
        assert all(t.app_type == "web_app" for t in result)

    def test_templates_for_function_app(self):
        result = get_templates_for_app_type("function_app")
        assert len(result) == 2

    def test_templates_for_logic_app(self):
        result = get_templates_for_app_type("logic_app")
        assert len(result) == 2

    def test_templates_for_unknown_type(self):
        assert get_templates_for_app_type("container_app") == []


# ---------------------------------------------------------------------------
# resolve_template
# ---------------------------------------------------------------------------


class TestResolveTemplate:
    def test_availability_template(self):
        result = resolve_template(
            "app-service-availability", "my-app", "ws-123"
        )
        assert result["name"] == "my-app-availability"
        assert result["service"] == "my-app"
        assert "my-app" in result["sli"]["good_query"]
        assert "my-app" in result["sli"]["total_query"]
        assert result["sli"]["workspace_id"] == "ws-123"
        assert result["objectives"][0]["target"] == 99.9
        assert result["alerting"]["enabled"] is True

    def test_latency_template(self):
        result = resolve_template(
            "app-service-latency", "my-app", "ws-123"
        )
        assert result["sli"]["type"] == "latency"
        assert result["sli"]["threshold"] == 1000.0
        assert result["sli"]["operator"] == "lte"
        assert "my-app" in result["sli"]["query"]

    def test_target_override(self):
        result = resolve_template(
            "app-service-availability", "x", "ws", target=99.5
        )
        assert result["objectives"][0]["target"] == 99.5

    def test_window_override(self):
        result = resolve_template(
            "app-service-availability", "x", "ws", window="7d"
        )
        assert result["objectives"][0]["window"] == "7d"

    def test_threshold_override(self):
        result = resolve_template(
            "app-service-latency", "x", "ws", threshold=500.0
        )
        assert result["sli"]["threshold"] == 500.0

    def test_unknown_template_raises(self):
        with pytest.raises(ValueError, match="Unknown template"):
            resolve_template("no-such-template", "x", "ws")

    def test_function_app_template(self):
        result = resolve_template(
            "function-app-availability", "my-func", "ws-456"
        )
        assert "my-func" in result["sli"]["good_query"]
        assert "AppRoleName" in result["sli"]["good_query"]

    def test_logic_app_template(self):
        result = resolve_template(
            "logic-app-success-rate", "my-workflow", "ws-789"
        )
        assert "my-workflow" in result["sli"]["good_query"]
        assert "MICROSOFT.LOGIC" in result["sli"]["good_query"]


# ---------------------------------------------------------------------------
# Config loading with templates
# ---------------------------------------------------------------------------


class TestTemplateConfigLoading:
    """Test that template-based YAML files load through the config pipeline."""

    def test_load_template_config(self, tmp_path: Path):
        config_data = {
            "slos": [
                {
                    "template": "app-service-availability",
                    "app_name": "test-app",
                    "workspace_id": "fake-ws-id",
                }
            ]
        }
        config_file = tmp_path / "slo.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        from azure_slo_guardian.config import load_config

        cfg = load_config(config_file)
        assert len(cfg.slos) == 1
        assert cfg.slos[0].service == "test-app"
        assert cfg.slos[0].sli.type.value == "availability"
        assert "test-app" in cfg.slos[0].sli.good_query

    def test_mixed_template_and_manual(self, tmp_path: Path):
        config_data = {
            "slos": [
                {
                    "template": "function-app-availability",
                    "app_name": "my-func",
                    "workspace_id": "ws-1",
                },
                {
                    "name": "manual-slo",
                    "description": "manual",
                    "service": "svc",
                    "sli": {
                        "type": "availability",
                        "query_type": "log_analytics",
                        "workspace_id": "ws-2",
                        "good_query": "T | where x | count",
                        "total_query": "T | count",
                    },
                    "objectives": [{"target": 99.0, "window": "7d"}],
                },
            ]
        }
        config_file = tmp_path / "slo.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        from azure_slo_guardian.config import load_config

        cfg = load_config(config_file)
        assert len(cfg.slos) == 2
        assert cfg.slos[0].name == "my-func-availability"
        assert cfg.slos[1].name == "manual-slo"

    def test_template_with_name_override(self, tmp_path: Path):
        config_data = {
            "slos": [
                {
                    "template": "app-service-availability",
                    "name": "custom-name",
                    "app_name": "app1",
                    "workspace_id": "ws",
                }
            ]
        }
        config_file = tmp_path / "slo.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        from azure_slo_guardian.config import load_config

        cfg = load_config(config_file)
        assert cfg.slos[0].name == "custom-name"

    def test_template_with_target_override(self, tmp_path: Path):
        config_data = {
            "slos": [
                {
                    "template": "app-service-availability",
                    "app_name": "app1",
                    "workspace_id": "ws",
                    "target": 99.5,
                }
            ]
        }
        config_file = tmp_path / "slo.yaml"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        from azure_slo_guardian.config import load_config

        cfg = load_config(config_file)
        assert cfg.slos[0].objectives[0].target == 99.5


# ---------------------------------------------------------------------------
# KQL injection prevention
# ---------------------------------------------------------------------------


class TestAppNameSanitization:
    """Test that app_name values are sanitized to prevent KQL injection."""

    def test_valid_app_names(self):
        """Normal Azure resource names should work fine."""
        for name in ["my-app", "web_app_01", "app.service.prod", "MyApp123"]:
            result = resolve_template(
                "app-service-availability", name, "ws-123"
            )
            assert result["service"] == name

    def test_rejects_kql_injection_pipe(self):
        """Pipe operator could inject KQL commands."""
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_template(
                "app-service-availability", "app | union OtherTable", "ws"
            )

    def test_rejects_kql_injection_semicolon(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_template(
                "app-service-availability", "app; drop table", "ws"
            )

    def test_rejects_kql_injection_quotes(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_template(
                "app-service-availability", 'app" or "1"="1', "ws"
            )

    def test_rejects_empty_app_name(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_template("app-service-availability", "", "ws")

    def test_rejects_very_long_app_name(self):
        with pytest.raises(ValueError, match="too long"):
            resolve_template("app-service-availability", "a" * 300, "ws")

    def test_rejects_newlines(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_template("app-service-availability", "app\n| union", "ws")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_template("app-service-availability", "app name", "ws")

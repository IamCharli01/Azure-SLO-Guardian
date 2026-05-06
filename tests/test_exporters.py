"""Unit tests for Grafana dashboard exporter."""

import json
from datetime import datetime, timezone

import pytest

from azure_slo_guardian.config import Objective
from azure_slo_guardian.exporters.grafana import (
    export_grafana_dashboard,
    export_grafana_json,
)
from azure_slo_guardian.slo_calculator import ErrorBudget, SLOStatus


def _status(meeting: bool = True) -> SLOStatus:
    now = datetime.now(timezone.utc)
    sli = 99.95 if meeting else 99.5
    target = 99.9
    eb_total = 100.0 - target
    current_error = 100.0 - sli
    return SLOStatus(
        slo_name="api-avail",
        service="backend",
        description="API availability",
        objective=Objective(target=target, window="30d"),
        current_sli=sli,
        is_meeting_slo=meeting,
        error_budget=ErrorBudget(
            slo_name="api-avail",
            target=target,
            window="30d",
            current_sli=sli,
            error_budget_total=eb_total,
            error_budget_remaining=eb_total - current_error,
            error_budget_consumed_pct=max(0.0, min(100.0, (current_error / eb_total) * 100.0)),
            is_exhausted=(eb_total - current_error) <= 0,
            measured_at=now,
        ),
        measured_at=now,
    )


class TestExportGrafanaDashboard:
    def test_returns_valid_structure(self):
        dash = export_grafana_dashboard([_status()])
        assert "dashboard" in dash
        assert dash["dashboard"]["uid"] == "slo-guardian"
        assert dash["dashboard"]["title"] == "SLO Dashboard"
        assert len(dash["dashboard"]["panels"]) == 3  # stat + gauge + status

    def test_custom_title_and_uid(self):
        dash = export_grafana_dashboard([_status()], title="My SLOs", uid="custom")
        assert dash["dashboard"]["title"] == "My SLOs"
        assert dash["dashboard"]["uid"] == "custom"

    def test_multiple_slos(self):
        dash = export_grafana_dashboard([_status(), _status(meeting=False)])
        assert len(dash["dashboard"]["panels"]) == 6

    def test_panels_have_required_keys(self):
        dash = export_grafana_dashboard([_status()])
        for panel in dash["dashboard"]["panels"]:
            assert "id" in panel
            assert "type" in panel
            assert "title" in panel
            assert "gridPos" in panel

    def test_failing_slo_status_panel(self):
        dash = export_grafana_dashboard([_status(meeting=False)])
        status_panel = dash["dashboard"]["panels"][2]
        assert status_panel["_slo_guardian_display"] == "FAIL"


class TestExportGrafanaJson:
    def test_returns_valid_json(self):
        output = export_grafana_json([_status()])
        data = json.loads(output)
        assert "dashboard" in data

    def test_custom_indent(self):
        output = export_grafana_json([_status()], indent=4)
        assert "    " in output

    def test_empty_results(self):
        output = export_grafana_json([])
        data = json.loads(output)
        assert data["dashboard"]["panels"] == []

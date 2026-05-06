"""Unit tests for CLI commands using Click CliRunner."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from azure_slo_guardian.burn_rate import BurnRateAlert
from azure_slo_guardian.cli import main
from azure_slo_guardian.config import BurnRateWindow, Objective
from azure_slo_guardian.slo_calculator import ErrorBudget, SLOStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CONFIG = """\
slos:
  - name: test-slo
    description: "Test SLO"
    service: test-service
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "test-workspace-id"
      good_query: |
        requests | where success == true | count
      total_query: |
        requests | count
    objectives:
      - target: 99.9
        window: 30d
"""

INVALID_CONFIG = """\
slos:
  - name: bad
    description: "Bad"
    service: svc
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "ws"
    objectives:
      - target: 99.9
        window: 30d
"""

ALERTING_CONFIG = """\
slos:
  - name: test-slo
    description: "Test SLO"
    service: test-service
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "test-workspace-id"
      good_query: |
        requests | where success == true | count
      total_query: |
        requests | count
    objectives:
      - target: 99.9
        window: 30d
    alerting:
      enabled: true
      windows:
        - consume_budget: 2.0
          short_window: 5m
          long_window: 1h
"""


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "slo.yaml"
    p.write_text(VALID_CONFIG)
    return p


@pytest.fixture()
def invalid_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "bad.yaml"
    p.write_text(INVALID_CONFIG)
    return p


@pytest.fixture()
def alerting_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "alert.yaml"
    p.write_text(ALERTING_CONFIG)
    return p


def _mock_slo_status(meeting: bool = True) -> SLOStatus:
    now = datetime.now(timezone.utc)
    target = 99.9
    sli = 99.95 if meeting else 99.5
    eb_total = 100.0 - target
    current_error = 100.0 - sli
    remaining = eb_total - current_error
    consumed = max(0.0, min(100.0, (current_error / eb_total) * 100.0))
    return SLOStatus(
        slo_name="test-slo",
        service="test-service",
        description="Test SLO",
        objective=Objective(target=target, window="30d"),
        current_sli=sli,
        is_meeting_slo=meeting,
        error_budget=ErrorBudget(
            slo_name="test-slo",
            target=target,
            window="30d",
            current_sli=sli,
            error_budget_total=eb_total,
            error_budget_remaining=remaining,
            error_budget_consumed_pct=consumed,
            is_exhausted=remaining <= 0,
            measured_at=now,
        ),
        measured_at=now,
    )


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    def test_valid_config(self, config_file: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["validate", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_invalid_config(self, invalid_config_file: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["validate", "--config", str(invalid_config_file)])
        assert result.exit_code == 1
        assert "invalid" in result.output.lower()

    def test_nonexistent_config(self):
        runner = CliRunner()
        result = runner.invoke(main, ["validate", "--config", "nonexistent.yaml"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# check command
# ---------------------------------------------------------------------------


class TestCheckCommand:
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_table_meeting_slo(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["check", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "test-slo" in result.output

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_exits_nonzero_when_failing(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=False)]

        runner = CliRunner()
        result = runner.invoke(main, ["check", "--config", str(config_file)])
        assert result.exit_code == 1

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_json_output(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["check", "--config", str(config_file), "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["slo_name"] == "test-slo"

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_yaml_output(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["check", "--config", str(config_file), "-f", "yaml"])
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_specific_slo(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["check", "--config", str(config_file), "-s", "test-slo"]
        )
        assert result.exit_code == 0

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_unknown_slo(self, mock_calc_cls, config_file: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["check", "--config", str(config_file), "-s", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# budget command
# ---------------------------------------------------------------------------


class TestBudgetCommand:
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_budget_table(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["budget", "--config", str(config_file), "-s", "test-slo"]
        )
        assert result.exit_code == 0

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_budget_json(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["budget", "--config", str(config_file), "-s", "test-slo", "-f", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_budget_unknown_slo(self, config_file: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["budget", "--config", str(config_file), "-s", "nope"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# version / help
# ---------------------------------------------------------------------------


class TestMeta:
    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Azure SLO Guardian" in result.output

    def test_verbose_flag(self, config_file: Path):
        runner = CliRunner()
        result = runner.invoke(main, ["-v", "validate", "--config", str(config_file)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# alert command
# ---------------------------------------------------------------------------


def _mock_burn_rate_alert(alerting: bool = False) -> BurnRateAlert:
    return BurnRateAlert(
        slo_name="test-slo",
        window_config=BurnRateWindow(consume_budget=2.0, short_window="5m", long_window="1h"),
        short_window_sli=99.95 if not alerting else 90.0,
        long_window_sli=99.95 if not alerting else 90.0,
        target=99.9,
        is_alerting=alerting,
        severity="critical" if alerting else "warning",
        message="SLO burn rate is acceptable" if not alerting else "SLO is burning budget",
        measured_at=datetime.now(timezone.utc),
    )


class TestAlertCommand:
    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_table_no_alerts(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=False)]

        runner = CliRunner()
        result = runner.invoke(main, ["alert", "--config", str(alerting_config_file)])
        assert result.exit_code == 0
        assert "test-slo" in result.output

    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_exits_nonzero_when_firing(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["alert", "--config", str(alerting_config_file)])
        assert result.exit_code == 1

    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_json_output(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=False)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["alert", "--config", str(alerting_config_file), "-f", "json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["slo_name"] == "test-slo"

    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_yaml_output(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=False)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["alert", "--config", str(alerting_config_file), "-f", "yaml"]
        )
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)

    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_specific_slo(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=False)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["alert", "--config", str(alerting_config_file), "-s", "test-slo"]
        )
        assert result.exit_code == 0

    def test_alert_unknown_slo(self, alerting_config_file: Path):
        runner = CliRunner()
        result = runner.invoke(
            main, ["alert", "--config", str(alerting_config_file), "-s", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_firing_shows_active_alerts(self, mock_calc_cls, alerting_config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_burn_rates.return_value = [_mock_burn_rate_alert(alerting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["alert", "--config", str(alerting_config_file)])
        assert "Active Alerts" in result.output or "burning budget" in result.output


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


class TestReportCommand:
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_stdout(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["report", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "SLO Daily Report" in result.output

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_stdout_all_passing(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(main, ["report", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "All SLOs are within budget" in result.output

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_with_failures(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=False)]

        runner = CliRunner()
        result = runner.invoke(main, ["report", "--config", str(config_file)])
        assert result.exit_code == 0
        assert "breaching" in result.output.lower()
        assert "test-slo" in result.output

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_to_file(self, mock_calc_cls, config_file: Path, tmp_path: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        out_file = tmp_path / "report.md"
        runner = CliRunner()
        result = runner.invoke(
            main, ["report", "--config", str(config_file), "-o", str(out_file)]
        )
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "SLO Daily Report" in content

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_budget_yaml_output(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["budget", "--config", str(config_file), "-s", "test-slo", "-f", "yaml"]
        )
        assert result.exit_code == 0
        data = yaml.safe_load(result.output)
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Notify and export flags
# ---------------------------------------------------------------------------


class TestCheckNotifyFlag:
    @patch("azure_slo_guardian.cli._send_slo_webhook")
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_with_notify_slack(self, mock_calc_cls, mock_send, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--config", str(config_file),
             "--notify", "slack", "--webhook-url", "https://hooks.slack.com/test"],
        )
        assert result.exit_code == 0
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        assert args[0] == "slack"
        assert args[1] == "https://hooks.slack.com/test"

    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_check_notify_without_url_warns(self, mock_calc_cls, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main, ["check", "--config", str(config_file), "--notify", "slack"],
        )
        # Should still work but warn about missing URL
        assert "webhook-url required" in result.output or result.exit_code == 0


class TestAlertNotifyFlag:
    @patch("azure_slo_guardian.cli._send_alert_webhook")
    @patch("azure_slo_guardian.cli.BurnRateCalculator")
    def test_alert_with_notify_teams(self, mock_br_cls, mock_send, config_file: Path):
        instance = mock_br_cls.return_value
        instance.calculate_all_burn_rates.return_value = []

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["alert", "--config", str(config_file),
             "--notify", "teams", "--webhook-url", "https://outlook.webhook.office.com/test"],
        )
        assert result.exit_code == 0
        mock_send.assert_called_once()


class TestReportExportFlag:
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_with_grafana_export(self, mock_calc_cls, config_file: Path, tmp_path: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        dashboard_path = tmp_path / "dashboard.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--config", str(config_file),
             "--export", "grafana", "--export-output", str(dashboard_path)],
        )
        assert result.exit_code == 0
        assert dashboard_path.exists()
        import json as _json
        data = _json.loads(dashboard_path.read_text(encoding="utf-8"))
        assert "panels" in data.get("dashboard", data)

    @patch("azure_slo_guardian.cli._send_slo_webhook")
    @patch("azure_slo_guardian.cli.SLOCalculator")
    def test_report_with_notify(self, mock_calc_cls, mock_send, config_file: Path):
        instance = mock_calc_cls.return_value
        instance.calculate_all_slos.return_value = [_mock_slo_status(meeting=True)]

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--config", str(config_file),
             "--notify", "generic", "--webhook-url", "https://example.com/hook"],
        )
        assert result.exit_code == 0
        mock_send.assert_called_once()


# ---------------------------------------------------------------------------
# Templates command
# ---------------------------------------------------------------------------


class TestTemplatesCommand:
    def test_lists_all_templates(self):
        runner = CliRunner()
        result = runner.invoke(main, ["templates"])
        assert result.exit_code == 0
        assert "app-service-availability" in result.output
        assert "app-service-latency" in result.output
        assert "function-app-availability" in result.output
        assert "logic-app-success-rate" in result.output

    def test_shows_app_types(self):
        runner = CliRunner()
        result = runner.invoke(main, ["templates"])
        assert "Web App" in result.output
        assert "Function App" in result.output
        assert "Logic App" in result.output


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------


class TestInitCommand:
    def test_generates_webapp_config(self, tmp_path: Path):
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        # Flow: type(1), name, workspace, templates(A), target, alerts(1), add another?(N)
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="1\nmy-web-app\nws-123\nA\n99.9\n1\nN\n",
        )
        assert result.exit_code == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "my-web-app" in content
        assert "ws-123" in content
        data = yaml.safe_load(content)
        assert "slos" in data
        assert len(data["slos"]) == 2  # availability + latency

    def test_generates_function_app_config(self, tmp_path: Path):
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="2\nmy-func\nws-456\nA\n99.9\n2\nN\n",
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert len(data["slos"]) == 2
        assert any("my-func" in str(s) for s in data["slos"])

    def test_generates_logic_app_config(self, tmp_path: Path):
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="3\nmy-workflow\nws-789\nA\n99.5\n4\nN\n",
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert len(data["slos"]) == 2
        # Alert sensitivity 4 = off
        assert data["slos"][0]["alerting"]["enabled"] is False

    def test_custom_target(self, tmp_path: Path):
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="1\napp1\nws\nA\n99.5\n1\nN\n",
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert data["slos"][0]["objectives"][0]["target"] == 99.5

    def test_select_single_template(self, tmp_path: Path):
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="1\napp1\nws\n1\n99.9\n1\nN\n",
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert len(data["slos"]) == 1

    def test_multiple_apps_different_workspaces(self, tmp_path: Path):
        """Two apps with different workspace IDs in one config."""
        out = tmp_path / "slo.yaml"
        runner = CliRunner()
        # App 1: web app with ws-aaa, then "add another? Y"
        # App 2: function app with ws-bbb, then "add another? N"
        result = runner.invoke(
            main,
            ["init", "-o", str(out)],
            input="1\nfrontend\nws-aaa\nA\n99.9\n1\ny\n2\napi-func\nws-bbb\nA\n99.5\n2\nN\n",
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text(encoding="utf-8"))
        # 2 templates per app = 4 SLOs total
        assert len(data["slos"]) == 4
        # Verify different workspace IDs
        ws_ids = {s["sli"]["workspace_id"] for s in data["slos"]}
        assert "ws-aaa" in ws_ids
        assert "ws-bbb" in ws_ids

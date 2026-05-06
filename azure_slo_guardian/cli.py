"""Command-line interface for Azure SLO Guardian."""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click
import yaml
from tabulate import tabulate

from azure_slo_guardian import __version__
from azure_slo_guardian.burn_rate import BurnRateCalculator
from azure_slo_guardian.config import load_config, validate_config
from azure_slo_guardian.slo_calculator import SLOCalculator

# Configure logging
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def main(verbose: bool) -> None:
    """Azure SLO Guardian - Azure-native SLO/SLI engine."""
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("azure_slo_guardian").setLevel(logging.DEBUG)


@main.command()
def templates() -> None:
    """List available SLO preset templates."""
    from azure_slo_guardian.templates import list_templates

    all_templates = list_templates()

    headers = ["Template Name", "App Type", "SLI Type", "Default Target", "Description"]
    rows = []
    for t in all_templates:
        app_label = t.app_type.replace("_", " ").title()
        rows.append([
            t.name,
            app_label,
            t.sli_type,
            f"{t.default_target}%",
            t.description,
        ])

    click.echo(tabulate(rows, headers=headers, tablefmt="grid"))
    click.echo(f"\nUse  azure-slo-guardian init  to generate a config from a template.")


@main.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default="slo-config.yaml",
    help="Output file path (default: slo-config.yaml)",
)
def init(output: Path) -> None:
    """Interactively generate an SLO config file using preset templates.

    Guides you through adding one or more Azure App Service apps —
    each with its own Log Analytics workspace ID — and choosing a
    reliability target.  No KQL knowledge required.
    """
    from azure_slo_guardian.templates import (
        get_templates_for_app_type,
        resolve_template,
    )

    app_types = [
        ("1", "web_app", "Web App (App Service)"),
        ("2", "function_app", "Function App"),
        ("3", "logic_app", "Logic App"),
    ]

    click.echo(click.style("Azure SLO Guardian — Config Generator", bold=True))
    click.echo("Add your Azure apps one at a time. Each app gets its own workspace ID.\n")

    slo_entries: list = []
    app_count = 0

    while True:
        app_count += 1
        click.echo(click.style(f"── App #{app_count} ──", bold=True))

        # --- App type ---
        click.echo("What type of Azure App Service?")
        for num, _, label in app_types:
            click.echo(f"  {num}) {label}")

        choice = click.prompt("Select", type=click.Choice(["1", "2", "3"]), default="1")
        _, app_type, app_label = next(a for a in app_types if a[0] == choice)
        click.echo("")

        # --- App name ---
        app_name = click.prompt(
            f"Enter your {app_label} name (as it appears in Azure)"
        )
        click.echo("")

        # --- Workspace ID (per app) ---
        click.echo(
            "Enter the Log Analytics workspace ID for this app.\n"
            "Tip: Azure Portal → Log Analytics workspace → Properties → Workspace ID"
        )
        workspace_id = click.prompt("Workspace ID")
        click.echo("")

        # --- Templates ---
        avail = get_templates_for_app_type(app_type)
        click.echo(f"Available SLO templates for {app_label}:")
        for i, t in enumerate(avail, 1):
            click.echo(f"  {i}) {t.display_name} — {t.description}")
        click.echo(f"  A) All of the above")

        tmpl_choice = click.prompt("Select templates", default="A")
        click.echo("")

        if tmpl_choice.upper() == "A":
            selected = avail
        else:
            indices = [int(x.strip()) - 1 for x in tmpl_choice.split(",") if x.strip().isdigit()]
            selected = [avail[i] for i in indices if 0 <= i < len(avail)]
            if not selected:
                selected = avail

        # --- Target ---
        default_target = selected[0].default_target
        click.echo(
            "What availability/reliability target?\n"
            "  Common choices: 99.9% (three nines), 99.5%, 99.0%"
        )
        target = click.prompt("Target %", type=float, default=default_target)
        click.echo("")

        # --- Alert sensitivity ---
        click.echo(
            "Alert sensitivity?\n"
            "  1) High   — alert quickly (recommended for production)\n"
            "  2) Medium — balanced\n"
            "  3) Low    — only major burns\n"
            "  4) Off    — no alerts"
        )
        alert_choice = click.prompt(
            "Select", type=click.Choice(["1", "2", "3", "4"]), default="1"
        )
        click.echo("")

        alerting_overrides = {
            "1": {"enabled": True, "windows": [
                {"consume_budget": 2.0, "short_window": "5m", "long_window": "1h"},
                {"consume_budget": 5.0, "short_window": "30m", "long_window": "6h"},
                {"consume_budget": 10.0, "short_window": "2h", "long_window": "24h"},
            ]},
            "2": {"enabled": True, "windows": [
                {"consume_budget": 5.0, "short_window": "15m", "long_window": "3h"},
                {"consume_budget": 10.0, "short_window": "1h", "long_window": "12h"},
            ]},
            "3": {"enabled": True, "windows": [
                {"consume_budget": 10.0, "short_window": "1h", "long_window": "12h"},
            ]},
            "4": {"enabled": False, "windows": []},
        }

        for t in selected:
            resolved = resolve_template(
                t.name, app_name, workspace_id, target=target,
            )
            resolved["alerting"] = alerting_overrides[alert_choice]
            slo_entries.append(resolved)

        click.echo(
            click.style(f"  ✓ Added {len(selected)} SLO(s) for '{app_name}'", fg="green")
        )

        # --- Another app? ---
        if not click.confirm("Add another app?", default=False):
            break
        click.echo("")

    # --- Write the YAML ---
    config_data = {"slos": slo_entries}
    yaml_str = yaml.dump(config_data, default_flow_style=False, sort_keys=False)
    header = (
        f"# Azure SLO Guardian Configuration\n"
        f"# {len(slo_entries)} SLO(s) across {app_count} app(s)\n"
        f"#\n"
        f"# Each app has its own Log Analytics workspace ID.\n"
        f"# Edit workspace_id values below if needed.\n"
        f"#\n"
        f"# To check your SLOs:\n"
        f"#   azure-slo-guardian check --config {output}\n"
        f"#\n"
        f"# To generate a report:\n"
        f"#   azure-slo-guardian report --config {output}\n"
        f"#\n\n"
    )

    output.write_text(header + yaml_str, encoding="utf-8")

    click.echo(click.style(f"\n✓ Config written to {output}", fg="green"))
    click.echo(f"\nNext steps:")
    click.echo(f"  1. Review workspace IDs in {output}")
    click.echo(f"  2. Validate:   azure-slo-guardian validate -c {output}")
    click.echo(f"  3. Check SLOs: azure-slo-guardian check -c {output}")


@main.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SLO configuration file",
)
def validate(config: Path) -> None:
    """Validate SLO configuration file."""
    is_valid, error = validate_config(config)

    if is_valid:
        click.echo(click.style("✓ Configuration is valid", fg="green"))
        sys.exit(0)
    else:
        click.echo(click.style(f"✗ Configuration is invalid: {error}", fg="red"))
        sys.exit(1)


@main.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SLO configuration file",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "yaml"], case_sensitive=False),
    default="table",
    help="Output format",
)
@click.option(
    "--slo",
    "-s",
    help="Check specific SLO by name (default: all)",
)
@click.option(
    "--notify",
    type=click.Choice(["slack", "teams", "generic"], case_sensitive=False),
    help="Send results via webhook (requires --webhook-url)",
)
@click.option(
    "--webhook-url",
    envvar="SLO_WEBHOOK_URL",
    help="Webhook URL for notifications (or set SLO_WEBHOOK_URL env var)",
)
def check(config: Path, format: str, slo: Optional[str], notify: Optional[str], webhook_url: Optional[str]) -> None:
    """Check SLO status and error budgets."""
    try:
        # Load configuration
        slo_config = load_config(config)

        # Filter SLOs if specific name provided
        slos = slo_config.slos
        if slo:
            filtered_slo = slo_config.get_slo(slo)
            if not filtered_slo:
                click.echo(click.style(f"✗ SLO '{slo}' not found", fg="red"))
                sys.exit(1)
            slos = [filtered_slo]

        # Calculate SLO status
        calculator = SLOCalculator()
        results = calculator.calculate_all_slos(slos)

        # Output results
        if format == "json":
            output = [r.to_dict() for r in results]
            click.echo(json.dumps(output, indent=2))
        elif format == "yaml":
            output = [r.to_dict() for r in results]
            click.echo(yaml.dump(output, default_flow_style=False))
        else:  # table
            _print_slo_table(results)

        # Send webhook notification
        if notify:
            _send_slo_webhook(notify, webhook_url, results)

        # Exit with error if any SLO is not meeting target
        if any(not r.is_meeting_slo for r in results):
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        logger.exception("Error checking SLOs")
        sys.exit(1)


@main.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SLO configuration file",
)
@click.option(
    "--slo",
    "-s",
    required=True,
    help="SLO name",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "yaml"], case_sensitive=False),
    default="table",
    help="Output format",
)
def budget(config: Path, slo: str, format: str) -> None:
    """Calculate error budget for an SLO."""
    try:
        # Load configuration
        slo_config = load_config(config)
        slo_obj = slo_config.get_slo(slo)

        if not slo_obj:
            click.echo(click.style(f"✗ SLO '{slo}' not found", fg="red"))
            sys.exit(1)

        # Calculate SLO status
        calculator = SLOCalculator()
        results = calculator.calculate_all_slos([slo_obj])

        # Output budget information
        if format == "json":
            output = [r.error_budget.to_dict() for r in results]
            click.echo(json.dumps(output, indent=2))
        elif format == "yaml":
            output = [r.error_budget.to_dict() for r in results]
            click.echo(yaml.dump(output, default_flow_style=False))
        else:  # table
            _print_budget_table(results)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        logger.exception("Error calculating budget")
        sys.exit(1)


@main.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SLO configuration file",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "yaml"], case_sensitive=False),
    default="table",
    help="Output format",
)
@click.option(
    "--slo",
    "-s",
    help="Check alerts for specific SLO (default: all)",
)
@click.option(
    "--notify",
    type=click.Choice(["slack", "teams", "generic"], case_sensitive=False),
    help="Send firing alerts via webhook (requires --webhook-url)",
)
@click.option(
    "--webhook-url",
    envvar="SLO_WEBHOOK_URL",
    help="Webhook URL for notifications (or set SLO_WEBHOOK_URL env var)",
)
def alert(config: Path, format: str, slo: Optional[str], notify: Optional[str], webhook_url: Optional[str]) -> None:
    """Check burn-rate alerts."""
    try:
        # Load configuration
        slo_config = load_config(config)

        # Filter SLOs if specific name provided
        slos = slo_config.slos
        if slo:
            filtered_slo = slo_config.get_slo(slo)
            if not filtered_slo:
                click.echo(click.style(f"✗ SLO '{slo}' not found", fg="red"))
                sys.exit(1)
            slos = [filtered_slo]

        # Calculate burn rates
        calculator = BurnRateCalculator()
        all_alerts = []
        for slo_obj in slos:
            alerts = calculator.calculate_all_burn_rates(slo_obj)
            all_alerts.extend(alerts)

        # Output results
        if format == "json":
            output = [a.to_dict() for a in all_alerts]
            click.echo(json.dumps(output, indent=2))
        elif format == "yaml":
            output = [a.to_dict() for a in all_alerts]
            click.echo(yaml.dump(output, default_flow_style=False))
        else:  # table
            _print_alert_table(all_alerts)

        # Send webhook notification for firing alerts
        if notify:
            _send_alert_webhook(notify, webhook_url, all_alerts)

        # Exit with error if any alert is firing
        if any(a.is_alerting for a in all_alerts):
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        logger.exception("Error checking alerts")
        sys.exit(1)


def _print_slo_table(results) -> None:
    """Print SLO status as a table."""
    headers = [
        "SLO",
        "Service",
        "Window",
        "Target",
        "Current SLI",
        "Status",
        "Budget Remaining",
    ]

    rows = []
    for r in results:
        status_icon = "✓" if r.is_meeting_slo else "✗"
        status_color = "green" if r.is_meeting_slo else "red"

        budget_pct = 100.0 - r.error_budget.error_budget_consumed_pct
        budget_str = f"{budget_pct:.1f}%"
        if budget_pct < 10:
            budget_color = "red"
        elif budget_pct < 25:
            budget_color = "yellow"
        else:
            budget_color = "green"

        rows.append(
            [
                r.slo_name,
                r.service,
                r.objective.window,
                f"{r.objective.target}%",
                f"{r.current_sli:.2f}%",
                click.style(f"{status_icon} {'PASS' if r.is_meeting_slo else 'FAIL'}", fg=status_color),
                click.style(budget_str, fg=budget_color),
            ]
        )

    click.echo(tabulate(rows, headers=headers, tablefmt="grid"))


def _print_budget_table(results) -> None:
    """Print error budget as a table."""
    headers = [
        "SLO",
        "Window",
        "Target",
        "Current SLI",
        "Budget Total",
        "Budget Remaining",
        "Consumed",
        "Status",
    ]

    rows = []
    for r in results:
        eb = r.error_budget
        status = "EXHAUSTED" if eb.is_exhausted else "OK"
        status_color = "red" if eb.is_exhausted else "green"

        rows.append(
            [
                eb.slo_name,
                eb.window,
                f"{eb.target}%",
                f"{eb.current_sli:.2f}%",
                f"{eb.error_budget_total:.3f}%",
                f"{eb.error_budget_remaining:.3f}%",
                f"{eb.error_budget_consumed_pct:.1f}%",
                click.style(status, fg=status_color),
            ]
        )

    click.echo(tabulate(rows, headers=headers, tablefmt="grid"))


def _print_alert_table(alerts) -> None:
    """Print burn-rate alerts as a table."""
    headers = [
        "SLO",
        "Short Window",
        "Long Window",
        "Short SLI",
        "Long SLI",
        "Target",
        "Severity",
        "Status",
    ]

    rows = []
    for alert in alerts:
        status = "ALERTING" if alert.is_alerting else "OK"
        status_color = "red" if alert.is_alerting else "green"

        severity_color = {
            "critical": "red",
            "high": "yellow",
            "warning": "yellow",
        }.get(alert.severity, "white")

        rows.append(
            [
                alert.slo_name,
                alert.window_config.short_window,
                alert.window_config.long_window,
                f"{alert.short_window_sli:.2f}%",
                f"{alert.long_window_sli:.2f}%",
                f"{alert.target}%",
                click.style(alert.severity.upper(), fg=severity_color),
                click.style(status, fg=status_color),
            ]
        )

    click.echo(tabulate(rows, headers=headers, tablefmt="grid"))

    # Print alert messages
    firing_alerts = [a for a in alerts if a.is_alerting]
    if firing_alerts:
        click.echo("\n" + click.style("Active Alerts:", fg="red", bold=True))
        for alert in firing_alerts:
            click.echo(f"  • {alert.message}")


@main.command()
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to SLO configuration file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Write Markdown report to file (default: stdout)",
)
@click.option(
    "--export",
    "export_format",
    type=click.Choice(["grafana"], case_sensitive=False),
    help="Also export a Grafana dashboard JSON file alongside the report",
)
@click.option(
    "--export-output",
    type=click.Path(path_type=Path),
    default=None,
    help="Path for exported file (default: slo-dashboard.json)",
)
@click.option(
    "--notify",
    type=click.Choice(["slack", "teams", "generic"], case_sensitive=False),
    help="Send report summary via webhook (requires --webhook-url)",
)
@click.option(
    "--webhook-url",
    envvar="SLO_WEBHOOK_URL",
    help="Webhook URL for notifications (or set SLO_WEBHOOK_URL env var)",
)
def report(config: Path, output: Optional[Path], export_format: Optional[str],
           export_output: Optional[Path], notify: Optional[str],
           webhook_url: Optional[str]) -> None:
    """Generate a Markdown SLO report (for daily reports / GitHub Actions summaries)."""
    try:
        slo_config = load_config(config)
        calculator = SLOCalculator()
        results = calculator.calculate_all_slos(slo_config.slos)

        md = _build_markdown_report(results)

        if output:
            output.write_text(md, encoding="utf-8")
            click.echo(f"Report written to {output}")
        else:
            # Use sys.stdout with utf-8 to avoid Windows cp1252 encoding issues
            sys.stdout.buffer.write(md.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")

        # Grafana export
        if export_format == "grafana":
            from azure_slo_guardian.exporters.grafana import export_grafana_json

            grafana_path = export_output or Path("slo-dashboard.json")
            grafana_path.write_text(export_grafana_json(results), encoding="utf-8")
            click.echo(f"Grafana dashboard written to {grafana_path}")

        # Webhook notification
        if notify:
            _send_slo_webhook(notify, webhook_url, results)

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"))
        logger.exception("Error generating report")
        sys.exit(1)


def _send_slo_webhook(notify: str, webhook_url: Optional[str], results) -> None:
    """Send SLO status via webhook."""
    if not webhook_url:
        click.echo(click.style("✗ --webhook-url required when using --notify", fg="red"))
        return
    from azure_slo_guardian.notifiers.webhook import WebhookFormat, notify_slo_status

    fmt = WebhookFormat(notify)
    result = notify_slo_status(webhook_url, results, fmt=fmt)
    if result.success:
        click.echo(click.style(f"✓ Notification sent to {notify}", fg="green"))
    else:
        click.echo(click.style(f"✗ Notification failed: {result.error}", fg="red"))


def _send_alert_webhook(notify: str, webhook_url: Optional[str], alerts) -> None:
    """Send burn-rate alerts via webhook."""
    if not webhook_url:
        click.echo(click.style("✗ --webhook-url required when using --notify", fg="red"))
        return
    from azure_slo_guardian.notifiers.webhook import WebhookFormat, notify_burn_rate_alerts

    fmt = WebhookFormat(notify)
    result = notify_burn_rate_alerts(webhook_url, alerts, fmt=fmt)
    if result.success:
        click.echo(click.style(f"✓ Alert notification sent to {notify}", fg="green"))
    else:
        click.echo(click.style(f"✗ Notification failed: {result.error}", fg="red"))


def _build_markdown_report(results) -> str:
    """Build a Markdown SLO report from calculation results."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    passing = [r for r in results if r.is_meeting_slo]
    failing = [r for r in results if not r.is_meeting_slo]
    total = len(results)

    # Header
    lines = [
        f"# 📊 SLO Daily Report — {now}",
        "",
        f"**{total}** SLOs evaluated | "
        f"**{len(passing)}** passing | "
        f"**{len(failing)}** breaching",
        "",
    ]

    # Summary status
    if not failing:
        lines.append("> ✅ All SLOs are within budget.\n")
    else:
        names = ", ".join(f"`{r.slo_name}`" for r in failing)
        lines.append(f"> 🔴 **{len(failing)} SLO(s) breaching target:** {names}\n")

    # Table
    lines.append("| Service | SLO | Window | Target | Actual | Budget Remaining | Status |")
    lines.append("|---------|-----|--------|--------|--------|------------------|--------|")

    for r in results:
        budget_remaining = 100.0 - r.error_budget.error_budget_consumed_pct
        if r.is_meeting_slo:
            status = "✅ OK"
        elif r.error_budget.is_exhausted:
            status = "🔴 EXHAUSTED"
        else:
            status = "⚠️ BURN"

        lines.append(
            f"| {r.service} "
            f"| {r.slo_name} "
            f"| {r.objective.window} "
            f"| {r.objective.target}% "
            f"| {r.current_sli:.2f}% "
            f"| {budget_remaining:.1f}% "
            f"| {status} |"
        )

    lines.append("")

    # Detail section for breaching SLOs
    if failing:
        lines.append("## Breaching SLOs — Detail")
        lines.append("")
        for r in failing:
            eb = r.error_budget
            lines.append(f"### 🔴 {r.slo_name} (`{r.service}`)")
            lines.append(f"- **Description:** {r.description}")
            lines.append(f"- **Target:** {r.objective.target}% over {r.objective.window}")
            lines.append(f"- **Current SLI:** {r.current_sli:.2f}%")
            lines.append(f"- **Error budget total:** {eb.error_budget_total:.3f}%")
            lines.append(f"- **Error budget remaining:** {eb.error_budget_remaining:.3f}%")
            lines.append(f"- **Budget consumed:** {eb.error_budget_consumed_pct:.1f}%")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Azure SLO Guardian - Demo Script

This script demonstrates the core functionality of Azure SLO Guardian
without requiring actual Azure credentials. It shows how the library
works with mock data.
"""

from datetime import datetime, timedelta

from azure_slo_guardian.config import (
    Objective,
    Operator,
    QueryType,
    SLO,
    SLIConfig,
    SLIType,
    SLOConfig,
)
from azure_slo_guardian.slo_calculator import ErrorBudget


def demo_config_validation():
    """Demonstrate configuration validation."""
    print("=" * 70)
    print("Azure SLO Guardian - Demo")
    print("=" * 70)
    print()

    print("1. Creating an SLO Configuration")
    print("-" * 70)

    # Create a sample SLO
    slo = SLO(
        name="api-availability",
        description="API service availability SLO",
        service="backend-api",
        sli=SLIConfig(
            type=SLIType.AVAILABILITY,
            query_type=QueryType.APPLICATION_INSIGHTS,
            workspace_id="demo-workspace-id",
            good_query="requests | where success == true | count",
            total_query="requests | count",
        ),
        objectives=[
            Objective(target=99.9, window="30d"),
            Objective(target=99.5, window="7d"),
        ],
    )

    print(f"✓ SLO Name: {slo.name}")
    print(f"✓ Service: {slo.service}")
    print(f"✓ SLI Type: {slo.sli.type.value}")
    print(f"✓ Objectives: {len(slo.objectives)}")
    for obj in slo.objectives:
        print(f"  - Target: {obj.target}% over {obj.window}")
    print()


def demo_error_budget_calculation():
    """Demonstrate error budget calculations."""
    print("2. Error Budget Calculation")
    print("-" * 70)

    scenarios = [
        ("Meeting SLO", 99.95, 99.9),
        ("Close to target", 99.91, 99.9),
        ("At target", 99.9, 99.9),
        ("Below target", 99.85, 99.9),
        ("Budget exhausted", 99.5, 99.9),
    ]

    for scenario_name, current_sli, target in scenarios:
        # Calculate error budget manually (simplified)
        error_budget_total = 100.0 - target
        current_error = 100.0 - current_sli
        error_budget_remaining = error_budget_total - current_error
        error_budget_consumed_pct = (current_error / error_budget_total) * 100.0
        is_exhausted = error_budget_remaining <= 0

        print(f"\n{scenario_name}:")
        print(f"  Current SLI: {current_sli}%")
        print(f"  Target: {target}%")
        print(f"  Error Budget Total: {error_budget_total}%")
        print(f"  Error Budget Remaining: {error_budget_remaining}%")
        print(f"  Budget Consumed: {error_budget_consumed_pct:.1f}%")
        print(f"  Status: {'❌ EXHAUSTED' if is_exhausted else '✅ OK'}")

    print()


def demo_burn_rate_scenarios():
    """Demonstrate burn-rate alert scenarios."""
    print("3. Burn-Rate Alert Scenarios")
    print("-" * 70)

    target = 99.9
    error_budget = 100.0 - target  # 0.1%

    scenarios = [
        ("Normal Operation", 99.95, 99.95, "No alert"),
        ("Slow Burn", 99.92, 99.90, "Warning - slow budget consumption"),
        ("Fast Burn", 99.85, 99.80, "Critical - rapid budget consumption"),
        ("Severe Outage", 98.0, 97.5, "Critical - major incident"),
    ]

    for scenario_name, long_window_sli, short_window_sli, expected in scenarios:
        print(f"\n{scenario_name}:")
        print(f"  Long window (6h) SLI: {long_window_sli}%")
        print(f"  Short window (1h) SLI: {short_window_sli}%")
        print(f"  Target: {target}%")
        print(f"  Expected: {expected}")

    print()


def demo_cli_commands():
    """Show example CLI commands."""
    print("4. CLI Usage Examples")
    print("-" * 70)

    commands = [
        ("Validate configuration", "azure-slo-guardian validate --config slo.yaml"),
        ("Check SLO status", "azure-slo-guardian check --config slo.yaml"),
        (
            "Check specific SLO",
            "azure-slo-guardian check --config slo.yaml --slo api-availability",
        ),
        ("View error budget", "azure-slo-guardian budget --config slo.yaml --slo api-availability"),
        ("Check burn-rate alerts", "azure-slo-guardian alert --config slo.yaml"),
        ("JSON output", "azure-slo-guardian check --config slo.yaml --format json"),
        ("Verbose mode", "azure-slo-guardian --verbose check --config slo.yaml"),
    ]

    for description, command in commands:
        print(f"\n{description}:")
        print(f"  $ {command}")

    print()


def demo_yaml_config():
    """Show example YAML configuration."""
    print("5. Example YAML Configuration")
    print("-" * 70)

    yaml_example = """
slos:
  - name: api-availability
    description: "API availability SLO - 99.9% over 30 days"
    service: backend-api
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "${APPINSIGHTS_WORKSPACE_ID}"
      good_query: |
        requests
        | where success == true
        | count
      total_query: |
        requests
        | count
    objectives:
      - target: 99.9
        window: 30d
    alerting:
      enabled: true
      windows:
        - consume_budget: 2.0
          short_window: 5m
          long_window: 1h
        - consume_budget: 5.0
          short_window: 30m
          long_window: 6h
"""

    print(yaml_example)


def main():
    """Run all demos."""
    demo_config_validation()
    demo_error_budget_calculation()
    demo_burn_rate_scenarios()
    demo_cli_commands()
    demo_yaml_config()

    print("=" * 70)
    print("Demo Complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review the README.md for full documentation")
    print("2. Check examples/ directory for sample configurations")
    print("3. Read QUICKSTART.md for a 5-minute getting started guide")
    print("4. Set up Azure credentials and try with real data")
    print()
    print("For help: azure-slo-guardian --help")
    print()


if __name__ == "__main__":
    main()

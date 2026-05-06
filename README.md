<div align="center">

# 🛡️ Azure SLO Guardian

### The missing SLO engine for Azure — define, track, and alert on Service Level Objectives in minutes.

[![CI](https://github.com/IamCharli01/Azure-SLO-Guardian/actions/workflows/ci.yml/badge.svg)](https://github.com/IamCharli01/Azure-SLO-Guardian/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/IamCharli01/Azure-SLO-Guardian/pulls)
[![GitHub Discussions](https://img.shields.io/github/discussions/IamCharli01/Azure-SLO-Guardian)](https://github.com/IamCharli01/Azure-SLO-Guardian/discussions)
[![GitHub Stars](https://img.shields.io/github/stars/IamCharli01/Azure-SLO-Guardian?style=social)](https://github.com/IamCharli01/Azure-SLO-Guardian/stargazers)

<br />

**Google has their SLO generator. Prometheus has Sloth. Azure had... nothing. Until now.**

[Quick Start](#-quick-start) · [Features](#-features) · [Documentation](QUICKSTART.md) · [Contributing](CONTRIBUTING.md) · [Discussions](https://github.com/IamCharli01/Azure-SLO-Guardian/discussions)

</div>

---

## 🤔 The Problem

Every SRE team on Azure faces the same frustration:
- Azure Monitor has metrics but no native SLO tracking
- Error budgets require manual spreadsheet calculations
- Burn-rate alerts need custom, complex alert rules
- No single tool ties it all together

## ✅ The Solution

Azure SLO Guardian gives you **production-ready SLO monitoring in under 5 minutes**:

```yaml
# That's it. Define your SLO in YAML:
slos:
  - name: api-availability
    sli:
      type: availability
      query_type: application_insights
      good_query: "requests | where success == true | count"
      total_query: "requests | count"
    objectives:
      - target: 99.9
        window: 30d
```

```bash
$ azure-slo-guardian check --config slo-config.yaml

┌─────────────────────┬────────┬───────────┬──────────────────┐
│ SLO                 │ Target │ Current   │ Error Budget     │
├─────────────────────┼────────┼───────────┼──────────────────┤
│ api-availability    │ 99.9%  │ 99.94%    │ 🟢 58% remaining │
│ api-latency-p95     │ 99.5%  │ 99.2%     │ 🔴 EXHAUSTED     │
└─────────────────────┴────────┴───────────┴──────────────────┘
```

## 🚀 Features

| Feature | Description |
|---------|-------------|
| 📝 **YAML-based SLOs** | Declarative config — version control your reliability targets |
| 🔌 **Native Azure** | Azure Monitor, Application Insights, Log Analytics via KQL |
| 📊 **Error Budgets** | Automatic calculation with remaining budget tracking |
| 🔥 **Burn-Rate Alerts** | Multi-window detection per Google SRE Workbook |
| 🧙 **Init Wizard** | Interactive setup — no KQL knowledge required |
| 📋 **Templates** | Pre-built SLOs for App Service, Functions, Logic Apps |
| 📈 **Grafana Export** | Starter dashboard template for Grafana import |
| 🔔 **Notifications** | Slack, Teams, and generic webhooks |
| ⚡ **CI/CD Ready** | GitHub Actions integration — SLO checks as PR gates |
| 🖥️ **Multi-format** | JSON, YAML, Markdown, and table output |

## Quick Start

### Installation

```bash
pip install azure-slo-guardian
```

> **Windows PATH note:** If you get `'azure-slo-guardian' is not recognized`, the
> Scripts directory isn't on your PATH. Use `python -m azure_slo_guardian` instead,
> or add the directory shown in pip's warning to your PATH.

### Define Your First SLO (no KQL required)

Use the interactive wizard to generate a config:

```bash
azure-slo-guardian init
```

Or create `slo-config.yaml` manually:

```yaml
slos:
  - name: api-availability
    description: "API service availability SLO"
    service: my-api-service
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
```

### Check SLO Status

```bash
# Check current SLO status
azure-slo-guardian check --config slo-config.yaml

# Check with detailed output
azure-slo-guardian check --config slo-config.yaml --verbose

# Export to JSON
azure-slo-guardian check --config slo-config.yaml --format json
```

## Configuration

### SLO Configuration Schema

```yaml
slos:
  - name: string                    # Unique SLO identifier
    description: string             # Human-readable description
    service: string                 # Service name
    sli:
      type: string                  # availability, latency, or custom
      query_type: string            # application_insights, log_analytics, or azure_monitor
      workspace_id: string          # Azure resource ID
      connection_id: string         # Optional: for Azure Monitor metrics
      
      # For ratio-based SLIs (availability, success rate)
      good_query: string            # KQL query for good events
      total_query: string           # KQL query for total events
      
      # For threshold-based SLIs (latency)
      query: string                 # KQL query returning values
      threshold: number             # Threshold value
      operator: string              # lt, lte, gt, gte
      
    objectives:
      - target: number              # SLO target (e.g., 99.9 for 99.9%)
        window: string              # Time window (e.g., 30d, 7d, 1h)
        
    alerting:                       # Optional burn-rate alerting
      enabled: boolean
      windows:                      # Multi-window burn-rate
        - consume_budget: number    # % of budget consumed
          short_window: string      # Short window duration
          long_window: string       # Long window duration
```

### Example Configurations

#### Availability SLO (Application Insights)
```yaml
slos:
  - name: frontend-availability
    service: web-frontend
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "/subscriptions/xxx/resourceGroups/xxx/providers/microsoft.insights/components/xxx"
      good_query: |
        requests
        | where success == true and resultCode < 500
      total_query: |
        requests
    objectives:
      - target: 99.9
        window: 30d
```

#### Latency SLO (Log Analytics)
```yaml
slos:
  - name: api-latency-p95
    service: backend-api
    sli:
      type: latency
      query_type: log_analytics
      workspace_id: "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.OperationalInsights/workspaces/xxx"
      query: |
        ContainerLog
        | where LogEntry has "request_duration"
        | extend duration = todouble(extract("duration=([0-9.]+)", 1, LogEntry))
        | summarize percentile_95 = percentile(duration, 95)
      threshold: 500
      operator: lte
    objectives:
      - target: 99.5
        window: 7d
```

#### Custom Metric SLO (Azure Monitor)
```yaml
slos:
  - name: queue-processing-success
    service: queue-processor
    sli:
      type: custom
      query_type: azure_monitor
      connection_id: "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.ServiceBus/namespaces/xxx"
      good_query: |
        SuccessfulRequests
        | summarize sum(total)
      total_query: |
        AllRequests
        | summarize sum(total)
    objectives:
      - target: 99.99
        window: 30d
```

## CLI Reference

```bash
# List available SLO templates
azure-slo-guardian templates

# Interactively generate an SLO config file
azure-slo-guardian init

# Validate SLO configuration
azure-slo-guardian validate --config slo-config.yaml

# Check SLO status
azure-slo-guardian check --config slo-config.yaml [--format json|yaml|table]

# Calculate error budget
azure-slo-guardian budget --config slo-config.yaml --slo <slo-name>

# Check burn-rate alerts
azure-slo-guardian alert --config slo-config.yaml

# Generate Markdown report (with optional Grafana dashboard export)
azure-slo-guardian report --config slo-config.yaml [--output report.md]
azure-slo-guardian report --config slo-config.yaml --export grafana --export-output dashboard.json

# Send results via webhook (Slack, Teams, or generic)
azure-slo-guardian check --config slo-config.yaml --notify slack --webhook-url $WEBHOOK_URL
```

## Authentication

Azure SLO Guardian uses Azure SDK authentication. Supported methods:

1. **Azure CLI** - `az login`
2. **Managed Identity** - When running in Azure
3. **Service Principal** - Set `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`
4. **Environment variables** - `AZURE_SUBSCRIPTION_ID`

## CI/CD Integration

### GitHub Actions

```yaml
name: SLO Check
on: [pull_request]

jobs:
  slo-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Azure SLO Guardian
        run: pip install azure-slo-guardian
      
      - name: Azure Login
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      
      - name: Check SLOs
        run: |
          azure-slo-guardian check --config slo-config.yaml --format json > slo-report.json
          
      - name: Fail if SLO violated
        run: |
          azure-slo-guardian validate --config slo-config.yaml --strict
```

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/IamCharli01/Azure-SLO-Guardian.git
cd Azure-SLO-Guardian

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=azure_slo_guardian --cov-report=html

# Run specific test
pytest tests/test_slo_calculator.py
```

### Project Structure

```
azure-slo-guardian/
├── azure_slo_guardian/
│   ├── __init__.py
│   ├── cli.py                 # CLI interface (Click)
│   ├── config.py              # Configuration parsing and validation (Pydantic)
│   ├── slo_calculator.py      # SLO/error budget calculations
│   ├── query_engine.py        # Azure query execution with retry logic
│   ├── burn_rate.py           # Multi-window burn-rate alert logic
│   ├── templates.py           # Pre-built SLO templates for Azure services
│   ├── exporters/
│   │   └── grafana.py         # Grafana dashboard export
│   └── notifiers/
│       └── webhook.py         # Slack, Teams, and generic webhook notifications
├── tests/
├── examples/
├── setup.py
├── pyproject.toml
├── README.md
└── LICENSE
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details.

See the [open issues](https://github.com/IamCharli01/Azure-SLO-Guardian/issues) for a list of proposed features and known issues.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

Inspired by:
- Google's SRE Workbook on SLOs and error budgets
- Sloth (Prometheus SLO generator)
- OpenSLO specification

---

<div align="center">

Built with ❤️ for the Azure SRE community

**If this project helps you, consider giving it a ⭐ — it helps others discover it!**

[⭐ Star this repo](https://github.com/IamCharli01/Azure-SLO-Guardian) · [🐛 Report Bug](https://github.com/IamCharli01/Azure-SLO-Guardian/issues/new?template=bug_report.yml) · [💡 Request Feature](https://github.com/IamCharli01/Azure-SLO-Guardian/issues/new?template=feature_request.yml) · [💬 Discussions](https://github.com/IamCharli01/Azure-SLO-Guardian/discussions)

</div>

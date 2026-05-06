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

[Quick Start](#-quick-start) · [Features](#-features) · [Docs](QUICKSTART.md) · [Contributing](CONTRIBUTING.md) · [Discussions](https://github.com/IamCharli01/Azure-SLO-Guardian/discussions)

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
# Define your SLO in YAML:
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

## 📦 Quick Start

```bash
# Install
pip install azure-slo-guardian

# Generate config interactively (no KQL needed)
azure-slo-guardian init

# Or validate an existing config
azure-slo-guardian validate --config slo-config.yaml

# Check your SLOs
azure-slo-guardian check --config slo-config.yaml
```

> **Windows PATH note:** If `azure-slo-guardian` isn't recognized, use `python -m azure_slo_guardian` instead.

## 🔐 Authentication

Azure SLO Guardian uses the Azure SDK's `DefaultAzureCredential`. Just make sure you're logged in:

```bash
az login
```

Or set environment variables for CI: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`.

## 📖 CLI Commands

| Command | What it does |
|---------|-------------|
| `init` | Interactive wizard to generate SLO config |
| `templates` | List available pre-built SLO templates |
| `validate` | Check config syntax (add `--strict` for Azure connectivity check) |
| `check` | Calculate current SLO status and error budgets |
| `budget` | Show error budget details for a specific SLO |
| `alert` | Check burn-rate alerts |
| `report` | Generate a Markdown report (great for GitHub Actions summaries) |

All commands support `--format json|yaml|table` and `--notify slack|teams|generic`.

## 🔗 CI/CD Integration

```yaml
# .github/workflows/slo-check.yml
- name: Check SLOs
  run: azure-slo-guardian check --config slo-config.yaml --format json

- name: Fail PR if SLO violated
  run: azure-slo-guardian validate --config slo-config.yaml --strict
```

See [examples/](examples/) for full workflow templates.

## 🛠️ Development

```bash
git clone https://github.com/IamCharli01/Azure-SLO-Guardian.git
cd Azure-SLO-Guardian
python -m venv venv && venv\Scripts\activate  # or source venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [QUICKSTART.md](QUICKSTART.md) | Full setup guide with examples |
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the internals work |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

## Contributing

Contributions are welcome! See [open issues](https://github.com/IamCharli01/Azure-SLO-Guardian/issues) — many are labeled `good first issue`.

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built with ❤️ for the Azure SRE community

**If this helps you, give it a ⭐ — it helps others discover it!**

[⭐ Star](https://github.com/IamCharli01/Azure-SLO-Guardian) · [🐛 Report Bug](https://github.com/IamCharli01/Azure-SLO-Guardian/issues/new?template=bug_report.yml) · [💡 Request Feature](https://github.com/IamCharli01/Azure-SLO-Guardian/issues/new?template=feature_request.yml) · [💬 Discussions](https://github.com/IamCharli01/Azure-SLO-Guardian/discussions)

</div>

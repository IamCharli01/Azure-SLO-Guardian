# Setup Guide

## 1. Install

```bash
pip install azure-slo-guardian

# With webhook notifications (Slack/Teams):
pip install azure-slo-guardian[notifications]
```

## 2. Create your config

```bash
# Interactive wizard — no KQL knowledge needed
azure-slo-guardian init
```

Or copy an example from `examples/` and fill in your app name + workspace ID.

## 3. Authentication

Azure SLO Guardian uses **`DefaultAzureCredential`** from the Azure SDK. This means it
automatically picks up credentials in this order:

| Method | Where it works | How |
|--------|---------------|-----|
| **Managed Identity** | Azure VMs, App Service, AKS, self-hosted runners | Assign identity to the compute, no secrets needed |
| **Service Principal** | GitHub Actions, Azure Pipelines | Set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` env vars |
| **Azure CLI** | Local development | Run `az login` first |
| **VS Code / Azure PS** | Local development | Sign in via VS Code Azure extension or `Connect-AzAccount` |

### Using Managed Identity (recommended for production)

If your pipeline runner (Azure DevOps self-hosted agent, AKS pod, Azure VM) has a
**system-assigned or user-assigned managed identity**, just assign the required roles.
No secrets, no expiring passwords.

Remove the `azure/login` step from the workflow — `DefaultAzureCredential` handles it.

### Using a Service Principal (GitHub Actions hosted runners)

```bash
# Create the service principal
az ad sp create-for-rbac \
  --name slo-guardian-sp \
  --role "Log Analytics Reader" \
  --scopes /subscriptions/<YOUR-SUBSCRIPTION-ID>

# Save the JSON output as a GitHub secret named AZURE_CREDENTIALS
```

## 4. Required Permissions (RBAC)

The identity (managed identity OR service principal) needs these roles on **each
Log Analytics workspace** referenced in your config:

| Role | Why | Required? |
|------|-----|-----------|
| **Log Analytics Reader** | Execute KQL queries against logs | Yes |
| **Monitoring Reader** | Query Azure Monitor metrics | Only if using `query_type: azure_monitor` |

### Assign the role

```bash
# For a specific workspace (recommended — least privilege)
az role assignment create \
  --assignee <IDENTITY-OBJECT-ID-OR-SP-APP-ID> \
  --role "Log Analytics Reader" \
  --scope /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.OperationalInsights/workspaces/<WORKSPACE-NAME>
```

```bash
# Or for the whole subscription (simpler but broader)
az role assignment create \
  --assignee <IDENTITY-OBJECT-ID-OR-SP-APP-ID> \
  --role "Log Analytics Reader" \
  --scope /subscriptions/<SUB>
```

### How to find your identity's Object ID

```bash
# Service principal
az ad sp show --id <APP-ID> --query id -o tsv

# System-assigned managed identity (VM example)
az vm show --name <VM> --resource-group <RG> --query identity.principalId -o tsv

# User-assigned managed identity
az identity show --name <NAME> --resource-group <RG> --query principalId -o tsv
```

## 5. Pick your workflow templates

Copy **only the ones you need** from `.github/workflows/templates/` into `.github/workflows/`:

| Template | What it does | Include if you want... |
|----------|-------------|----------------------|
| `slo-daily-report.yml` | Markdown report in GitHub Actions summary | A daily/weekly status report |
| `slo-slack-notify.yml` | Sends to Slack via webhook | Slack alerts when SLOs breach |
| `slo-teams-notify.yml` | Sends to Teams via webhook | Teams alerts when SLOs breach |
| `slo-grafana-export.yml` | Generates Grafana dashboard JSON | Grafana dashboards |
| `slo-pr-gate.yml` | Blocks PRs when SLOs are breaching | Deploy protection |

**Each template is independent.** If you don't use Grafana, don't include the Grafana template —
the other workflows won't try to export anything. If you don't set `SLO_WEBHOOK_URL`, the
notify steps warn but don't fail.

## 6. Set the schedule

Every workflow template has a `cron:` line you **must configure**. Look for the
`<-- CHANGE THIS` comment:

```yaml
on:
  schedule:
    - cron: '0 9 * * *'       # <-- CHANGE THIS
```

Common schedules:

| Cron | Frequency |
|------|-----------|
| `'0 9 * * *'` | Daily at 9 AM UTC |
| `'0 9 * * 1'` | Weekly on Monday at 9 AM UTC |
| `'0 */6 * * *'` | Every 6 hours |
| `'0 * * * *'` | Every hour |
| `'0 9,17 * * 1-5'` | Twice daily (9 AM + 5 PM UTC) on weekdays |

## 7. Required secrets (GitHub Actions)

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Required by | Value |
|--------|------------|-------|
| `AZURE_CREDENTIALS` | All templates | JSON from `az ad sp create-for-rbac` |
| `SLO_WEBHOOK_URL` | Slack/Teams templates | Incoming webhook URL |
| `GRAFANA_URL` | Grafana template (optional) | e.g. `https://grafana.mycompany.com` |
| `GRAFANA_TOKEN` | Grafana template (optional) | Grafana API token |

## 8. Validate and run

```bash
# Validate your config
azure-slo-guardian validate -c slo-config.yaml

# Test locally (requires az login or managed identity)
azure-slo-guardian check -c slo-config.yaml
azure-slo-guardian report -c slo-config.yaml
```

# Azure SLO Guardian - Quick Start Guide

This guide will help you get started with Azure SLO Guardian in 5 minutes.

## Prerequisites

- Python 3.9+
- Azure subscription with Application Insights or Log Analytics
- Azure CLI installed and logged in (`az login`)

## Installation

```bash
pip install azure-slo-guardian
```

> **Windows PATH note:** If you see `'azure-slo-guardian' is not recognized`, the
> Scripts directory isn't on your PATH. Use `python -m azure_slo_guardian` instead,
> or add the directory shown in pip's warning to your PATH.

For development:
```bash
git clone https://github.com/IamCharli01/Azure-SLO-Guardian.git
cd Azure-SLO-Guardian
pip install -e ".[dev]"
```

## Step 1: Create Your First SLO Configuration

The easiest way is the interactive wizard:

```bash
azure-slo-guardian init
```

This asks for your app type, name, workspace ID, SLO target, and alert sensitivity —
then writes a ready-to-use `slo-config.yaml`. No KQL knowledge required.

Or create a file manually named `my-slo.yaml`:

```yaml
slos:
  - name: api-availability
    description: "API availability SLO - 99.9% over 30 days"
    service: my-api
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "YOUR_APPINSIGHTS_WORKSPACE_ID"
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

Replace `YOUR_APPINSIGHTS_WORKSPACE_ID` with your actual Application Insights workspace ID.

You can find it in Azure Portal:
1. Navigate to your Application Insights resource
2. Go to Properties
3. Copy the Workspace ID

Or use environment variables:
```yaml
workspace_id: "${APPINSIGHTS_WORKSPACE_ID}"
```

Then set:
```bash
export APPINSIGHTS_WORKSPACE_ID="your-workspace-id"
```

## Step 2: Validate Your Configuration

```bash
azure-slo-guardian validate --config my-slo.yaml
```

Expected output:
```
✓ Configuration is valid
```

## Step 3: Check SLO Status

```bash
azure-slo-guardian check --config my-slo.yaml
```

This will query Azure and display your current SLO status in a table format.

## Step 4: View Error Budget

```bash
azure-slo-guardian budget --config my-slo.yaml --slo api-availability
```

This shows how much error budget you have remaining.

## Step 5: Setup Burn-Rate Alerts

Add alerting to your SLO configuration:

```yaml
slos:
  - name: api-availability
    description: "API availability SLO"
    service: my-api
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
```

Check alerts:
```bash
azure-slo-guardian alert --config my-slo.yaml
```

## Common KQL Queries

### Application Insights - Availability

```yaml
good_query: |
  requests
  | where success == true and resultCode < 500
  | count

total_query: |
  requests
  | count
```

### Application Insights - Latency (P95 < 500ms)

```yaml
query: |
  requests
  | summarize percentile_95 = percentile(duration, 95)

threshold: 500
operator: lte
```

### Log Analytics - Custom Metric

```yaml
good_query: |
  ContainerLog
  | where LogEntry has "status=success"
  | count

total_query: |
  ContainerLog
  | count
```

## Integration with CI/CD

### GitHub Actions

Create `.github/workflows/slo-check.yml`:

```yaml
name: SLO Check

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  check-slos:
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
        run: azure-slo-guardian check --config slo-config.yaml
```

## Next Steps

1. **Add more SLOs** - Define SLOs for different services
2. **Setup monitoring** - Integrate with your monitoring dashboards
3. **Configure alerts** - Set up notifications for budget burn
4. **CI/CD integration** - Add SLO checks to your deployment pipeline

## Troubleshooting

### Authentication Issues

If you get authentication errors:

1. Ensure you're logged in to Azure CLI:
   ```bash
   az login
   ```

2. Set the subscription:
   ```bash
   az account set --subscription "Your Subscription Name"
   ```

3. For service principal authentication:
   ```bash
   export AZURE_CLIENT_ID="your-client-id"
   export AZURE_CLIENT_SECRET="your-client-secret"
   export AZURE_TENANT_ID="your-tenant-id"
   ```

### Query Errors

If queries fail:

1. Test your KQL query in Azure Portal first
2. Verify workspace ID is correct
3. Check you have read permissions on the workspace
4. Ensure the time window has data

### Getting Help

- Check the [README](README.md) for full documentation
- View [examples](examples/) for more configurations
- Open an issue on GitHub for bugs or questions

## Advanced Usage

### Output Formats

```bash
# JSON output
azure-slo-guardian check --config my-slo.yaml --format json

# YAML output
azure-slo-guardian check --config my-slo.yaml --format yaml

# Table (default)
azure-slo-guardian check --config my-slo.yaml --format table
```

### Check Specific SLO

```bash
azure-slo-guardian check --config my-slo.yaml --slo api-availability
```

### Verbose Mode

```bash
azure-slo-guardian --verbose check --config my-slo.yaml
```

Happy SLO monitoring! 🎯

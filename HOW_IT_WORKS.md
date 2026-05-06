# How Azure SLO Guardian Works - Complete Walkthrough

## Real-World Example: E-Commerce Company

Let's say **"CloudMart"** is an e-commerce company running on Azure. They want to implement SRE best practices for their critical services.

---

## The Problem CloudMart Has

CloudMart has:
- A **web frontend** (customers browse products)
- A **checkout API** (handles payments)
- An **order processing service** (processes orders)

All services send telemetry to Azure Application Insights and Log Analytics.

**Current Issues:**
- ❌ No clear reliability targets
- ❌ Manual dashboard monitoring
- ❌ Don't know how much "error budget" they have
- ❌ Can't tell if a small issue will blow their reliability target
- ❌ No automated way to prevent deployments when things are already degraded

---

## How They Use Azure SLO Guardian

### Step 1: Install the Tool

CloudMart's SRE team installs Azure SLO Guardian:

```bash
pip install azure-slo-guardian
```

Or add it to their DevOps pipelines:
```yaml
# In their CI/CD pipeline
- name: Install SLO Guardian
  run: pip install azure-slo-guardian
```

---

### Step 2: Define Their SLOs in YAML

The SRE team creates `slo-config.yaml` defining what "good" means:

```yaml
slos:
  # FRONTEND: Users should be able to browse 99.9% of the time
  - name: frontend-availability
    description: "Web frontend must be available 99.9% of the time over 30 days"
    service: web-frontend
    sli:
      type: availability
      query_type: application_insights
      workspace_id: "abc123-appinsights-workspace-id"
      
      # "Good" = HTTP requests that succeeded
      good_query: |
        requests
        | where name startswith "GET /products" or name startswith "GET /cart"
        | where success == true and resultCode < 500
        | count
      
      # "Total" = All HTTP requests
      total_query: |
        requests
        | where name startswith "GET /products" or name startswith "GET /cart"
        | count
    
    objectives:
      - target: 99.9    # 99.9% availability over 30 days
        window: 30d
      - target: 99.5    # 99.5% availability over last 7 days (stricter)
        window: 7d

  # CHECKOUT API: Payment processing must be fast
  - name: checkout-latency
    description: "95% of checkout requests must complete under 2 seconds"
    service: checkout-api
    sli:
      type: latency
      query_type: application_insights
      workspace_id: "abc123-appinsights-workspace-id"
      
      # Query returns 95th percentile latency
      query: |
        requests
        | where name == "POST /api/checkout"
        | summarize p95_latency = percentile(duration, 95)
      
      threshold: 2000  # 2000ms = 2 seconds
      operator: lte    # less than or equal
    
    objectives:
      - target: 99.5    # 99.5% of time, p95 must be under 2s
        window: 7d

  # ORDER PROCESSING: Background jobs must succeed
  - name: order-processing-success
    description: "Order processing jobs must succeed 99.99% of the time"
    service: order-processor
    sli:
      type: custom
      query_type: log_analytics
      workspace_id: "xyz789-loganalytics-workspace-id"
      
      # Count successful order processing from logs
      good_query: |
        ContainerLog
        | where LogEntry has "OrderProcessor"
        | where LogEntry has "status=completed"
        | count
      
      total_query: |
        ContainerLog
        | where LogEntry has "OrderProcessor"
        | where LogEntry has "status=completed" or LogEntry has "status=failed"
        | count
    
    objectives:
      - target: 99.99
        window: 30d
    
    # Alert if burning error budget too fast
    alerting:
      enabled: true
      windows:
        # Alert if consuming 2% of monthly budget in just 1 hour
        - consume_budget: 2.0
          short_window: 5m
          long_window: 1h
        # Alert if consuming 5% of monthly budget in 6 hours
        - consume_budget: 5.0
          short_window: 30m
          long_window: 6h
```

This file is **version controlled** in their Git repository alongside their code.

---

### Step 3: Daily Monitoring - Check Current SLO Status

Every day, their SRE team (or automated monitoring) runs:

```bash
azure-slo-guardian check --config slo-config.yaml
```

**Output they see:**

```
+------------------------+-----------------+--------+--------+-------------+---------+------------------+
| SLO                    | Service         | Window | Target | Current SLI | Status  | Budget Remaining |
+------------------------+-----------------+--------+--------+-------------+---------+------------------+
| frontend-availability  | web-frontend    | 30d    | 99.9%  | 99.95%      | ✓ PASS  | 50.0%            |
| frontend-availability  | web-frontend    | 7d     | 99.5%  | 99.97%      | ✓ PASS  | 90.6%            |
| checkout-latency       | checkout-api    | 7d     | 99.5%  | 99.8%       | ✓ PASS  | 40.0%            |
| order-processing       | order-processor | 30d    | 99.99% | 99.98%      | ✗ FAIL  | -100.0%          |
+------------------------+-----------------+--------+--------+-------------+---------+------------------+
```

**What they learn:**
- ✅ Frontend is healthy (50% error budget remaining)
- ✅ Checkout is healthy (40% error budget remaining)
- ⚠️ Order processing is **violating SLO** - budget exhausted!

---

### Step 4: Understanding Error Budget

When they want details on a specific service:

```bash
azure-slo-guardian budget --config slo-config.yaml --slo order-processing-success
```

**Output:**

```
+------------------------+--------+--------+-------------+---------------+-------------------+-----------+------------+
| SLO                    | Window | Target | Current SLI | Budget Total  | Budget Remaining  | Consumed  | Status     |
+------------------------+--------+--------+-------------+---------------+-------------------+-----------+------------+
| order-processing       | 30d    | 99.99% | 99.98%      | 0.01%         | -0.01%            | 200%      | EXHAUSTED  |
+------------------------+--------+--------+-------------+---------------+-------------------+-----------+------------+
```

**Translation:**
- They promised 99.99% success rate (only 0.01% allowed failures)
- Currently at 99.98% (0.02% failure rate)
- They've consumed **200% of their error budget** (2x what they promised)
- **Action needed**: Stop new deployments, focus on reliability!

---

### Step 5: Burn-Rate Alerts - Catch Problems Early

Azure SLO Guardian monitors if error budget is being consumed too **fast**:

```bash
azure-slo-guardian alert --config slo-config.yaml
```

**Scenario: Sudden spike in checkout failures**

```
+------------------------+--------------+-------------+------------+------------+--------+----------+-----------+
| SLO                    | Short Window | Long Window | Short SLI  | Long SLI   | Target | Severity | Status    |
+------------------------+--------------+-------------+------------+------------+--------+----------+-----------+
| frontend-availability  | 5m           | 1h          | 99.95%     | 99.95%     | 99.9%  | WARNING  | OK        |
| checkout-latency       | 5m           | 1h          | 98.5%      | 99.2%      | 99.5%  | CRITICAL | ALERTING  |
| order-processing       | 30m          | 6h          | 99.99%     | 99.99%     | 99.99% | WARNING  | OK        |
+------------------------+--------------+-------------+------------+------------+--------+----------+-----------+

Active Alerts:
  • SLO 'checkout-latency' is burning error budget at 2.0% rate. 
    Short window (5m) SLI: 98.50%, Long window (1h) SLI: 99.20%, Target: 99.5%
```

**What happened:**
- In the last **5 minutes**, checkout is only at 98.5% (well below 99.5% target)
- In the last **1 hour**, it's at 99.2% (still below target)
- **This is a FAST burn** - they're consuming error budget rapidly
- **Action**: Page on-call engineer immediately!

---

### Step 6: CI/CD Integration - Prevent Bad Deployments

CloudMart adds Azure SLO Guardian to their deployment pipeline:

**.github/workflows/deploy.yml**
```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  check-slo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install Azure SLO Guardian
        run: pip install azure-slo-guardian
      
      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      
      - name: Check SLO Status
        id: slo_check
        run: |
          azure-slo-guardian check --config slo-config.yaml --format json > slo-status.json
          
          # Exit 1 if any SLO is violated (budget exhausted)
          azure-slo-guardian check --config slo-config.yaml
      
      - name: Block Deployment if SLO Violated
        if: failure()
        run: |
          echo "::error::Cannot deploy - SLO is currently violated"
          echo "Error budget is exhausted. Fix reliability issues before deploying new features."
          exit 1
  
  deploy:
    needs: check-slo
    runs-on: ubuntu-latest
    steps:
      - name: Deploy Application
        run: ./deploy.sh
```

**What happens:**

1. **Developer pushes code** to deploy new feature
2. **GitHub Actions triggers**
3. **Azure SLO Guardian checks** current SLO status
4. If **error budget exhausted** → ❌ **Deployment BLOCKED**
5. If **error budget healthy** → ✅ **Deployment proceeds**

**Real scenario:**
```
❌ Deployment Failed!

Cannot deploy - SLO is currently violated
Error budget is exhausted. Fix reliability issues before deploying new features.

Current Status:
  order-processing-success: FAIL (budget: -100%)
  
Action Required:
  1. Investigate why order processing is failing
  2. Fix the reliability issue
  3. Wait for error budget to recover
  4. Then try deploying again
```

---

### Step 7: Automated Daily Reports

CloudMart sets up a scheduled check:

**.github/workflows/slo-report.yml**
```yaml
name: Daily SLO Report

on:
  schedule:
    - cron: '0 9 * * *'  # 9 AM daily

jobs:
  slo-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Generate SLO Report
        run: |
          azure-slo-guardian check --config slo-config.yaml --format json > daily-slo-report.json
      
      - name: Upload Report
        uses: actions/upload-artifact@v3
        with:
          name: slo-report-${{ github.run_number }}
          path: daily-slo-report.json
      
      # Optional: Send to Slack, Teams, email, etc.
      - name: Notify Team
        run: |
          # Send report to Slack channel
          ./scripts/post-to-slack.sh daily-slo-report.json
```

Every morning, the team sees:
- Current SLO compliance status
- Error budget remaining for each service
- Trends over time

---

## Behind the Scenes: What's Actually Happening

### When They Run `azure-slo-guardian check`:

1. **Reads configuration** from `slo-config.yaml`
2. **Authenticates to Azure** using Azure CLI credentials or service principal
3. **For each SLO**, it:
   - Calculates the time window (e.g., "last 30 days")
   - **Executes KQL queries** against Application Insights / Log Analytics
   - For availability SLO: Runs `good_query` and `total_query`
   - For latency SLO: Runs `query` and checks against threshold
4. **Calculates SLI** (Service Level Indicator):
   - Availability: `good_events / total_events * 100`
   - Latency: `1 if p95 <= threshold else 0`
5. **Calculates Error Budget**:
   - Total budget: `100% - target%` (e.g., 100% - 99.9% = 0.1%)
   - Current error: `100% - current_SLI%`
   - Remaining: `total_budget - current_error`
   - Consumed %: `(current_error / total_budget) * 100`
6. **Displays results** in table/JSON/YAML format
7. **Returns exit code**:
   - `0` = All SLOs met
   - `1` = One or more SLOs violated (useful for CI/CD)

### When They Run `azure-slo-guardian alert`:

1. **For each SLO with alerting enabled**:
2. **Calculates SLI for multiple windows** (e.g., last 5 minutes AND last 1 hour)
3. **Checks burn rate**: Are both windows below acceptable levels?
4. **Multi-window approach catches**:
   - **Fast burns**: Short window degraded (acute problem)
   - **Slow burns**: Long window degraded (chronic problem)
   - **No alert if only one window**: Avoids false positives
5. **Returns results** with severity levels

---

## Real-World Impact at CloudMart

### Before Azure SLO Guardian:
- ❌ Deployed new feature during existing outage → made it worse
- ❌ Didn't realize order processing was slowly degrading
- ❌ No clear definition of "acceptable reliability"
- ❌ Manual dashboard checking (someone had to remember)

### After Azure SLO Guardian:
- ✅ **Deployments auto-blocked** when reliability poor
- ✅ **Burn-rate alerts** catch problems in minutes, not hours
- ✅ **Clear reliability targets** everyone understands
- ✅ **Automated daily checks** in CI/CD pipeline
- ✅ **Data-driven decisions**: "We have 50% error budget, safe to deploy"
- ✅ **Quarterly reports** show reliability trends for executives

---

## Different Teams Use It Differently

### SRE Team:
```bash
# Check overall health
azure-slo-guardian check --config slo-config.yaml

# Deep dive on specific service
azure-slo-guardian budget --config slo-config.yaml --slo checkout-latency --verbose

# Monitor burn rates
azure-slo-guardian alert --config slo-config.yaml
```

### DevOps/Platform Team:
```bash
# Validate config changes before merging
azure-slo-guardian validate --config slo-config.yaml

# CI/CD pipeline integration
azure-slo-guardian check --config slo-config.yaml --format json | jq '.[] | select(.is_meeting_slo == false)'
```

### Engineering Managers:
```bash
# Weekly status report
azure-slo-guardian check --config slo-config.yaml --format json > weekly-report.json

# Track error budget consumption trends
cat weekly-report.json | jq '.[] | {slo: .slo_name, budget_remaining: .error_budget.error_budget_remaining}'
```

---

## The Flow: From Problem to Resolution

1. **🔔 Alert fires**: "checkout-latency is burning error budget fast"
2. **👤 On-call engineer investigates**: What changed recently?
3. **📊 Checks Azure SLO Guardian**: `azure-slo-guardian budget --slo checkout-latency`
   - Sees: 80% of error budget consumed in last hour
4. **🔍 Uses the KQL query** from config to investigate in Azure Portal
5. **🛠️ Fixes the issue** (e.g., scales up database)
6. **✅ Verifies recovery**: `azure-slo-guardian check --slo checkout-latency`
   - Sees: SLI back above target, budget recovering
7. **📝 Post-incident**: Updates SLO config if needed

---

## Summary: The Value Proposition

**Without Azure SLO Guardian:**
- Manual dashboard monitoring
- Unclear reliability targets
- Reactive to outages
- No objective deployment criteria
- Difficult to track error budgets

**With Azure SLO Guardian:**
- ✅ **Automated monitoring** via CI/CD
- ✅ **Clear, measurable** reliability targets
- ✅ **Proactive alerting** before SLO violation
- ✅ **Deployment gating** based on error budget
- ✅ **Easy tracking** of reliability over time
- ✅ **Data-driven** reliability decisions
- ✅ **Version-controlled** SLO definitions

It transforms reliability from a vague goal into a measurable, trackable, enforceable practice.

# Azure SLO Guardian - Technical Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User / CI/CD Pipeline                        │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ CLI Commands
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Azure SLO Guardian                            │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │   CLI        │  │   Config     │  │  SLO Calc    │             │
│  │  (Click)     │─▶│  (Pydantic)  │─▶│  (Core Logic)│             │
│  └──────────────┘  └──────────────┘  └──────┬───────┘             │
│                                               │                      │
│                                               ▼                      │
│  ┌──────────────────────────────────────────────────────┐          │
│  │           Query Engine (Azure SDK)                    │          │
│  │  • Authenticates with Azure                          │          │
│  │  • Executes KQL queries                              │          │
│  │  • Returns metrics                                   │          │
│  └──────────────────────┬───────────────────────────────┘          │
│                         │                                            │
└─────────────────────────┼────────────────────────────────────────────┘
                          │
                          │ HTTPS / Azure SDK
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Azure Cloud                                   │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  Application     │  │  Log Analytics   │  │  Azure Monitor   │ │
│  │  Insights        │  │  Workspace       │  │  Metrics         │ │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘ │
│           │                      │                      │            │
│           └──────────────────────┴──────────────────────┘            │
│                              │                                       │
│                         (KQL Queries)                                │
│                              │                                       │
│  ┌────────────────────────────────────────────────────────────────┐│
│  │              Actual Application Telemetry                       ││
│  │  • HTTP requests (success/failure, duration)                   ││
│  │  • Custom events and logs                                      ││
│  │  • Performance counters                                        ││
│  └────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. CLI Layer (`cli.py`)

**Responsibility**: User interaction

```python
# Commands available:
azure-slo-guardian validate --config slo.yaml    # Validate config
azure-slo-guardian check --config slo.yaml       # Check SLO status
azure-slo-guardian budget --config slo.yaml      # View error budgets
azure-slo-guardian alert --config slo.yaml       # Check burn-rate alerts
```

**Flow:**
1. Parse command-line arguments (using Click)
2. Load configuration file
3. Call appropriate business logic
4. Format and display results
5. Return exit code for CI/CD

---

### 2. Configuration Layer (`config.py`)

**Responsibility**: Parse, validate, and model SLO definitions

```python
# Pydantic models ensure type safety and validation

SLOConfig
  └── List[SLO]
       ├── name: str
       ├── service: str
       ├── sli: SLIConfig
       │    ├── type: availability | latency | custom
       │    ├── query_type: application_insights | log_analytics | azure_monitor
       │    ├── workspace_id: str
       │    ├── good_query: str (for ratio-based)
       │    ├── total_query: str (for ratio-based)
       │    └── query: str (for threshold-based)
       ├── objectives: List[Objective]
       │    ├── target: float (e.g., 99.9)
       │    └── window: str (e.g., "30d")
       └── alerting: AlertingConfig (optional)
            └── windows: List[BurnRateWindow]
```

**Validation Examples:**
- ✅ Target must be 0-100
- ✅ Window must be valid duration (5m, 1h, 7d, 30d)
- ✅ Availability SLI must have both good_query and total_query
- ✅ Latency SLI must have query, threshold, and operator
- ✅ SLO names must be unique
- ✅ Environment variables expanded (${VAR_NAME})

---

### 3. Query Engine (`query_engine.py`)

**Responsibility**: Execute KQL queries against Azure

```python
class AzureQueryEngine:
    def __init__(self):
        # Uses DefaultAzureCredential (supports multiple auth methods)
        self.credential = DefaultAzureCredential()
        self.logs_client = LogsQueryClient(self.credential)
    
    def execute_query(self, sli_config, query, start_time, end_time):
        # Execute KQL query
        # Return QueryResult with metrics
```

**Authentication Methods Supported:**
1. **Azure CLI**: User already logged in with `az login`
2. **Managed Identity**: When running in Azure (AKS, VMs, Functions)
3. **Service Principal**: Environment variables set
4. **Visual Studio Code**: Logged in via VS Code
5. **Azure PowerShell**: Logged in via PowerShell

**Query Execution:**
```python
# Example: Availability SLI
good_result = execute_query(
    workspace_id="abc123",
    query="requests | where success == true | count",
    start_time=datetime.now() - timedelta(days=30),
    end_time=datetime.now()
)
# Returns: {'count': 999500}

total_result = execute_query(
    workspace_id="abc123",
    query="requests | count",
    start_time=datetime.now() - timedelta(days=30),
    end_time=datetime.now()
)
# Returns: {'count': 1000000}

# Calculate SLI: 999500 / 1000000 * 100 = 99.95%
```

---

### 4. SLO Calculator (`slo_calculator.py`)

**Responsibility**: Calculate SLI, error budgets, and compliance

```python
class SLOCalculator:
    def calculate_slo(self, slo, objective, end_time):
        # 1. Calculate time window
        window_delta = parse_duration(objective.window)  # e.g., 30 days
        start_time = end_time - window_delta
        
        # 2. Execute queries to get metrics
        if slo.sli.type == "availability":
            good_count, total_count = query_engine.execute_ratio_queries(...)
            current_sli = (good_count / total_count) * 100
        
        # 3. Calculate error budget
        error_budget = self._calculate_error_budget(
            target=objective.target,     # e.g., 99.9
            current_sli=current_sli      # e.g., 99.95
        )
        
        # 4. Return status
        return SLOStatus(
            current_sli=99.95,
            is_meeting_slo=True,
            error_budget=error_budget
        )
```

**Error Budget Math:**
```python
# Example: Target 99.9% availability over 30 days

Target:              99.9%
Total Error Budget:   0.1%  (100% - 99.9%)

# Scenario 1: Currently at 99.95%
Current Error:        0.05% (100% - 99.95%)
Remaining Budget:     0.05% (0.1% - 0.05%)
Consumed:            50.0%  (0.05 / 0.1 * 100)
Status:              ✅ OK

# Scenario 2: Currently at 99.85%
Current Error:        0.15% (100% - 99.85%)
Remaining Budget:    -0.05% (0.1% - 0.15%)
Consumed:           150.0%  (0.15 / 0.1 * 100)
Status:              ❌ EXHAUSTED

# In time-based terms for 30 days:
30 days = 43,200 minutes
0.1% error budget = 43.2 minutes of downtime allowed
At 99.95%: Used 21.6 minutes (50% of budget)
At 99.85%: Used 64.8 minutes (150% of budget - OVER!)
```

---

### 5. Burn-Rate Calculator (`burn_rate.py`)

**Responsibility**: Detect fast consumption of error budget

**Why Burn-Rate Matters:**

Imagine two scenarios with 99.9% SLO over 30 days (0.1% error budget = 43.2 minutes):

**Scenario A: Slow burn**
- Day 1-29: 100% availability (perfect)
- Day 30: 50% availability (12 hours down)
- Monthly SLI: ~98.3% → ❌ SLO violated

**Scenario B: Fast burn**
- Days 1-5: 100% availability
- Day 6, Hour 1: Complete outage (1 hour down)
- Days 7-30: 100% availability
- Monthly SLI: 99.86% → ✅ Still meeting SLO!

**Problem:** Without burn-rate alerting, both look the same in the moment!

**Solution: Multi-Window Burn-Rate**

```python
# Check TWO time windows simultaneously
short_window = last_5_minutes   # Catch FAST problems
long_window = last_1_hour        # Confirm it's sustained

# Alert only if BOTH windows are bad
if short_window_sli < threshold AND long_window_sli < threshold:
    ALERT("Burning error budget rapidly!")
```

**Example Configuration:**
```yaml
alerting:
  windows:
    # Fast burn: 2% of monthly budget in 1 hour
    - consume_budget: 2.0      # 2% of 0.1% = 0.002% error
      short_window: 5m         # Check last 5 minutes
      long_window: 1h          # Check last 1 hour
    
    # Slow burn: 5% of monthly budget in 6 hours  
    - consume_budget: 5.0      # 5% of 0.1% = 0.005% error
      short_window: 30m        # Check last 30 minutes
      long_window: 6h          # Check last 6 hours
```

**How It Works:**
```python
# For a 99.9% SLO over 30 days:
error_budget = 0.1%
monthly_window = 30 days = 43,200 minutes

# Window 1: consume_budget=2%, short=5m, long=1h
# Acceptable error in 1 hour = (0.1% * 0.02) * (60min / 43,200min) = 0.0000277%
# If short (5m) AND long (1h) both exceed this → ALERT

# This catches:
# ✓ Sudden spikes (short window)
# ✗ Brief blips that self-recover (only short window bad)
# ✓ Sustained problems (both windows bad)
```

---

## Data Flow Example

### Complete Flow: Check Frontend Availability

```
1. User runs:
   $ azure-slo-guardian check --config slo.yaml

2. CLI loads config:
   - Reads slo.yaml
   - Pydantic validates structure
   - Creates SLOConfig object with:
     * SLO: frontend-availability
     * Target: 99.9% over 30 days
     * Query: Application Insights

3. Calculator determines time range:
   - end_time = now()              # 2026-03-21 08:00:00
   - window = 30 days
   - start_time = now() - 30 days  # 2026-02-19 08:00:00

4. Query Engine executes KQL:
   
   Query 1 (good):
   ┌──────────────────────────────────────┐
   │ requests                             │
   │ | where timestamp >= datetime(...)   │
   │ | where timestamp <= datetime(...)   │
   │ | where success == true              │
   │ | where resultCode < 500             │
   │ | count                              │
   └──────────────────────────────────────┘
            ↓
   Application Insights API
            ↓
   Result: {"count": 999,500}
   
   Query 2 (total):
   ┌──────────────────────────────────────┐
   │ requests                             │
   │ | where timestamp >= datetime(...)   │
   │ | where timestamp <= datetime(...)   │
   │ | count                              │
   └──────────────────────────────────────┘
            ↓
   Application Insights API
            ↓
   Result: {"count": 1,000,000}

5. Calculator computes SLI:
   current_sli = (999,500 / 1,000,000) * 100 = 99.95%

6. Calculator computes error budget:
   target = 99.9%
   error_budget_total = 100% - 99.9% = 0.1%
   current_error = 100% - 99.95% = 0.05%
   remaining = 0.1% - 0.05% = 0.05%
   consumed_pct = (0.05% / 0.1%) * 100 = 50%

7. CLI formats output:
   ┌────────────┬─────────┬────────┬────────┬─────────┬────────┬──────────┐
   │ SLO        │ Service │ Window │ Target │ Current │ Status │ Budget   │
   ├────────────┼─────────┼────────┼────────┼─────────┼────────┼──────────┤
   │ frontend-  │ web-    │ 30d    │ 99.9%  │ 99.95%  │ ✓ PASS │ 50.0%    │
   │ availability│ frontend│        │        │         │        │          │
   └────────────┴─────────┴────────┴────────┴─────────┴────────┴──────────┘

8. CLI returns exit code:
   exit 0  (success - all SLOs met)
```

---

## Scalability & Performance

### Query Optimization
- **Single query per metric**: Doesn't spam Azure APIs
- **Configurable time windows**: Only query what you need
- **Batch processing**: Multiple SLOs processed efficiently

### Caching (Future Enhancement)
```python
# Could add caching to avoid repeated queries
@cache(ttl=300)  # Cache for 5 minutes
def get_sli_for_window(slo, window):
    # Query Azure
    pass
```

### Parallel Execution (Future Enhancement)
```python
# Could parallelize multiple SLO checks
with ThreadPoolExecutor() as executor:
    results = executor.map(calculate_slo, slos)
```

---

## Security Considerations

### Credentials
- ✅ **Never stores credentials** in config files
- ✅ Uses **Azure SDK authentication** (follows Azure best practices)
- ✅ Supports **Managed Identity** for zero-credential scenarios
- ✅ **Workspace IDs** are not sensitive (can be in config)

### Permissions Required
```
Azure RBAC roles needed:
- "Monitoring Reader" on Application Insights
- "Log Analytics Reader" on Log Analytics Workspace
- Or custom role with permissions:
  * Microsoft.Insights/components/read
  * Microsoft.Insights/components/query/read
  * Microsoft.OperationalInsights/workspaces/read
  * Microsoft.OperationalInsights/workspaces/query/read
```

---

## Extensibility Points

### 1. Custom SLI Types
```python
# Add new SLI type in config.py
class SLIType(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    CUSTOM = "custom"
    THROUGHPUT = "throughput"  # NEW!

# Implement in slo_calculator.py
def _calculate_throughput_sli(self, slo, start_time, end_time):
    # Custom logic
    pass
```

### 2. New Query Backends
```python
# Add in query_engine.py
class QueryType(str, Enum):
    APPLICATION_INSIGHTS = "application_insights"
    LOG_ANALYTICS = "log_analytics"
    AZURE_MONITOR = "azure_monitor"
    PROMETHEUS = "prometheus"  # NEW!

def execute_prometheus_query(self, query, start, end):
    # Integration with Prometheus
    pass
```

### 3. Export Formats
```python
# exporters/grafana.py
def export_to_grafana(slos):
    # Generate Grafana dashboard JSON
    pass

# exporters/bicep.py
def export_to_bicep(slos):
    # Generate Azure Monitor alert rules
    pass
```

### 4. Notification Channels
```python
# notifiers/teams.py
def send_teams_notification(alert):
    # Post to Microsoft Teams webhook
    pass

# notifiers/pagerduty.py
def trigger_pagerduty(alert):
    # Create PagerDuty incident
    pass
```

---

## Error Handling Strategy

```python
# Graceful degradation at each layer

# 1. Config validation errors
try:
    config = load_config("slo.yaml")
except ValidationError as e:
    print(f"Configuration error: {e}")
    exit(1)

# 2. Azure authentication errors
try:
    credential = DefaultAzureCredential()
except CredentialUnavailableError:
    print("Cannot authenticate to Azure. Run 'az login'")
    exit(1)

# 3. Query execution errors
try:
    result = query_engine.execute_query(...)
except AzureError as e:
    print(f"Query failed: {e}")
    # Return error status, don't crash
    return SLOStatus(error=str(e))

# 4. Partial failures
# If one SLO check fails, continue checking others
for slo in slos:
    try:
        status = calculate_slo(slo)
        results.append(status)
    except Exception as e:
        results.append(SLOStatus(slo=slo, error=str(e)))
```

---

## Summary

Azure SLO Guardian is a **layered architecture** that:

1. **Accepts** user-friendly YAML configuration
2. **Validates** configuration with type safety
3. **Authenticates** securely to Azure
4. **Executes** KQL queries against real telemetry
5. **Calculates** SLI and error budgets using SRE math
6. **Detects** fast budget consumption via burn-rates
7. **Reports** in multiple formats (table/JSON/YAML)
8. **Integrates** with CI/CD via exit codes

All while being **extensible**, **secure**, and **production-ready**.

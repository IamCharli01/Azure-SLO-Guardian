# Podcast Talking Points — SLOs, SLIs & Burn Rates

## Opening: Why Should Anyone Care About SLOs?

- Every team says "we want 100% uptime" — that's not realistic and it's not even desirable
- Google's SRE team figured out: **the question isn't "is my app up?" — it's "are my users happy enough?"**
- SLOs give you a **data-driven way to answer that question** and make decisions about when to ship vs when to fix

---

## The Big Three: SLI → SLO → Error Budget

### SLI (Service Level Indicator) — "What are we measuring?"

- A **specific metric** that tells you how your service is performing from the user's perspective
- Examples:
  - **Availability**: "What percentage of requests returned a non-5xx response?"
  - **Latency**: "What percentage of requests completed in under 500ms?"
  - **Correctness**: "What percentage of API calls returned the right answer?"
- Keep it simple — you want 2-4 SLIs per service, not 50 dashboards nobody looks at
- The key insight: **SLIs should measure what the user experiences, not what the server reports**

### SLO (Service Level Objective) — "What's good enough?"

- A **target** you set against your SLI
- Example: "99.9% of requests should succeed over a 30-day rolling window"
- 99.9% sounds high, but that's still **43 minutes of allowed downtime per month**
- The SLO is a **decision-making tool**:
  - Meeting SLO? → Ship features, move fast
  - Breaching SLO? → Stop, fix reliability first
- It's NOT a promise to customers (that's an SLA) — it's an **internal engineering target**

### Error Budget — "How much failure can we afford?"

- If your SLO is 99.9%, your error budget is **0.1%** of total requests
- Think of it like a **reliability bank account** — every outage, every slow response withdraws from it
- When budget is healthy (say 80% remaining): green light to deploy, experiment, take risks
- When budget is low (say 10% remaining): slow down, focus on stability
- When budget is exhausted: **feature freeze until reliability improves**
- This is the magic — it turns reliability from "a feeling" into "a number engineering and product can agree on"

---

## Burn Rate — "How Fast Are We Spending Our Budget?"

- Error budget tells you **how much** you've spent. Burn rate tells you **how fast**
- A burn rate of **1x** means you'll exactly exhaust your budget by end of window — that's baseline
- **5x burn rate** = you'll blow through your budget in 6 days instead of 30
- **10x burn rate** = catastrophic — budget gone in 3 days

### Multi-Window Alerting (Google SRE Workbook approach)

- Don't just alert on one window — use **fast + slow window pairs**:
  - **Fast burn (14.4x over 1hr)**: Something is on fire right now — page someone
  - **Medium burn (6x over 6hrs)**: Sustained degradation — create an urgent ticket
  - **Slow burn (1x over 3 days)**: Creeping issue — ticket for next sprint
- Why this matters: **you stop waking people up at 3am for things that can wait until morning**
- Traditional threshold alerts ("CPU > 90%") are noisy. Burn rate alerts are **tied to user impact**

---

## The Azure Angle — Why This Matters for Azure Shops

- Most Azure teams monitor with Azure Monitor, App Insights, Log Analytics — great tools
- But they're **metric tools, not SLO tools** — they tell you "CPU is at 80%" not "users are 0.2% from breaching our reliability target"
- Azure doesn't have a native SLO product (unlike Google Cloud's SLO Monitoring)
- That's the gap: **you need something that sits on top of Azure Monitor and thinks in SLOs**

### What an SLO tool does on Azure

1. Runs **KQL queries** against Log Analytics to calculate SLIs (availability, latency, error rates)
2. Compares against your **SLO targets** (99.9%, 99.5%, whatever you set)
3. Calculates **error budgets** — "you have 67% of your monthly budget remaining"
4. Calculates **burn rates** — "you're burning at 3.2x, you'll exhaust budget in 9 days"
5. Alerts through the channels your team already uses (Slack, Teams, PagerDuty)

---

## Making It Accessible — "My Devs Aren't SREs"

- Biggest barrier to SLO adoption: **the learning curve**
- Most teams don't have dedicated SRE staff — it's dev teams wearing multiple hats
- Solution: **templates and presets**
  - "I have an Azure Web App" → Here are pre-built SLIs for availability + latency with sensible defaults
  - "I have a Function App" → Here are pre-built SLIs for invocation success + error rates
  - No KQL knowledge required — the templates generate the queries
- Config-driven approach:
  ```yaml
  slos:
    - template: app-service-availability
      app_name: my-web-app
      workspace_id: abc-123
      target: 99.9
  ```
- A developer who's never heard of SLOs can have burn-rate alerting in **5 minutes**

---

## Common Pushbacks (and Responses)

| Pushback | Response |
|----------|----------|
| "We already have monitoring" | Monitoring tells you something is broken. SLOs tell you **if users care** that it's broken. A background job failing at 2am might not matter. |
| "We can't agree on a target" | Start with **99.5%** — it's deliberately generous. You can tighten it later. The act of picking a number is more valuable than the number itself. |
| "Leadership wants 99.99%" | Do the math: 99.99% = **4.3 minutes of downtime per month**. Are they willing to invest in the infrastructure and on-call that requires? Usually not. |
| "This feels like overhead" | SLOs **reduce** overhead — fewer false alerts, clearer priorities, less "is this actually a problem?" meetings |
| "We're too small for this" | If you have users and you deploy code, you need SLOs. A 3-person team benefits just as much. |

---

## Quotable Sound Bites

- "An SLO is a contract between your team and reality"
- "Error budgets turn the reliability conversation from a feelings debate into a math problem"
- "If you're not measuring from the user's perspective, you're measuring the wrong thing"
- "The goal isn't 100% uptime — the goal is **happy enough users while still shipping features**"
- "Burn rate alerts let you sleep through the noise and wake up for the fires"
- "You don't need to be Google to do SLOs — you just need a config file and a target"

---

## Flow for the Conversation

1. **Hook**: "Every team monitors uptime, but almost nobody can answer: how much unreliability can we actually afford this month?"
2. **Problem**: Traditional monitoring is noisy, metric-focused, disconnected from user impact
3. **Concept**: SLI → SLO → Error Budget → Burn Rate (build up the stack)
4. **Azure context**: Gap in the Azure ecosystem — no native SLO tooling
5. **Demo-ready**: Show a simple config file → "this is all a dev team needs to set up"
6. **Close**: SLOs aren't just for Google-scale — they're a decision-making framework that works at any size

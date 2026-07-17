# API Log Analyser & Automated Alert System

A production-style API monitoring tool that simulates a real Support Engineer workflow — parsing logs, detecting anomalies, firing alerts, running recovery scripts, and displaying a live dashboard.

---

## Features

- Parses JSON HTTP API logs to detect 4xx/5xx error spikes
- Stores structured events in SQLite for querying and analysis
- Evaluates threshold-based alert rules (5xx error rate + avg latency)
- Fires automated alerts with endpoint details (Slack/email simulated via webhook)
- Runs service-recovery scripts and logs resolution timestamps
- Exposes `/metrics` endpoint in Prometheus format (port 8000)
- Auto-updates every 30 seconds with fresh logs and re-evaluated alerts
- Generates a clean HTML dashboard with status distribution, endpoint performance, and full alert log

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| Data Storage | SQLite, JSON |
| Querying | SQL |
| Metrics | Prometheus-format /metrics endpoint |
| Scheduling | schedule library |
| Dashboard | HTML / CSS |
| Alerting | Webhook (Slack/Email simulated) |

---

## Run

```bash
pip install schedule
python log_analyser.py
```

- Open `dashboard.html` in your browser
- Visit `http://localhost:8000/metrics` for Prometheus metrics
- Dashboard auto-refreshes every 30 seconds

---

## How It Works

```
JSON Logs Generated
       ↓
Parse & Store in SQLite
       ↓
Analyse per Endpoint (5xx count, avg latency)
       ↓
Evaluate Alert Thresholds
       ↓
🚨 Alert Fired (HIGH_5XX_RATE / HIGH_LATENCY)
       ↓
🔧 Recovery Script Runs (restart → health check → log resolution)
       ↓
📊 Dashboard Updated + /metrics Exposed
       ↓
🔄 Repeat every 30 seconds
```

---

## Alert Rules

| Alert Type | Condition |
|---|---|
| `HIGH_5XX_RATE` | 5xx errors on an endpoint exceed threshold (default: 5) |
| `HIGH_LATENCY` | Average response time exceeds threshold (default: 700ms) |

---

## Project Structure

```
api-log-analyser/
├── log_analyser.py    # main script — all logic
├── api_logs.json      # generated JSON log data
├── api_logs.db        # SQLite database (events + alert log)
├── dashboard.html     # live monitoring dashboard
└── README.md
```

---

## Sample Dashboard

The HTML dashboard shows:
- **Total requests, 5xx errors, alerts fired, alerts resolved** — summary cards
- **HTTP Status Distribution** — breakdown of 2xx / 4xx / 5xx counts
- **Endpoint Performance** — avg latency, error count, error rate, health status per endpoint
- **Alert Log** — every alert with type, endpoint, detail, resolution time, and action taken

---

## Relevance

This project directly mirrors the IDfy Support Engineer workflow:
- Defining monitoring events and setting up alerts
- Triaging and investigating 4xx/5xx error spikes
- Running service recovery scripts
- Creating analytical dashboards for service performance
- Exposing Prometheus metrics for Grafana integration

---

## Author

**Svara Chheda**  
B.Tech IT (Honors – Data Science) · SAKEC, Mumbai · CGPA: 9.07  
[LinkedIn](https://linkedin.com/in/svara-chheda) · [GitHub](https://github.com/svara1410)

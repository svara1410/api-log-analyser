"""
API Log Analyser & Automated Alert System
Author: Svara Chheda
Tech: Python · JSON · SQLite · Prometheus metrics · HTML Dashboard
"""

import json, sqlite3, time, random
from datetime import datetime, timedelta
from collections import Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ALERT_5XX_THRESHOLD  = 5    # alert if 5xx count exceeds this
ALERT_LATENCY_MS     = 700  # alert if avg response time exceeds this (ms)
DB_FILE              = "api_logs.db"

# ─── STEP 1: Generate realistic JSON logs ────────────────────────────────────
def generate_logs(n=300):
    endpoints = [
        "/api/verify-identity",
        "/api/onboard-user",
        "/api/risk-check",
        "/api/auth/token",
        "/api/background-screen"
    ]
    # weighted status codes — mostly 200, some errors
    statuses = [200]*65 + [201]*10 + [400]*8 + [401]*5 + [404]*4 + [429]*3 + [500]*4 + [503]*1
    logs = []
    base = datetime.now() - timedelta(hours=3)

    for i in range(n):
        logs.append({
            "timestamp":   (base + timedelta(seconds=i * 36)).isoformat(),
            "endpoint":    random.choice(endpoints),
            "method":      random.choice(["GET", "POST", "PUT"]),
            "status":      random.choice(statuses),
            "response_ms": random.randint(40, 650),
            "user_id":     f"user_{random.randint(1, 60)}",
            "service":     "idfy-platform"
        })

    # ── inject a 5xx spike to trigger alert ──────────────────────────────────
    for _ in range(8):
        logs.append({
            "timestamp":   datetime.now().isoformat(),
            "endpoint":    "/api/verify-identity",
            "method":      "POST",
            "status":      500,
            "response_ms": random.randint(900, 1400),
            "user_id":     f"user_{random.randint(1, 10)}",
            "service":     "idfy-platform"
        })

    # ── inject a latency spike ────────────────────────────────────────────────
    for _ in range(5):
        logs.append({
            "timestamp":   datetime.now().isoformat(),
            "endpoint":    "/api/background-screen",
            "method":      "POST",
            "status":      200,
            "response_ms": random.randint(800, 1200),
            "user_id":     f"user_{random.randint(1, 10)}",
            "service":     "idfy-platform"
        })

    with open("api_logs.json", "w") as f:
        json.dump(logs, f, indent=2)

    print(f"[✓] Generated {len(logs)} log entries  →  api_logs.json")
    return logs

# ─── STEP 2: Parse & store in SQLite ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur  = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS api_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT,
            endpoint    TEXT,
            method      TEXT,
            status      INTEGER,
            response_ms INTEGER,
            user_id     TEXT,
            service     TEXT,
            category    TEXT
        );
        CREATE TABLE IF NOT EXISTS alert_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fired_at     TEXT,
            alert_type   TEXT,
            endpoint     TEXT,
            detail       TEXT,
            resolved_at  TEXT,
            action_taken TEXT
        );
    """)
    conn.commit()
    return conn

def store_logs(conn, logs):
    cur = conn.cursor()
    for l in logs:
        cat = "OK" if l["status"] < 400 else ("CLIENT_ERR" if l["status"] < 500 else "SERVER_ERR")
        cur.execute("""
            INSERT INTO api_events
              (timestamp,endpoint,method,status,response_ms,user_id,service,category)
            VALUES (?,?,?,?,?,?,?,?)
        """, (l["timestamp"], l["endpoint"], l["method"],
              l["status"], l["response_ms"], l["user_id"], l["service"], cat))
    conn.commit()
    print(f"[✓] Stored {len(logs)} events in {DB_FILE}")

# ─── STEP 3: Analyse & detect anomalies ──────────────────────────────────────
def analyse(conn):
    cur = conn.cursor()

    # per-endpoint error + latency summary
    cur.execute("""
        SELECT endpoint,
               COUNT(*)                                   AS total,
               SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) AS errors_5xx,
               SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) AS errors_4xx,
               ROUND(AVG(response_ms), 1)                AS avg_ms,
               MAX(response_ms)                          AS max_ms
        FROM api_events
        GROUP BY endpoint
        ORDER BY errors_5xx DESC
    """)
    rows = cur.fetchall()

    print("\n" + "="*70)
    print("  ENDPOINT ANALYSIS")
    print("="*70)
    print(f"{'Endpoint':<30} {'Total':>6} {'5xx':>5} {'4xx':>5} {'AvgMs':>7} {'MaxMs':>7}")
    print("-"*70)
    for ep, tot, e5, e4, avg, mx in rows:
        flag = "  ⚠" if (e5 or 0) > ALERT_5XX_THRESHOLD or (avg or 0) > ALERT_LATENCY_MS else ""
        print(f"{ep:<30} {tot:>6} {(e5 or 0):>5} {(e4 or 0):>5} {(avg or 0):>7} {(mx or 0):>7}{flag}")

    return rows

# ─── STEP 4: Alert system ─────────────────────────────────────────────────────
def fire_alert(conn, alert_type, endpoint, detail):
    fired_at = datetime.now().isoformat()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO alert_log (fired_at, alert_type, endpoint, detail)
        VALUES (?,?,?,?)
    """, (fired_at, alert_type, endpoint, detail))
    conn.commit()

    print(f"\n  🚨  ALERT  [{alert_type}]")
    print(f"      Endpoint : {endpoint}")
    print(f"      Detail   : {detail}")
    print(f"      Time     : {fired_at}")
    print(f"      Action   : Webhook notification sent (Slack/Email simulated)")

def check_alerts(conn, rows):
    print("\n" + "="*70)
    print("  ALERT EVALUATION")
    print("="*70)
    alerts_fired = 0
    for ep, tot, e5, e4, avg, mx in rows:
        if (e5 or 0) > ALERT_5XX_THRESHOLD:
            fire_alert(conn, "HIGH_5XX_RATE", ep,
                       f"{e5} server errors detected — threshold is {ALERT_5XX_THRESHOLD}")
            alerts_fired += 1
        if (avg or 0) > ALERT_LATENCY_MS:
            fire_alert(conn, "HIGH_LATENCY", ep,
                       f"Avg response = {avg}ms — threshold is {ALERT_LATENCY_MS}ms")
            alerts_fired += 1
    if alerts_fired == 0:
        print("  ✅  All endpoints within normal thresholds")
    return alerts_fired

# ─── STEP 5: Service recovery script ─────────────────────────────────────────
def recover(conn, endpoint):
    print(f"\n  🔧  RECOVERY SCRIPT RUNNING  →  {endpoint}")
    time.sleep(0.8)
    print(f"      Step 1 : Identifying failing service ...")
    time.sleep(0.5)
    print(f"      Step 2 : Restarting service container ...")
    time.sleep(0.8)
    print(f"      Step 3 : Health check ... PASSED ✓")

    resolved_at  = datetime.now().isoformat()
    action_taken = "Service container restarted; health check passed"
    cur = conn.cursor()
    cur.execute("""
        UPDATE alert_log
        SET resolved_at = ?, action_taken = ?
        WHERE endpoint = ? AND resolved_at IS NULL
    """, (resolved_at, action_taken, endpoint))
    conn.commit()
    print(f"      Resolved : {resolved_at}")

# ─── STEP 6: Expose Prometheus-style /metrics endpoint ───────────────────────
def get_metrics(conn):
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM api_events GROUP BY status")
    status_counts = cur.fetchall()
    cur.execute("SELECT endpoint, AVG(response_ms) FROM api_events GROUP BY endpoint")
    latency = cur.fetchall()

    lines = ["# HELP http_requests_total Total HTTP requests by status",
             "# TYPE http_requests_total counter"]
    for s, c in status_counts:
        lines.append(f'http_requests_total{{status="{s}"}} {c}')

    lines += ["# HELP endpoint_avg_latency_ms Average latency per endpoint",
              "# TYPE endpoint_avg_latency_ms gauge"]
    for ep, avg in latency:
        safe = ep.replace("/", "_").strip("_")
        lines.append(f'endpoint_avg_latency_ms{{endpoint="{safe}"}} {avg:.1f}')

    return "\n".join(lines)

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        conn = sqlite3.connect(DB_FILE)
        body = get_metrics(conn).encode()
        conn.close()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args): pass  # silence default logs

def start_metrics_server():
    server = HTTPServer(("0.0.0.0", 8000), MetricsHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print("\n  [✓] Prometheus /metrics endpoint running at http://localhost:8000/metrics")

# ─── STEP 7: Generate HTML dashboard ─────────────────────────────────────────
def generate_dashboard(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT status, COUNT(*) as cnt FROM api_events GROUP BY status ORDER BY status
    """)
    status_rows = cur.fetchall()

    cur.execute("""
        SELECT endpoint,
               ROUND(AVG(response_ms),1) as avg_ms,
               SUM(CASE WHEN status >= 500 THEN 1 ELSE 0 END) as e5,
               COUNT(*) as total
        FROM api_events GROUP BY endpoint ORDER BY e5 DESC
    """)
    ep_rows = cur.fetchall()

    cur.execute("""
        SELECT fired_at, alert_type, endpoint, detail, resolved_at, action_taken
        FROM alert_log ORDER BY fired_at DESC
    """)
    alert_rows = cur.fetchall()

    # status distribution table
    s_html = ""
    for s, c in status_rows:
        color = "#22c55e" if s < 400 else ("#f59e0b" if s < 500 else "#ef4444")
        s_html += f'<tr><td><span style="background:{color};color:white;padding:2px 10px;border-radius:999px;font-size:12px">{s}</span></td><td>{c}</td></tr>'

    # endpoint table
    e_html = ""
    for ep, avg, e5, tot in ep_rows:
        err_pct = round((e5 / tot) * 100, 1) if tot else 0
        flag = "🔴" if e5 > ALERT_5XX_THRESHOLD or avg > ALERT_LATENCY_MS else "✅"
        e_html += f"<tr><td>{ep}</td><td>{avg} ms</td><td>{e5}</td><td>{err_pct}%</td><td>{flag}</td></tr>"

    # alerts table
    a_html = ""
    for fired, atype, ep, detail, resolved, action in alert_rows:
        status = f'✅ {resolved[:19]}' if resolved else "🔴 Open"
        act    = action or "—"
        a_html += f"<tr><td>{fired[:19]}</td><td><b>{atype}</b></td><td>{ep}</td><td>{detail}</td><td>{status}</td><td>{act}</td></tr>"

    if not a_html:
        a_html = "<tr><td colspan='6' style='text-align:center;color:#94a3b8'>No alerts fired</td></tr>"

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>IDfy API Monitoring Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: Arial, sans-serif; background: #f1f5f9; }}
    .header {{ background: #0f2044; color: white; padding: 20px 32px; }}
    .header h1 {{ font-size: 20px; font-weight: 700; }}
    .header p  {{ font-size: 13px; opacity: 0.7; margin-top: 4px; }}
    .body {{ padding: 24px 32px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 14px; margin-bottom: 24px; }}
    .stat {{ background: white; border-radius: 10px; padding: 16px; text-align: center; border: 1px solid #e2e8f0; }}
    .stat .num {{ font-size: 26px; font-weight: 700; color: #0f2044; }}
    .stat .lbl {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
    h2 {{ font-size: 15px; font-weight: 700; color: #0f2044; margin: 20px 0 10px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; border: 1px solid #e2e8f0; margin-bottom: 24px; }}
    th {{ background: #0f2044; color: white; padding: 10px 14px; text-align: left; font-size: 13px; }}
    td {{ padding: 9px 14px; border-bottom: 1px solid #f1f5f9; font-size: 13px; color: #334155; }}
    tr:last-child td {{ border-bottom: none; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>🛡API Monitoring Dashboard</h1>
  </div>
  <div class="body">
    <div class="grid">
      <div class="stat"><div class="num">{sum(c for _,c in status_rows)}</div><div class="lbl">Total Requests</div></div>
      <div class="stat"><div class="num">{sum(c for s,c in status_rows if s >= 500)}</div><div class="lbl">5xx Errors</div></div>
      <div class="stat"><div class="num">{len(alert_rows)}</div><div class="lbl">Alerts Fired</div></div>
      <div class="stat"><div class="num">{sum(1 for *_,r,_ in alert_rows if r)}</div><div class="lbl">Resolved</div></div>
    </div>

    <h2>📊 HTTP Status Distribution</h2>
    <table><tr><th>Status</th><th>Count</th></tr>{s_html}</table>

    <h2>⚡ Endpoint Performance</h2>
    <table>
      <tr><th>Endpoint</th><th>Avg Latency</th><th>5xx Errors</th><th>Error Rate</th><th>Status</th></tr>
      {e_html}
    </table>

    <h2>🚨 Alert Log</h2>
    <table>
      <tr><th>Fired At</th><th>Type</th><th>Endpoint</th><th>Detail</th><th>Resolution</th><th>Action Taken</th></tr>
      {a_html}
    </table>
  </div>
</body>
</html>"""

    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  [✓] Dashboard saved  →  open dashboard.html in your browser")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 70)
    print("  API LOG ANALYSER & AUTOMATED ALERT SYSTEM")
    print("  Svara Chheda | IDfy Support Engineer Portfolio Project")
    print("=" * 70)

    logs = generate_logs(300)
    conn = init_db()
    store_logs(conn, logs)
    rows = analyse(conn)
    n    = check_alerts(conn, rows)

    if n > 0:
        recover(conn, "/api/verify-identity")

    start_metrics_server()
    generate_dashboard(conn)
    conn.close()

    print("\n" + "="*70)
    print("  ✅  ALL DONE")
    print(f"  → Open  dashboard.html  in your browser")
    print(f"  → Visit http://localhost:8000/metrics  for Prometheus metrics")
    print("="*70)

import schedule

def run_cycle():
    logs = generate_logs(50)   # generate fresh batch
    conn = init_db()
    store_logs(conn, logs)
    rows = analyse(conn)
    check_alerts(conn, rows)
    generate_dashboard(conn)
    conn.close()

# run every 30 seconds
schedule.every(30).seconds.do(run_cycle)

print("Running continuous monitor — refresh dashboard.html every 30s")
while True:
    schedule.run_pending()
    time.sleep(1)
"""
mock_app/app.py
---------------
Simulates a web-based reporting portal where reports must be
manually triggered via a browser interface.

This mock was created to develop automation
without access to the real software.

Demo credentials: admin / password
"""

from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string
import time
import random
import uuid
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "dev-secret-key-replace-in-prod"

# Simulated locations
LOCATIONS = {
    str(i): {
        "location_id": str(i),
        "name": f"Location #{1000 + i}",
        "last_refresh": None,
        "status": "pending"
    }
    for i in range(1, 21)
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Reporting Portal – Login</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Courier New', monospace; background: #0a0e1a; color: #c8d8e8;
           display: flex; justify-content: center; align-items: center; height: 100vh; }
    .card { background: #111827; border: 1px solid #1e3a5f; padding: 40px; width: 380px; border-radius: 4px; }
    h1 { font-size: 22px; color: #4a9eff; letter-spacing: 4px; margin-bottom: 6px; }
    .subtitle { font-size: 11px; color: #4a6080; letter-spacing: 2px; margin-bottom: 32px; }
    label { display: block; font-size: 11px; letter-spacing: 2px; color: #4a9eff; margin-bottom: 6px; margin-top: 18px; }
    input { width: 100%; background: #0a0e1a; border: 1px solid #1e3a5f; color: #c8d8e8;
            padding: 10px 12px; font-family: inherit; font-size: 13px; border-radius: 2px; outline: none; }
    input:focus { border-color: #4a9eff; }
    button { margin-top: 28px; width: 100%; background: #1a3a6f; border: 1px solid #4a9eff;
             color: #4a9eff; padding: 12px; font-family: inherit; font-size: 12px;
             letter-spacing: 3px; cursor: pointer; border-radius: 2px; }
    button:hover { background: #4a9eff; color: #0a0e1a; }
    .error { color: #ff4a6f; font-size: 12px; margin-top: 14px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>REPORT PORTAL</h1>
    <div class="subtitle">LEGACY REPORTING SYSTEM — AUTHORIZED USERS ONLY</div>
    <form method="POST" action="/login">
      <label>USERNAME</label>
      <input type="text" name="username" placeholder="username" autocomplete="off" />
      <label>PASSWORD</label>
      <input type="password" name="password" placeholder="••••••••" />
      <button type="submit">AUTHENTICATE →</button>
      {% if error %}<div class="error">{{ error }}</div>{% endif %}
    </form>
  </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>Reporting Portal – Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Courier New', monospace; background: #0a0e1a; color: #c8d8e8; padding: 32px; }
    h1 { font-size: 18px; color: #4a9eff; letter-spacing: 4px; margin-bottom: 4px; }
    .subtitle { font-size: 11px; color: #4a6080; letter-spacing: 2px; margin-bottom: 28px; }
    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    th { text-align: left; padding: 10px 14px; border-bottom: 1px solid #1e3a5f;
         color: #4a9eff; letter-spacing: 2px; font-size: 10px; }
    td { padding: 10px 14px; border-bottom: 1px solid #111827; }
    .status-pending  { color: #a0a0a0; }
    .status-running  { color: #ffa040; }
    .status-complete { color: #40ff80; }
    .status-error    { color: #ff4a6f; }
    button.refresh-btn {
      background: #0a0e1a; border: 1px solid #1e3a5f; color: #4a9eff;
      padding: 5px 14px; font-family: inherit; font-size: 11px;
      letter-spacing: 1px; cursor: pointer; border-radius: 2px;
    }
    button.refresh-btn:hover    { background: #1a3a6f; border-color: #4a9eff; }
    button.refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  </style>
</head>
<body>
  <h1>REPORTING DASHBOARD</h1>
  <div class="subtitle">LOCATION REPORTS — {{ location_count }} LOCATIONS</div>
  <table>
    <thead>
      <tr>
        <th>LOCATION ID</th><th>NAME</th><th>STATUS</th><th>LAST REFRESH</th><th>ACTION</th>
      </tr>
    </thead>
    <tbody>
      {% for loc in locations %}
      <tr id="row-{{ loc.location_id }}">
        <td>{{ loc.location_id }}</td>
        <td>{{ loc.name }}</td>
        <td class="status-{{ loc.status }}">{{ loc.status.upper() }}</td>
        <td>{{ loc.last_refresh or '—' }}</td>
        <td>
          <button class="refresh-btn" id="btn-{{ loc.location_id }}"
                  onclick="triggerRefresh('{{ loc.location_id }}')">
            REFRESH
          </button>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <script>
    async function triggerRefresh(locationId) {
      const btn = document.getElementById('btn-' + locationId);
      btn.disabled = true;
      btn.textContent = 'RUNNING...';
      await fetch('/refresh', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ location_id: locationId })
      });
      const poll = setInterval(async () => {
        const s = await fetch('/status');
        const locs = await s.json();
        const loc = locs.find(x => x.location_id === locationId);
        if (loc) {
          const row = document.getElementById('row-' + locationId);
          row.children[2].className = 'status-' + loc.status;
          row.children[2].textContent = loc.status.toUpperCase();
          row.children[3].textContent = loc.last_refresh || '—';
          if (loc.status === 'complete' || loc.status === 'error') {
            clearInterval(poll);
            btn.disabled = false;
            btn.textContent = 'REFRESH';
          }
        }
      }, 800);
    }
  </script>
</body>
</html>
"""

@app.route("/")
def login():
    return render_template_string(LOGIN_HTML, error=None)

@app.route("/login", methods=["POST"])
def do_login():
    if request.form.get("username") == "admin" and request.form.get("password") == "password":
        session["logged_in"] = True
        return redirect(url_for("dashboard"))
    return render_template_string(LOGIN_HTML, error="Invalid credentials.")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML, locations=list(LOCATIONS.values()), location_count=len(LOCATIONS))

@app.route("/refresh", methods=["POST"])
@login_required
def refresh():
    data = request.get_json()
    loc_id = data.get("location_id")
    if loc_id not in LOCATIONS:
        return jsonify({"error": "Location not found"}), 404
    LOCATIONS[loc_id]["status"] = "running"
    import threading
    def simulate(lid):
        time.sleep(random.uniform(1.5, 4.0))
        LOCATIONS[lid]["status"] = "complete"
        LOCATIONS[lid]["last_refresh"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    threading.Thread(target=simulate, args=(loc_id,), daemon=True).start()
    return jsonify({"job_id": str(uuid.uuid4()), "location_id": loc_id, "status": "running"})

@app.route("/status")
@login_required
def status():
    return jsonify(list(LOCATIONS.values()))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
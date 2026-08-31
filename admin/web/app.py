import os
import secrets
import sqlite3
import unicodedata

import requests
from flask import Flask, request, session, redirect, url_for, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DB_PATH = "ops.db"
FILESERVER_HOST = os.environ.get("FILESERVER_HOST", "internal-fileserver:8080")

RESERVED_LOCAL_PARTS = {"admin", "root", "operator", "security"}

PRIVILEGED_ACCOUNTS = {
    "operator@nightshift-corp.com": "operator",
    "admin@nightshift-corp.com": "admin",
}

WEBHOOK_ACTION_ID = "act_7f3a9c2e1b48"
# Flavor line shown on the dashboard. Hints (obliquely) that the access
# roster is checked against old names before the new ones are applied.
DASH_NOTE = "The east wing still runs on the old roster. It never learned the new names, it only checks the ones it was given."


def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE services (
        id INTEGER PRIMARY KEY, name TEXT, hostname TEXT, note TEXT)""")
    c.executemany("INSERT INTO services (name,hostname,note) VALUES (?,?,?)", [
        ("public-api", "api.nightshift-corp.example", "customer-facing gateway"),
        ("internal-fileserver", FILESERVER_HOST, "restricted — ops artifacts, internal only"),
        ("mail-relay", "mail.nightshift-corp.example", "smtp relay"),
        ("monitoring", "grafana.nightshift-corp.example", "internal dashboards"),
    ])
    conn.commit()
    conn.close()

init_db()

USERS = dict(PRIVILEGED_ACCOUNTS)


LOGIN_PAGE = """
<h2>Nightshift Ops Portal — Sign in</h2>
<form method="POST" action="/register">
  <input name="email" placeholder="you@nightshift-corp.com" size="40">
  <button type="submit">Request access</button>
</form>
<p>{{ msg }}</p>
"""

DASH_PAGE = """
<h2>Nightshift Ops Dashboard</h2>
<p>Signed in as: <b>{{ email }}</b> (role: {{ role }})</p>

{% if role in ('operator','admin') %}
<p style="color:#888"><i>{{ dash_note }}</i></p>
<h3>Internal Services Directory</h3>
<form method="GET" action="/dashboard/search">
  <input name="q" placeholder="search services..." size="30">
  <button type="submit">Search</button>
</form>
{% endif %}

{% if role == 'admin' %}
<p><i>Full administrative access granted.</i></p>
{% endif %}
"""

SEARCH_RESULTS = """
<h2>Search results for: {{ q }}</h2>
<table border="1" cellpadding="4">
<tr><th>Name</th><th>Hostname</th><th>Note</th></tr>
{% for row in rows %}
<tr><td>{{ row[0] }}</td><td>{{ row[1] }}</td><td>{{ row[2] }}</td></tr>
{% endfor %}
</table>
<p><a href="/dashboard">Back</a></p>
"""


@app.route("/")
def index():
    if "email" in session:
        return render_template_string(DASH_PAGE, email=session["email"],
                                       role=session["role"], dash_note=DASH_NOTE)
    return render_template_string(LOGIN_PAGE, msg="")


@app.route("/register", methods=["POST"])
def register():
    raw_email = request.form.get("email", "")

    if "@" in raw_email:
        local_part = raw_email.split("@", 1)[0].lower()
        if local_part in RESERVED_LOCAL_PARTS:
            return render_template_string(LOGIN_PAGE, msg="That address is reserved. Contact IT.")

    identity = unicodedata.normalize("NFKC", raw_email)

    if identity not in USERS:
        USERS[identity] = "user"

    session["email"] = identity
    session["role"] = USERS[identity]
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    if "email" not in session:
        return redirect(url_for("index"))
    return render_template_string(DASH_PAGE, email=session["email"],
                                   role=session["role"], dash_note=DASH_NOTE)


@app.route("/dashboard/search")
def dashboard_search():
    if session.get("role") not in ("operator", "admin"):
        return jsonify({"error": "forbidden"}), 403

    term = request.args.get("q", "")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = f"SELECT name, hostname, note FROM services WHERE name LIKE '%{term}%'"
    try:
        rows = c.execute(query).fetchall()
    except sqlite3.OperationalError as e:
        return jsonify({"error": str(e)}), 400
    finally:
        conn.close()

    return render_template_string(SEARCH_RESULTS, q=term, rows=rows)


@app.route("/internal/actions")
def internal_actions():
    return jsonify([
        {
            "id": "act_deadbeef1234",
            "name": "metrics",
            "method": "GET",
            "endpoint": "/actions/act_deadbeef1234",
            "target": "/metrics"
        },
        {
            "id": "act_7f3a9c2e1b48",
            "name": "webhook_test",
            "method": "POST",
            "endpoint": "/actions/act_7f3a9c2e1b48",
            "target": "/status"
        },
        {
            "id": "act_cafebabe5678",
            "name": "healthcheck",
            "method": "GET",
            "endpoint": "/actions/act_cafebabe5678",
            "target": "/health"
        }
    ])
@app.route("/robots.txt")
def robots():
    return "User-agent: *\nDisallow: /internal/actions\n", 200, {
        "Content-Type": "text/plain"
    }

@app.route("/actions/<action_id>", methods=["POST"])
def invoke_action(action_id):
    if session.get("role") != "admin":
        return jsonify({"error": "forbidden"}), 403

    if action_id != WEBHOOK_ACTION_ID:
        return jsonify({"error": "unknown action"}), 404

    path = request.form.get("path", "/status")
    if not path.startswith("/"):
        path = "/" + path

    target_host = request.headers.get("X-Forwarded-Host", "api.nightshift-corp.example")

    try:
        resp = requests.get(f"http://{target_host}{path}", timeout=5)
        # IMPORTANT: use resp.content (raw bytes), not resp.text — several
        # proxied artifacts (vault.enc, memory.lime, readme.enc, ...) are
        # binary, and resp.text force-decodes as UTF-8, corrupting/breaking
        # on any non-UTF-8 byte (e.g. ciphertext containing 0xFF).
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return resp.content, resp.status_code, {"Content-Type": content_type}
    except Exception as e:
        return jsonify({"error": str(e)}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

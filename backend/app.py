import os
import json
import subprocess
import uuid
import socket
import sqlite3

from flask import Flask, request, jsonify, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash


# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, 'data')
FRONTEND_DIR = os.path.join(PROJECT_DIR, 'frontend')
DB_FILE = os.path.join(DATA_DIR, 'socat.db')

os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

active_processes = {}  # {rule_id: [Popen, ...]}


# --- DB helpers ---
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def db_get_config(key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else None


def db_set_config(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    conn.close()

    # Defaults
    if not db_get_config("username"):
        db_set_config("username", "admin")
    if not db_get_config("password_hash"):
        db_set_config("password_hash", generate_password_hash("admin"))


def db_get_rules():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT data FROM rules")
    rows = cur.fetchall()
    conn.close()

    rules = []
    for r in rows:
        try:
            rules.append(json.loads(r["data"]))
        except Exception:
            pass
    return rules


def db_save_rule(rule):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO rules (id, data) VALUES (?, ?)", (rule["id"], json.dumps(rule)))
    conn.commit()
    conn.close()


def db_delete_rule(rule_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()


# --- Auth helpers ---
def db_check_credentials(username, password):
    stored_user = db_get_config("username") or ""
    stored_hash = db_get_config("password_hash") or ""
    if not stored_user or not stored_hash:
        return False
    if username != stored_user:
        return False
    return check_password_hash(stored_hash, password)


def db_set_credentials(username, password):
    db_set_config("username", username)
    db_set_config("password_hash", generate_password_hash(password))


# --- Network helpers ---
def get_external_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "0.0.0.0"


def parse_port_range(port_str):
    try:
        p = str(port_str).strip()
        if "-" in p:
            a, b = p.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                return []
            return list(range(start, end + 1))
        return [int(p)]
    except Exception:
        return []


def validate_rule_data(data):
    src_ports = parse_port_range(data.get("src_port"))
    dst_ports = parse_port_range(data.get("dst_port"))

    if not src_ports or not dst_ports:
        return "Invalid port format"

    if len(src_ports) != len(dst_ports):
        return "Port range mismatch: Source and Dest must have same count"

    proto = (data.get("proto") or "TCP").upper()
    if proto not in ("TCP", "UDP"):
        return "Invalid protocol"

    return None


def check_port_conflict(candidate, rules, ignore_id=None):
    cand_proto = (candidate.get("proto") or "TCP").upper()
    cand_ports = set(parse_port_range(candidate.get("src_port")))

    for r in rules:
        if ignore_id and r.get("id") == ignore_id:
            continue

        if (r.get("proto") or "TCP").upper() != cand_proto:
            continue

        used_ports = set(parse_port_range(r.get("src_port")))
        inter = cand_ports.intersection(used_ports)
        if inter:
            sample = sorted(list(inter))[:20]
            return f"Conflict: inbound port(s) already used for {cand_proto}: {sample}"
    return None


# --- Socat management ---
def stop_socat(rule_id):
    procs = active_processes.get(rule_id, [])
    for p in procs:
        try:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    p.kill()
        except Exception:
            pass
    if rule_id in active_processes:
        del active_processes[rule_id]


def start_socat(rule):
    rule_id = rule["id"]
    stop_socat(rule_id)

    if not rule.get("enabled", False):
        return

    src_ports = parse_port_range(rule.get("src_port"))
    dst_ports = parse_port_range(rule.get("dst_port"))
    proto = (rule.get("proto") or "TCP").upper()
    src_ip = rule.get("src_ip") or "0.0.0.0"
    dst_ip = rule.get("dst_ip")

    procs = []
    for i in range(len(src_ports)):
        sport = src_ports[i]
        dport = dst_ports[i]

        listen_part = f"{proto}-LISTEN:{sport},fork,bind={src_ip}"
        connect_part = f"{proto}:{dst_ip}:{dport}"
        cmd = ["socat", listen_part, connect_part]

        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append(p)
        except Exception:
            # if one fails, keep trying others
            pass

    if procs:
        active_processes[rule_id] = procs


def sync_processes():
    for rule in db_get_rules():
        if rule.get("enabled"):
            start_socat(rule)


# --- Routes / Static ---
@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)


# --- API ---
@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "authenticated": session.get("logged_in", False),
        "external_ip": get_external_ip()
    })


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if db_check_credentials(username, password):
        session["logged_in"] = True
        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("logged_in", None)
    return jsonify({"status": "success"})


@app.route("/api/change-credentials", methods=["POST"])
def change_credentials():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    old_username = (data.get("old_username") or "").strip()
    old_password = data.get("old_password") or ""
    new_username = (data.get("new_username") or "").strip()
    new_password = data.get("new_password") or ""

    if not db_check_credentials(old_username, old_password):
        return jsonify({"error": "Wrong current login/password"}), 400

    if not new_username:
        return jsonify({"error": "New login cannot be empty"}), 400

    if not new_password:
        return jsonify({"error": "New password cannot be empty"}), 400

    db_set_credentials(new_username, new_password)
    return jsonify({"status": "success"})


@app.route("/api/rules", methods=["GET"])
def api_get_rules():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(db_get_rules())


@app.route("/api/rules", methods=["POST"])
def api_add_rule():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    err = validate_rule_data(data)
    if err:
        return jsonify({"error": err}), 400

    rules = db_get_rules()
    conflict = check_port_conflict(data, rules)
    if conflict:
        return jsonify({"error": conflict}), 409

    new_rule = {
        "id": str(uuid.uuid4()),
        "description": (data.get("description") or "").strip(),
        "src_ip": (data.get("src_ip") or "0.0.0.0").strip(),
        "src_port": str(data.get("src_port")).strip(),
        "dst_ip": (data.get("dst_ip") or "").strip(),
        "dst_port": str(data.get("dst_port")).strip(),
        "proto": (data.get("proto") or "TCP").upper(),
        "enabled": False
    }

    db_save_rule(new_rule)
    return jsonify(new_rule)


@app.route("/api/rules/<rule_id>", methods=["PUT"])
def api_update_rule(rule_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    err = validate_rule_data(data)
    if err:
        return jsonify({"error": err}), 400

    rules = db_get_rules()
    target = next((r for r in rules if r.get("id") == rule_id), None)
    if not target:
        return jsonify({"error": "Not found"}), 404

    conflict = check_port_conflict(data, rules, ignore_id=rule_id)
    if conflict:
        return jsonify({"error": conflict}), 409

    # stop before changing
    stop_socat(rule_id)

    target.update({
        "description": (data.get("description") or "").strip(),
        "src_ip": (data.get("src_ip") or "0.0.0.0").strip(),
        "src_port": str(data.get("src_port")).strip(),
        "dst_ip": (data.get("dst_ip") or "").strip(),
        "dst_port": str(data.get("dst_port")).strip(),
        "proto": (data.get("proto") or "TCP").upper(),
    })

    db_save_rule(target)

    if target.get("enabled"):
        start_socat(target)

    return jsonify(target)


@app.route("/api/rules/<rule_id>", methods=["DELETE"])
def api_delete_rule(rule_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    stop_socat(rule_id)
    db_delete_rule(rule_id)
    return jsonify({"status": "deleted"})


@app.route("/api/rules/<rule_id>/toggle", methods=["POST"])
def api_toggle_rule(rule_id):
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401

    rules = db_get_rules()
    target = next((r for r in rules if r.get("id") == rule_id), None)
    if not target:
        return jsonify({"error": "Not found"}), 404

    target["enabled"] = not bool(target.get("enabled"))
    db_save_rule(target)

    if target["enabled"]:
        start_socat(target)
    else:
        stop_socat(rule_id)

    return jsonify(target)


if __name__ == "__main__":
    init_db()
    sync_processes()

    # installer uses PORT=...
    port_env = os.environ.get("PORT") or os.environ.get("FLASK_PORT") or "5000"
    try:
        port = int(port_env)
    except ValueError:
        port = 5000

    app.run(host="0.0.0.0", port=port)

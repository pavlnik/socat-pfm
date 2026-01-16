import os
import json
import subprocess
import sys
import uuid
import socket
import sqlite3
from flask import Flask, request, jsonify, send_from_directory, session
from werkzeug.security import generate_password_hash, check_password_hash

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), 'data')
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), 'frontend')
DB_FILE = os.path.join(DATA_DIR, 'socat.db')

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.secret_key = os.urandom(24)

active_processes = {}

# --- DATABASE ---
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, data TEXT)''')
    c.execute("SELECT value FROM config WHERE key='password_hash'")
    if not c.fetchone():
        default_hash = generate_password_hash("admin")
        c.execute("INSERT INTO config (key, value) VALUES (?, ?)", ('password_hash', default_hash))
        print(">>> Default password set to: 'admin'")
    c.execute("SELECT value FROM config WHERE key='username'")
    if not c.fetchone():
        c.execute("INSERT INTO config (key, value) VALUES (?, ?)", ('username', 'admin'))
        print(">>> Default username set to: 'admin'")
        
    conn.commit()
    conn.close()

def db_check_credentials(username, password):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='username'")
    db_user = c.fetchone()
    c.execute("SELECT value FROM config WHERE key='password_hash'")
    db_pass = c.fetchone()
    conn.close()
    if db_user and db_pass:
        if db_user['value'] == username and check_password_hash(db_pass['value'], password):
            return True
    return False

def db_update_credentials(new_username, new_password):
    new_hash = generate_password_hash(new_password)
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('username', new_username))
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('password_hash', new_hash))
    conn.commit()
    conn.close()

def db_get_rules():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT data FROM rules")
    rows = c.fetchall()
    conn.close()
    return [json.loads(row['data']) for row in rows]

def db_save_rule(rule):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO rules (id, data) VALUES (?, ?)", (rule['id'], json.dumps(rule)))
    conn.commit()
    conn.close()

def db_delete_rule(rule_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM rules WHERE id=?", (rule_id,))
    conn.commit()
    conn.close()

# --- LOGIC ---
def parse_port_range(port_str):
    try:
        if '-' in str(port_str):
            start, end = map(int, str(port_str).split('-'))
            if start > end: return []
            return list(range(start, end + 1))
        else:
            return [int(port_str)]
    except ValueError:
        return []

def check_port_conflict(new_rule, rules, ignore_id=None):
    """
    Checks if new_rule's source ports overlap with any existing rules
    that have the same protocol.
    """
    new_ports = set(parse_port_range(new_rule['src_port']))
    new_proto = new_rule['proto'].upper()

    for r in rules:
        if ignore_id and r['id'] == ignore_id:
            continue
        
        if r['proto'].upper() != new_proto:
            continue

        existing_ports = set(parse_port_range(r['src_port']))
        
        # Check intersection
        conflict = new_ports.intersection(existing_ports)
        if conflict:
            return f"Conflict: Port(s) {list(conflict)} are already used by rule (ID: {r['id'][:8]}...)"
    return None

def validate_rule_data(data):
    src_ports = parse_port_range(data['src_port'])
    dst_ports = parse_port_range(data['dst_port'])
    if not src_ports or not dst_ports:
        return "Invalid port format"
    if len(src_ports) != len(dst_ports):
        return "Port range mismatch: Source and Dest must have same count"
    return None

def start_socat(rule):
    rule_id = rule['id']
    stop_socat(rule_id)
    if not rule.get('enabled', False): return

    src_ports = parse_port_range(rule['src_port'])
    dst_ports = parse_port_range(rule['dst_port'])
    processes = []
    
    for i in range(len(src_ports)):
        sport = src_ports[i]
        dport = dst_ports[i]
        proto = rule['proto'].upper()
        
        # bind=... is important so we don't bind to all interfaces unless specified
        listen_part = f"{proto}-LISTEN:{sport},fork,bind={rule['src_ip']}"
        connect_part = f"{proto}:{rule['dst_ip']}:{dport}"
        cmd = ["socat", listen_part, connect_part]
        
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(proc)
        except Exception as e:
            print(f"Error starting {sport}->{dport}: {e}")

    if processes:
        active_processes[rule_id] = processes

def stop_socat(rule_id):
    if rule_id in active_processes:
        for proc in active_processes[rule_id]:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
        del active_processes[rule_id]

def sync_processes():
    rules = db_get_rules()
    for rule in rules:
        if rule.get('enabled'):
            start_socat(rule)

# --- API ---
@app.route('/')
def index(): return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path): return send_from_directory(FRONTEND_DIR, path)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if db_check_credentials(username, password):
        session['logged_in'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/change-credentials', methods=['POST'])
def change_credentials():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    
    current_username = data.get('current_username')
    current_password = data.get('current_password')
    new_username = data.get('new_username')
    new_password = data.get('new_password')
    
    if not db_check_credentials(current_username, current_password):
        return jsonify({"error": "Wrong current credentials"}), 400
    db_update_credentials(new_username, new_password)
    return jsonify({"status": "success"})

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "authenticated": session.get('logged_in', False),
        "external_ip": "0.0.0.0" # Simplification for container
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('logged_in', None)
    return jsonify({"status": "success"})

@app.route('/api/rules', methods=['GET'])
def get_rules():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    return jsonify(db_get_rules())

@app.route('/api/rules', methods=['POST'])
def add_rule():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    
    # Validation
    error = validate_rule_data(data)
    if error: return jsonify({"error": error}), 400

    # Conflict Check
    existing_rules = db_get_rules()
    conflict = check_port_conflict(data, existing_rules)
    if conflict: return jsonify({"error": conflict}), 409
    
    new_rule = {
        "id": str(uuid.uuid4()),
        "description": data.get('description', ''), # NEW Field
        "src_ip": data.get('src_ip', '0.0.0.0'),
        "src_port": str(data['src_port']), 
        "dst_ip": data['dst_ip'],
        "dst_port": str(data['dst_port']),
        "proto": data.get('proto', 'TCP'),
        "enabled": False
    }
    
    db_save_rule(new_rule)
    return jsonify(new_rule)

@app.route('/api/rules/<rule_id>', methods=['PUT'])
def update_rule(rule_id):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    
    error = validate_rule_data(data)
    if error: return jsonify({"error": error}), 400
    
    existing_rules = db_get_rules()
    target_rule = next((r for r in existing_rules if r['id'] == rule_id), None)
    if not target_rule: return jsonify({"error": "Not found"}), 404

    # Check conflict excluding itself
    conflict = check_port_conflict(data, existing_rules, ignore_id=rule_id)
    if conflict: return jsonify({"error": conflict}), 409

    stop_socat(rule_id)
    target_rule.update({
        'description': data.get('description', ''), # NEW
        'src_ip': data.get('src_ip', '0.0.0.0'),
        'src_port': str(data['src_port']),
        'dst_ip': data['dst_ip'],
        'dst_port': str(data['dst_port']),
        'proto': data.get('proto', 'TCP')
    })
    
    db_save_rule(target_rule)
    if target_rule['enabled']: start_socat(target_rule)
    return jsonify(target_rule)

@app.route('/api/rules/<rule_id>', methods=['DELETE'])
def delete_rule(rule_id):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    stop_socat(rule_id)
    db_delete_rule(rule_id)
    return jsonify({"status": "deleted"})

@app.route('/api/rules/<rule_id>/toggle', methods=['POST'])
def toggle_rule(rule_id):
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    rules = db_get_rules()
    target_rule = next((r for r in rules if r['id'] == rule_id), None)
    
    if target_rule:
        # Check conflict before enabling if ports changed by other means? 
        # Usually update handles it, but good to be safe. 
        # Skipping for now to keep toggle fast.
        
        target_rule['enabled'] = not target_rule['enabled']
        db_save_rule(target_rule)
        if target_rule['enabled']: start_socat(target_rule)
        else: stop_socat(rule_id)
        return jsonify(target_rule)
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    init_db()
    sync_processes()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)


import os
import json
import subprocess
import signal
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

# Ensure data directory exists
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

app = Flask(__name__, static_folder=FRONTEND_DIR)
app.secret_key = os.urandom(24)

# Global process storage: {rule_id: [proc1, proc2, ...]}
active_processes = {}

# --- DATABASE HELPERS ---

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Table for configuration (password hash)
    c.execute('''CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Table for rules (storing as JSON blob for simplicity and flexibility)
    c.execute('''CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, data TEXT)''')
    
    # Check if password exists, if not set default: "admin"
    c.execute("SELECT value FROM config WHERE key='password_hash'")
    if not c.fetchone():
        default_hash = generate_password_hash("admin")
        c.execute("INSERT INTO config (key, value) VALUES (?, ?)", ('password_hash', default_hash))
        print(">>> Default password set to: 'admin'")
        
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

def db_check_password(password):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key='password_hash'")
    row = c.fetchone()
    conn.close()
    if row and check_password_hash(row['value'], password):
        return True
    return False

def db_change_password(new_password):
    new_hash = generate_password_hash(new_password)
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", ('password_hash', new_hash))
    conn.commit()
    conn.close()

# --- SOCAT LOGIC ---

def get_external_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "0.0.0.0"

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

def validate_rule_data(data):
    src_ports = parse_port_range(data['src_port'])
    dst_ports = parse_port_range(data['dst_port'])
    if not src_ports or not dst_ports:
        return "Invalid port format"
    if len(src_ports) != len(dst_ports):
        return "Port range mismatch"
    return None

def start_socat(rule):
    rule_id = rule['id']
    stop_socat(rule_id) 
    
    if not rule.get('enabled', False):
        return

    src_ports = parse_port_range(rule['src_port'])
    dst_ports = parse_port_range(rule['dst_port'])
    
    processes = []
    
    for i in range(len(src_ports)):
        sport = src_ports[i]
        dport = dst_ports[i]
        proto = rule['proto'].upper()
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
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(FRONTEND_DIR, path)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    password = data.get('password')
    
    if db_check_password(password):
        session['logged_in'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Invalid password"}), 401

@app.route('/api/change-password', methods=['POST'])
def change_password():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not db_check_password(current_password):
        return jsonify({"error": "Wrong current password"}), 400
        
    db_change_password(new_password)
    return jsonify({"status": "success"})

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        "authenticated": session.get('logged_in', False),
        "external_ip": get_external_ip()
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
    
    error = validate_rule_data(data)
    if error: return jsonify({"error": error}), 400
    
    new_rule = {
        "id": str(uuid.uuid4()),
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
    
    rules = db_get_rules()
    target_rule = next((r for r in rules if r['id'] == rule_id), None)
            
    if not target_rule: return jsonify({"error": "Not found"}), 404

    stop_socat(rule_id)
    target_rule.update({
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


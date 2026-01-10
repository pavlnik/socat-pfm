const API = '/api';
const ICONS = {
    edit: '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>'
};

const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const modal = document.getElementById('modal');
const pwdModal = document.getElementById('pwd-modal');
const loginForm = document.getElementById('login-form');
const ruleForm = document.getElementById('rule-form');
const pwdForm = document.getElementById('pwd-form');

// --- Input Validation ---
function validateIpInput(event) {
    let value = event.target.value.replace(/[^0-9.]/g, '');
    const parts = value.split('.');
    const fixedParts = parts.map(part => {
        if (part === '') return '';
        const num = parseInt(part, 10);
        if (num > 255) return '255';
        return part;
    });
    if (value !== event.target.value) event.target.value = value;
    const lastPart = parts[parts.length - 1];
    if (lastPart && parseInt(lastPart) > 255) {
         fixedParts[fixedParts.length - 1] = '255';
         event.target.value = fixedParts.join('.');
    }
}
function validatePortInput(event) {
    let value = event.target.value.replace(/[^0-9-]/g, '');
    const parts = value.split('-');
    if (parts[0] && parseInt(parts[0]) > 65535) parts[0] = '65535';
    if (parts.length > 1 && parts[1] !== '' && parseInt(parts[1]) > 65535) parts[1] = '65535';
    const newValue = parts.join('-');
    if (newValue !== event.target.value) event.target.value = newValue;
}

document.getElementById('src_ip').addEventListener('input', validateIpInput);
document.getElementById('dst_ip').addEventListener('input', validateIpInput);
document.getElementById('src_port').addEventListener('input', validatePortInput);
document.getElementById('dst_port').addEventListener('input', validatePortInput);

// --- Auth & Main ---
checkStatus();

async function checkStatus() {
    try {
        const res = await fetch(`${API}/status`);
        const data = await res.json();
        if (data.authenticated) { showApp(); } 
        else { showLogin(); }
    } catch(e) { showLogin(); }
}

function showLogin() {
    loginScreen.classList.remove('hidden');
    appScreen.classList.add('hidden');
}

function showApp() {
    loginScreen.classList.add('hidden');
    appScreen.classList.remove('hidden');
    loadRules();
}

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const password = e.target.password.value;
    const res = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
    });
    if (res.ok) { 
        document.getElementById('login-error').textContent = ''; 
        e.target.password.value = '';
        checkStatus(); 
    } 
    else { document.getElementById('login-error').textContent = 'Invalid password'; }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch(`${API}/logout`, { method: 'POST' });
    window.location.reload();
});

// --- Rules CRUD ---
async function loadRules() {
    const res = await fetch(`${API}/rules`);
    const rules = await res.json();
    renderRules(rules);
}

function renderRules(rules) {
    const container = document.getElementById('rules-list');
    container.innerHTML = '';
    rules.forEach(rule => {
        const ruleJson = JSON.stringify(rule).replace(/"/g, '&quot;');
        const div = document.createElement('div');
        div.className = `rule-card ${rule.enabled ? '' : 'disabled'}`;
        div.innerHTML = `
            <div class="rule-header">
                <span class="badge ${rule.proto.toLowerCase()}">${rule.proto}</span>
                <div class="btn-group">
                    <button class="btn btn-icon" onclick="editRule(${ruleJson})" title="Edit">${ICONS.edit}</button>
                    <button class="btn btn-icon delete" onclick="deleteRule('${rule.id}')" title="Delete">${ICONS.trash}</button>
                </div>
            </div>
            <div class="connection-visual">
                <div><div style="font-size:0.8em; color:#888">IN (${rule.src_ip === '0.0.0.0' ? 'ALL' : rule.src_ip})</div>:${rule.src_port}</div>
                <div class="arrow">➜</div>
                <div style="text-align:right"><div style="font-size:0.8em; color:#888">TO (${rule.dst_ip})</div>:${rule.dst_port}</div>
            </div>
            <div class="rule-actions">
                <div class="toggle-switch ${rule.enabled ? 'active' : ''}" onclick="toggleRule('${rule.id}')">
                    <div class="indicator"></div><span class="status-text">${rule.enabled ? 'Active' : 'Disabled'}</span>
                </div>
            </div>`;
        container.appendChild(div);
    });
}

async function toggleRule(id) { await fetch(`${API}/rules/${id}/toggle`, { method: 'POST' }); loadRules(); }
async function deleteRule(id) { if(confirm('Delete rule?')) { await fetch(`${API}/rules/${id}`, { method: 'DELETE' }); loadRules(); } }

function editRule(rule) {
    document.getElementById('modal-title').textContent = 'Edit Rule';
    document.getElementById('rule_id').value = rule.id;
    document.getElementById('src_ip').value = rule.src_ip;
    document.getElementById('src_port').value = rule.src_port; 
    document.getElementById('proto').value = rule.proto;
    document.getElementById('dst_ip').value = rule.dst_ip;
    document.getElementById('dst_port').value = rule.dst_port; 
    modal.classList.remove('hidden');
}

function resetModal() {
    document.getElementById('modal-title').textContent = 'New Rule';
    document.getElementById('rule_id').value = '';
    ruleForm.reset();
    document.getElementById('src_ip').value = "0.0.0.0";
}

document.getElementById('open-modal-btn').onclick = () => { resetModal(); modal.classList.remove('hidden'); };
document.querySelectorAll('.close-modal, .close-modal-btn').forEach(el => { el.onclick = () => modal.classList.add('hidden'); });

ruleForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('rule_id').value;
    const isEdit = !!id;
    const data = {
        src_ip: document.getElementById('src_ip').value,
        src_port: document.getElementById('src_port').value,
        proto: document.getElementById('proto').value,
        dst_ip: document.getElementById('dst_ip').value,
        dst_port: document.getElementById('dst_port').value,
    };
    const method = isEdit ? 'PUT' : 'POST';
    const url = isEdit ? `${API}/rules/${id}` : `${API}/rules`;
    const res = await fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    const json = await res.json();
    if (res.ok) { modal.classList.add('hidden'); resetModal(); loadRules(); } 
    else { alert('Error: ' + (json.error || 'Unknown error')); }
});

// --- Password Change Logic ---
document.getElementById('open-pwd-modal-btn').onclick = () => pwdModal.classList.remove('hidden');
document.querySelectorAll('.close-pwd-modal, .close-pwd-modal-btn').forEach(el => { el.onclick = () => pwdModal.classList.add('hidden'); });

pwdForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const current_password = document.getElementById('current_pwd').value;
    const new_password = document.getElementById('new_pwd').value;
    
    const res = await fetch(`${API}/change-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password, new_password })
    });
    
    if (res.ok) {
        alert("Password updated successfully");
        pwdModal.classList.add('hidden');
        pwdForm.reset();
    } else {
        alert("Error: Incorrect current password");
    }
});

window.deleteRule = deleteRule; window.toggleRule = toggleRule; window.editRule = editRule;
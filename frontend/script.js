const API = '/api';
const ICONS = {
    edit: '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
    trash: '<svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>'
};

// Elements
const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');
const modal = document.getElementById('modal');
const credsModal = document.getElementById('creds-modal');
const confirmModal = document.getElementById('confirm-modal');
const notificationContainer = document.getElementById('notification-container');
const ruleForm = document.getElementById('rule-form');

// --- NOTIFICATIONS ---
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${message}</span>`;
    
    notificationContainer.appendChild(toast);
    
    // Auto remove
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- INPUT VALIDATION ---
function validateIpInput(event) {
    let value = event.target.value;
    
    // 1. Allow only numbers and dots
    value = value.replace(/[^0-9.]/g, '');
    
    // 2. Prevent multiple dots
    value = value.replace(/\.\./g, '.');

    // 3. Split into octets
    let parts = value.split('.');
    
    // 4. Limit to 4 octets
    if (parts.length > 4) {
        parts = parts.slice(0, 4);
        value = parts.join('.');
    }

    // 5. Check limits (0-255) for each part
    const fixedParts = parts.map(part => {
        if (part === '') return '';
        const num = parseInt(part, 10);
        if (num > 255) return '255';
        return part;
    });

    // 6. Update input value if cleaned value differs
    if (value !== event.target.value) {
        event.target.value = value;
    }
    
    // Check the last typing part immediately
    const lastIndex = parts.length - 1;
    const lastPart = parts[lastIndex];
    if (lastPart && parseInt(lastPart) > 255) {
         fixedParts[lastIndex] = '255';
         event.target.value = fixedParts.join('.');
    }
}

function validatePortInput(event) {
    let value = event.target.value;
    
    // 1. Allow only numbers and hyphen
    value = value.replace(/[^0-9-]/g, '');
    
    // 2. Remove leading hyphen
    if (value.startsWith('-')) {
        value = value.substring(1);
    }

    // 3. Allow only ONE hyphen
    const firstHyphenIndex = value.indexOf('-');
    if (firstHyphenIndex !== -1) {
        // Keep part before hyphen + hyphen + part after (stripped of any other hyphens)
        const before = value.substring(0, firstHyphenIndex + 1);
        const after = value.substring(firstHyphenIndex + 1).replace(/-/g, '');
        value = before + after;
    }

    // 4. Validate ranges (0-65535)
    const parts = value.split('-');
    
    // Validate first port
    if (parts[0] && parseInt(parts[0]) > 65535) {
        parts[0] = '65535';
    }
    
    // Validate second port (if exists and not empty)
    if (parts.length > 1 && parts[1] !== '') {
         if (parseInt(parts[1]) > 65535) {
             parts[1] = '65535';
         }
    }
    
    const newValue = parts.join('-');

    // 5. Update UI
    if (newValue !== event.target.value) {
        event.target.value = newValue;
    } else if (value !== event.target.value) {
        // Fallback if we just stripped chars via regex/logic but parts were valid
        event.target.value = value;
    }
}

document.getElementById('src_ip').addEventListener('input', validateIpInput);
document.getElementById('dst_ip').addEventListener('input', validateIpInput);
document.getElementById('src_port').addEventListener('input', validatePortInput);
document.getElementById('dst_port').addEventListener('input', validatePortInput);

// --- AUTH & MAIN ---
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

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    // Берем значения из новых ID
    const username = document.getElementById('login_username').value;
    const password = document.getElementById('login_password').value;
    
    const res = await fetch(`${API}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }) // Отправляем пару
    });
    if (res.ok) { 
        document.getElementById('login_password').value = '';
        checkStatus(); 
        showToast('Welcome back!');
    } else { 
        showToast('Invalid credentials', 'error');
    }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    await fetch(`${API}/logout`, { method: 'POST' });
    window.location.reload();
});

// --- RULES CRUD ---
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
                <div class="rule-title">
                    <span class="badge ${rule.proto.toLowerCase()}">${rule.proto}</span>
                    ${rule.description ? `<span class="rule-desc" title="${rule.description}">${rule.description}</span>` : ''}
                </div>
                <div class="btn-group">
                    <button class="btn btn-icon" onclick="editRule(${ruleJson})" title="Edit">${ICONS.edit}</button>
                    <button class="btn btn-icon delete" onclick="confirmDelete('${rule.id}')" title="Delete">${ICONS.trash}</button>
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

// --- DELETE CONFIRMATION ---
let deleteTargetId = null;

window.confirmDelete = function(id) {
    deleteTargetId = id;
    confirmModal.classList.remove('hidden');
}

document.getElementById('confirm-btn').onclick = async () => {
    if (deleteTargetId) {
        const res = await fetch(`${API}/rules/${deleteTargetId}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Rule deleted');
            loadRules();
        } else {
            showToast('Error deleting rule', 'error');
        }
    }
    confirmModal.classList.add('hidden');
};

document.querySelectorAll('.close-confirm-modal, .close-confirm-modal-btn').forEach(el => {
    el.onclick = () => confirmModal.classList.add('hidden');
});

// --- EDIT & SAVE ---
window.editRule = function(rule) {
    document.getElementById('modal-title').textContent = 'Edit Rule';
    document.getElementById('rule_id').value = rule.id;
    document.getElementById('description').value = rule.description || '';
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
        description: document.getElementById('description').value,
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
    
    if (res.ok) { 
        modal.classList.add('hidden'); 
        resetModal(); 
        loadRules(); 
        showToast(isEdit ? 'Rule updated' : 'Rule created');
    } 
    else { 
        showToast(json.error || 'Unknown error', 'error'); 
    }
});

// --- CREDENTIALS MODAL ---
document.getElementById('open-creds-modal-btn').onclick = () => {
    document.getElementById('creds-form').reset();
    credsModal.classList.remove('hidden');
};

document.querySelectorAll('.close-creds-modal, .close-creds-modal-btn').forEach(el => { 
    el.onclick = () => credsModal.classList.add('hidden'); 
});

document.getElementById('creds-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const current_username = document.getElementById('old_username').value;
    const current_password = document.getElementById('old_password').value;
    const new_username = document.getElementById('new_username').value;
    const new_password = document.getElementById('new_password').value;
    
    const res = await fetch(`${API}/change-credentials`, { // Новый URL
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            current_username, 
            current_password, 
            new_username, 
            new_password 
        })
    });
    
    if (res.ok) {
        showToast('Credentials updated successfully');
        credsModal.classList.add('hidden');
        e.target.reset();
    } else {
        showToast('Incorrect current credentials', 'error');
    }
});


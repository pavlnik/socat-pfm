const API = '/api';

const ICONS = {
  edit: '<svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>'
};

// Screens
const loginScreen = document.getElementById('login-screen');
const appScreen = document.getElementById('app-screen');

// Modals
const modal = document.getElementById('modal');
const credModal = document.getElementById('cred-modal');
const confirmModal = document.getElementById('confirm-modal');

// Forms
const loginForm = document.getElementById('login-form');
const ruleForm = document.getElementById('rule-form');
const credForm = document.getElementById('cred-form');

// Notifications
const notificationContainer = document.getElementById('notification-container');

// --- Toasts ---
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;

  notificationContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// --- Input validation ---
function validateIpInput(event) {
  let value = event.target.value;

  value = value.replace(/[^0-9.]/g, '');
  value = value.replace(/\.\.+/g, '.');

  let parts = value.split('.');
  if (parts.length > 4) {
    parts = parts.slice(0, 4);
    value = parts.join('.');
  }

  const fixedParts = parts.map(part => {
    if (part === '') return '';
    const num = parseInt(part, 10);
    if (Number.isNaN(num)) return '';
    if (num > 255) return '255';
    return String(num);
  });

  const fixedValue = fixedParts.join('.');

  if (fixedValue !== event.target.value) {
    event.target.value = fixedValue;
  }
}

function validatePortInput(event) {
  let value = event.target.value;

  value = value.replace(/[^0-9-]/g, '');
  if (value.startsWith('-')) value = value.slice(1);

  // allow only one hyphen
  const hyphenPos = value.indexOf('-');
  if (hyphenPos !== -1) {
    const before = value.slice(0, hyphenPos + 1);
    const after = value.slice(hyphenPos + 1).replace(/-/g, '');
    value = before + after;
  }

  const parts = value.split('-');
  if (parts[0]) {
    const p1 = Math.min(parseInt(parts[0], 10) || 0, 65535);
    parts[0] = String(p1);
  }
  if (parts.length > 1 && parts[1] !== '') {
    const p2 = Math.min(parseInt(parts[1], 10) || 0, 65535);
    parts[1] = String(p2);
  }

  const newValue = parts.join('-');
  if (newValue !== event.target.value) event.target.value = newValue;
}

// attach validators
document.getElementById('src_ip').addEventListener('input', validateIpInput);
document.getElementById('dst_ip').addEventListener('input', validateIpInput);
document.getElementById('src_port').addEventListener('input', validatePortInput);
document.getElementById('dst_port').addEventListener('input', validatePortInput);

// --- Auth flow ---
checkStatus();

async function checkStatus() {
  try {
    const res = await fetch(`${API}/status`);
    const data = await res.json();
    if (data.authenticated) showApp();
    else showLogin();
  } catch {
    showLogin();
  }
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

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;

  const res = await fetch(`${API}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });

  if (res.ok) {
    document.getElementById('login-error').textContent = '';
    document.getElementById('password').value = '';
    showToast('Login successful');
    checkStatus();
  } else {
    const j = await res.json().catch(() => ({}));
    document.getElementById('login-error').textContent = j.message || 'Invalid credentials';
  }
});

document.getElementById('logout-btn').addEventListener('click', async () => {
  await fetch(`${API}/logout`, { method: 'POST' });
  window.location.reload();
});

// --- Credentials modal ---
document.getElementById('open-cred-modal-btn').onclick = () => credModal.classList.remove('hidden');

document.querySelectorAll('.close-cred-modal, .close-cred-modal-btn').forEach(el => {
  el.onclick = () => credModal.classList.add('hidden');
});

credForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const payload = {
    old_username: document.getElementById('old_username').value.trim(),
    old_password: document.getElementById('old_password').value,
    new_username: document.getElementById('new_username').value.trim(),
    new_password: document.getElementById('new_password').value,
  };

  const res = await fetch(`${API}/change-credentials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    showToast('Credentials updated');
    credForm.reset();
    credModal.classList.add('hidden');
  } else {
    const j = await res.json().catch(() => ({}));
    showToast(j.error || 'Failed to update credentials', 'error');
  }
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
        <div>
          <div style="font-size:0.8em; color:#888">IN (${rule.src_ip === '0.0.0.0' ? 'ALL' : rule.src_ip})</div>
          :${rule.src_port}
        </div>
        <div class="arrow">➜</div>
        <div>
          <div style="font-size:0.8em; color:#888">TO (${rule.dst_ip})</div>
          :${rule.dst_port}
        </div>
      </div>

      <div class="rule-actions">
        <div class="toggle-switch ${rule.enabled ? 'active' : ''}" onclick="toggleRule('${rule.id}')">
          <div class="indicator"></div>
          <span class="status-text">${rule.enabled ? 'Active' : 'Disabled'}</span>
        </div>
      </div>
    `;

    container.appendChild(div);
  });
}

async function toggleRule(id) {
  const res = await fetch(`${API}/rules/${id}/toggle`, { method: 'POST' });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    showToast(j.error || 'Toggle failed', 'error');
  }
  loadRules();
}

// --- Delete confirm modal ---
let deleteTargetId = null;

window.confirmDelete = function (id) {
  deleteTargetId = id;
  confirmModal.classList.remove('hidden');
};

document.getElementById('confirm-btn').onclick = async () => {
  if (!deleteTargetId) return;

  const res = await fetch(`${API}/rules/${deleteTargetId}`, { method: 'DELETE' });
  if (res.ok) {
    showToast('Rule deleted');
    loadRules();
  } else {
    const j = await res.json().catch(() => ({}));
    showToast(j.error || 'Delete failed', 'error');
  }

  deleteTargetId = null;
  confirmModal.classList.add('hidden');
};

document.querySelectorAll('.close-confirm-modal, .close-confirm-modal-btn').forEach(el => {
  el.onclick = () => {
    deleteTargetId = null;
    confirmModal.classList.add('hidden');
  };
});

// --- Rule modal open/close ---
function resetRuleModal() {
  document.getElementById('modal-title').textContent = 'New Rule';
  document.getElementById('rule_id').value = '';
  ruleForm.reset();
  document.getElementById('src_ip').value = '0.0.0.0';
}

document.getElementById('open-modal-btn').onclick = () => {
  resetRuleModal();
  modal.classList.remove('hidden');
};

document.querySelectorAll('.close-modal, .close-modal-btn').forEach(el => {
  el.onclick = () => modal.classList.add('hidden');
});

window.editRule = function (rule) {
  document.getElementById('modal-title').textContent = 'Edit Rule';
  document.getElementById('rule_id').value = rule.id;
  document.getElementById('description').value = rule.description || '';
  document.getElementById('src_ip').value = rule.src_ip;
  document.getElementById('src_port').value = rule.src_port;
  document.getElementById('proto').value = rule.proto;
  document.getElementById('dst_ip').value = rule.dst_ip;
  document.getElementById('dst_port').value = rule.dst_port;
  modal.classList.remove('hidden');
};

ruleForm.addEventListener('submit', async (e) => {
  e.preventDefault();

  const id = document.getElementById('rule_id').value;
  const isEdit = !!id;

  const payload = {
    description: document.getElementById('description').value.trim(),
    src_ip: document.getElementById('src_ip').value.trim(),
    src_port: document.getElementById('src_port').value.trim(),
    proto: document.getElementById('proto').value,
    dst_ip: document.getElementById('dst_ip').value.trim(),
    dst_port: document.getElementById('dst_port').value.trim(),
  };

  const method = isEdit ? 'PUT' : 'POST';
  const url = isEdit ? `${API}/rules/${id}` : `${API}/rules`;

  const res = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });

  const j = await res.json().catch(() => ({}));

  if (res.ok) {
    modal.classList.add('hidden');
    resetRuleModal();
    loadRules();
    showToast(isEdit ? 'Rule updated' : 'Rule created');
  } else {
    showToast(j.error || 'Unknown error', 'error');
  }
});

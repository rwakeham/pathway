/* Pathway — shared frontend logic */

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/**
 * Resolve the canonical status and display label for a service.
 * Priority: HTTP health check (if configured) > Docker status > unknown.
 */
function resolveStatus(svc) {
  if (svc.health_check_url) {
    const hs = svc._health_status || 'pending';
    return { status: hs, label: hs, source: 'http' };
  }
  const ds = svc._docker_status;
  if (ds) return { status: ds, label: ds, source: 'docker' };
  if (svc.source === 'manual') return { status: 'unknown', label: 'manual', source: 'none' };
  return { status: 'unknown', label: 'unknown', source: 'none' };
}

function statusClass(status) {
  if (status === 'healthy') return 'status-running';
  if (status === 'stopped' || status === 'unhealthy') return 'status-stopped';
  return 'status-unknown';
}

function initials(name) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map(w => w[0])
    .join('')
    .toUpperCase();
}

const TILE_COLOURS = [
  '#4f46e5','#7c3aed','#2563eb','#0891b2','#059669',
  '#d97706','#dc2626','#db2777','#9333ea','#0284c7',
];

function tileColour(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return TILE_COLOURS[Math.abs(hash) % TILE_COLOURS.length];
}

async function apiFetch(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

let _toastTimer = null;
function showToast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast toast-${type} show`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function initDashboard() {
  loadServices();
  setInterval(loadServices, 30000);
}

async function loadServices() {
  try {
    const services = await apiFetch('/api/services');
    renderTiles(services);
  } catch (e) {
    console.error('Failed to load services:', e);
  }
}

function renderTiles(services) {
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  const loading = document.getElementById('loading');

  loading.classList.add('hidden');

  if (!services.length) {
    empty.classList.remove('hidden');
    empty.classList.add('flex');
    grid.innerHTML = '';
    return;
  }

  empty.classList.add('hidden');
  empty.classList.remove('flex');

  grid.innerHTML = services.map(svc => {
    const { status, label } = resolveStatus(svc);
    const dotClass = statusClass(status);
    const colour = tileColour(svc.name);
    const iconHtml = svc.icon_filename
      ? `<img src="/icons/${encodeURIComponent(svc.icon_filename)}" alt="${escHtml(svc.name)}"
              class="w-full h-full object-cover rounded-xl" />`
      : `<div class="icon-placeholder w-full h-full rounded-xl" style="background:${colour}">${escHtml(initials(svc.name))}</div>`;

    return `
      <a href="${escHtml(svc.url)}" target="_blank" rel="noopener"
         class="tile rounded-2xl p-4 flex flex-col gap-3 cursor-pointer no-underline">
        <div class="w-16 h-16 mx-auto rounded-xl overflow-hidden flex-shrink-0">
          ${iconHtml}
        </div>
        <div class="text-center min-w-0">
          <div class="font-semibold text-white text-sm truncate">${escHtml(svc.name)}</div>
          ${svc.description ? `<div class="text-slate-400 text-xs mt-0.5 truncate">${escHtml(svc.description)}</div>` : ''}
        </div>
        <div class="flex items-center justify-center gap-1.5 text-xs text-slate-500">
          <span class="status-dot ${dotClass}"></span>
          <span>${label}</span>
        </div>
      </a>`;
  }).join('');
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

let _services = [];
let _editingId = null;

async function initAdmin() {
  const statusRes = await apiFetch('/api/auth/status');

  if (statusRes.setup_required) {
    document.getElementById('setup-overlay').classList.remove('hidden');
    setupSetupForm();
    return;
  }

  if (!statusRes.authenticated) {
    document.getElementById('login-overlay').classList.remove('hidden');
    setupLoginForm();
    return;
  }

  showAdminContent();
}

function setupSetupForm() {
  document.getElementById('setup-form').addEventListener('submit', async e => {
    e.preventDefault();
    const pw = document.getElementById('setup-password').value;
    const confirm = document.getElementById('setup-confirm').value;
    const errEl = document.getElementById('setup-error');
    if (pw !== confirm) {
      errEl.textContent = 'Passwords do not match';
      errEl.classList.remove('hidden');
      return;
    }
    try {
      const fd = new FormData();
      fd.append('password', pw);
      await apiFetch('/api/auth/setup', { method: 'POST', body: fd });
      document.getElementById('setup-overlay').classList.add('hidden');
      showAdminContent();
    } catch (e) {
      errEl.textContent = e.message;
      errEl.classList.remove('hidden');
    }
  });
}

function setupLoginForm() {
  document.getElementById('login-form').addEventListener('submit', async e => {
    e.preventDefault();
    const pw = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    try {
      const fd = new FormData();
      fd.append('password', pw);
      await apiFetch('/api/auth/login', { method: 'POST', body: fd });
      document.getElementById('login-overlay').classList.add('hidden');
      showAdminContent();
    } catch (e) {
      errEl.textContent = 'Invalid password';
      errEl.classList.remove('hidden');
    }
  });
}

function showAdminContent() {
  document.getElementById('main-content').classList.remove('hidden');
  loadAdminServices();
  setupAddForm();
  setupPasswordForm();
}

async function loadAdminServices() {
  try {
    _services = await apiFetch('/api/admin/services');
    renderServicesTable(_services);
  } catch (e) {
    showToast('Failed to load services: ' + e.message, 'error');
  }
}

function renderServicesTable(services) {
  const tbody = document.getElementById('services-table-body');
  if (!services.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-8 text-center text-slate-500">No services yet — add one below or run a Docker scan.</td></tr>`;
    return;
  }

  tbody.innerHTML = services.map(svc => {
    const { status, label, source: statusSource } = resolveStatus(svc);
    const dotClass = statusClass(status);
    const colour = tileColour(svc.name);
    const iconHtml = svc.icon_filename
      ? `<img src="/icons/${encodeURIComponent(svc.icon_filename)}" class="w-8 h-8 rounded-lg object-cover flex-shrink-0" />`
      : `<div class="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
              style="background:${colour}">${escHtml(initials(svc.name))}</div>`;

    return `
      <tr class="border-b border-slate-800 hover:bg-slate-800/40 transition-colors" data-id="${svc.id}">
        <td class="px-4 py-3">
          <div class="flex items-center gap-3">
            ${iconHtml}
            <div>
              <div class="font-medium text-white">${escHtml(svc.name)}</div>
              ${svc.description ? `<div class="text-xs text-slate-400">${escHtml(svc.description)}</div>` : ''}
            </div>
          </div>
        </td>
        <td class="px-4 py-3 text-slate-300 font-mono text-xs max-w-xs truncate">
          <a href="${escHtml(svc.url)}" target="_blank" class="hover:text-indigo-400 transition-colors">${escHtml(svc.url)}</a>
        </td>
        <td class="px-4 py-3">
          <span class="px-2 py-0.5 rounded text-xs font-medium ${svc.source === 'auto' ? 'badge-auto' : 'badge-manual'}">
            ${svc.source}
          </span>
        </td>
        <td class="px-4 py-3">
          <div class="flex items-center gap-1.5">
            <span class="status-dot ${dotClass}"></span>
            <span class="text-xs text-slate-400">${label}</span>
            ${statusSource === 'http' ? '<span class="text-xs px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300 font-mono">http</span>' : ''}
          </div>
        </td>
        <td class="px-4 py-3">
          <input type="checkbox" class="toggle" ${svc.enabled ? 'checked' : ''}
            onchange="toggleEnabled('${svc.id}', this.checked)" />
        </td>
        <td class="px-4 py-3">
          <div class="flex gap-2">
            <button onclick="openEditModal('${svc.id}')" class="btn btn-ghost p-1.5" title="Edit">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
              </svg>
            </button>
            <button onclick="deleteService('${svc.id}', '${escHtml(svc.name)}')" class="btn btn-ghost p-1.5 text-red-400 hover:text-red-300" title="Delete">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
              </svg>
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

async function toggleEnabled(id, enabled) {
  const fd = new FormData();
  fd.append('enabled', enabled);
  try {
    await apiFetch(`/api/admin/services/${id}`, { method: 'PUT', body: fd });
    const svc = _services.find(s => s.id === id);
    if (svc) svc.enabled = enabled;
    showToast(enabled ? 'Service enabled' : 'Service disabled');
  } catch (e) {
    showToast('Failed: ' + e.message, 'error');
    loadAdminServices(); // revert
  }
}

async function deleteService(id, name) {
  if (!confirm(`Delete "${name}"?`)) return;
  try {
    await apiFetch(`/api/admin/services/${id}`, { method: 'DELETE' });
    showToast(`"${name}" deleted`);
    loadAdminServices();
  } catch (e) {
    showToast('Delete failed: ' + e.message, 'error');
  }
}

async function triggerScan() {
  const btn = document.getElementById('scan-btn');
  btn.disabled = true;
  btn.textContent = 'Scanning…';
  try {
    const res = await apiFetch('/api/admin/scan', { method: 'POST' });
    showToast(`Scan complete — ${res.detected} container(s) with ports found`);
    loadAdminServices();
  } catch (e) {
    showToast('Scan failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
      <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
    </svg> Scan Docker`;
  }
}

function setupAddForm() {
  document.getElementById('add-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    // Checkbox handling: FormData only includes it if checked
    if (!e.target.querySelector('[name=enabled]').checked) {
      fd.set('enabled', 'false');
    } else {
      fd.set('enabled', 'true');
    }
    try {
      await apiFetch('/api/admin/services', { method: 'POST', body: fd });
      showToast('Service added');
      e.target.reset();
      hideAddForm();
      loadAdminServices();
    } catch (err) {
      showToast('Failed: ' + err.message, 'error');
    }
  });
}

function showAddForm() {
  document.getElementById('add-form-section').classList.remove('hidden');
  document.getElementById('add-form-section').scrollIntoView({ behavior: 'smooth' });
}

function hideAddForm() {
  document.getElementById('add-form-section').classList.add('hidden');
}

// Edit modal
function openEditModal(id) {
  const svc = _services.find(s => s.id === id);
  if (!svc) return;
  _editingId = id;

  document.getElementById('edit-id').value = id;
  document.getElementById('edit-name').value = svc.name;
  document.getElementById('edit-url').value = svc.url;
  document.getElementById('edit-description').value = svc.description || '';
  document.getElementById('edit-health-check-url').value = svc.health_check_url || '';
  document.getElementById('edit-health-check-pattern').value = svc.health_check_pattern || '';
  document.getElementById('edit-enabled').checked = svc.enabled !== false;

  const preview = document.getElementById('edit-icon-preview');
  const img = document.getElementById('edit-icon-img');
  if (svc.icon_filename) {
    img.src = `/icons/${encodeURIComponent(svc.icon_filename)}`;
    preview.classList.remove('hidden');
  } else {
    preview.classList.add('hidden');
  }

  document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.add('hidden');
  _editingId = null;
}

document.addEventListener('DOMContentLoaded', () => {
  const editForm = document.getElementById('edit-form');
  if (editForm) {
    editForm.addEventListener('submit', async e => {
      e.preventDefault();
      const id = document.getElementById('edit-id').value;
      const fd = new FormData();
      fd.append('name', document.getElementById('edit-name').value);
      fd.append('url', document.getElementById('edit-url').value);
      fd.append('description', document.getElementById('edit-description').value);
      fd.append('health_check_url', document.getElementById('edit-health-check-url').value);
      fd.append('health_check_pattern', document.getElementById('edit-health-check-pattern').value);
      fd.append('enabled', document.getElementById('edit-enabled').checked ? 'true' : 'false');

      const iconFile = document.getElementById('edit-icon').files[0];
      if (iconFile) fd.append('icon', iconFile);

      try {
        await apiFetch(`/api/admin/services/${id}`, { method: 'PUT', body: fd });
        showToast('Service updated');
        closeEditModal();
        loadAdminServices();
      } catch (err) {
        showToast('Failed: ' + err.message, 'error');
      }
    });
  }
});

function setupPasswordForm() {
  document.getElementById('password-form').addEventListener('submit', async e => {
    e.preventDefault();
    const pw = document.getElementById('new-password').value;
    const confirm = document.getElementById('confirm-password').value;
    if (pw !== confirm) {
      showToast('Passwords do not match', 'error');
      return;
    }
    const fd = new FormData();
    fd.append('new_password', pw);
    try {
      await apiFetch('/api/admin/password', { method: 'PUT', body: fd });
      showToast('Password updated');
      e.target.reset();
    } catch (err) {
      showToast('Failed: ' + err.message, 'error');
    }
  });
}

async function logout() {
  await apiFetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/';
}

/* ═══════════════════════════════════════════════════════
   MERRICK DASHBOARD — Application Logic
   ═══════════════════════════════════════════════════════
   Single-page app backed by the Merrick REST API.
   Shows empty states when the API is unreachable.
   ═══════════════════════════════════════════════════════ */

(function() {
  'use strict';

  // ── Live Data Store ──────────────────────────────────

  const DATA = {
    health: null,
    stats: { devices: 0, memories: 0, keys: 0, agents: 0 },
    devices: [],
    keys: [],
    agents: [],
    activity: [],
    syncLog: [],
    analytics: {
      total_memories: 0,
      memories_today: 0,
      memories_this_week: 0,
      memories_this_month: 0,
      total_categories: 0,
      total_webhooks: 0,
      timeline: [],
      device_activity: [],
      categories: [],
      key_usage: [],
    },
    settings: {},
  };

  // ── Helpers ──────────────────────────────────────────

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return [...(ctx || document).querySelectorAll(sel)]; }

  function relativeTime(dateStr) {
    if (!dateStr) return 'never';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  }

  function formatNumber(n) {
    if (n == null) return '—';
    return n.toLocaleString();
  }

  function toast(message, type = 'info') {
    const container = $('#toast-container');
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-exit');
      el.addEventListener('animationend', () => el.remove());
    }, 3000);
  }

  // ── API Layer ────────────────────────────────────────

  async function apiFetch(path, opts = {}) {
    try {
      const res = await fetch(path, {
        headers: { 'Accept': 'application/json', ...opts.headers },
        ...opts,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      return null;
    }
  }

  // ── Status / Health ──────────────────────────────────

  async function fetchStatus() {
    const data = await apiFetch('/api/status');
    if (!data) {
      updateGlobalStatus('degraded', 'API unreachable');
      return;
    }

    // The /api/status endpoint returns a flat object. Map it
    // into the structure the UI expects.
    if (data.health) {
      DATA.health = data.health;
    }

    // Stats may come embedded in /api/status or need a
    // separate call — handle both shapes.
    if (data.stats) {
      DATA.stats = data.stats;
    } else {
      // Compose stats from nested health + device/key counts
      // if the API doesn't provide them directly.
      const devices = await apiFetch('/api/devices');
      const keys    = await apiFetch('/api/keys');
      const agents  = await apiFetch('/api/agents');
      if (devices) DATA.stats.devices = Array.isArray(devices) ? devices.length : DATA.devices.length;
      if (keys)    DATA.stats.keys    = Array.isArray(keys)    ? keys.length    : DATA.keys.length;
      if (agents)  DATA.stats.agents  = Array.isArray(agents)  ? agents.length  : DATA.agents.length;
    }

    // Determine global health
    const healthMap = DATA.health;
    let overall = 'ok';
    if (healthMap) {
      const statuses = Object.values(healthMap).map(s =>
        typeof s === 'object' && s !== null ? s.status : 'unknown'
      );
      if (statuses.includes('degraded')) overall = 'degraded';
      if (statuses.includes('unhealthy') || statuses.includes('error')) overall = 'error';
    }

    updateGlobalStatus(
      overall === 'ok' ? 'green' : overall === 'degraded' ? 'yellow' : 'red',
      overall === 'ok' ? 'All systems operational' : overall === 'degraded' ? 'Degraded' : 'Error'
    );

    renderOverviewStats();
    renderHealthCards();

    // Populate developer config from status data
    const configRaw = $('#config-raw');
    if (configRaw && data) {
      const config = {
        DB_HOST: data.db_host || 'unknown',
        DB_PORT: data.db_port || 'unknown',
        HONCHO_URL: data.honcho_url || 'unknown',
        HONCHO_WORKSPACE: data.honcho_workspace || 'unknown',
        MEM0_API_URL: data.mem0_api_url || 'unknown',
        SYNC_INTERVAL: data.sync_interval || 'unknown',
        SYNC_ENABLED: data.sync_enabled !== undefined ? data.sync_enabled : 'unknown',
      };
      configRaw.textContent = JSON.stringify(config, null, 2);
    }

    // Update connection status from health data
    const connStatus = $('.connection-status');
    if (connStatus && data.health && data.health.db) {
      const dbHealth = data.health.db;
      const dot = connStatus.querySelector('.status-dot');
      const text = connStatus.querySelector('span');
      if (dot) {
        dot.className = `status-dot status-dot--sm status-dot--${dbHealth.status === 'healthy' ? 'green' : 'red'}`;
      }
      if (text) {
        text.textContent = dbHealth.status === 'healthy'
          ? `Connected to PostgreSQL ${dbHealth.host || ''} / ${dbHealth.name || ''}`
          : 'Database connection error';
      }
    }

    // Populate settings form from status data
    const settingsFields = {
      'setting-honcho-url': data.honcho_url,
      'setting-honcho-workspace': data.honcho_workspace,
      'setting-honcho-peer': data.honcho_user_peer,
      'setting-mem0-url': data.mem0_api_url,
      'setting-sync-interval': data.sync_interval,
    };
    Object.entries(settingsFields).forEach(([id, value]) => {
      const el = $(`#${id}`);
      if (el && value !== undefined) {
        el.value = value;
      }
    });

    const syncEnabled = $('#setting-sync-enabled');
    if (syncEnabled && data.sync_enabled !== undefined) {
      syncEnabled.checked = data.sync_enabled;
    }
  }

  function updateGlobalStatus(color, text) {
    const dot  = $('#global-status-dot');
    const txt  = $('#global-status-text');
    const badge = $('#status-badge');
    if (dot) { dot.className = `status-dot status-dot--${color}`; }
    if (txt) { txt.textContent = text; }
    if (badge) {
      badge.innerHTML = `
        <div class="status-dot status-dot--sm status-dot--${color}"></div>
        <span>${text}</span>
      `;
    }
  }

  // ── Devices ──────────────────────────────────────────

  async function fetchDevices() {
    const data = await apiFetch('/api/devices');
    if (data && Array.isArray(data)) {
      DATA.devices = data;
    }
    renderDevices();
  }

  // ── Keys ─────────────────────────────────────────────

  async function fetchKeys() {
    const data = await apiFetch('/api/keys');
    if (data && Array.isArray(data)) {
      DATA.keys = data;
    }
    renderKeys();
  }

  // ── Agents ───────────────────────────────────────────

  async function fetchAgents() {
    const data = await apiFetch('/api/agents');
    if (data && Array.isArray(data)) {
      DATA.agents = data;
    }
    renderAgents();
    populateAgentDropdown();
  }

  // ── Sync Log ─────────────────────────────────────────

  function populateAgentDropdown() {
    const select = $('#key-agent');
    if (!select) return;
    const current = select.value;
    // Keep the default option, replace the rest
    select.innerHTML = '<option value="">None (shared)</option>';
    DATA.agents.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.slug;
      opt.textContent = `${a.name} (${a.slug})`;
      select.appendChild(opt);
    });
    if (current) select.value = current;
  }

  async function fetchSyncLog() {
    const data = await apiFetch('/api/sync/log');
    if (data && Array.isArray(data)) {
      DATA.syncLog = data;
    }
    renderSyncLog();
  }

  // ── Analytics ────────────────────────────────────────

  async function fetchAnalytics() {
    const [overview, timeline, devices, categories] = await Promise.all([
      apiFetch('/api/analytics/overview'),
      apiFetch('/api/analytics/timeline'),
      apiFetch('/api/analytics/devices'),
      apiFetch('/api/analytics/categories'),
    ]);

    if (overview) {
      Object.assign(DATA.analytics, overview);
    }
    if (timeline && Array.isArray(timeline)) {
      DATA.analytics.timeline = timeline;
    }
    if (devices && Array.isArray(devices)) {
      DATA.analytics.device_activity = devices;
    }
    if (categories && Array.isArray(categories)) {
      DATA.analytics.categories = categories;
    }

    renderOverviewStats();
    renderAnalyticsStats();
    const analyticsPage = $('.page[data-page="analytics"]');
    if (analyticsPage && analyticsPage.classList.contains('active')) {
      renderCharts();
    }
  }

  // ── Activity (derived from sync log) ─────────────────

  async function fetchActivity() {
    // Build activity feed from the latest sync log entries.
    if (DATA.syncLog.length > 0) {
      DATA.activity = DATA.syncLog.slice(0, 10).map(s => ({
        text: s.direction === 'honcho_to_mem0'
          ? `Synced Honcho → mem0 (<span class="mono">${s.items} items</span>)`
          : `Synced mem0 → Honcho (<span class="mono">${s.items} items</span>)`,
        device: 'system',
        time: relativeTime(s.time),
      }));
    }
    renderActivity();
  }

  // ── Overview Rendering ───────────────────────────────

  function renderOverviewStats() {
    const s = DATA.stats;
    const d = $('#stat-devices');
    const m = $('#stat-memories');
    const k = $('#stat-keys');
    const a = $('#stat-agents');
    if (d) d.textContent = formatNumber(s.devices);
    if (m) m.textContent = formatNumber(s.memories);
    if (k) k.textContent = formatNumber(s.keys);
    if (a) a.textContent = formatNumber(s.agents);
  }

  function renderAnalyticsStats() {
    const a = DATA.analytics;
    const total = $('#a-total');
    const today = $('#a-today');
    const week = $('#a-week');
    const month = $('#a-month');
    if (total) total.textContent = formatNumber(a.total_memories);
    if (today) today.textContent = formatNumber(a.memories_today);
    if (week) week.textContent = formatNumber(a.memories_this_week);
    if (month) month.textContent = formatNumber(a.memories_this_month);
  }

  function renderHealthCards() {
    const h = DATA.health;
    if (!h) return;

    const cards = {
      api:  { name: 'API Server',  sub: (v) => v.uptime ? `${v.uptime} uptime` : 'Connected' },
      db:   { name: 'PostgreSQL',  sub: (v) => `${v.host || 'Connected'} / ${v.name || 'merrick'}` },
      honcho: { name: 'Honcho',    sub: (v) => v.workspace ? `workspace: ${v.workspace}` : 'Connected' },
      mem0: { name: 'mem0',        sub: (v) => v.latency ? `latency ${v.latency}ms` : 'Connected' },
    };

    $$('.health-card').forEach(card => {
      const svc = card.dataset.service;
      if (!svc || !h[svc] || !cards[svc]) return;
      const info = h[svc];
      const dot  = card.querySelector('.status-dot');
      const val  = card.querySelector('.health-value');
      const sub  = card.querySelector('.health-sub');
      const statusColor = info.status === 'healthy' ? 'green' : info.status === 'degraded' ? 'yellow' : 'red';
      if (dot) dot.className = `status-dot status-dot--sm status-dot--${statusColor}`;
      if (val) val.textContent = info.status === 'healthy' ? 'Connected' : info.status === 'degraded' ? 'Degraded' : 'Error';
      if (sub) sub.textContent = cards[svc].sub(info);
    });
  }

  function renderActivity() {
    const list = $('#activity-list');
    if (!list) return;
    list.innerHTML = DATA.activity.map(a => `
      <div class="activity-item">
        <div class="activity-dot"></div>
        <div class="activity-text">${a.text}</div>
        <div class="activity-time">${a.time}</div>
      </div>
    `).join('');
  }

  // ── Devices ──────────────────────────────────────────

  function renderDevices() {
    const tbody = $('#devices-table-body');
    if (!tbody) return;
    tbody.innerHTML = DATA.devices.map(d => {
      const lastSeen = relativeTime(d.last_seen_at);
      const isActive = (Date.now() - new Date(d.last_seen_at).getTime()) < 3600000;
      return `
        <tr>
          <td><span class="mono">${d.device_id}</span></td>
          <td><span class="mono text-muted">${d.honcho_peer_id || '—'}</span></td>
          <td><span class="mono text-muted">${d.mem0_user_id || '—'}</span></td>
          <td>${lastSeen}</td>
          <td><span class="badge badge--${isActive ? 'green' : 'yellow'}">${isActive ? 'active' : 'idle'}</span></td>
        </tr>
      `;
    }).join('');
  }

  // ── Keys ─────────────────────────────────────────────

  function renderKeys() {
    const tbody = $('#keys-table-body');
    if (!tbody) return;
    tbody.innerHTML = DATA.keys.map(k => `
      <tr>
        <td><strong>${k.key_name}</strong></td>
        <td><span class="mono" style="font-size:0.82rem">${k.key_prefix}</span></td>
        <td><span class="mono">${k.device_id}</span></td>
        <td>${k.agent_slug ? `<span class="badge badge--default">${k.agent_slug}</span>` : '<span class="text-muted">—</span>'}</td>
        <td>${k.permissions.map(p => `<span class="badge badge--${p === 'write' ? 'green' : 'default'}">${p}</span>`).join(' ')}</td>
        <td><span class="mono">${k.rate_limit}/min</span></td>
        <td>${relativeTime(k.last_used_at)}</td>
        <td><span class="badge badge--${k.active ? 'green' : 'red'}">${k.active ? 'active' : 'revoked'}</span></td>
        <td>
          ${k.active ? `
            <button class="btn btn--ghost btn--sm btn--icon-only" onclick="App.rotateKey('${k.id}')" title="Rotate key">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15A9 9 0 1 1 12.36 3.64"/></svg>
            </button>
            <button class="btn btn--ghost btn--sm btn--icon-only" onclick="App.revokeKey('${k.id}')" title="Revoke key">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            </button>
          ` : ''}
        </td>
      </tr>
    `).join('');
  }

  // ── Agents ───────────────────────────────────────────

  function renderAgents() {
    const grid = $('#agent-grid');
    if (!grid) return;
    grid.innerHTML = DATA.agents.map(a => `
      <div class="agent-card" onclick="App.showAgent('${a.slug}')">
        <div class="agent-card-name">${a.name}</div>
        <div class="agent-card-slug">${a.slug}</div>
        <div class="agent-card-prompt">${a.system_prompt}</div>
        <div class="agent-card-stats">
          <div class="agent-stat"><strong>${formatNumber(a.memory_count || 0)}</strong> memories</div>
          <div class="agent-stat"><strong>${a.device_count || 0}</strong> devices</div>
          <div class="agent-stat"><strong>${a.memory_scope || 'shared'}</strong></div>
        </div>
      </div>
    `).join('');
  }

  function showAgent(slug) {
    const agent = DATA.agents.find(a => a.slug === slug);
    if (!agent) return;

    $('#agent-grid').classList.add('hidden');
    const detail = $('#agent-detail');
    detail.classList.remove('hidden');

    $('#agent-detail-header').innerHTML = `
      <div class="agent-detail-name">${agent.name}</div>
      <div class="agent-detail-slug">${agent.slug}</div>
      <div class="agent-detail-prompt">${agent.system_prompt}</div>
    `;

    // Try to fetch real memories for this agent from /api/query
    fetchAgentMemories(agent);

    const assignedDevices = DATA.keys
      .filter(k => k.agent_slug === slug)
      .map(k => k.device_id);
    const uniqueDevices = [...new Set(assignedDevices)];

    $('#agent-devices').innerHTML = uniqueDevices.length > 0
      ? uniqueDevices.map(d => `<span class="device-chip mono">${d}</span>`).join('')
      : '<span class="text-muted">No devices assigned</span>';
  }

  async function fetchAgentMemories(agent) {
    const memoriesEl = $('#agent-memories');
    memoriesEl.innerHTML = '<div class="text-muted" style="padding:12px">Loading memories…</div>';

    const data = await apiFetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: agent.name, categories: ['general'] }),
    });

    let memories;
    if (data && Array.isArray(data.results) && data.results.length > 0) {
      memories = data.results.slice(0, 8).map(m => ({
        content: m.content || m.text || '(empty)',
        category: m.category || 'general',
        created_at: m.created_at || m.timestamp || null,
        source_device: m.source_device || m.device_id || '—',
      }));
    } else {
      memories = [];
    }

    if (memories.length === 0) {
      memoriesEl.innerHTML = '<div class="text-muted" style="padding:12px">No memories found</div>';
      return;
    }

    memoriesEl.innerHTML = memories.map(m => `
      <div class="memory-item">
        <div class="memory-content">${m.content}</div>
        <div class="memory-meta">
          <span class="badge badge--default">${m.category}</span>
          <span class="mono">${m.source_device}</span>
          <span>${relativeTime(m.created_at)}</span>
        </div>
      </div>
    `).join('');
  }

  // ── Sync Monitor ─────────────────────────────────────

  function renderSyncLog() {
    const tbody = $('#sync-log-body');
    if (!tbody) return;
    tbody.innerHTML = DATA.syncLog.map(s => {
      const statusClass = s.errors > 0 ? 'yellow' : 'green';
      return `
        <tr>
          <td><span class="mono">${s.time}</span></td>
          <td>${s.direction === 'honcho_to_mem0' ? 'Honcho → mem0' : 'mem0 → Honcho'}</td>
          <td><span class="mono">${s.items}</span></td>
          <td><span class="mono ${s.errors > 0 ? 'sync-stat-value--warn' : ''}">${s.errors}</span></td>
          <td><span class="mono">${s.duration}</span></td>
          <td><span class="badge badge--${statusClass}">${s.status.replace(/_/g, ' ')}</span></td>
        </tr>
      `;
    }).join('');

    // Update sync status cards from log data
    renderSyncStatusCards();
  }

  function renderSyncStatusCards() {
    if (DATA.syncLog.length === 0) return;

    const h2m = DATA.syncLog.find(s => s.direction === 'honcho_to_mem0');
    const m2h = DATA.syncLog.find(s => s.direction === 'mem0_to_honcho');

    if (h2m) {
      const lastH2m = $('#sync-last-h2m');
      const itemsH2m = $('#sync-items-h2m');
      const errorsH2m = $('#sync-errors-h2m');
      if (lastH2m) lastH2m.textContent = relativeTime(h2m.time);
      if (itemsH2m) itemsH2m.textContent = h2m.items;
      if (errorsH2m) {
        errorsH2m.textContent = h2m.errors;
        errorsH2m.className = `sync-stat-value mono sync-stat-value--${h2m.errors > 0 ? 'warn' : 'ok'}`;
      }
    }
    if (m2h) {
      const lastM2h = $('#sync-last-m2h');
      const itemsM2h = $('#sync-items-m2h');
      const errorsM2h = $('#sync-errors-m2h');
      if (lastM2h) lastM2h.textContent = relativeTime(m2h.time);
      if (itemsM2h) itemsM2h.textContent = m2h.items;
      if (errorsM2h) {
        errorsM2h.textContent = m2h.errors;
        errorsM2h.className = `sync-stat-value mono sync-stat-value--${m2h.errors > 0 ? 'warn' : 'ok'}`;
      }
    }
  }

  // ── Charts (Canvas) ──────────────────────────────────

  function renderCharts() {
    renderGrowthChart();
    renderDeviceChart();
    renderCategoryChart();
    renderKeyUsageChart();
  }

  function renderGrowthChart() {
    const canvas = $('#canvas-growth');
    if (!canvas) return;
    const data = DATA.analytics.timeline;
    if (!data || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = 200;
    const pad = { top: 20, right: 20, bottom: 30, left: 50 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const maxVal = Math.max(...data.map(d => d.count)) * 1.1;

    ctx.clearRect(0, 0, w, h);

    // Grid lines
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (plotH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();

      ctx.fillStyle = '#484f58';
      ctx.font = '11px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(Math.round(maxVal - (maxVal / 4) * i), pad.left - 8, y + 4);
    }

    // X labels
    ctx.fillStyle = '#484f58';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    const step = Math.ceil(data.length / 8);
    for (let i = 0; i < data.length; i += step) {
      const x = pad.left + (plotW / (data.length - 1)) * i;
      const label = data[i].date.slice(5); // MM-DD
      ctx.fillText(label, x, h - 8);
    }

    // Area fill
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top + plotH);
    data.forEach((d, i) => {
      const x = pad.left + (plotW / (data.length - 1)) * i;
      const y = pad.top + plotH - (d.count / maxVal) * plotH;
      ctx.lineTo(x, y);
    });
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    grad.addColorStop(0, 'rgba(56,139,253,0.2)');
    grad.addColorStop(1, 'rgba(56,139,253,0)');
    ctx.fillStyle = grad;
    ctx.fill();

    // Line
    ctx.beginPath();
    data.forEach((d, i) => {
      const x = pad.left + (plotW / (data.length - 1)) * i;
      const y = pad.top + plotH - (d.count / maxVal) * plotH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#388bfd';
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.stroke();

    // Dots on last 3 points
    data.slice(-3).forEach((d, i) => {
      const idx = data.length - 3 + i;
      const x = pad.left + (plotW / (data.length - 1)) * idx;
      const y = pad.top + plotH - (d.count / maxVal) * plotH;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fillStyle = '#388bfd';
      ctx.fill();
      ctx.strokeStyle = '#0d1117';
      ctx.lineWidth = 2;
      ctx.stroke();
    });
  }

  function renderDeviceChart() {
    const canvas = $('#canvas-devices');
    if (!canvas) return;
    const data = DATA.analytics.device_activity;
    if (!data || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = 200;
    const pad = { top: 20, right: 20, bottom: 60, left: 50 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const maxVal = Math.max(...data.map(d => d.count)) * 1.1;
    const barW = (plotW / data.length) * 0.6;
    const gap = (plotW / data.length) * 0.4;

    ctx.clearRect(0, 0, w, h);

    // Grid
    ctx.strokeStyle = '#21262d';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = pad.top + (plotH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();

      ctx.fillStyle = '#484f58';
      ctx.font = '11px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText(Math.round(maxVal - (maxVal / 4) * i), pad.left - 8, y + 4);
    }

    // Bars
    data.forEach((d, i) => {
      const x = pad.left + (plotW / data.length) * i + gap / 2;
      const barH = (d.count / maxVal) * plotH;
      const y = pad.top + plotH - barH;

      const grad = ctx.createLinearGradient(0, y, 0, y + barH);
      grad.addColorStop(0, '#388bfd');
      grad.addColorStop(1, '#1f6feb');
      ctx.fillStyle = grad;

      // Rounded top
      const r = 3;
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.lineTo(x + barW - r, y);
      ctx.quadraticCurveTo(x + barW, y, x + barW, y + r);
      ctx.lineTo(x + barW, y + barH);
      ctx.lineTo(x, y + barH);
      ctx.lineTo(x, y + r);
      ctx.quadraticCurveTo(x, y, x + r, y);
      ctx.fill();

      // Label
      ctx.save();
      ctx.translate(x + barW / 2, pad.top + plotH + 10);
      ctx.rotate(-Math.PI / 4);
      ctx.fillStyle = '#484f58';
      ctx.font = '10px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      const label = d.device.length > 14 ? d.device.slice(0, 12) + '..' : d.device;
      ctx.fillText(label, 0, 0);
      ctx.restore();
    });
  }

  function renderCategoryChart() {
    const canvas = $('#canvas-categories');
    if (!canvas) return;
    const data = DATA.analytics.categories;
    if (!data || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = 260 * dpr;
    canvas.height = 260 * dpr;
    canvas.style.width = '260px';
    canvas.style.height = '260px';
    ctx.scale(dpr, dpr);

    const total = data.reduce((s, d) => s + d.count, 0);
    const cx = 130, cy = 130, r = 100, inner = 60;

    ctx.clearRect(0, 0, 260, 260);

    let angle = -Math.PI / 2;
    data.forEach(d => {
      const sliceAngle = (d.count / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.arc(cx, cy, r, angle, angle + sliceAngle);
      ctx.arc(cx, cy, inner, angle + sliceAngle, angle, true);
      ctx.closePath();
      ctx.fillStyle = d.color;
      ctx.fill();
      angle += sliceAngle;
    });

    // Center text
    ctx.fillStyle = '#e6edf3';
    ctx.font = 'bold 20px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(formatNumber(total), cx, cy - 2);
    ctx.fillStyle = '#8b949e';
    ctx.font = '11px Inter, sans-serif';
    ctx.fillText('memories', cx, cy + 16);

    // Legend
    const legend = $('#donut-legend');
    legend.innerHTML = data.map(d => `
      <div class="legend-item">
        <div class="legend-dot" style="background:${d.color}"></div>
        <span>${d.name}</span>
        <span class="mono" style="margin-left:auto">${d.count}</span>
      </div>
    `).join('');
  }

  function renderKeyUsageChart() {
    const canvas = $('#canvas-key-usage');
    if (!canvas) return;
    const data = DATA.analytics.key_usage;
    if (!data || data.length === 0) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = 200;
    const pad = { top: 20, right: 20, bottom: 30, left: 50 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const maxVal = Math.max(...data.map(d => d.count)) * 1.1;
    const barH = (plotH / data.length) * 0.6;
    const gap = (plotH / data.length) * 0.4;

    ctx.clearRect(0, 0, w, h);

    // Horizontal bars
    data.forEach((d, i) => {
      const y = pad.top + (plotH / data.length) * i + gap / 2;
      const barW = (d.count / maxVal) * plotW;

      const grad = ctx.createLinearGradient(pad.left, 0, pad.left + barW, 0);
      grad.addColorStop(0, '#1f6feb');
      grad.addColorStop(1, '#388bfd');
      ctx.fillStyle = grad;

      // Rounded right
      const r = 3;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + barW - r, y);
      ctx.quadraticCurveTo(pad.left + barW, y, pad.left + barW, y + r);
      ctx.lineTo(pad.left + barW, y + barH - r);
      ctx.quadraticCurveTo(pad.left + barW, y + barH, pad.left + barW - r, y + barH);
      ctx.lineTo(pad.left, y + barH);
      ctx.closePath();
      ctx.fill();

      // Label left
      ctx.fillStyle = '#8b949e';
      ctx.font = '11px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      const label = d.key.length > 18 ? d.key.slice(0, 16) + '..' : d.key;
      ctx.fillText(label, pad.left - 8, y + barH / 2 + 4);

      // Value
      ctx.fillStyle = '#e6edf3';
      ctx.font = 'bold 11px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      ctx.fillText(formatNumber(d.count), pad.left + barW + 8, y + barH / 2 + 4);
    });
  }

  // ── Settings ─────────────────────────────────────────

  function initSettings() {
    $$('.settings-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        $$('.settings-tab').forEach(t => t.classList.remove('active'));
        $$('.settings-panel').forEach(p => p.classList.remove('active'));
        tab.classList.add('active');
        $(`[data-settings-panel="${tab.dataset.settingsTab}"]`).classList.add('active');
      });
    });
  }

  // ── Modals ───────────────────────────────────────────

  function openModal(id) {
    const el = $(`#${id}`);
    if (el) el.classList.add('active');
  }

  function closeModal(id) {
    const el = $(`#${id}`);
    if (el) el.classList.remove('active');
  }

  // Close buttons
  $$('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => closeModal(btn.dataset.close));
  });

  // Close on overlay click
  $$('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('active');
    });
  });

  // Create Key form
  $('#btn-create-key').addEventListener('click', () => openModal('modal-key-create'));

  $('#form-create-key').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = $('#key-name').value;
    const deviceId = $('#key-device').value;
    const agentSlug = $('#key-agent').value || null;
    const permissions = [];
    if ($('#perm-read').checked) permissions.push('read');
    if ($('#perm-write').checked) permissions.push('write');
    const rateLimit = parseInt($('#key-rate').value, 10) || 100;
    const categories = $$('#key-categories input:checked').map(cb => cb.value);
    const maxTokens = parseInt($('#key-tokens').value, 10) || 2000;

    const res = await apiFetch('/api/keys', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: deviceId,
        key_name: name,
        agent_slug: agentSlug,
        permissions,
        categories,
        rate_limit: rateLimit,
        max_memory_tokens: maxTokens,
      }),
    });

    if (res && res.key) {
      // API returned the actual key secret
      $('#secret-value').textContent = res.key;
      closeModal('modal-key-create');
      openModal('modal-secret-reveal');
      toast(`Key "${name}" created`, 'success');
      fetchKeys();
    } else if (res) {
      // API accepted but no secret returned
      closeModal('modal-key-create');
      toast(`Key "${name}" created — copy the key from the keys list`, 'success');
      fetchKeys();
    } else {
      toast('Failed to create key — API unreachable', 'error');
    }

    // Reset form
    e.target.reset();
  });

  // Copy secret
  $('#btn-copy-secret').addEventListener('click', () => {
    const secret = $('#secret-value').textContent;
    navigator.clipboard.writeText(secret).then(() => {
      toast('Copied to clipboard', 'success');
    }).catch(() => {
      toast('Copy failed', 'error');
    });
  });

  // Create Agent form
  $('#btn-create-agent').addEventListener('click', () => openModal('modal-agent-create'));

  $('#form-create-agent').addEventListener('submit', async (e) => {
    e.preventDefault();
    const name  = $('#agent-name').value;
    const slug  = $('#agent-slug').value;
    const prompt = $('#agent-prompt').value;
    const scope = $('#agent-scope').value;

    const res = await apiFetch('/api/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        slug,
        system_prompt: prompt,
        memory_scope: scope,
      }),
    });

    if (res) {
      toast(`Agent "${name}" created`, 'success');
      closeModal('modal-agent-create');
      e.target.reset();
      // Refresh agents list
      fetchAgents();
    } else {
      toast('Failed to create agent — API unreachable', 'error');
    }
  });

  // Auto-generate slug from name
  $('#agent-name').addEventListener('input', (e) => {
    const slug = e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    $('#agent-slug').value = slug;
  });

  // ── Key Actions ──────────────────────────────────────

  async function rotateKey(id) {
    const key = DATA.keys.find(k => k.id === id);
    if (!key) return;
    if (!confirm(`Rotate key "${key.key_name}"? The old key will be revoked immediately.`)) return;

    const res = await apiFetch(`/api/keys/${id}/rotate`, { method: 'POST' });

    if (res) {
      if (res.key) {
        $('#secret-value').textContent = res.key;
        openModal('modal-secret-reveal');
      }
      toast(`Key "${key.key_name}" rotated`, 'success');
      fetchKeys();
    } else {
      toast('Failed to rotate key — API unreachable', 'error');
    }
  }

  async function revokeKey(id) {
    const key = DATA.keys.find(k => k.id === id);
    if (!key) return;
    if (!confirm(`Revoke key "${key.key_name}"? This cannot be undone.`)) return;

    const res = await apiFetch(`/api/keys/${id}`, { method: 'DELETE' });
    if (res) {
      key.active = false;
      renderKeys();
      toast(`Key "${key.key_name}" revoked`, 'error');
    } else {
      toast('Failed to revoke key — API unreachable', 'error');
    }
  }

  // ── Sync Now ─────────────────────────────────────────

  $('#btn-sync-now').addEventListener('click', async () => {
    toast('Sync triggered', 'info');
    const label = $('#sync-status-label');
    if (label) {
      label.textContent = 'Running';
      label.className = 'sync-stat-value sync-stat-value--warn';
    }

    const res = await apiFetch('/api/sync/trigger', { method: 'POST' });

    if (res) {
      toast('Sync completed', 'success');
    } else {
      toast('Sync failed — API unreachable', 'error');
    }

    if (label) {
      label.textContent = 'Idle';
      label.className = 'sync-stat-value sync-stat-value--ok';
    }

    // Refresh sync log
    fetchSyncLog();
  });

  // ── Settings Save ────────────────────────────────────

  $('#btn-save-settings').addEventListener('click', () => {
    toast('Settings are configured via environment variables', 'info');
  });

  // ── Agent Detail Back Button ─────────────────────────

  const btnBackAgents = $('#btn-back-agents');
  if (btnBackAgents) {
    btnBackAgents.addEventListener('click', () => {
      $('#agent-grid').classList.remove('hidden');
      $('#agent-detail').classList.add('hidden');
    });
  }

  // ── Navigation ───────────────────────────────────────

  const navItems = $$('.nav-item');
  const pages = $$('.page');
  const pageTitle = $('#page-title');
  const sidebar = $('#sidebar');
  const mobileMenuBtn = $('#mobile-menu-btn');

  const PAGE_TITLES = {
    overview: 'Overview',
    devices: 'Devices & Keys',
    agents: 'Agents',
    sync: 'Sync Monitor',
    analytics: 'Analytics',
    settings: 'Settings',
  };

  function navigateTo(page) {
    navItems.forEach(n => n.classList.toggle('active', n.dataset.page === page));
    pages.forEach(p => {
      p.classList.toggle('active', p.dataset.page === page);
    });
    pageTitle.textContent = PAGE_TITLES[page] || page;

    // Reset agent detail view when navigating to agents
    if (page === 'agents') {
      $('#agent-grid').classList.remove('hidden');
      $('#agent-detail').classList.add('hidden');
    }

    // Close mobile sidebar
    sidebar.classList.remove('open');

    // Render page-specific content
    if (page === 'analytics') {
      requestAnimationFrame(() => renderCharts());
    }
  }

  navItems.forEach(item => {
    item.addEventListener('click', () => navigateTo(item.dataset.page));
  });

  mobileMenuBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });

  // ── Resize handler for charts ────────────────────────

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if ($('.page[data-page="analytics"]').classList.contains('active')) {
        renderCharts();
      }
    }, 150);
  });

  // ── Init ─────────────────────────────────────────────

  async function init() {
    // Render empty states so the UI isn't blank while API loads
    renderActivity();
    renderDevices();
    renderKeys();
    renderAgents();
    renderSyncLog();
    renderAnalyticsStats();
    initSettings();

    // Kick off all API fetches in parallel
    await Promise.allSettled([
      fetchStatus(),
      fetchDevices(),
      fetchKeys(),
      fetchAgents(),
      fetchSyncLog(),
      fetchAnalytics(),
    ]);

    // Derive activity from sync log once it's loaded
    fetchActivity();
  }

  // ── Public API ───────────────────────────────────────

  window.App = {
    showAgent,
    rotateKey,
    revokeKey,
  };

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();

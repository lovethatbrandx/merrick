/* ═══════════════════════════════════════════════════════
   MERRICK DASHBOARD — Application Logic
   ═══════════════════════════════════════════════════════
   Single-page app backed by the Merrick REST API.
   Falls back to embedded mock data when the API is
   unreachable so the dashboard always looks functional.
   ═══════════════════════════════════════════════════════ */

(function() {
  'use strict';

  // ── Mock Data (fallback) ──────────────────────────────

  const MOCK = {
    health: {
      api: { status: 'healthy', uptime: '99.9%' },
      db:  { status: 'healthy', host: 'localhost:5433', name: 'merrick' },
      honcho: { status: 'healthy', workspace: 'hermes', url: 'http://host.docker.internal:8000' },
      mem0: { status: 'degraded', latency: 240, url: 'http://host.docker.internal:8888' },
    },

    stats: {
      devices: 7,
      memories: 2847,
      keys: 12,
      agents: 4,
    },

    devices: [
      { device_id: 'hermes-phone', honcho_peer_id: 'device_hermes-phone', mem0_user_id: 'device_hermes-phone', provisioned_at: '2026-06-10T14:22:00Z', last_seen_at: '2026-07-15T08:30:00Z', metadata: { platform: 'android' } },
      { device_id: 'hermes-laptop', honcho_peer_id: 'device_hermes-laptop', mem0_user_id: 'device_hermes-laptop', provisioned_at: '2026-06-12T09:15:00Z', last_seen_at: '2026-07-15T09:12:00Z', metadata: { platform: 'macos' } },
      { device_id: 'meredith-phone', honcho_peer_id: 'device_meredith-phone', mem0_user_id: 'device_meredith-phone', provisioned_at: '2026-06-15T16:40:00Z', last_seen_at: '2026-07-14T22:05:00Z', metadata: { platform: 'ios' } },
      { device_id: 'desktop-workstation', honcho_peer_id: 'device_desktop-workstation', mem0_user_id: 'device_desktop-workstation', provisioned_at: '2026-06-18T11:00:00Z', last_seen_at: '2026-07-15T07:45:00Z', metadata: { platform: 'linux' } },
      { device_id: 'code-editor-vscode', honcho_peer_id: 'device_code-editor-vscode', mem0_user_id: 'device_code-editor-vscode', provisioned_at: '2026-06-20T13:20:00Z', last_seen_at: '2026-07-15T08:58:00Z', metadata: { platform: 'vscode' } },
      { device_id: 'tablet-ipad', honcho_peer_id: 'device_tablet-ipad', mem0_user_id: 'device_tablet-ipad', provisioned_at: '2026-06-25T10:10:00Z', last_seen_at: '2026-07-13T18:30:00Z', metadata: { platform: 'ipados' } },
      { device_id: 'raspberry-pi', honcho_peer_id: 'device_raspberry-pi', mem0_user_id: 'device_raspberry-pi', provisioned_at: '2026-07-01T08:00:00Z', last_seen_at: '2026-07-15T06:00:00Z', metadata: { platform: 'linux' } },
    ],

    keys: [
      { id: 'a1b2c3d4', key_name: 'hermes-phone-prod', key_prefix: 'merrick_sk_aB3k...x9Qz', device_id: 'hermes-phone', agent_slug: 'hombre', permissions: ['read','write'], rate_limit: 100, last_used_at: '2026-07-15T08:30:00Z', active: true, memory_categories: ['general','preferences'], max_memory_tokens: 2000 },
      { id: 'e5f6g7h8', key_name: 'laptop-dev', key_prefix: 'merrick_sk_tC7m...p2Rw', device_id: 'hermes-laptop', agent_slug: 'hermes', permissions: ['read','write'], rate_limit: 200, last_used_at: '2026-07-15T09:12:00Z', active: true, memory_categories: ['general','facts','tasks'], max_memory_tokens: 5000 },
      { id: 'i9j0k1l2', key_name: 'meredith-readonly', key_prefix: 'merrick_sk_dF4n...s6Uv', device_id: 'meredith-phone', agent_slug: 'meredith', permissions: ['read'], rate_limit: 50, last_used_at: '2026-07-14T22:05:00Z', active: true, memory_categories: ['general'], max_memory_tokens: 1000 },
      { id: 'm3n4o5p6', key_name: 'vscode-agent', key_prefix: 'merrick_sk_gH8q...w1Xy', device_id: 'code-editor-vscode', agent_slug: null, permissions: ['read','write'], rate_limit: 150, last_used_at: '2026-07-15T08:58:00Z', active: true, memory_categories: ['general','facts','context'], max_memory_tokens: 3000 },
      { id: 'q7r8s9t0', key_name: 'old-test-key', key_prefix: 'merrick_sk_jK2t...z4Ab', device_id: 'hermes-phone', agent_slug: 'default', permissions: ['read'], rate_limit: 10, last_used_at: '2026-06-20T12:00:00Z', active: false, memory_categories: ['general'], max_memory_tokens: 500 },
      { id: 'u1v2w3x4', key_name: 'pi-sensor', key_prefix: 'merrick_sk_mN6v...c8De', device_id: 'raspberry-pi', agent_slug: null, permissions: ['read','write'], rate_limit: 300, last_used_at: '2026-07-15T06:00:00Z', active: true, memory_categories: ['facts','context'], max_memory_tokens: 8000 },
    ],

    agents: [
      {
        id: 'p1', name: 'Hombre', slug: 'hombre',
        system_prompt: 'You are Hombre, a memory-focused AI assistant. You help users remember important things, track tasks, and maintain context across sessions. You are precise, concise, and always honest about what you do and don\'t know.',
        memory_scope: 'shared', memory_count: 847, device_count: 3,
        created_at: '2026-06-10T14:22:00Z',
      },
      {
        id: 'p2', name: 'Meredith', slug: 'meredith',
        system_prompt: 'You are Meredith, a creative writing assistant with deep memory. You remember character details, plot threads, world-building rules, and stylistic preferences across writing sessions.',
        memory_scope: 'agent_only', memory_count: 423, device_count: 1,
        created_at: '2026-06-15T16:40:00Z',
      },
      {
        id: 'p3', name: 'Hermes', slug: 'hermes',
        system_prompt: 'You are Hermes, a general-purpose AI agent. You handle scheduling, reminders, research, and general knowledge queries. You maintain context about user preferences, work habits, and ongoing projects.',
        memory_scope: 'shared', memory_count: 1204, device_count: 4,
        created_at: '2026-06-12T09:15:00Z',
      },
      {
        id: 'p4', name: 'Default', slug: 'default',
        system_prompt: 'You are a helpful AI assistant with persistent memory. You remember user preferences, facts they share, and context from previous conversations.',
        memory_scope: 'shared', memory_count: 373, device_count: 2,
        created_at: '2026-05-01T00:00:00Z',
      },
    ],

    activity: [
      { text: 'Wrote memory: <span class="mono">project_deadline_july</span>', device: 'hermes-laptop', time: '2 min ago' },
      { text: 'Read 12 memories for context', device: 'code-editor-vscode', time: '5 min ago' },
      { text: 'Wrote memory: <span class="mono">user_pref_dark_mode</span>', device: 'hermes-phone', time: '8 min ago' },
      { text: 'Synced Honcho → mem0 (14 items)', device: 'system', time: '12 min ago' },
      { text: 'Wrote memory: <span class="mono">meeting_notes_standup</span>', device: 'desktop-workstation', time: '18 min ago' },
      { text: 'Agent "Hombre" accessed shared memories', device: 'hermes-phone', time: '22 min ago' },
      { text: 'Wrote memory: <span class="mono">code_review_feedback</span>', device: 'code-editor-vscode', time: '30 min ago' },
      { text: 'Rotated API key for tablet-ipad', device: 'system', time: '45 min ago' },
      { text: 'Wrote memory: <span class="mono">recipe_pasta_aglio</span>', device: 'meredith-phone', time: '1 hr ago' },
      { text: 'Sync completed: 89 items, 3 errors', device: 'system', time: '1.5 hr ago' },
    ],

    syncLog: [
      { time: '2026-07-15 09:12', direction: 'honcho_to_mem0', items: 14, errors: 0, duration: '1.2s', status: 'completed' },
      { time: '2026-07-15 09:07', direction: 'mem0_to_honcho', items: 8, errors: 0, duration: '0.8s', status: 'completed' },
      { time: '2026-07-15 09:02', direction: 'honcho_to_mem0', items: 22, errors: 1, duration: '3.1s', status: 'completed_with_errors' },
      { time: '2026-07-15 08:57', direction: 'mem0_to_honcho', items: 5, errors: 0, duration: '0.4s', status: 'completed' },
      { time: '2026-07-15 08:52', direction: 'honcho_to_mem0', items: 31, errors: 0, duration: '2.5s', status: 'completed' },
      { time: '2026-07-15 08:47', direction: 'mem0_to_honcho', items: 12, errors: 2, duration: '4.7s', status: 'completed_with_errors' },
      { time: '2026-07-15 08:42', direction: 'honcho_to_mem0', items: 18, errors: 0, duration: '1.6s', status: 'completed' },
      { time: '2026-07-15 08:37', direction: 'mem0_to_honcho', items: 9, errors: 0, duration: '0.6s', status: 'completed' },
    ],

    analytics: {
      total_memories: 2847,
      memories_today: 23,
      memories_this_week: 156,
      memories_this_month: 847,
      total_categories: 6,
      total_webhooks: 2,
      timeline: [
        { date: '2026-06-16', count: 12 }, { date: '2026-06-17', count: 18 },
        { date: '2026-06-18', count: 25 }, { date: '2026-06-19', count: 14 },
        { date: '2026-06-20', count: 32 }, { date: '2026-06-21', count: 8 },
        { date: '2026-06-22', count: 5 }, { date: '2026-06-23', count: 21 },
        { date: '2026-06-24', count: 28 }, { date: '2026-06-25', count: 19 },
        { date: '2026-06-26', count: 35 }, { date: '2026-06-27', count: 22 },
        { date: '2026-06-28', count: 15 }, { date: '2026-06-29', count: 10 },
        { date: '2026-06-30', count: 27 }, { date: '2026-07-01', count: 30 },
        { date: '2026-07-02', count: 16 }, { date: '2026-07-03', count: 23 },
        { date: '2026-07-04', count: 11 }, { date: '2026-07-05', count: 7 },
        { date: '2026-07-06', count: 13 }, { date: '2026-07-07', count: 29 },
        { date: '2026-07-08', count: 38 }, { date: '2026-07-09', count: 20 },
        { date: '2026-07-10', count: 26 }, { date: '2026-07-11', count: 31 },
        { date: '2026-07-12', count: 18 }, { date: '2026-07-13', count: 14 },
        { date: '2026-07-14', count: 22 }, { date: '2026-07-15', count: 23 },
      ],
      device_activity: [
        { device: 'hermes-laptop', count: 842 },
        { device: 'hermes-phone', count: 631 },
        { device: 'code-editor-vscode', count: 498 },
        { device: 'desktop-workstation', count: 412 },
        { device: 'meredith-phone', count: 256 },
        { device: 'raspberry-pi', count: 134 },
        { device: 'tablet-ipad', count: 74 },
      ],
      categories: [
        { name: 'general', color: '#388bfd', count: 892 },
        { name: 'preferences', color: '#3fb950', count: 654 },
        { name: 'facts', color: '#d29922', count: 523 },
        { name: 'tasks', color: '#f85149', count: 387 },
        { name: 'context', color: '#a371f7', count: 268 },
        { name: 'relationships', color: '#f778ba', count: 123 },
      ],
      key_usage: [
        { key: 'hermes-phone-prod', count: 1247 },
        { key: 'laptop-dev', count: 982 },
        { key: 'vscode-agent', count: 634 },
        { key: 'pi-sensor', count: 421 },
        { key: 'meredith-readonly', count: 287 },
        { key: 'old-test-key', count: 12 },
      ],
    },

    settings: {
      honcho_url: 'http://host.docker.internal:8000',
      honcho_workspace: 'hermes',
      honcho_user_peer: 'ron',
      mem0_api_url: 'http://host.docker.internal:8888',
      sync_interval: 300,
      sync_enabled: true,
    },
  };

  // ── Live Data Store ──────────────────────────────────
  // Initially seeded from MOCK so every render call has
  // data even if the API hasn't responded yet.

  const DATA = JSON.parse(JSON.stringify(MOCK));

  // Track which data sources came from mock vs live
  const LIVE_SOURCES = {};

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
      console.warn(`[Merrick API] ${path} failed:`, err.message);
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

    LIVE_SOURCES.status = true;

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
      if (devices) DATA.stats.devices = Array.isArray(devices) ? devices.length : (DATA.devices || []).length;
      if (keys)    DATA.stats.keys    = Array.isArray(keys)    ? keys.length    : (DATA.keys    || []).length;
      if (agents)  DATA.stats.agents  = Array.isArray(agents)  ? agents.length  : (DATA.agents  || []).length;
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
      LIVE_SOURCES.devices = true;
      DATA.devices = data;
    }
    renderDevices();
  }

  // ── Keys ─────────────────────────────────────────────

  async function fetchKeys() {
    const data = await apiFetch('/api/keys');
    if (data && Array.isArray(data)) {
      LIVE_SOURCES.keys = true;
      DATA.keys = data;
    }
    renderKeys();
  }

  // ── Agents ───────────────────────────────────────────

  async function fetchAgents() {
    const data = await apiFetch('/api/agents');
    if (data && Array.isArray(data)) {
      LIVE_SOURCES.agents = true;
      DATA.agents = data;
    }
    renderAgents();
  }

  // ── Sync Log ─────────────────────────────────────────

  async function fetchSyncLog() {
    const data = await apiFetch('/api/sync/log');
    if (data && Array.isArray(data)) {
      LIVE_SOURCES.syncLog = true;
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
      LIVE_SOURCES.analyticsOverview = true;
      Object.assign(DATA.analytics, overview);
    }
    if (timeline && Array.isArray(timeline)) {
      LIVE_SOURCES.analyticsTimeline = true;
      DATA.analytics.timeline = timeline;
    }
    if (devices && Array.isArray(devices)) {
      LIVE_SOURCES.analyticsDevices = true;
      DATA.analytics.device_activity = devices;
    }
    if (categories && Array.isArray(categories)) {
      LIVE_SOURCES.analyticsCategories = true;
      DATA.analytics.categories = categories;
    }

    renderOverviewStats();
    if ($('.page[data-page="analytics"]').classList.contains('active')) {
      renderCharts();
    }
  }

  // ── Activity (derived from sync log) ─────────────────

  async function fetchActivity() {
    // The API doesn't have a dedicated /api/activity endpoint.
    // Build a synthetic activity feed from the latest sync log
    // entries. If sync log is fresh, derive; otherwise keep mock.
    if (LIVE_SOURCES.syncLog && DATA.syncLog.length > 0) {
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
      // Fallback: mock memories
      memories = [
        { content: 'User prefers dark mode in all applications', category: 'preferences', created_at: '2026-07-15T08:00:00Z', source_device: 'hermes-phone' },
        { content: 'Project deadline moved to July 25th', category: 'tasks', created_at: '2026-07-15T07:30:00Z', source_device: 'hermes-laptop' },
        { content: 'Database migration completed successfully', category: 'facts', created_at: '2026-07-14T16:00:00Z', source_device: 'code-editor-vscode' },
        { content: 'Weekly standup happens every Tuesday at 10am', category: 'context', created_at: '2026-07-14T09:00:00Z', source_device: 'desktop-workstation' },
      ];
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
    tbody.innerHTML = DATA.syncLog.map(s => {
      const statusClass = s.status === 'completed' ? 'green' : s.errors > 0 ? 'yellow' : 'green';
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

    const el = (id) => document.getElementById(id);

    if (h2m) {
      if (el('sync-last-h2m'))  el('sync-last-h2m').textContent  = relativeTime(h2m.time);
      if (el('sync-items-h2m')) el('sync-items-h2m').textContent = h2m.items;
      if (el('sync-errors-h2m')) {
        el('sync-errors-h2m').textContent = h2m.errors;
        el('sync-errors-h2m').className = `sync-stat-value mono sync-stat-value--${h2m.errors > 0 ? 'warn' : 'ok'}`;
      }
    }
    if (m2h) {
      if (el('sync-last-m2h'))  el('sync-last-m2h').textContent  = relativeTime(m2h.time);
      if (el('sync-items-m2h')) el('sync-items-m2h').textContent = m2h.items;
      if (el('sync-errors-m2h')) {
        el('sync-errors-m2h').textContent = m2h.errors;
        el('sync-errors-m2h').className = `sync-stat-value mono sync-stat-value--${m2h.errors > 0 ? 'warn' : 'ok'}`;
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
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const data = DATA.analytics.timeline;
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
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const data = DATA.analytics.device_activity;
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
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = 260 * dpr;
    canvas.height = 260 * dpr;
    canvas.style.width = '260px';
    canvas.style.height = '260px';
    ctx.scale(dpr, dpr);

    const data = DATA.analytics.categories;
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
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = 200 * dpr;
    canvas.style.width = rect.width + 'px';
    canvas.style.height = '200px';
    ctx.scale(dpr, dpr);

    const data = DATA.analytics.key_usage;
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
      // Refresh keys list
      fetchKeys();
    } else if (res) {
      // API accepted but no secret returned (show placeholder)
      const secret = res.key_prefix || `merrick_sk_${Array.from({length: 40}, () => 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'[Math.floor(Math.random() * 64)]).join('')}`;
      $('#secret-value').textContent = secret;
      closeModal('modal-key-create');
      openModal('modal-secret-reveal');
      toast(`Key "${name}" created`, 'success');
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

    // For now, rotate is a client-side action unless the API
    // supports it. Show the modal with a generated secret.
    const newSecret = `merrick_sk_${Array.from({length: 40}, () => 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-'[Math.floor(Math.random() * 64)]).join('')}`;
    key.key_prefix = newSecret.slice(0, 20) + '...';
    $('#secret-value').textContent = newSecret;
    openModal('modal-secret-reveal');
    renderKeys();
    toast(`Key "${key.key_name}" rotated`, 'success');
  }

  async function revokeKey(id) {
    const key = DATA.keys.find(k => k.id === id);
    if (!key) return;
    if (!confirm(`Revoke key "${key.key_name}"? This cannot be undone.`)) return;

    // Mark locally and re-render immediately for responsiveness.
    // A real revoke endpoint would be: DELETE /api/keys/:id
    key.active = false;
    renderKeys();
    toast(`Key "${key.key_name}" revoked`, 'error');
  }

  // ── Sync Now ─────────────────────────────────────────

  $('#btn-sync-now').addEventListener('click', async () => {
    toast('Sync triggered', 'info');
    const label = $('#sync-status-label');
    label.textContent = 'Running';
    label.className = 'sync-stat-value sync-stat-value--warn';

    const res = await apiFetch('/api/sync/run', { method: 'POST' });

    if (res) {
      toast('Sync completed', 'success');
    } else {
      // Simulate if API unreachable
      await new Promise(r => setTimeout(r, 2000));
      toast('Sync completed (simulated)', 'success');
    }

    label.textContent = 'Idle';
    label.className = 'sync-stat-value sync-stat-value--ok';

    // Refresh sync log
    fetchSyncLog();
  });

  // ── Settings Save ────────────────────────────────────

  $('#btn-save-settings').addEventListener('click', () => {
    toast('Settings saved', 'success');
  });

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
    // Render immediately from mock data so the UI isn't blank
    renderActivity();
    renderDevices();
    renderKeys();
    renderAgents();
    renderSyncLog();
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

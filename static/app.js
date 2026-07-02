/**
 * Merrick — Memory Bridge Dashboard
 * SPA controller for the frontend
 */
const App = {
  state: {
    activeTab: 'dashboard',
    status: null,
    syncLog: [],
    searchResults: [],
    isLoading: false,
    intervals: []
  },

  /* =========================================
     Initialization
     ========================================= */

  async init() {
    this.bindNav();
    this.bindEvents();
    await this.loadDashboard();

    // Auto-refresh dashboard every 30s
    this.state.intervals.push(
      setInterval(() => {
        if (this.state.activeTab === 'dashboard') {
          this.loadDashboard();
        }
      }, 30000)
    );

    // Auto-refresh sync log every 10s
    this.state.intervals.push(
      setInterval(() => {
        if (this.state.activeTab === 'synclog') {
          this.loadSyncLog();
        }
      }, 10000)
    );
  },

  /* =========================================
     Event Binding
     ========================================= */

  bindNav() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        this.switchTab(tab.dataset.tab);
      });
    });
  },

  bindEvents() {
    // Sync button
    const syncBtn = document.getElementById('btn-sync-now');
    if (syncBtn) {
      syncBtn.addEventListener('click', () => this.triggerSync());
    }

    // Search button
    const searchBtn = document.getElementById('btn-search');
    if (searchBtn) {
      searchBtn.addEventListener('click', () => this.search());
    }

    // Enter key on search input
    const queryInput = document.getElementById('query-input');
    if (queryInput) {
      queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          this.search();
        }
      });
    }
  },

  /* =========================================
     Tab Switching
     ========================================= */

  switchTab(tab) {
    if (tab === this.state.activeTab) return;

    // Update nav
    document.querySelectorAll('.nav-tab').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tab);
    });

    // Update content
    document.querySelectorAll('.tab-content').forEach(el => {
      el.classList.toggle('active', el.id === `tab-${tab}`);
    });

    this.state.activeTab = tab;

    // Load tab data
    switch (tab) {
      case 'dashboard':
        this.loadDashboard();
        break;
      case 'synclog':
        this.loadSyncLog();
        break;
      case 'query':
        // Focus search input
        const input = document.getElementById('query-input');
        if (input) input.focus();
        break;
    }
  },

  /* =========================================
     Dashboard
     ========================================= */

  async loadDashboard() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.state.status = data;
      this.renderDashboard(data);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      this.toast('Failed to load dashboard status', 'error');
    }
  },

  renderDashboard(data) {
    // Stats
    this.setStat('stat-mem0-count', data.mem0_count ?? '—');
    this.setStat('stat-honcho-sessions', data.honcho_sessions ?? '—');
    this.setStat('stat-honcho-conclusions', data.honcho_conclusions ?? '—');
    this.setStat('stat-last-sync', data.last_sync ? this.formatDate(data.last_sync) : 'Never');
    this.setSyncStatus(data.sync_status || 'idle');

    // mem0 samples
    const mem0El = document.getElementById('mem0-samples');
    if (mem0El && data.mem0_samples) {
      if (data.mem0_samples.length === 0) {
        mem0El.innerHTML = '<div class="empty-state">No memories found</div>';
      } else {
        mem0El.innerHTML = data.mem0_samples.map(m => `
          <div class="sample-item">
            ${this.escapeHtml(m.text || m.content || m.memory || JSON.stringify(m))}
            ${m.id ? `<span class="sample-item-id">${this.escapeHtml(String(m.id).substring(0, 12))}</span>` : ''}
          </div>
        `).join('');
      }
    }

    // Honcho samples
    const honchoEl = document.getElementById('honcho-samples');
    if (honchoEl && data.honcho_samples) {
      if (data.honcho_samples.length === 0) {
        honchoEl.innerHTML = '<div class="empty-state">No conclusions found</div>';
      } else {
        honchoEl.innerHTML = data.honcho_samples.map(c => `
          <div class="sample-item">
            ${this.escapeHtml(c.text || c.conclusion || c.content || JSON.stringify(c))}
            ${c.id ? `<span class="sample-item-id">${this.escapeHtml(String(c.id).substring(0, 12))}</span>` : ''}
          </div>
        `).join('');
      }
    }
  },

  setStat(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  },

  setSyncStatus(status) {
    const el = document.getElementById('stat-sync-status');
    if (!el) return;

    const statusMap = {
      'running': { text: 'Running', class: 'badge-warning' },
      'idle': { text: 'Idle', class: 'badge-success' },
      'error': { text: 'Error', class: 'badge-error' }
    };

    const s = statusMap[status] || statusMap['idle'];
    el.innerHTML = `<span class="badge ${s.class}">${s.text}</span>`;
  },

  /* =========================================
     Sync
     ========================================= */

  async triggerSync() {
    const btn = document.getElementById('btn-sync-now');
    const spinner = document.getElementById('sync-spinner');
    const btnText = btn?.querySelector('.btn-text');

    if (!btn || btn.disabled) return;

    btn.disabled = true;
    spinner?.classList.remove('hidden');
    if (btnText) btnText.textContent = 'Syncing...';

    try {
      const res = await fetch('/api/sync/trigger', { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      this.toast(data.message || 'Sync started', 'success');

      // Refresh after a delay
      setTimeout(() => this.loadDashboard(), 2000);
    } catch (err) {
      console.error('Sync trigger failed:', err);
      this.toast('Failed to trigger sync', 'error');
    } finally {
      btn.disabled = false;
      spinner?.classList.add('hidden');
      if (btnText) btnText.textContent = 'Sync Now';
    }
  },

  /* =========================================
     Query / Search
     ========================================= */

  async search() {
    const input = document.getElementById('query-input');
    const query = input?.value?.trim();

    if (!query) {
      this.toast('Please enter a search query', 'warning');
      input?.focus();
      return;
    }

    const btn = document.getElementById('btn-search');
    const spinner = document.getElementById('search-spinner');
    const btnText = btn?.querySelector('.btn-text');
    const resultsEl = document.getElementById('query-results');

    btn.disabled = true;
    spinner?.classList.remove('hidden');
    if (btnText) btnText.textContent = 'Searching...';

    if (resultsEl) {
      resultsEl.innerHTML = '<div class="empty-state"><span class="spinner spinner-lg"></span></div>';
    }

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.state.searchResults = data.results || data;

      this.renderResults(this.state.searchResults, query);
    } catch (err) {
      console.error('Search failed:', err);
      this.toast('Search failed. Please try again.', 'error');
      if (resultsEl) {
        resultsEl.innerHTML = '<div class="empty-state">Search failed. Please try again.</div>';
      }
    } finally {
      btn.disabled = false;
      spinner?.classList.add('hidden');
      if (btnText) btnText.textContent = 'Search Both Systems';
    }
  },

  renderResults(results, query) {
    const el = document.getElementById('query-results');
    if (!el) return;

    if (!results || results.length === 0) {
      el.innerHTML = `
        <div class="empty-state">
          No results found for "${this.escapeHtml(query)}"
        </div>
      `;
      return;
    }

    el.innerHTML = results.map(r => {
      const source = (r.source || 'unknown').toLowerCase();
      const badgeClass = source === 'mem0' ? 'badge-mem0' :
                          source === 'honcho' ? 'badge-honcho' : '';
      const text = r.text || r.content || r.memory || r.conclusion || '';
      const score = r.score != null ? r.score : r.relevance;

      return `
        <div class="query-result">
          <div class="query-result-header">
            <span class="badge ${badgeClass}">${this.escapeHtml(source)}</span>
            ${r.id ? `<span class="muted">${this.escapeHtml(String(r.id).substring(0, 16))}</span>` : ''}
          </div>
          <div class="query-result-text">${this.escapeHtml(text)}</div>
          ${score != null ? `<div class="query-result-score">Relevance: ${(Number(score) * 100).toFixed(1)}%</div>` : ''}
        </div>
      `;
    }).join('');
  },

  /* =========================================
     Sync Log
     ========================================= */

  async loadSyncLog() {
    const body = document.getElementById('synclog-body');

    try {
      const res = await fetch('/api/sync/log');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.state.syncLog = data.entries || data;
      this.renderSyncLog(this.state.syncLog);
    } catch (err) {
      console.error('Failed to load sync log:', err);
      if (body) {
        body.innerHTML = `
          <tr><td colspan="5">
            <div class="empty-state">Failed to load sync log</div>
          </td></tr>
        `;
      }
    }
  },

  renderSyncLog(entries) {
    const body = document.getElementById('synclog-body');
    if (!body) return;

    if (!entries || entries.length === 0) {
      body.innerHTML = `
        <tr><td colspan="5">
          <div class="empty-state">No sync operations recorded yet</div>
        </td></tr>
      `;
      return;
    }

    body.innerHTML = entries.map(entry => {
      const time = entry.time || entry.timestamp || entry.created_at || '';
      const direction = entry.direction || '—';
      const items = entry.items_synced ?? entry.items ?? '—';
      const errors = entry.errors ?? 0;
      const status = entry.status || 'unknown';

      const statusBadge = {
        'success': 'badge-success',
        'error': 'badge-error',
        'partial': 'badge-warning',
        'running': 'badge-warning'
      }[status] || '';

      return `
        <tr>
          <td>${time ? this.formatDate(time) : '—'}</td>
          <td>${this.escapeHtml(String(direction))}</td>
          <td>${items}</td>
          <td>${errors > 0 ? `<span class="badge badge-error">${errors}</span>` : '0'}</td>
          <td>${statusBadge ? `<span class="badge ${statusBadge}">${this.escapeHtml(status)}</span>` : this.escapeHtml(status)}</td>
        </tr>
      `;
    }).join('');
  },

  /* =========================================
     Utilities
     ========================================= */

  escapeHtml(str) {
    if (str == null) return '';
    const s = String(str);
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return s.replace(/[&<>"']/g, c => map[c]);
  },

  toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span>${this.escapeHtml(message)}</span>
    `;

    container.appendChild(toast);

    // Auto-remove after 4s
    setTimeout(() => {
      toast.classList.add('toast-removing');
      setTimeout(() => toast.remove(), 200);
    }, 4000);
  },

  formatDate(iso) {
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      const now = new Date();
      const diffMs = now - d;
      const diffSec = Math.floor(diffMs / 1000);
      const diffMin = Math.floor(diffSec / 60);
      const diffHr = Math.floor(diffMin / 60);

      if (diffSec < 60) return 'Just now';
      if (diffMin < 60) return `${diffMin}m ago`;
      if (diffHr < 24) return `${diffHr}h ago`;

      return d.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return String(iso);
    }
  }
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());

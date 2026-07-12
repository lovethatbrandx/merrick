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
    intervals: [],
    categories: [],
    categoryMemories: [],
    analytics: null,
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

    // Auto-refresh categories every 60s
    this.state.intervals.push(
      setInterval(() => {
        if (this.state.activeTab === 'categories') {
          this.loadCategories();
        }
      }, 60000)
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

    // Category buttons
    const newCatBtn = document.getElementById('btn-new-category');
    if (newCatBtn) {
      newCatBtn.addEventListener('click', () => {
        document.getElementById('new-category-form').classList.remove('hidden');
        document.getElementById('cat-name-input').focus();
      });
    }

    const cancelCatBtn = document.getElementById('btn-cancel-category');
    if (cancelCatBtn) {
      cancelCatBtn.addEventListener('click', () => {
        document.getElementById('new-category-form').classList.add('hidden');
        document.getElementById('cat-name-input').value = '';
      });
    }

    const createCatBtn = document.getElementById('btn-create-category');
    if (createCatBtn) {
      createCatBtn.addEventListener('click', () => this.createCategory());
    }

    const backCatBtn = document.getElementById('btn-back-categories');
    if (backCatBtn) {
      backCatBtn.addEventListener('click', () => {
        document.getElementById('category-memories').classList.add('hidden');
        document.getElementById('category-grid').classList.remove('hidden');
        document.querySelector('#tab-categories .section-header').classList.remove('hidden');
      });
    }

    // Event delegation for category cards (view/delete buttons)
    document.addEventListener('click', (e) => {
      const viewBtn = e.target.closest('.btn-view');
      if (viewBtn) {
        this.viewCategoryMemories(viewBtn.dataset.catId, viewBtn.dataset.catName);
        return;
      }
      const deleteBtn = e.target.closest('.btn-delete-cat');
      if (deleteBtn) {
        this.deleteCategory(deleteBtn.dataset.catId);
        return;
      }
      const unassignBtn = e.target.closest('.btn-unassign');
      if (unassignBtn) {
        this.unassignMemory(unassignBtn.dataset.catId, unassignBtn.dataset.memId, unassignBtn.dataset.catName);
        return;
      }
    });
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
      case 'categories':
        this.loadCategories();
        break;
      case 'analytics':
        this.loadAnalytics();
        break;
      case 'export':
        // No loading needed
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
    this.setStat('stat-last-sync', data.last_sync ? this.formatDate(data.last_sync.completed_at || data.last_sync.started_at) : 'Never');
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
      this.state.syncLog = data.log || data.entries || data;
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
      const time = entry.started_at || entry.time || entry.timestamp || entry.created_at || '';
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
     Categories
     ========================================= */

  async loadCategories() {
    try {
      const res = await fetch('/api/categories');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.state.categories = data.categories || [];
      this.renderCategories(this.state.categories);
    } catch (err) {
      console.error('Failed to load categories:', err);
      const grid = document.getElementById('category-grid');
      if (grid) grid.innerHTML = '<div class="empty-state">Failed to load categories</div>';
    }
  },

  renderCategories(categories) {
    const grid = document.getElementById('category-grid');
    if (!grid) return;

    if (!categories || categories.length === 0) {
      grid.innerHTML = '<div class="empty-state">No categories yet. Create one to get started.</div>';
      return;
    }

    grid.innerHTML = categories.map(cat => `
      <div class="category-card" data-id="${this.escapeHtml(cat.id)}">
        <div class="category-card-header">
          <span class="category-dot" style="background: ${this.escapeHtml(cat.color)}"></span>
          <span class="category-name">${this.escapeHtml(cat.name)}</span>
          <span class="category-count">${cat.memory_count} memories</span>
        </div>
        <div class="category-card-actions">
          <button class="btn btn-ghost btn-sm btn-view" data-cat-id="${this.escapeHtml(cat.id)}" data-cat-name="${this.escapeHtml(cat.name)}">View</button>
          <button class="btn btn-ghost btn-sm btn-danger btn-delete-cat" data-cat-id="${this.escapeHtml(cat.id)}">Delete</button>
        </div>
      </div>
    `).join('');
  },

  async createCategory() {
    const nameInput = document.getElementById('cat-name-input');
    const colorInput = document.getElementById('cat-color-input');
    const name = nameInput?.value?.trim();
    const color = colorInput?.value || '#6366f1';

    if (!name) {
      this.toast('Please enter a category name', 'warning');
      return;
    }

    try {
      const res = await fetch('/api/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, color }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || `HTTP ${res.status}`);
      }

      this.toast(`Category "${name}" created`, 'success');
      nameInput.value = '';
      document.getElementById('new-category-form').classList.add('hidden');
      await this.loadCategories();
    } catch (err) {
      console.error('Create category failed:', err);
      this.toast(err.message || 'Failed to create category', 'error');
    }
  },

  async deleteCategory(id) {
    if (!confirm('Delete this category? Memories will not be deleted.')) return;

    try {
      const res = await fetch(`/api/categories/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.toast('Category deleted', 'success');
      await this.loadCategories();
    } catch (err) {
      console.error('Delete category failed:', err);
      this.toast('Failed to delete category', 'error');
    }
  },

  async viewCategoryMemories(categoryId, categoryName) {
    try {
      const res = await fetch(`/api/categories/${categoryId}/memories`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.state.categoryMemories = data.memories || [];

      // Show memories view
      document.getElementById('category-grid').classList.add('hidden');
      document.querySelector('#tab-categories .section-header').classList.add('hidden');
      document.getElementById('category-memories').classList.remove('hidden');
      document.getElementById('category-memories-title').textContent = `Memories in "${categoryName}" (${data.count})`;

      const list = document.getElementById('category-memories-list');
      if (this.state.categoryMemories.length === 0) {
        list.innerHTML = '<div class="empty-state">No memories in this category</div>';
        return;
      }

      list.innerHTML = this.state.categoryMemories.map(m => `
        <div class="query-result">
          <div class="query-result-header">
            <span class="badge badge-mem0">${this.escapeHtml(m.source || 'mem0')}</span>
            <span class="muted">${this.escapeHtml(String(m.id).substring(0, 16))}</span>
            <button class="btn btn-ghost btn-sm btn-danger btn-unassign" data-cat-id="${this.escapeHtml(categoryId)}" data-mem-id="${this.escapeHtml(m.id)}" data-cat-name="${this.escapeHtml(categoryName)}">Remove</button>
          </div>
          <div class="query-result-text">${this.escapeHtml(m.data || '(empty)')}</div>
        </div>
      `).join('');
    } catch (err) {
      console.error('Load category memories failed:', err);
      this.toast('Failed to load category memories', 'error');
    }
  },

  async unassignMemory(categoryId, memoryId, categoryName) {
    try {
      const res = await fetch(`/api/categories/${categoryId}/unassign/${memoryId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      this.toast('Memory removed from category', 'success');
      await this.viewCategoryMemories(categoryId, categoryName);
    } catch (err) {
      console.error('Unassign memory failed:', err);
      this.toast('Failed to remove memory', 'error');
    }
  },

  /* =========================================
     Analytics
     ========================================= */

  async loadAnalytics() {
    try {
      const [overviewRes, sourcesRes, categoriesRes, timelineRes] = await Promise.all([
        fetch('/api/analytics/overview'),
        fetch('/api/analytics/sources'),
        fetch('/api/analytics/categories'),
        fetch('/api/analytics/timeline?period=day&days=30'),
      ]);

      if (overviewRes.ok) {
        const overview = await overviewRes.json();
        this.setStat('analytics-total-memories', overview.total_memories ?? '—');
        this.setStat('analytics-today', overview.memories_today ?? '—');
        this.setStat('analytics-week', overview.memories_this_week ?? '—');
        this.setStat('analytics-month', overview.memories_this_month ?? '—');
        this.setStat('analytics-categories-count', overview.total_categories ?? '—');
        this.setStat('analytics-webhooks-count', overview.total_webhooks ?? '—');
      }

      if (sourcesRes.ok) {
        const sources = await sourcesRes.json();
        this.renderAnalyticsSources(sources.sources || []);
      }

      if (categoriesRes.ok) {
        const cats = await categoriesRes.json();
        this.renderAnalyticsCategories(cats.categories || []);
      }

      if (timelineRes.ok) {
        const timeline = await timelineRes.json();
        this.renderAnalyticsTimeline(timeline.timeline || []);
      }
    } catch (err) {
      console.error('Failed to load analytics:', err);
    }
  },

  renderAnalyticsSources(sources) {
    const el = document.getElementById('analytics-sources');
    if (!el) return;

    if (!sources || sources.length === 0) {
      el.innerHTML = '<div class="empty-state">No source data yet</div>';
      return;
    }

    const maxCount = Math.max(...sources.map(s => s.count));
    el.innerHTML = sources.map(s => {
      const pct = maxCount > 0 ? (s.count / maxCount * 100) : 0;
      const badgeClass = s.source === 'mem0' ? 'badge-mem0' :
                         s.source === 'honcho' ? 'badge-honcho' : '';
      return `
        <div class="analytics-bar-row">
          <span class="badge ${badgeClass}">${this.escapeHtml(s.source)}</span>
          <div class="analytics-bar-track">
            <div class="analytics-bar-fill" style="width: ${pct}%"></div>
          </div>
          <span class="analytics-bar-count">${s.count}</span>
        </div>
      `;
    }).join('');
  },

  renderAnalyticsCategories(categories) {
    const el = document.getElementById('analytics-categories');
    if (!el) return;

    if (!categories || categories.length === 0) {
      el.innerHTML = '<div class="empty-state">No categories yet</div>';
      return;
    }

    const maxCount = Math.max(...categories.map(c => c.count));
    el.innerHTML = categories.map(c => {
      const pct = maxCount > 0 ? (c.count / maxCount * 100) : 0;
      return `
        <div class="analytics-bar-row">
          <span class="category-dot-sm" style="background: ${this.escapeHtml(c.color)}"></span>
          <span class="analytics-bar-label">${this.escapeHtml(c.name)}</span>
          <div class="analytics-bar-track">
            <div class="analytics-bar-fill" style="width: ${pct}%; background: ${this.escapeHtml(c.color)}"></div>
          </div>
          <span class="analytics-bar-count">${c.count}</span>
        </div>
      `;
    }).join('');
  },

  renderAnalyticsTimeline(timeline) {
    const el = document.getElementById('analytics-timeline');
    if (!el) return;

    if (!timeline || timeline.length === 0) {
      el.innerHTML = '<div class="empty-state">No activity data yet</div>';
      return;
    }

    const maxCount = Math.max(...timeline.map(t => t.count));
    el.innerHTML = `
      <div class="timeline-chart">
        ${timeline.map(t => {
          const pct = maxCount > 0 ? (t.count / maxCount * 100) : 0;
          const dateStr = new Date(t.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
          return `
            <div class="timeline-bar-wrapper" title="${dateStr}: ${t.count}">
              <div class="timeline-bar" style="height: ${pct}%"></div>
              <span class="timeline-label">${dateStr}</span>
            </div>
          `;
        }).join('')}
      </div>
    `;
  },

  /* =========================================
     Export
     ========================================= */

  exportData(format) {
    const url = `/api/export/${format}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = `merrick_export.${format === 'markdown' ? 'md' : format}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    this.toast(`Exporting as ${format.toUpperCase()}...`, 'info');
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

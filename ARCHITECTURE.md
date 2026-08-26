# Merrick — Universal Memory Daemon Architecture

## Table of Contents

1. [Component Map](#1-component-map)
2. [Database Schema](#2-database-schema)
3. [Route Structure & API Contract](#3-route-structure--api-contract)
4. [Settings System](#4-settings-system)
5. [One-Click Setup Flow](#5-one-click-setup-flow)
6. [Config File Structure](#6-config-file-structure)
7. [Dependencies](#7-dependencies)
8. [Phased Implementation Plan](#8-phased-implementation-plan)

---

## 1. Component Map

### 1.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         MERRICK DAEMON                              │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ Dashboard │  │ Internal │  │ External │  │   Sync Engine     │  │
│  │   SPA     │  │  /api/*  │  │  /v1/*   │  │  (Background)     │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬──────────┘  │
│       │              │              │                  │             │
│  ┌────┴──────────────┴──────────────┴──────────────────┴──────────┐ │
│  │                     MIDDLEWARE LAYER                           │ │
│  │  CORS · Auth (API Key) · Rate Limiting · Request Logging      │ │
│  └────────────────────────┬──────────────────────────────────────┘ │
│                           │                                        │
│  ┌────────────────────────┴──────────────────────────────────────┐ │
│  │                     SERVICE LAYER                             │ │
│  │  Settings · Devices · Keys · Memory · Analytics · Webhooks   │ │
│  └────┬─────────────┬──────────────┬────────────────────────────┘ │
│       │             │              │                               │
│  ┌────┴────┐  ┌─────┴─────┐  ┌────┴──────┐                      │
│  │ mem0    │  │  Honcho    │  │ PostgreSQL │                      │
│  │ Client  │  │  Client    │  │ (Merrick)  │                      │
│  └────┬────┘  └─────┬─────┘  └────┬──────┘                      │
└───────┼──────────────┼──────────────┼──────────────────────────────┘
        │              │              │
┌───────┴──┐  ┌───────┴──────┐  ┌────┴──────────────────────┐
│  mem0    │  │   Honcho     │  │   PostgreSQL + pgvector    │
│  (port   │  │   (port 8000 │  │   (port 5433)              │
│  8888)   │  │   or cloud)  │  │   - memories (mem0)        │
│          │  │              │  │   - merrick_* (internal)    │
└──────────┘  └──────────────┘  └────────────────────────────┘

Device Fleet:
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Desktop  │  │ Android  │  │  iOS     │  │ Discord  │
│ Client   │  │ Client   │  │ Client   │  │  Bot     │
│          │  │          │  │          │  │          │
│ Bearer   │  │ Bearer   │  │ Bearer   │  │ Bearer   │
│ token    │  │ token    │  │ token    │  │ token    │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                        │
                   /v1/* (external API)
                        │
                   ┌────┴────┐
                   │ MERRICK │
                   └─────────┘
```

### 1.2 Component Responsibilities

| Component | File(s) | Responsibility |
|---|---|---|
| **FastAPI App** | `app.py` | Entrypoint, lifespan, CORS, router mount, static serving, health check |
| **Config Loader** | `config.py` → `settings.py` | Cascading config: env vars → config file → database → API overrides |
| **Database** | `database.py` | Connection pool, query helpers, schema init/migration |
| **Honcho Client** | `honcho.py` | HTTP client for Honcho API (local or cloud). Thread-safe singleton. |
| **mem0 Client** | `mem0_client.py` (new) | HTTP client for mem0 API. Auth token management. Replaces inline httpx calls. |
| **Sync Engine** | `sync.py` | Bidirectional sync between mem0 and Honcho. Background daemon thread. |
| **Auth Middleware** | `middleware/auth.py` (new) | API key validation, device identification, rate limit lookup |
| **Rate Limiter** | `middleware/ratelimit.py` (new) | Per-key, per-endpoint rate limiting (token bucket in-memory, with DB persistence for cross-restart) |
| **Device Registry** | `services/devices.py` (new) | Device CRUD, peer mapping, device-scoped memory operations |
| **Key Manager** | `services/keys.py` (new) | API key generation, rotation, revocation, scoping |
| **Settings Service** | `services/settings.py` (new) | Settings CRUD with cascade logic |
| **Setup Wizard** | `services/setup.py` (new) | One-click installation, dependency detection, config generation |
| **CLI** | `cli.py` (new) | `merrick` command entrypoint for all subcommands |
| **Dashboard SPA** | `static/*` | Browser UI for management, visualization, settings |

### 1.3 Data Flow Diagrams

#### Memory Write (External Device → `/v1/memory/write`)

```
Device                    Merrick                     mem0              Honcho
  │                          │                          │                 │
  │  POST /v1/memory/write   │                          │                 │
  │  Authorization: Bearer k │                          │                 │
  │─────────────────────────>│                          │                 │
  │                          │                          │                 │
  │                     [auth middleware]               │                 │
  │                     validate API key                │                 │
  │                     identify device_id              │                 │
  │                     check rate limit                │                 │
  │                     resolve scope                   │                 │
  │                          │                          │                 │
  │                     [memory service]               │                 │
  │                     ┌────┴────────────────────┐    │                 │
  │                     │ if scope includes mem0:  │    │                 │
  │                     │   POST /memories ────────│───>│                 │
  │                     │                          │<───│ (result)       │
  │                     │ if scope includes honcho: │   │                 │
  │                     │   POST session/msg ───────│────│──────────────>│
  │                     │                          │    │                 │<───│
  │                     └────┬────────────────────┘    │                 │
  │                          │                          │                 │
  │                     [analytics]                    │                 │
  │                     track_event(memory.created,    │                 │
  │                       device_id=device_x)           │                 │
  │                          │                          │                 │
  │                     [webhooks]                     │                 │
  │                     fire_webhooks(memory.created)  │                 │
  │                          │                          │                 │
  │  { status, results }    │                          │                 │
  │<─────────────────────────│                          │                 │
```

#### Memory Read (External Device → `/v1/memory/search`)

```
Device                    Merrick                     mem0              Honcho
  │                          │                          │                 │
  │  POST /v1/memory/search  │                          │                 │
  │  Authorization: Bearer k │                          │                 │
  │─────────────────────────>│                          │                 │
  │                          │                          │                 │
  │                     [auth + rate limit]             │                 │
  │                          │                          │                 │
  │                     [query service]                 │                 │
  │                     ┌────┴────────────────────┐    │                 │
  │                     │ full-text search ────────│───>│                 │
  │                     │                          │<───│ (results)      │
  │                     │ honcho peer search ──────│────│──────────────>│
  │                     │                          │    │                 │<───│
  │                     │ deduplicate              │    │                 │
  │                     │ filter by device scope    │    │                 │
  │                     └────┬────────────────────┘    │                 │
  │                          │                          │                 │
  │  { results, count }      │                          │                 │
  │<─────────────────────────│                          │                 │
```

#### Background Sync

```
Sync Engine (daemon thread)                mem0           Honcho
  │                                          │              │
  │  every N seconds                         │              │
  │  ┌───────────────────────────┐           │              │
  │  │ sync_mem0_to_honcho()    │           │              │
  │  │  SELECT from memories ────│──>        │              │
  │  │  for each unsynced:      │           │              │
  │  │    POST message ──────────────────────────────────>│
  │  │    INSERT sync_state     │           │              │
  │  └───────────────────────────┘           │              │
  │  ┌───────────────────────────┐           │              │
  │  │ sync_honcho_to_mem0()    │           │              │
  │  │  list conclusions ─────────────────────>           │
  │  │  for each unsynced:      │           │              │
  │  │    INSERT into memories ──│──>        │              │
  │  │    INSERT sync_state     │           │              │
  │  └───────────────────────────┘           │              │
  │  INSERT sync_log (completed)  │           │              │
  │  fire webhooks (sync.completed)│         │              │
```

#### Device Registration

```
Admin Dashboard / CLI         Merrick                 PostgreSQL
  │                              │                       │
  │  POST /api/devices           │                       │
  │  { name, type }              │                       │
  │─────────────────────────────>│                       │
  │                              │  INSERT device_peers  │
  │                              │──────────────────────>│
  │                              │                       │
  │                              │  POST /api/keys       │
  │                              │  { device_id, scope } │
  │                              │──────────────────────>│
  │                              │  INSERT api_keys      │
  │                              │                       │
  │                              │  Honcho: create peer  │
  │                              │───────────────────────│──> honcho API
  │                              │<──────────────────────│<── peer created
  │                              │  UPDATE device_peers  │
  │                              │  SET honcho_peer_id   │
  │                              │──────────────────────>│
  │  { device, api_key }         │                       │
  │<─────────────────────────────│                       │
```

---

## 2. Database Schema

All tables live in the same PostgreSQL database that mem0 uses. Merrick owns its own tables; the `memories` table is owned by mem0.

### 2.1 Existing Tables (Modified)

#### `sync_state` — Unchanged
```sql
CREATE TABLE IF NOT EXISTS sync_state (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('mem0', 'honcho')),
    source_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK (source IN ('mem0', 'honcho')),
    target_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, source_id, target)
);
```

#### `sync_log` — Add `device_id` column
```sql
ALTER TABLE sync_log ADD COLUMN IF NOT EXISTS device_id UUID REFERENCES device_peers(id) ON DELETE SET NULL;
```
A `NULL` device_id means the sync was triggered by the system (background) rather than a specific device.

#### `categories` — Unchanged
```sql
CREATE TABLE IF NOT EXISTS categories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6366f1',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### `memory_categories` — Unchanged
```sql
CREATE TABLE IF NOT EXISTS memory_categories (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, category_id)
);
```

#### `webhooks` — Add `events` expansion
```sql
-- Existing, but event types will expand to include:
-- 'memory.created', 'memory.updated', 'sync.completed',
-- 'device.registered', 'device.revoked', 'key.rotated'
```

#### `analytics` — Add `device_id` column
```sql
ALTER TABLE analytics ADD COLUMN IF NOT EXISTS device_id UUID REFERENCES device_peers(id) ON DELETE SET NULL;
```

### 2.2 New Tables

#### `device_peers` — Registered devices and their Honcho peers
```sql
CREATE TABLE IF NOT EXISTS device_peers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,                          -- Human-readable name ("Desktop App", "Android Phone")
    device_type TEXT NOT NULL CHECK (device_type IN (
        'desktop', 'mobile', 'bot', 'server', 'browser', 'other'
    )),
    honcho_peer_id TEXT,                         -- Honcho peer ID (populated after Honcho registration)
    honcho_session_prefix TEXT,                  -- Session prefix for this device (e.g., "dev_abc123_")
    user_id TEXT DEFAULT 'ron',                  -- Owner user ID
    is_active BOOLEAN DEFAULT true,
    last_seen_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',                 -- Device-reported metadata (OS, app version, etc.)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_device_peers_user ON device_peers(user_id);
CREATE INDEX IF NOT EXISTS idx_device_peers_active ON device_peers(is_active);
```

**Design notes:**
- `honcho_peer_id` is nullable because the device may be registered before Honcho is reachable. The sync engine or a background task can backfill it.
- `honcho_session_prefix` is used to namespace Honcho sessions per device. When device `abc123` writes to Honcho, the session ID becomes `dev_abc123_<context>` instead of a global session.
- `is_active` allows soft-revocation without deleting the device record (preserves analytics history).

#### `api_keys` — Authentication tokens for external devices
```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    device_id UUID NOT NULL REFERENCES device_peers(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,               -- SHA-256 hash of the raw key (never store raw keys)
    key_prefix TEXT NOT NULL,                    -- First 8 chars of key for display ("mk_abc123...")
    name TEXT DEFAULT '',                        -- Optional label ("Production key", "Dev key")
    scope TEXT[] NOT NULL DEFAULT ARRAY['memory.read', 'memory.write', 'query.read'],
    rate_limit_rpm INTEGER DEFAULT 60,           -- Requests per minute (0 = unlimited)
    rate_limit_rpd INTEGER DEFAULT 10000,        -- Requests per day
    is_active BOOLEAN DEFAULT true,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,                      -- NULL = never expires
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_device ON api_keys(device_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
```

**Key format:** `mk_` prefix + 40 random alphanumeric characters. Example: `mk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0`

**Key hash:** `SHA-256(key_bytes)` stored in DB. The raw key is only shown once at creation time. Verification: hash the incoming bearer token and compare against `key_hash`.

**Scope values:**
| Scope | Grants |
|---|---|
| `memory.read` | Search/read memories via `/v1/memory/search`, `/v1/memory/read` |
| `memory.write` | Write memories via `/v1/memory/write` |
| `query.read` | Use the OpenAI-compatible `/v1/chat/completions` endpoint |
| `sync.read` | View sync status for this device |
| `device.read` | View own device info |

**Default scope** for new keys: `['memory.read', 'memory.write', 'query.read']`

#### `settings` — Persistent configuration overrides
```sql
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'database' CHECK (source IN ('database', 'api', 'wizard')),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by TEXT                             -- 'dashboard', 'cli', 'setup_wizard', 'api'
);

CREATE INDEX IF NOT EXISTS idx_settings_source ON settings(source);
```

**Key format:** Dot-notation namespace. Examples:
- `general.honcho_mode` → `"cloud"` or `"local"`
- `general.honcho_url` → `"https://honcho.dev"` or `"http://localhost:8000"`
- `general.mem0_mode` → `"managed"` or `"postgresql"`
- `general.mem0_url` → `"http://localhost:8888"`
- `general.main_user_peer` → `"ron"`
- `general.honcho_workspace` → `"hermes"`
- `sync.interval` → `300`
- `sync.enabled` → `true`
- `server.host` → `"0.0.0.0"`
- `server.port` → `5001`
- `server.cors_origins` → `["*"]`
- `rate_limiting.enabled` → `true`
- `rate_limiting.default_rpm` → `60`
- `rate_limiting.default_rpd` → `10000`

#### `device_memory_links` — Maps device writes to memory IDs
```sql
CREATE TABLE IF NOT EXISTS device_memory_links (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    device_id UUID NOT NULL REFERENCES device_peers(id) ON DELETE CASCADE,
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    mem0_id TEXT,                                -- mem0's memory ID for this entry
    honcho_message_id TEXT,                      -- Honcho message ID for this entry
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(device_id, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_device_memory_links_device ON device_memory_links(device_id);
CREATE INDEX IF NOT EXISTS idx_device_memory_links_memory ON device_memory_links(memory_id);
```

**Purpose:** When device A writes a memory, we need to know which memories belong to which device for:
- Device-scoped search results (return only memories written by that device, or all if no filter)
- Analytics per-device breakdown
- Device revocation (optionally unlink memories when removing a device)

### 2.3 Migration Strategy

There is no Alembic. Migrations run via `database.py:init_schema()` at startup:

1. `CREATE TABLE IF NOT EXISTS` for all tables (safe, idempotent)
2. `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns on existing tables
3. A new `schema_version` table tracks which migrations have run:

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);
```

The `init_schema()` function checks `SELECT MAX(version) FROM schema_version` and applies any migrations above the current version. Each migration is a numbered SQL string in a Python dict.

---

## 3. Route Structure & API Contract

### 3.1 Internal Namespace: `/api/*`

All `/api/*` routes are **unauthenticated** (dashboard and local CLI use only). They are protected only by network binding (default: `127.0.0.1` for non-Docker deployments).

#### Health & Status

| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/api/health` | Health check | `{"status": "ok", "service": "merrick", "version": "0.2.0"}` |
| `GET` | `/api/status` | Dashboard aggregate stats | See status schema below |

**GET /api/status response:**
```json
{
  "mem0_count": 42,
  "mem0_samples": [...],
  "honcho_sessions": 5,
  "honcho_conclusions": 12,
  "honcho_samples": [...],
  "last_sync": { "status": "completed", "items_synced": 3, ... },
  "sync_state_counts": { "mem0_to_honcho": 42, "honcho_to_mem0": 12 },
  "devices_count": 3,
  "active_keys": 5,
  "server": { "host": "0.0.0.0", "port": 5001, "sync_enabled": true }
}
```

#### Memory (Internal — No Device Scope)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/memory/write` | Write to both mem0 + Honcho (no device association) |
| `POST` | `/api/memory/reasoning` | Honcho peer search for deep reasoning |

**POST /api/memory/write request:**
```json
{
  "content": "User prefers dark mode",
  "source": "hermes",
  "user_id": "ron",
  "metadata": { "context": "settings_discussion" }
}
```

**POST /api/memory/write response:**
```json
{
  "status": "ok",
  "results": {
    "mem0": { "success": true, "id": "abc-123" },
    "honcho": { "success": true, "id": "msg-456" }
  }
}
```

#### Query (Internal)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/query` | Cross-system search with deduplication |

**POST /api/query request:**
```json
{ "query": "dark mode preferences" }
```

**POST /api/query response:**
```json
{
  "results": [
    { "source": "mem0", "data": "User prefers dark mode", "user_id": "ron" },
    { "source": "honcho", "data": "User has consistently chosen dark mode...", "metadata": {...} }
  ],
  "count": 2
}
```

#### Sync (Internal)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/sync/trigger` | Trigger a full sync run (background) |
| `GET` | `/api/sync/status` | Current sync status + state counts |
| `GET` | `/api/sync/log` | Sync history (paginated) |

**GET /api/sync/status response:**
```json
{
  "running": 0,
  "last_sync": {
    "id": "...", "direction": "full",
    "items_synced": 5, "errors": 0,
    "started_at": "...", "completed_at": "...",
    "status": "completed"
  },
  "sync_state_counts": [
    { "source": "mem0", "target": "honcho", "count": 42 },
    { "source": "honcho", "target": "mem0", "count": 12 }
  ]
}
```

**GET /api/sync/log query params:** `?limit=50&offset=0`

**GET /api/sync/log response:**
```json
{
  "logs": [
    {
      "id": "...", "direction": "full",
      "items_synced": 5, "errors": 0,
      "started_at": "...", "completed_at": "...",
      "status": "completed"
    }
  ],
  "total": 120
}
```

#### Categories (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/categories` | List all categories with memory counts |
| `POST` | `/api/categories` | Create a category |
| `DELETE` | `/api/categories/{id}` | Delete a category |
| `POST` | `/api/categories/{id}/assign` | Assign a memory to a category |
| `DELETE` | `/api/categories/{id}/unassign/{memory_id}` | Remove memory from category |
| `GET` | `/api/categories/{id}/memories` | List memories in a category |

#### Webhooks (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/webhooks` | List all webhooks |
| `POST` | `/api/webhooks` | Create a webhook |
| `PUT` | `/api/webhooks/{id}` | Update a webhook |
| `DELETE` | `/api/webhooks/{id}` | Delete a webhook |
| `POST` | `/api/webhooks/{id}/test` | Test-fire a webhook |

#### Analytics (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/analytics/overview` | Aggregate stats |
| `GET` | `/api/analytics/timeline` | Memory creation over time |
| `GET` | `/api/analytics/sources` | Breakdown by source |
| `GET` | `/api/analytics/categories` | Breakdown by category |
| `GET` | `/api/analytics/devices` | Per-device breakdown (**new**) |
| `POST` | `/api/analytics/track` | Track a custom event |

**GET /api/analytics/devices response (new):**
```json
{
  "devices": [
    {
      "device_id": "abc-123",
      "device_name": "Desktop App",
      "device_type": "desktop",
      "memory_count": 42,
      "last_write": "2026-07-13T10:00:00Z",
      "writes_today": 5,
      "writes_this_week": 23
    }
  ]
}
```

#### Export (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/export/json` | Export memories as JSON |
| `GET` | `/api/export/csv` | Export as CSV |
| `GET` | `/api/export/markdown` | Export as Markdown |
| `GET` | `/api/export/full` | Full backup: settings + devices + keys + memories (**new**) |

**GET /api/export/full response:**
```json
{
  "exported_at": "2026-07-13T12:00:00Z",
  "version": "0.2.0",
  "settings": { ... },
  "devices": [ ... ],
  "api_keys": [ ... { "key_prefix": "mk_abc..." } ],
  "categories": [ ... ],
  "memories": [ ... ],
  "sync_log": [ ... ],
  "analytics_summary": { ... }
}
```

#### Devices & API Keys (Internal — New)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/devices` | List all registered devices |
| `POST` | `/api/devices` | Register a new device |
| `GET` | `/api/devices/{id}` | Get device details + key list |
| `PUT` | `/api/devices/{id}` | Update device metadata |
| `DELETE` | `/api/devices/{id}` | Soft-delete (deactivate) a device |
| `POST` | `/api/devices/{id}/restore` | Reactivate a device |

**POST /api/devices request:**
```json
{
  "name": "Desktop App",
  "device_type": "desktop",
  "user_id": "ron",
  "metadata": { "os": "linux", "app_version": "1.0.0" }
}
```

**POST /api/devices response:**
```json
{
  "device": {
    "id": "...",
    "name": "Desktop App",
    "device_type": "desktop",
    "honcho_peer_id": null,
    "honcho_session_prefix": "dev_abc123_",
    "is_active": true,
    "created_at": "..."
  }
}
```

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/devices/{id}/keys` | Create an API key for a device |
| `GET` | `/api/devices/{id}/keys` | List keys for a device |
| `DELETE` | `/api/keys/{key_id}` | Revoke an API key |
| `POST` | `/api/keys/{key_id}/rotate` | Rotate an API key (revoke old, create new) |

**POST /api/devices/{id}/keys request:**
```json
{
  "name": "Production key",
  "scope": ["memory.read", "memory.write", "query.read"],
  "rate_limit_rpm": 60,
  "rate_limit_rpd": 10000,
  "expires_at": "2027-01-01T00:00:00Z"
}
```

**POST /api/devices/{id}/keys response:**
```json
{
  "key": "mk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0",
  "key_id": "...",
  "key_prefix": "mk_a1b2c3",
  "scope": ["memory.read", "memory.write", "query.read"],
  "rate_limit_rpm": 60,
  "rate_limit_rpd": 10000,
  "expires_at": "2027-01-01T00:00:00Z",
  "created_at": "..."
}
```

**WARNING:** The `key` field is only returned once at creation time. It cannot be retrieved later.

**POST /api/keys/{key_id}/rotate response:**
```json
{
  "new_key": "mk_z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0",
  "old_key_id": "...",
  "new_key_id": "...",
  "rotated_at": "..."
}
```

#### Settings (Internal — New)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/settings` | Get all settings (resolved cascade) |
| `GET` | `/api/settings/{key}` | Get a specific setting |
| `PUT` | `/api/settings/{key}` | Update a setting (database override) |
| `DELETE` | `/api/settings/{key}` | Reset a setting (remove DB override, fall back to config file) |
| `POST` | `/api/settings/test` | Test a setting value (e.g., test Honcho connection) |

**GET /api/settings response:**
```json
{
  "general": {
    "honcho_mode": "cloud",
    "honcho_url": "https://honcho.dev",
    "honcho_workspace": "hermes",
    "main_user_peer": "ron",
    "mem0_mode": "managed",
    "mem0_url": "http://localhost:8888"
  },
  "sync": {
    "interval": 300,
    "enabled": true
  },
  "server": {
    "host": "0.0.0.0",
    "port": 5001,
    "cors_origins": ["*"]
  },
  "rate_limiting": {
    "enabled": true,
    "default_rpm": 60,
    "default_rpd": 10000
  },
  "_meta": {
    "sources": {
      "general.honcho_mode": "database",
      "general.honcho_url": "config_file",
      "sync.interval": "default"
    }
  }
}
```

**PUT /api/settings/{key} request:**
```json
{ "value": "cloud" }
```

**POST /api/settings/test request:**
```json
{
  "type": "honcho",
  "url": "https://honcho.dev",
  "workspace": "hermes"
}
```

**POST /api/settings/test response:**
```json
{
  "status": "ok",
  "message": "Honcho connection successful",
  "latency_ms": 142
}
```

#### Setup Wizard (Internal — New)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/setup/status` | Check what's installed, what's missing, wizard state |
| `POST` | `/api/setup/detect` | Auto-detect running services |
| `POST` | `/api/setup/configure` | Apply wizard selections |
| `POST` | `/api/setup/validate` | Validate a configuration before applying |

**GET /api/setup/status response:**
```json
{
  "wizard_completed": false,
  "honcho": {
    "installed": true,
    "running": true,
    "mode": "local",
    "url": "http://localhost:8000",
    "version": "0.3.1"
  },
  "mem0": {
    "installed": true,
    "running": true,
    "mode": "postgresql",
    "url": "http://localhost:8888",
    "db_connected": true
  },
  "postgresql": {
    "installed": true,
    "running": true,
    "version": "15.4",
    "pgvector": true
  },
  "merrick": {
    "version": "0.2.0",
    "devices_registered": 0,
    "sync_configured": true
  }
}
```

**POST /api/setup/detect response:**
```json
{
  "detected": {
    "hombre": { "status": "running", "port": 8000 },
    "mem0": { "status": "running", "port": 8888 },
    "postgresql": { "status": "running", "port": 5433 },
    "pgvector": { "installed": true }
  },
  "recommendations": [
    { "type": "info", "message": "All services detected. Ready to configure." }
  ]
}
```

**POST /api/setup/configure request:**
```json
{
  "honcho_mode": "local",
  "honcho_url": "http://localhost:8000",
  "honcho_workspace": "hermes",
  "mem0_mode": "postgresql",
  "mem0_url": "http://localhost:8888",
  "db_host": "localhost",
  "db_port": 5433,
  "db_user": "postgres",
  "db_password": "secret",
  "db_name": "postgres",
  "main_user_peer": "ron",
  "create_first_device": true,
  "first_device_name": "My First Device"
}
```

**POST /api/setup/configure response:**
```json
{
  "status": "ok",
  "settings_applied": 12,
  "first_device": {
    "id": "...",
    "name": "My First Device",
    "api_key": "mk_..."
  },
  "next_steps": [
    "Save your API key: mk_...",
    "Connect a device using: merrick connect --key mk_...",
    "Dashboard is ready at http://localhost:5001"
  ]
}
```

---

### 3.2 External Namespace: `/v1/*`

All `/v1/*` routes require a valid API key via `Authorization: Bearer <key>`. Rate limiting applies per key. Device scope is resolved from the key.

#### Middleware Chain for `/v1/*`

```
Request → CORS → Rate Limiter → Auth Middleware → Route Handler
                                 │
                                 ├─ Validate Bearer token (SHA-256 hash lookup)
                                 ├─ Identify device_id from key
                                 ├─ Resolve scope permissions
                                 ├─ Check rate limits (RPM + RPD)
                                 ├─ Set request.state.device_id, request.state.scope
                                 └─ Update last_used_at (async, non-blocking)
```

#### Memory (External — Device-Scoped)

| Method | Path | Description | Scopes Required |
|---|---|---|---|
| `POST` | `/v1/memory/write` | Write a memory (scoped to device) | `memory.write` |
| `POST` | `/v1/memory/search` | Search memories | `memory.read` |
| `POST` | `/v1/memory/read` | Read a specific memory by ID | `memory.read` |

**POST /v1/memory/write request:**
```json
{
  "content": "User prefers dark mode",
  "metadata": { "context": "settings_discussion" }
}
```

**POST /v1/memory/write response:**
```json
{
  "id": "abc-123",
  "status": "ok",
  "results": {
    "mem0": { "success": true, "id": "mem0-456" },
    "honcho": { "success": true, "id": "msg-789" }
  }
}
```

**Note:** The `source` field is automatically set to the device's `device_type` or name. The `user_id` is set from the device's owner. No user_id override is allowed from external requests.

**POST /v1/memory/search request:**
```json
{
  "query": "dark mode preferences",
  "limit": 10,
  "device_filter": false
}
```

**POST /v1/memory/search response:**
```json
{
  "results": [
    {
      "id": "...",
      "source": "mem0",
      "data": "User prefers dark mode",
      "device_id": "abc-123",
      "score": 0.95
    }
  ],
  "count": 1,
  "device_id": "abc-123"
}
```

When `device_filter: true`, only memories written by the requesting device are returned. Default is `false` (search all).

**POST /v1/memory/read request:**
```json
{ "memory_id": "abc-123" }
```

**POST /v1/memory/read response:**
```json
{
  "id": "abc-123",
  "source": "mem0",
  "data": "User prefers dark mode",
  "user_id": "ron",
  "device_id": "abc-123",
  "metadata": { "source": "desktop", "merrick": true },
  "created_at": "..."
}
```

#### OpenAI-Compatible Endpoint

| Method | Path | Description | Scopes Required |
|---|---|---|---|
| `POST` | `/v1/chat/completions` | Memory-augmented chat completion | `query.read` |

**POST /v1/chat/completions request:**
```json
{
  "model": "gpt-4",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "What are my preferences?" }
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**How it works:**
1. Extract the user's last message from `messages`.
2. Search both mem0 and Honcho for relevant memories matching the user message.
3. Construct a memory context block from the search results.
4. Prepend the memory context to the system message (or inject it as a system-level context message).
5. Forward the augmented request to the configured upstream LLM API (OpenAI, Anthropic, etc.).
6. Return the response from the upstream API, augmented with a `merrick_context` field.

**POST /v1/chat/completions response (OpenAI-compatible):**
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1690000000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Based on your preferences, you prefer dark mode..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 523, "completion_tokens": 45, "total_tokens": 568 },
  "merrick_context": {
    "memories_injected": 3,
    "memory_sources": ["mem0", "honcho"],
    "device_id": "abc-123"
  }
}
```

**LLM provider configuration (stored in settings):**
```
llm.provider = "openai" | "anthropic" | "ollama" | "custom"
llm.api_key = "sk-..."
llm.api_url = "https://api.openai.com/v1" (or custom base URL)
llm.default_model = "gpt-4"
llm.temperature = 0.7
llm.max_tokens = 4096
```

#### Device Self-Service (External)

| Method | Path | Description | Scopes Required |
|---|---|---|---|
| `GET` | `/v1/device/info` | Get own device info | `device.read` |
| `POST` | `/v1/device/ping` | Update last_seen_at, report metadata | `device.read` |

**POST /v1/device/ping request:**
```json
{
  "metadata": { "os": "android", "app_version": "2.1.0", "battery": 85 }
}
```

**POST /v1/device/ping response:**
```json
{
  "status": "ok",
  "device_id": "abc-123",
  "sync_enabled": true,
  "rate_limit": { "rpm": 60, "rpd": 10000, "rpm_remaining": 55, "rpd_remaining": 9847 }
}
```

#### Sync Status (External — Device-Scoped)

| Method | Path | Description | Scopes Required |
|---|---|---|---|
| `GET` | `/v1/sync/status` | Sync status for this device | `sync.read` |

**GET /v1/sync/status response:**
```json
{
  "last_sync": { "..." },
  "device_syncs": 5,
  "total_syncs": 120,
  "memories_written_by_device": 42
}
```

---

## 4. Settings System

### 4.1 Cascade Priority (Highest to Lowest)

```
1. Database overrides (settings table)     ← Dashboard writes here
2. Config file (~/.merrick/config.json)     ← CLI / manual edits
3. Environment variables (MERRICK_*)        ← Docker / systemd
4. Hardcoded defaults                        ← Fallback
```

When a setting is read, the system checks in this order and returns the first value found.

### 4.2 Settings Registry

Every setting has a key, default value, type, and whether it's user-facing (editable in dashboard) or internal-only.

| Key | Default | Type | User-Facing | Description |
|---|---|---|---|---|
| `general.honcho_mode` | `"local"` | `enum[local,cloud]` | Yes | Honcho backend selection |
| `general.honcho_url` | `"http://localhost:8000"` | `string` | Yes | Honcho API base URL |
| `general.honcho_cloud_url` | `"https://honcho.dev"` | `string` | No | Honcho Cloud URL (when mode=cloud) |
| `general.honcho_workspace` | `"hermes"` | `string` | Yes | Honcho workspace name |
| `general.main_user_peer` | `"ron"` | `string` | Yes | Default Honcho peer ID |
| `general.mem0_mode` | `"postgresql"` | `enum[managed,postgresql]` | Yes | mem0 backend selection |
| `general.mem0_url` | `"http://localhost:8888"` | `string` | Yes | mem0 API URL (when mode=managed) |
| `general.mem0_email` | `""` | `string` | Yes | mem0 dashboard login (for managed mode) |
| `general.mem0_password` | `""` | `secret` | Yes | mem0 dashboard password |
| `sync.interval` | `300` | `integer` | Yes | Seconds between sync runs |
| `sync.enabled` | `true` | `boolean` | Yes | Enable/disable background sync |
| `sync.batch_size` | `100` | `integer` | No | Items per sync batch |
| `server.host` | `"0.0.0.0"` | `string` | No | Bind address |
| `server.port` | `5001` | `integer` | No | Listen port |
| `server.cors_origins` | `["*"]` | `string[]` | No | CORS allowed origins |
| `server.log_level` | `"INFO"` | `enum[DEBUG,INFO,WARNING,ERROR]` | Yes | Logging verbosity |
| `rate_limiting.enabled` | `true` | `boolean` | Yes | Enable rate limiting for /v1/* |
| `rate_limiting.default_rpm` | `60` | `integer` | Yes | Default requests per minute |
| `rate_limiting.default_rpd` | `10000` | `integer` | Yes | Default requests per day |
| `llm.provider` | `"openai"` | `enum[openai,anthropic,ollama,custom]` | Yes | LLM provider for /v1/chat/completions |
| `llm.api_key` | `""` | `secret` | Yes | LLM API key |
| `llm.api_url` | `""` | `string` | Yes | LLM API base URL (custom provider) |
| `llm.default_model` | `"gpt-4"` | `string` | Yes | Default model name |
| `llm.temperature` | `0.7` | `number` | Yes | Default temperature |
| `llm.max_tokens` | `4096` | `integer` | Yes | Default max tokens |
| `setup.completed` | `false` | `boolean` | No | Whether setup wizard has been completed |

### 4.3 Implementation: `settings.py`

```python
# settings.py — Cascading settings with file → env → database → API overrides

class SettingsManager:
    """Manages Merrick settings with a cascading priority system.

    Priority (highest to lowest):
      1. Database overrides (settings table)
      2. Config file (~/.merrick/config.json)
      3. Environment variables (MERRICK_*)
      4. Hardcoded defaults
    """

    def __init__(self):
        self._defaults = { ... }  # The registry above
        self._config_file = None  # Loaded once at startup
        self._db_cache = {}       # Cached DB overrides, refreshed periodically

    def get(self, key: str) -> Any:
        """Resolve a setting value through the cascade."""

    def set(self, key: str, value: Any, source: str = "api", updated_by: str = "dashboard"):
        """Write an override to the database."""

    def reset(self, key: str):
        """Remove the database override, falling back to config file / env."""

    def get_all(self) -> dict:
        """Return all resolved settings with source metadata."""

    def test_connection(self, setting_type: str, **kwargs) -> dict:
        """Test a connection (Honcho, mem0, LLM) with the given params."""

    def reload(self):
        """Force reload from config file and database (clears caches)."""
```

### 4.4 Config File ↔ Database Interaction

When the dashboard writes a setting:
1. The API handler calls `settings.set(key, value)`.
2. The settings manager writes to the `settings` table in PostgreSQL.
3. The in-memory cache is updated immediately.
4. Other settings reads see the new value instantly.

When the CLI writes a config file:
1. `merrick config set key value` writes to `~/.merrick/config.json`.
2. On next settings reload (or process restart), the config file is re-read.
3. Database overrides still take precedence.

When the setup wizard runs:
1. It writes all settings to the database AND the config file (for redundancy).
2. It marks `setup.completed = true` in the database.

---

## 5. One-Click Setup Flow

### 5.1 First-Launch Detection

On startup, Merrick checks:

```python
def check_setup_state():
    if not settings.get("setup.completed"):
        return {"state": "wizard_needed", "detected": detect_services()}
    else:
        return {"state": "ready"}
```

The dashboard displays a setup wizard overlay when `state == "wizard_needed"`.

### 5.2 Wizard Steps

#### Step 1: Welcome & Mode Selection

```
┌─────────────────────────────────────────────┐
│         Welcome to Merrick                  │
│     Universal Memory Daemon                 │
│                                             │
│  Merrick synchronizes memory between AI     │
│  systems. Let's get you set up.             │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Honcho Cloud   │  │  Honcho Local   │  │
│  │                  │  │                  │  │
│  │  Use honcho.dev  │  │  Run hombre on   │  │
│  │  hosted service  │  │  this machine    │  │
│  │                  │  │                  │  │
│  │  [Select]        │  │  [Select]        │  │
│  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────┘
```

**Logic:**
- If Honcho Cloud is selected: prompt for `honcho.dev` credentials / API key.
- If Honcho Local is selected: check if `hombre` is running on port 8000.
  - If running: auto-detect and confirm.
  - If not running: offer to install via `merrick install hombre` or Docker.

#### Step 2: Memory Backend

```
┌─────────────────────────────────────────────┐
│         Memory Backend                      │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │   mem0 Managed   │  │  PostgreSQL     │  │
│  │   (Docker)       │  │  Direct         │  │
│  │                  │  │                  │  │
│  │  mem0 runs in    │  │  Connect to any  │  │
│  │  Docker, auto-   │  │  PostgreSQL +    │  │
│  │  configured      │  │  pgvector DB     │  │
│  │                  │  │                  │  │
│  │  [Select]        │  │  [Select]        │  │
│  └─────────────────┘  └─────────────────┘  │
│                                             │
│  Auto-detected: PostgreSQL running on 5433  │
│  pgvector extension: installed              │
└─────────────────────────────────────────────┘
```

**Logic:**
- If mem0 Managed: check Docker availability, pull mem0 image, start container, configure connection.
- If PostgreSQL Direct: prompt for host/port/user/password/database. Validate connection and pgvector extension.

#### Step 3: Connection Details

```
┌─────────────────────────────────────────────┐
│         Connection Details                  │
│                                             │
│  Honcho URL:  [http://localhost:8000    ]   │
│  Workspace:   [hermes                 ]   │
│  User Peer:   [ron                    ]   │
│                                             │
│  PostgreSQL Host:     [localhost       ]   │
│  PostgreSQL Port:     [5433            ]   │
│  PostgreSQL User:     [postgres        ]   │
│  PostgreSQL Password: [••••••••••       ]   │
│  PostgreSQL Database: [postgres        ]   │
│                                             │
│  [Test Connections]                         │
│  ✅ Honcho: Connected (142ms)              │
│  ✅ PostgreSQL: Connected (23ms)           │
│  ✅ pgvector: Installed                    │
│                                             │
│           [Continue →]                      │
└─────────────────────────────────────────────┘
```

#### Step 4: First Device

```
┌─────────────────────────────────────────────┐
│         Register Your First Device          │
│                                             │
│  Device Name:  [My First Device       ]    │
│  Device Type:  [Desktop  ▼]               │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  API Key (save this — shown once!)  │   │
│  │                                     │   │
│  │  mk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4  │   │
│  │                                     │   │
│  │  [Copy to Clipboard]               │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  Connect your device:                       │
│  $ merrick connect --key mk_a1b2c3d4...    │
│                                             │
│           [Finish Setup →]                  │
└─────────────────────────────────────────────┘
```

### 5.3 Auto-Detection Logic

```python
def detect_services():
    results = {}

    # Check PostgreSQL
    try:
        conn = psycopg2.connect(host="localhost", port=5433, ...)
        cur = conn.cursor()
        cur.execute("SELECT version()")
        results["postgresql"] = {
            "status": "running",
            "version": cur.fetchone()[0],
            "pgvector": check_pgvector(cur),
            "port": 5433
        }
        conn.close()
    except:
        results["postgresql"] = {"status": "not_found"}

    # Check Honcho (hombre)
    try:
        resp = httpx.get("http://localhost:8000/health", timeout=2)
        results["honcho"] = {
            "status": "running",
            "url": "http://localhost:8000",
            "version": resp.headers.get("X-Version", "unknown")
        }
    except:
        results["honcho"] = {"status": "not_found"}

    # Check mem0
    try:
        resp = httpx.get("http://localhost:8888/health", timeout=2)
        results["mem0"] = {
            "status": "running",
            "url": "http://localhost:8888"
        }
    except:
        results["mem0"] = {"status": "not_found"}

    # Check Docker (for mem0 managed mode)
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
        results["docker"] = {"status": "available"}
    except:
        results["docker"] = {"status": "not_found"}

    # Check systemd/launchd (for system app mode)
    if platform.system() == "Linux":
        try:
            subprocess.run(["systemctl", "--user", "status", "merrick"],
                         capture_output=True)
            results["systemd"] = {"status": "available"}
        except:
            results["systemd"] = {"status": "not_found"}

    return results
```

---

## 6. Config File Structure

### 6.1 Location

`~/.merrick/config.json` (user-level) or `/etc/merrick/config.json` (system-level).

### 6.2 Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Merrick Configuration",
  "type": "object",
  "properties": {
    "general": {
      "type": "object",
      "properties": {
        "honcho_mode": { "type": "string", "enum": ["local", "cloud"], "default": "local" },
        "honcho_url": { "type": "string", "default": "http://localhost:8000" },
        "honcho_cloud_url": { "type": "string", "default": "https://honcho.dev" },
        "honcho_workspace": { "type": "string", "default": "hermes" },
        "main_user_peer": { "type": "string", "default": "ron" },
        "mem0_mode": { "type": "string", "enum": ["managed", "postgresql"], "default": "postgresql" },
        "mem0_url": { "type": "string", "default": "http://localhost:8888" },
        "mem0_email": { "type": "string", "default": "" },
        "mem0_password": { "type": "string", "default": "" }
      }
    },
    "database": {
      "type": "object",
      "properties": {
        "host": { "type": "string", "default": "localhost" },
        "port": { "type": "integer", "default": 5433 },
        "user": { "type": "string", "default": "postgres" },
        "password": { "type": "string", "default": "" },
        "name": { "type": "string", "default": "postgres" },
        "pool_min": { "type": "integer", "default": 2 },
        "pool_max": { "type": "integer", "default": 10 }
      }
    },
    "sync": {
      "type": "object",
      "properties": {
        "interval": { "type": "integer", "default": 300 },
        "enabled": { "type": "boolean", "default": true },
        "batch_size": { "type": "integer", "default": 100 }
      }
    },
    "server": {
      "type": "object",
      "properties": {
        "host": { "type": "string", "default": "0.0.0.0" },
        "port": { "type": "integer", "default": 5001 },
        "cors_origins": { "type": "array", "items": { "type": "string" }, "default": ["*"] },
        "log_level": { "type": "string", "enum": ["DEBUG", "INFO", "WARNING", "ERROR"], "default": "INFO" }
      }
    },
    "rate_limiting": {
      "type": "object",
      "properties": {
        "enabled": { "type": "boolean", "default": true },
        "default_rpm": { "type": "integer", "default": 60 },
        "default_rpd": { "type": "integer", "default": 10000 }
      }
    },
    "llm": {
      "type": "object",
      "properties": {
        "provider": { "type": "string", "enum": ["openai", "anthropic", "ollama", "custom"], "default": "openai" },
        "api_key": { "type": "string", "default": "" },
        "api_url": { "type": "string", "default": "" },
        "default_model": { "type": "string", "default": "gpt-4" },
        "temperature": { "type": "number", "default": 0.7 },
        "max_tokens": { "type": "integer", "default": 4096 }
      }
    }
  }
}
```

### 6.3 Example Config File

```json
{
  "general": {
    "honcho_mode": "local",
    "honcho_url": "http://localhost:8000",
    "honcho_workspace": "hermes",
    "main_user_peer": "ron",
    "mem0_mode": "postgresql",
    "mem0_url": "http://localhost:8888"
  },
  "database": {
    "host": "localhost",
    "port": 5433,
    "user": "postgres",
    "password": "",
    "name": "postgres"
  },
  "sync": {
    "interval": 300,
    "enabled": true
  },
  "server": {
    "host": "0.0.0.0",
    "port": 5001,
    "log_level": "INFO"
  },
  "llm": {
    "provider": "openai",
    "api_key": "",
    "default_model": "gpt-4"
  }
}
```

---

## 7. Dependencies

### 7.1 New Python Packages

| Package | Version | Purpose |
|---|---|---|
| `pydantic-settings` | `^2.0` | Settings validation and cascade (extends FastAPI's Pydantic) |
| `click` | `^8.0` | CLI framework for `merrick` command |
| `rich` | `^13.0` | Pretty CLI output (tables, progress, colors) |
| `tenacity` | `^8.0` | Retry logic for API calls (Honcho, mem0, LLM) |
| `apscheduler` | `^3.10` | Background sync scheduling (replaces raw threading) |

### 7.2 Updated `requirements.txt`

```
fastapi==0.138.0
uvicorn[standard]==0.49.0
httpx==0.28.1
psycopg2-binary==2.9.10
python-multipart==0.0.20
pydantic-settings>=2.0.0
click>=8.0.0
rich>=13.0.0
tenacity>=8.0.0
apscheduler>=3.10.0
```

### 7.3 New Files to Create

| File | Purpose |
|---|---|
| `settings.py` | Settings manager with cascade logic |
| `mem0_client.py` | Dedicated mem0 HTTP client (replaces inline httpx in routes/memory.py and sync.py) |
| `middleware/__init__.py` | Middleware package |
| `middleware/auth.py` | API key validation, device identification |
| `middleware/ratelimit.py` | Per-key rate limiting (token bucket) |
| `middleware/requestlog.py` | Request logging middleware |
| `services/__init__.py` | Services package |
| `services/devices.py` | Device registry operations |
| `services/keys.py` | API key management (create, rotate, revoke) |
| `services/settings.py` | Settings service (thin wrapper around settings.py for route handlers) |
| `services/setup.py` | Setup wizard detection and configuration |
| `services/llm.py` | OpenAI-compatible chat completion proxy |
| `cli.py` | Click-based CLI entrypoint |
| `cli_commands/__init__.py` | CLI commands package |
| `cli_commands/serve.py` | `merrick serve` / `merrick stop` / `merrick status` |
| `cli_commands/config.py` | `merrick config set/show` |
| `cli_commands/keys.py` | `merrick keys create/list/revoke/rotate` |
| `cli_commands/devices.py` | `merrick devices list/show/remove` |
| `cli_commands/memory.py` | `merrick memory write/search/export` |
| `cli_commands/sync.py` | `merrick sync trigger/status/history` |
| `routes/devices.py` | Device management routes (/api/devices) |
| `routes/keys.py` | API key management routes (/api/devices/{id}/keys) |
| `routes/settings.py` | Settings routes (/api/settings) |
| `routes/setup.py` | Setup wizard routes (/api/setup) |
| `routes/v1/__init__.py` | External API package |
| `routes/v1/memory.py` | External memory routes (/v1/memory/*) |
| `routes/v1/chat.py` | OpenAI-compatible endpoint (/v1/chat/completions) |
| `routes/v1/device.py` | Device self-service routes (/v1/device/*) |
| `routes/v1/sync.py` | External sync status (/v1/sync/status) |
| `schema/migrations.py` | Database migration runner |

### 7.4 Files to Modify

| File | Changes |
|---|---|
| `app.py` | Register new routers (internal + external), add auth middleware for /v1/*, update lifespan |
| `config.py` | Add new env vars (LLM, server, rate limiting), load from config file |
| `database.py` | Add new tables to init_schema(), add migration support |
| `sync.py` | Refactor to use mem0_client, add device-scoped sync, update sync_log schema |
| `honcho.py` | Add device peer creation, session prefix support, cloud auth |
| `routes/memory.py` | Refactor to use mem0_client, add device tracking via device_memory_links |
| `routes/query.py` | Add device-scoped filtering |
| `routes/analytics.py` | Add device breakdown endpoint |
| `routes/export.py` | Add full backup endpoint |
| `routes/webhooks.py` | Expand event types (device.registered, key.rotated, sync.completed) |
| `static/app.js` | Complete rewrite for new dashboard tabs (pipe system theme) |
| `static/style.css` | Complete rewrite for pipe system theme |
| `static/index.html` | Complete rewrite for new tab structure |
| `docker-compose.yml` | Update for multi-service stack (optional) |
| `Dockerfile` | Add CLI entrypoint, install click/rich |
| `AGENT.md` | Update for new architecture |
| `schema/merrick.sql` | Update with all tables (sync state, sync_log, categories, memory_categories, webhooks, analytics, device_peers, api_keys, settings, device_memory_links, schema_version) |

---

## 8. Phased Implementation Plan

### Phase 1: Foundation (Settings + Config + Auth)
**Goal:** Settings system works, API keys work, external devices can authenticate.

**Deploys independently:** Yes — existing `/api/*` routes remain unauthenticated. New `/v1/*` routes are gated by auth middleware but nothing breaks.

| Task | Files | Effort |
|---|---|---|
| Create `settings.py` with cascade logic | `settings.py` | Medium |
| Add config file loading to `config.py` | `config.py` | Small |
| Create `~/.merrick/config.json` schema | `config.py` | Small |
| Create `device_peers` table | `database.py` | Small |
| Create `api_keys` table | `database.py` | Small |
| Create `settings` table | `database.py` | Small |
| Create `schema_version` table + migration runner | `database.py`, `schema/migrations.py` | Medium |
| Create `middleware/auth.py` | `middleware/auth.py` | Medium |
| Create `middleware/ratelimit.py` | `middleware/ratelimit.py` | Medium |
| Create `services/keys.py` (SHA-256 hashing, create/rotate/revoke) | `services/keys.py` | Medium |
| Create `routes/devices.py` (internal device CRUD) | `routes/devices.py` | Medium |
| Create `routes/keys.py` (internal key management) | `routes/keys.py` | Medium |
| Create `routes/settings.py` (internal settings CRUD) | `routes/settings.py` | Medium |
| Wire auth middleware on /v1/* in app.py | `app.py` | Small |
| Add `mem0_client.py` (extract from routes/memory.py) | `mem0_client.py` | Small |

### Phase 2: External API (Device-Scoped Memory)
**Goal:** External devices can write and search memories via `/v1/*`.

**Deploys independently:** Yes — external devices can authenticate and use memory endpoints. Dashboard still works as before.

| Task | Files | Effort |
|---|---|---|
| Create `device_memory_links` table | `database.py` | Small |
| Create `routes/v1/memory.py` (write + search + read) | `routes/v1/memory.py` | Medium |
| Create `routes/v1/device.py` (info + ping) | `routes/v1/device.py` | Small |
| Create `routes/v1/sync.py` (device-scoped status) | `routes/v1/sync.py` | Small |
| Update `routes/memory.py` to track device_memory_links | `routes/memory.py` | Small |
| Update `routes/query.py` to support device filtering | `routes/query.py` | Small |
| Update `sync.py` to use mem0_client | `sync.py` | Small |
| Update `honcho.py` with device peer support | `honcho.py` | Medium |
| Update webhooks with new event types | `routes/webhooks.py` | Small |
| Update analytics with device breakdown | `routes/analytics.py` | Small |
| Add device analytics endpoint to internal API | `routes/analytics.py` | Small |

### Phase 3: Dashboard Redesign (Pipe System Theme)
**Goal:** New dashboard with pipe visualization, device management, settings UI.

**Deploys independently:** Yes — new dashboard is a static file replacement. Backend is already in place from Phases 1-2.

| Task | Files | Effort |
|---|---|---|
| Redesign `static/index.html` with new tab structure | `static/index.html` | Large |
| Rewrite `static/style.css` with pipe system theme | `static/style.css` | Large |
| Rewrite `static/app.js` with new tabs + API calls | `static/app.js` | Large |
| Tab: Overview (pipe visualization with animated flow) | `static/*` | Large |
| Tab: Devices & API Keys (CRUD UI) | `static/*` | Medium |
| Tab: Settings → General (backend config) | `static/*` | Medium |
| Tab: Settings → Developer (server, rate limits, webhooks) | `static/*` | Medium |
| Tab: Sync Monitor (live status, history) | `static/*` | Medium |
| Tab: Analytics (per-device breakdown) | `static/*` | Medium |
| Tab: Export (download configs, memories, full backup) | `static/*` | Small |
| Add full backup endpoint to export routes | `routes/export.py` | Small |

### Phase 4: Setup Wizard + CLI
**Goal:** One-click setup, `merrick` CLI for all operations.

**Deploys independently:** Yes — wizard is optional (skip if settings.completed = true). CLI is a separate entrypoint.

| Task | Files | Effort |
|---|---|---|
| Create `services/setup.py` (detect + configure) | `services/setup.py` | Medium |
| Create `routes/setup.py` (wizard API) | `routes/setup.py` | Medium |
| Wizard UI in dashboard (step-by-step overlay) | `static/*` | Medium |
| Create `cli.py` with Click | `cli.py` | Medium |
| `merrick serve` / `merrick stop` / `merrick status` | `cli_commands/serve.py` | Medium |
| `merrick config set/show` | `cli_commands/config.py` | Small |
| `merrick keys create/list/revoke/rotate` | `cli_commands/keys.py` | Medium |
| `merrick devices list/show/remove` | `cli_commands/devices.py` | Medium |
| `merrick memory write/search/export` | `cli_commands/memory.py` | Medium |
| `merrick sync trigger/status/history` | `cli_commands/sync.py` | Medium |
| Add `[project.scripts]` to pyproject.toml for `merrick` command | `pyproject.toml` | Small |

### Phase 5: OpenAI-Compatible Endpoint + LLM Integration
**Goal:** `/v1/chat/completions` for memory-augmented generation.

**Deploys independently:** Yes — requires LLM settings to be configured, gracefully degrades without them.

| Task | Files | Effort |
|---|---|---|
| Create `services/llm.py` (LLM provider abstraction) | `services/llm.py` | Large |
| Create `routes/v1/chat.py` (OpenAI-compatible endpoint) | `routes/v1/chat.py` | Medium |
| Add LLM settings to settings registry | `settings.py` | Small |
| Add LLM provider UI in Settings → Developer | `static/*` | Medium |
| Support OpenAI, Anthropic, Ollama, custom providers | `services/llm.py` | Large |
| Memory injection logic (search → inject → forward) | `services/llm.py` | Medium |

### Phase 6: Docker Compose Full Stack + Packaging
**Goal:** `docker compose up` brings up Merrick + Honcho + mem0 + PostgreSQL. Installable as a system package.

**Deploys independently:** Yes — full stack is optional (single-container mode still works).

| Task | Files | Effort |
|---|---|---|
| Multi-service docker-compose.yml | `docker-compose.yml` | Medium |
| Honcho (hombre) service definition | `docker-compose.yml` | Medium |
| mem0 service definition | `docker-compose.yml` | Medium |
| PostgreSQL + pgvector service definition | `docker-compose.yml` | Small |
| Shared volume for database data | `docker-compose.yml` | Small |
| Health checks for all services | `docker-compose.yml` | Small |
| `merrick install` command (systemd/launchd) | `cli_commands/serve.py` | Medium |
| `merrick uninstall` command | `cli_commands/serve.py` | Small |
| Create `pyproject.toml` with proper packaging | `pyproject.toml` | Small |
| Publish to PyPI (optional) | — | Small |

---

## Appendix A: File Tree After All Phases

```
merrick/
├── app.py                          # FastAPI entrypoint (modified)
├── config.py                       # Env + file config loading (modified)
├── settings.py                     # Settings manager with cascade (new)
├── database.py                     # Connection pool + schema + migrations (modified)
├── honcho.py                       # Honcho client (modified)
├── mem0_client.py                  # mem0 client (new, extracted from routes/memory.py)
├── sync.py                         # Sync engine (modified)
├── cli.py                          # Click CLI entrypoint (new)
├── cli_commands/
│   ├── __init__.py
│   ├── serve.py                    # serve/stop/status/install/uninstall
│   ├── config.py                   # config set/show
│   ├── keys.py                     # keys create/list/revoke/rotate
│   ├── devices.py                  # devices list/show/remove
│   ├── memory.py                   # memory write/search/export
│   └── sync.py                     # sync trigger/status/history
├── middleware/
│   ├── __init__.py
│   ├── auth.py                     # API key validation
│   ├── ratelimit.py                # Per-key rate limiting
│   └── requestlog.py               # Request logging
├── services/
│   ├── __init__.py
│   ├── devices.py                  # Device registry operations
│   ├── keys.py                     # API key management
│   ├── settings.py                 # Settings service (thin wrapper)
│   ├── setup.py                    # Setup wizard detection + config
│   └── llm.py                      # LLM provider abstraction
├── routes/
│   ├── __init__.py
│   ├── analytics.py                # Analytics (modified)
│   ├── categories.py               # Categories (unchanged)
│   ├── devices.py                  # Device CRUD (new)
│   ├── export.py                   # Export (modified)
│   ├── keys.py                     # Key management (new)
│   ├── memory.py                   # Internal memory write (modified)
│   ├── query.py                    # Internal query (modified)
│   ├── settings.py                 # Settings CRUD (new)
│   ├── setup.py                    # Setup wizard (new)
│   ├── status.py                   # Dashboard status (modified)
│   ├── sync.py                     # Internal sync (modified)
│   ├── webhooks.py                 # Webhooks (modified)
│   └── v1/
│       ├── __init__.py
│       ├── memory.py               # External memory (new)
│       ├── chat.py                 # OpenAI-compatible endpoint (new)
│       ├── device.py               # Device self-service (new)
│       └── sync.py                 # External sync status (new)
├── schema/
│   ├── merrick.sql                 # Reference DDL (modified)
│   └── migrations.py               # Migration runner (new)
├── static/
│   ├── index.html                  # Dashboard SPA (rewritten)
│   ├── app.js                      # Dashboard JS (rewritten)
│   └── style.css                   # Dashboard CSS (rewritten)
├── pyproject.toml                  # Package metadata + CLI entrypoint (new)
├── requirements.txt                # Dependencies (modified)
├── Dockerfile                      # Container build (modified)
├── docker-compose.yml              # Full stack orchestration (modified)
├── AGENT.md                        # Agent guide (modified)
├── ARCHITECTURE.md                 # This document (new)
├── DOCS.md                         # Developer docs (modified)
└── README.md                       # Project README (modified)
```

---

## Appendix B: Environment Variables (Complete)

All env vars are prefixed `MERRICK_` and map to config file keys:

| Env Var | Config Key | Default |
|---|---|---|
| `MERRICK_DB_HOST` | `database.host` | `localhost` |
| `MERRICK_DB_PORT` | `database.port` | `5433` |
| `MERRICK_DB_USER` | `database.user` | `postgres` |
| `MERRICK_DB_PASSWORD` | `database.password` | `""` |
| `MERRICK_DB_NAME` | `database.name` | `postgres` |
| `MERRICK_HONCHO_URL` | `general.honcho_url` | `http://localhost:8000` |
| `MERRICK_HONCHO_WORKSPACE` | `general.honcho_workspace` | `hermes` |
| `MERRICK_HONCHO_USER_PEER` | `general.main_user_peer` | `ron` |
| `MERRICK_MEM0_API_URL` | `general.mem0_url` | `http://localhost:8888` |
| `MERRICK_MEM0_EMAIL` | `general.mem0_email` | `""` |
| `MERRICK_MEM0_PASSWORD` | `general.mem0_password` | `""` |
| `MERRICK_SYNC_INTERVAL` | `sync.interval` | `300` |
| `MERRICK_SYNC_ENABLED` | `sync.enabled` | `true` |
| `MERRICK_SERVER_HOST` | `server.host` | `0.0.0.0` |
| `MERRICK_SERVER_PORT` | `server.port` | `5001` |
| `MERRICK_LOG_LEVEL` | `server.log_level` | `INFO` |
| `MERRICK_RATE_LIMIT_RPM` | `rate_limiting.default_rpm` | `60` |
| `MERRICK_RATE_LIMIT_RPD` | `rate_limiting.default_rpd` | `10000` |
| `MERRICK_LLM_PROVIDER` | `llm.provider` | `openai` |
| `MERRICK_LLM_API_KEY` | `llm.api_key` | `""` |
| `MERRICK_LLM_API_URL` | `llm.api_url` | `""` |
| `MERRICK_LLM_MODEL` | `llm.default_model` | `gpt-4` |

---

## Appendix C: Key Format Specification

```
Format: mk_ + 40 alphanumeric characters
Length:  43 characters total
Prefix:  mk_ (identifies as Merrick key)
Example: mk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0

Storage: SHA-256 hash in database
         key_prefix (first 8 chars) stored for display
         raw key returned ONLY at creation time
```

### Hash Verification Flow

```
1. Client sends: Authorization: Bearer mk_a1b2c3d4...
2. Middleware extracts: raw_key = "mk_a1b2c3d4..."
3. Compute: key_hash = SHA-256(raw_key)
4. Query: SELECT * FROM api_keys WHERE key_hash = %s AND is_active = true
5. If no match → 401 Unauthorized
6. If match → check expires_at, check rate limits
7. If all OK → set request.state.device_id, request.state.scope
8. Update: UPDATE api_keys SET last_used_at = NOW() WHERE id = %s (async)
```

---

*Document generated by Monica Hall, VP of Business Development at Pied Piper.*
*Version: 0.2.0 | Date: 2026-07-13*

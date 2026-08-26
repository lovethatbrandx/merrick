# Merrick — Universal Memory Daemon Architecture

## Table of Contents

1. [Component Map](#1-component-map)
2. [Database Schema](#2-database-schema)
3. [Route Structure & API Contract](#3-route-structure--api-contract)
4. [Auth Middleware](#4-auth-middleware)
5. [Configuration System](#5-configuration-system)
6. [Dreaming Engine](#6-dreaming-engine)
7. [Agent System](#7-agent-system)
8. [Device Provisioning](#8-device-provisioning)
9. [MCP Server](#9-mcp-server)
10. [CLI](#10-cli)
11. [Docker](#11-docker)
12. [Current Status](#12-current-status)

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
│  │                    CORS · Auth (API Key)                       │ │
│  └────────────────────────┬──────────────────────────────────────┘ │
│                           │                                        │
│  ┌────────────────────────┴──────────────────────────────────────┐ │
│  │                     ROUTE LAYER                               │ │
│  │  memory · query · sync · status · categories · webhooks       │ │
│  │  analytics · export · keys · devices · agents · dreaming      │ │
│  └────┬─────────────┬──────────────┬────────────────────────────┘ │
│       │             │              │                               │
│  ┌────┴────┐  ┌─────┴─────┐  ┌────┴──────┐                      │
│  │ honcho  │  │ provisioning│  │ PostgreSQL │                      │
│  │ Client  │  │ (auto-dev) │  │ (Merrick)  │                      │
│  └────┬────┘  └─────┬─────┘  └────┬──────┘                      │
└───────┼──────────────┼──────────────┼──────────────────────────────┘
        │              │              │
┌───────┴──┐  ┌────────┴────┐  ┌────┴──────────────────────┐
│  Honcho  │  │  Honcho     │  │   PostgreSQL + pgvector    │
│  (port   │  │  Peer Mgmt  │  │   (port 5433)              │
│  8000)   │  │             │  │   - memories (mem0)        │
│          │  │             │  │   - merrick_* (internal)    │
└──────────┘  └─────────────┘  └────────────────────────────┘

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
| **Config** | `config.py` | Flat env-var loading via `os.getenv()`. No cascade, no file, no DB. |
| **Database** | `database.py` | Connection pool (`psycopg2`), query helpers, schema init via `CREATE TABLE IF NOT EXISTS` |
| **Auth Middleware** | `middleware/auth.py` | Intercepts `/v1/*` only. Bearer token → SHA-256 hash → DB lookup → rate limit → inject `request.state` |
| **Honcho Client** | `honcho.py` | HTTP client for Honcho API (local or cloud). Thread-safe singleton. |
| **Sync Engine** | `sync.py` | Bidirectional sync between mem0 and Honcho. Background daemon thread started in `app.py` lifespan. |
| **Provisioning** | `provisioning.py` | Auto-creates Honcho peers and mem0 user mappings on first device connect. Thread-safe cache + DB persistence. |
| **Dreaming Engine** | `dreaming.py` | Memory compaction loop: deduplication, contradiction detection, staleness marking. Background daemon thread. |
| **Agent Profiles** | `routes/agents.py` | CRUD for agent profiles, agent-scoped memory read/write, external agent endpoint with token-budget-aware memory loading. |
| **API Keys** | `routes/keys.py` | Key generation (`merrick_sk_` + `secrets.token_urlsafe`), SHA-256 hashing, CRUD, rotation, revocation. |
| **Devices** | `routes/devices.py` | Device listing via provisioning module. Thin route layer. |
| **Dreaming Routes** | `routes/dreaming.py` | Manual trigger and stats for the dreaming engine. |
| **MCP Server** | `mcp_server/` | Exposes Merrick as MCP tools/resources for LM Studio, Claude Desktop, etc. Stdio transport. |
| **CLI** | `merrick_cli/` | Click-based CLI: status, devices, keys, memory, sync, doctor. Talks to Merrick over HTTP. |
| **Dashboard SPA** | `static/*` | Browser UI for management, visualization, settings |

### 1.3 Data Flow: External Device Write

```
Device                    Merrick                     mem0              Honcho
  │                          │                          │                 │
  │  POST /v1/memory/write   │                          │                 │
  │  Authorization: Bearer m │                          │                 │
  │─────────────────────────>│                          │                 │
  │                          │                          │                 │
  │                     [auth middleware]               │                 │
  │                     validate API key                │                 │
  │                     identify device_id              │                 │
  │                     check rate limit                │                 │
  │                     check permissions               │                 │
  │                          │                          │                 │
  │                     [provisioning]                  │                 │
  │                     get_or_provision(device_id)     │                 │
  │                     → honcho_peer_id, mem0_user_id  │                 │
  │                          │                          │                 │
  │                     [memory route]                  │                 │
  │                     POST /api/memory/write ─────────│──>              │
  │                     POST /api/memory/write ─────────────────────────>│
  │                          │                          │                 │
  │  { status, results }    │                          │                 │
  │<─────────────────────────│                          │                 │
```

---

## 2. Database Schema

All tables live in a single PostgreSQL + pgvector database. Merrick owns all tables; the `memories` table is shared with mem0.

### 2.1 `memories` — Shared with mem0

```sql
CREATE TABLE IF NOT EXISTS memories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    vector FLOAT8[],
    payload JSONB DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_payload ON memories USING GIN (payload);
```

The `payload` JSONB column contains: `data` (text content), `source`, `user_id`, `compacted` (boolean), `compacted_at`, `compacted_reason`, and custom metadata.

### 2.2 `api_keys` — Authentication tokens

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    key_name TEXT NOT NULL,
    device_id TEXT NOT NULL,
    agent_slug TEXT,
    load_memories BOOLEAN DEFAULT true,
    memory_categories TEXT[],
    memory_exclude_categories TEXT[] DEFAULT '{}',
    memory_scope TEXT DEFAULT 'shared'
        CHECK (memory_scope IN ('shared', 'agent_only', 'both')),
    max_memory_tokens INTEGER DEFAULT 2000,
    permissions TEXT[] DEFAULT ARRAY['read', 'write'],
    rate_limit INTEGER DEFAULT 100,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_api_keys_device ON api_keys(device_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(id) WHERE active = true;
```

**Key format:** `merrick_sk_` + `secrets.token_urlsafe(32)`. Example: `merrick_sk_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890_`

**Key hash:** `SHA-256(key_bytes)` stored in DB. Raw key shown once at creation. Verification: hash incoming bearer and compare against `key_hash`.

**Memory scope values:**
| Scope | Behavior |
|---|---|
| `shared` | Agent reads from the global `memories` table only |
| `agent_only` | Agent reads from `agent_memories` table only |
| `both` | Agent reads from both tables, combined |

**Permission values:** `read`, `write`. Write permission is checked for mutating methods (POST/PUT/DELETE/PATCH) on `/v1/*` endpoints.

### 2.3 `agent_profiles` — Agent definitions

```sql
CREATE TABLE IF NOT EXISTS agent_profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    system_prompt TEXT NOT NULL,
    personality JSONB DEFAULT '{}',
    custom_instructions TEXT,
    memory_scope TEXT DEFAULT 'shared'
        CHECK (memory_scope IN ('shared', 'agent_only')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.4 `agent_memories` — Agent-scoped memories

```sql
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    source_device TEXT,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_agent_memories_profile ON agent_memories(profile_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_category ON agent_memories(category);
CREATE INDEX IF NOT EXISTS idx_agent_memories_profile_category ON agent_memories(profile_id, category);
```

The `context` JSONB column stores compaction metadata (`compacted`, `compacted_at`, `compacted_reason`, etc.).

### 2.5 `agent_profile_devices` — Device-agent assignments

```sql
CREATE TABLE IF NOT EXISTS agent_profile_devices (
    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    active BOOLEAN DEFAULT true,
    loaded_at TIMESTAMPTZ,
    PRIMARY KEY (profile_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_profile_devices_device ON agent_profile_devices(device_id);
```

### 2.6 `device_identities` — Auto-provisioned device storage

```sql
CREATE TABLE IF NOT EXISTS device_identities (
    device_id TEXT PRIMARY KEY,
    honcho_peer_id TEXT NOT NULL,
    mem0_user_id TEXT NOT NULL,
    honcho_workspace TEXT,
    provisioned_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_device_identities_last_seen ON device_identities(last_seen_at);
```

### 2.7 `sync_state` — Bidirectional sync tracking

```sql
CREATE TABLE IF NOT EXISTS sync_state (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('mem0', 'honcho')),
    source_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK (target IN ('mem0', 'honcho')),
    target_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, source_id, target)
);
```

### 2.8 `sync_log` — Sync run history

```sql
CREATE TABLE IF NOT EXISTS sync_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    direction TEXT NOT NULL CHECK (direction IN ('mem0_to_honcho', 'honcho_to_mem0')),
    items_synced INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running'
);
```

### 2.9 `categories` — Memory categories

```sql
CREATE TABLE IF NOT EXISTS categories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6366f1',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.10 `memory_categories` — Junction table

```sql
CREATE TABLE IF NOT EXISTS memory_categories (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, category_id)
);
```

### 2.11 `webhooks` — Event webhooks

```sql
CREATE TABLE IF NOT EXISTS webhooks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    url TEXT NOT NULL,
    events TEXT[] DEFAULT ARRAY['memory.created'],
    active BOOLEAN DEFAULT true,
    secret TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.12 `analytics` — Event tracking

```sql
CREATE TABLE IF NOT EXISTS analytics (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics(event_type);
```

### 2.13 Migration Strategy

There is no Alembic. All migrations run via `database.py:init_schema()` at startup using `CREATE TABLE IF NOT EXISTS` (idempotent). Adding a new column or table requires editing `init_schema()` directly.

---

## 3. Route Structure & API Contract

### 3.1 Internal Namespace: `/api/*`

All `/api/*` routes are **unauthenticated** (dashboard and local CLI use only). They are protected only by network binding (default: `0.0.0.0` for Docker).

Both `/api/*` and `/v1/*` routes are **co-located in the same route files** under `routes/`. There is no separate `routes/v1/` directory.

#### Health & Status

| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/api/health` | Health check | `{"status": "ok", "service": "merrick"}` |
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

**GET /api/sync/log query params:** `?limit=50&offset=0`

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
| `GET` | `/api/analytics/devices` | Per-device breakdown |
| `POST` | `/api/analytics/track` | Track a custom event |

#### Export (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/export/json` | Export memories as JSON |
| `GET` | `/api/export/csv` | Export as CSV |
| `GET` | `/api/export/markdown` | Export as Markdown |
| `GET` | `/api/export/full` | Full backup: devices + keys + memories |

#### Devices (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/devices` | List all provisioned devices |

**GET /api/devices response:**
```json
{
  "devices": [
    {
      "device_id": "hermes_phone_abc123",
      "honcho_peer_id": "device_hermes_phone_abc123",
      "mem0_user_id": "device_hermes_phone_abc123",
      "provisioned_at": "2026-07-13T10:00:00Z",
      "last_seen_at": "2026-07-13T12:00:00Z",
      "metadata": {}
    }
  ],
  "count": 1
}
```

#### API Keys (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/keys` | List all API keys (never returns `key_hash`) |
| `POST` | `/api/keys` | Create a new API key (secret shown once) |
| `PUT` | `/api/keys/{key_id}` | Update key scope/config |
| `DELETE` | `/api/keys/{key_id}` | Soft-delete (set `active=false`, `revoked_at=NOW()`) |
| `POST` | `/api/keys/{key_id}/rotate` | Rotate key (new secret, invalidate old) |

**POST /api/keys request:**
```json
{
  "device_id": "hermes_phone_abc123",
  "key_name": "Production key",
  "agent_slug": "hermes",
  "load_memories": true,
  "memory_categories": ["preferences", "context"],
  "memory_exclude_categories": [],
  "memory_scope": "shared",
  "max_memory_tokens": 2000,
  "permissions": ["read", "write"],
  "rate_limit": 100
}
```

**POST /api/keys response:**
```json
{
  "id": "...",
  "secret": "merrick_sk_aBcDeFgHiJkLmNoPqRsTuVwXyZ01234567890_",
  "key_prefix": "merrick_sk_aBcDeFg...",
  "key_name": "Production key",
  "device_id": "hermes_phone_abc123",
  "agent_slug": "hermes",
  "permissions": ["read", "write"],
  "rate_limit": 100,
  "active": true,
  "memory_categories": ["preferences", "context"],
  "max_memory_tokens": 2000,
  "created_at": "..."
}
```

**WARNING:** The `secret` field is only returned once at creation time. It cannot be retrieved later.

#### Agents (Internal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/agents` | List all agent profiles with memory counts |
| `POST` | `/api/agents` | Create a new agent profile |
| `GET` | `/api/agents/{slug}` | Get full agent profile with recent memories |
| `PUT` | `/api/agents/{slug}` | Update an agent profile |
| `DELETE` | `/api/agents/{slug}` | Delete agent profile (cascades to memories + device assignments) |

#### Dreaming (Internal)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/dreaming/run` | Manually trigger a dreaming cycle |
| `GET` | `/api/dreaming/stats` | Get compaction statistics |

---

### 3.2 External Namespace: `/v1/*`

All `/v1/*` routes require a valid API key via `Authorization: Bearer <key>`. Rate limiting applies per key. Device scope is resolved from the key.

#### Middleware Chain for `/v1/*`

```
Request → CORS → AuthMiddleware → Route Handler
                                   │
                                   ├─ Extract Bearer token (must start with merrick_sk_)
                                   ├─ SHA-256 hash → lookup in api_keys WHERE active=true
                                   ├─ Rate limit check (in-memory sliding window, 60s)
                                   ├─ Permission check (write required for POST/PUT/DELETE/PATCH)
                                   ├─ Inject request.state:
                                   │    key_id, key_name, device_id, agent_slug,
                                   │    load_memories, memory_categories,
                                   │    memory_exclude_categories, memory_scope,
                                   │    max_memory_tokens, permissions
                                   └─ Update last_used_at (fire-and-forget)
```

#### Memory (External — Device-Scoped)

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/memory/write` | Write a memory (scoped to device) |
| `POST` | `/v1/memory/search` | Search memories |
| `POST` | `/v1/memory/read` | Read a specific memory by ID |

**POST /v1/memory/write request:**
```json
{
  "content": "User prefers dark mode",
  "metadata": { "context": "settings_discussion" }
}
```

#### Query (External)

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/query` | Cross-system search (mem0 + Honcho) |

#### Agents (External)

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/agents` | List available agent profiles (filtered by key's agent scope) |
| `GET` | `/v1/agents/{slug}` | Get agent profile with memories (token-budget-aware truncation) |

**GET /v1/agents/{slug} response:**
```json
{
  "profile": { "id": "...", "name": "Hermes", "slug": "hermes", "system_prompt": "...", ... },
  "memories": [
    { "id": "...", "content": "User prefers dark mode", "category": "preferences", ... }
  ],
  "memory_count": 5,
  "tokens_used": 1234,
  "max_memory_tokens": 2000
}
```

Memories are truncated to fit within `max_memory_tokens` from the API key. Token estimation: ~4 chars per token.

**Memory loading behavior by `memory_scope`:**
| Scope | Behavior |
|---|---|
| `shared` | Loads from global `memories` table, filtered by `memory_categories` |
| `agent_only` | Loads from `agent_memories` table for this agent |
| `both` | Loads from both tables, combined |

#### Agent Memory (External)

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/agents/{slug}/memory` | Write a memory to a specific agent |
| `POST` | `/v1/agents/{slug}/memory/search` | Search agent memories by full-text query |

**POST /v1/agents/{slug}/memory request:**
```json
{
  "content": "User asked about API rates",
  "category": "support"
}
```

---

## 4. Auth Middleware

### 4.1 Scope: `/v1/*` Only

The `AuthMiddleware` in `middleware/auth.py` intercepts only requests starting with `/v1/`. Internal `/api/*` routes bypass auth entirely.

### 4.2 Flow

1. **Extract** — Bearer token from `Authorization` header
2. **Validate format** — Must start with `merrick_sk_`
3. **Hash** — `SHA-256(token)` → lookup in `api_keys WHERE key_hash = %s AND active = true`
4. **Rate limit** — In-memory sliding window per key_id. 60-second window. Returns `429` with `retry_after: 60` when exceeded.
5. **Permission check** — For POST/PUT/DELETE/PATCH, the key must have `write` in its `permissions` array
6. **Inject** — All key properties set on `request.state`
7. **Update** — `last_used_at = NOW()` (fire-and-forget, best-effort)

### 4.3 `request.state` Fields

After successful auth, the following fields are available to route handlers:

| Field | Type | Source Column | Description |
|---|---|---|---|
| `key_id` | `str` | `api_keys.id` | UUID of the API key |
| `key_name` | `str` | `api_keys.key_name` | Human-readable key name |
| `device_id` | `str` | `api_keys.device_id` | Device identifier bound to this key |
| `agent_slug` | `str \| None` | `api_keys.agent_slug` | Agent slug if key is agent-scoped |
| `load_memories` | `bool` | `api_keys.load_memories` | Whether to load memories for this key |
| `memory_categories` | `list[str] \| None` | `api_keys.memory_categories` | Category filter for memory loading |
| `memory_exclude_categories` | `list[str]` | `api_keys.memory_exclude_categories` | Categories to exclude |
| `memory_scope` | `str` | `api_keys.memory_scope` | `"shared"`, `"agent_only"`, or `"both"` |
| `max_memory_tokens` | `int` | `api_keys.max_memory_tokens` | Token budget for agent memory loading |
| `permissions` | `list[str]` | `api_keys.permissions` | `["read"]`, `["write"]`, or `["read", "write"]` |

### 4.4 Rate Limiting

In-memory sliding window. No Redis. No DB persistence across restarts. Good enough for a local daemon.

```python
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_WINDOW = 60  # seconds
```

When `len(timestamps within window) >= rate_limit`, returns `429`.

---

## 5. Configuration System

### 5.1 Flat Environment Variables

There is no cascading settings system, no config file, no database settings table. Configuration is loaded from environment variables via `config.py` at import time using `os.getenv()`.

### 5.2 Environment Variables

| Env Var | Default | Description |
|---|---|---|
| `MERRICK_DB_HOST` | `host.docker.internal` | PostgreSQL host |
| `MERRICK_DB_PORT` | `5433` | PostgreSQL port |
| `MERRICK_DB_USER` | `postgres` | PostgreSQL user |
| `MERRICK_DB_PASSWORD` | `""` | PostgreSQL password |
| `MERRICK_DB_NAME` | `postgres` | PostgreSQL database name |
| `MERRICK_HONCHO_URL` | `http://host.docker.internal:8000` | Honcho API base URL |
| `MERRICK_HONCHO_WORKSPACE` | `hermes` | Honcho workspace name |
| `MERRICK_HONCHO_USER_PEER` | `ron` | Default Honcho peer ID |
| `MERRICK_MEM0_API_URL` | `http://host.docker.internal:8888` | mem0 API URL |
| `MERRICK_MEM0_EMAIL` | `""` | mem0 dashboard login |
| `MERRICK_MEM0_PASSWORD` | `""` | mem0 dashboard password |
| `MERRICK_SYNC_INTERVAL` | `300` | Seconds between sync runs |
| `MERRICK_SYNC_ENABLED` | `true` | Enable/disable background sync |
| `MERRICK_DREAMING_ENABLED` | `true` | Enable/disable dreaming engine |
| `MERRICK_DREAMING_INTERVAL` | `3600` | Seconds between dreaming cycles (1 hour) |
| `MERRICK_DREAMING_STALE_DAYS` | `90` | Days before a memory is considered stale |
| `MERRICK_DREAMING_SIMILARITY_THRESHOLD` | `0.7` | Jaccard + word overlap threshold for dedup |

### 5.3 Additional Config (MCP Server)

| Env Var | Default | Description |
|---|---|---|
| `MERRICK_URL` | `http://localhost:5001` | Merrick API URL (used by MCP server and CLI) |
| `MERRICK_API_KEY` | `""` | API key for MCP server authentication |

### 5.4 Additional Config (CLI)

| Env Var | Default | Description |
|---|---|---|
| `MERRICK_URL` | `http://localhost:5001` | Merrick API URL |
| `MERRICK_CLI_TIMEOUT` | `30` | HTTP request timeout in seconds |

---

## 6. Dreaming Engine

### 6.1 Purpose

The dreaming engine (`dreaming.py`) is a background memory compaction loop that periodically runs to prevent prompt pollution. It marks memories as **compacted** rather than deleting them, so users can recover anything that was touched.

### 6.2 Background Thread

Started in `app.py` lifespan when `config.DREAMING_ENABLED` is true. Runs in a daemon thread at `config.DREAMING_INTERVAL` (default: 3600s / 1 hour).

### 6.3 Compaction Phases

Each dreaming cycle runs four phases in order:

#### Phase 1: Deduplication

Scans all non-compacted memories for duplicates using:
- **Exact match** after normalization (lowercase, strip punctuation, remove stop words)
- **Fuzzy match** using combined Jaccard similarity + word overlap ratio

Both metrics must exceed `DREAMING_SIMILARITY_THRESHOLD` (default: 0.7) to flag a duplicate. The older memory is marked compacted; the newer one is kept.

#### Phase 2: Contradiction Detection

Finds memories with similar topic openers (first ~10 words) but different full content. This catches cases like:
- "Project deadline is July 25" vs "Project deadline is August 1"

Topic similarity must be >= 0.6, full content similarity must be < 0.8. The older memory is marked compacted with `superseded_by` pointing to the newer one.

#### Phase 3: Staleness Detection

Finds memories older than `DREAMING_STALE_DAYS` (default: 90) that haven't been accessed recently. Marks them as compacted with reason `"stale"`.

#### Phase 4: Agent Memory Compaction

Runs deduplication and staleness (30-day threshold) on the `agent_memories` table separately.

### 6.4 Compaction Metadata

When a memory is compacted, its payload/context JSONB gets these fields added:

```json
{
  "compacted": true,
  "compacted_at": "2026-07-13T12:00:00Z",
  "compacted_reason": "duplicate",
  "compacted_from": ["uuid-of-kept-memory"],
  "similarity_score": 0.95
}
```

Reasons: `"duplicate"`, `"contradiction"`, `"stale"`.

### 6.5 Manual Trigger

```bash
POST /api/dreaming/run
GET  /api/dreaming/stats
```

---

## 7. Agent System

### 7.1 Agent Profiles

Agents are defined in `agent_profiles` with a name, slug (URL-safe identifier), system prompt, personality JSONB, optional custom instructions, and a memory scope.

Agents are created via the internal API:

```bash
POST /api/agents
{
  "name": "Hermes",
  "slug": "hermes",
  "system_prompt": "You are Hermes, a helpful AI assistant...",
  "personality": { "tone": "friendly", "style": "concise" },
  "custom_instructions": "Always refer to the user as 'sir'",
  "memory_scope": "shared"
}
```

### 7.2 Memory Scopes

| Scope | What the agent can see |
|---|---|
| `shared` | Global memories from the `memories` table (via mem0 sync) |
| `agent_only` | Only memories written to `agent_memories` for this specific agent |
| `both` | Both shared and agent-specific memories, combined |

### 7.3 Key-Agent Binding

API keys can be bound to a specific agent via `agent_slug`. When a key is agent-scoped:

- `GET /v1/agents` returns only that agent
- `GET /v1/agents/{slug}` is denied if `slug != key's agent_slug`
- `POST /v1/agents/{slug}/memory` is denied if `slug != key's agent_slug`

### 7.4 External Agent Endpoint

`GET /v1/agents/{slug}` is the main endpoint devices call. It returns the agent profile plus its memories, truncated to fit within `max_memory_tokens`.

Token budget truncation: memories are added in order (most recent first) until the token budget is exhausted. Token estimation: `len(content) // 4`.

### 7.5 Agent Memory Search

`POST /v1/agents/{slug}/memory/search` performs PostgreSQL full-text search on `agent_memories.content` using `plainto_tsquery('simple', ...)`. Results are filtered by the key's `memory_categories` and `memory_exclude_categories`.

---

## 8. Device Provisioning

### 8.1 Auto-Provisioning

When a new `device_id` hits any `/v1/*` endpoint, the provisioning module (`provisioning.py`) automatically:

1. Checks if `device_id` exists in `device_identities`
2. If not, derives storage IDs:
   - `honcho_peer_id = "device_{safe_device_id}"`
   - `mem0_user_id = "device_{safe_device_id}"`
3. Creates a Honcho peer via `POST /v3/workspaces/{workspace}/peers` (non-fatal if it fails)
4. Stores the mapping in `device_identities`
5. Returns the device's storage IDs for use in write/query

### 8.2 Caching

A thread-safe in-memory cache (`dict`) prevents repeated DB lookups. Cache is populated on first access and updated with `last_seen_at` on each request.

### 8.3 Fallback

If `device_id` is `"unknown"` or empty, the global `HONCHO_USER_PEER` is used as the fallback identity.

---

## 9. MCP Server

### 9.1 Purpose

The MCP (Model Context Protocol) server (`mcp_server/`) exposes Merrick's memory system as tools and resources for any MCP-compatible client: LM Studio, Claude Desktop, VS Code, etc.

### 9.2 Architecture

```
MCP Client (LM Studio, Claude Desktop)
    │
    │  stdio transport
    │
    ▼
mcp_server/server.py (MCPServer)
    │
    │  httpx (async)
    │
    ▼
Merrick HTTP API (localhost:5001)
```

The MCP server does **not** access the database directly. It talks to Merrick over HTTP, keeping it clean, stateless, and capable of connecting to remote instances.

### 9.3 Running

```bash
python -m mcp_server          # stdio transport (default)
mcp run mcp_server/server.py  # via MCP CLI
```

### 9.4 Configuration

| Env Var | Default | Description |
|---|---|---|
| `MERRICK_URL` | `http://localhost:5001` | Merrick API URL |
| `MERRICK_API_KEY` | `""` | API key (optional, for authenticated endpoints) |

### 9.5 Tools

| Tool | Description |
|---|---|
| `write_memory` | Write a memory to Merrick (via mem0 + Honcho). Params: `content`, `source`, `categories`. |
| `search_memories` | Search memories by query. Params: `query`, `categories`, `limit`. |
| `list_memories` | List recent memories. Params: `limit`, `category`. |
| `get_memory` | Get a specific memory by ID. Note: fetches all and filters (no per-memory GET endpoint). |
| `delete_memory` | Currently unsupported — returns an error with guidance. |
| `get_status` | Get Merrick health status (read-only). |

### 9.6 Resources

| Resource URI | Description |
|---|---|
| `merrick://status` | Merrick health status as JSON (same as `get_status`). |
| `merrick://memories` | 20 most recent memories as JSON. |

### 9.7 Files

| File | Purpose |
|---|---|
| `mcp_server/server.py` | MCPServer setup, tool/resource handlers, lifespan |
| `mcp_server/client.py` | Async HTTP client (`httpx`) for Merrick API |
| `mcp_server/config.py` | Environment variable loading |
| `mcp_server/__main__.py` | Entry point for `python -m mcp_server` |

---

## 10. CLI

### 10.1 Purpose

The CLI (`merrick_cli/`) provides a terminal interface for managing Merrick. Built with Click + Rich. Talks to Merrick over HTTP (same API as the dashboard).

### 10.2 Commands

| Command | Description |
|---|---|
| `merrick status` | Show health status and memory/session counts |
| `merrick devices` | List all provisioned devices |
| `merrick keys list` | List all API keys |
| `merrick keys create` | Create a new API key (interactive prompts) |
| `merrick memory write <content>` | Write a memory |
| `merrick memory search <query>` | Search memories |
| `merrick memory export` | Export all memories as JSON |
| `merrick sync` | Trigger a manual sync and show status |
| `merrick doctor` | Check if Merrick is running and diagnose issues |

### 10.3 Configuration

| Env Var | Default | Description |
|---|---|---|
| `MERRICK_URL` | `http://localhost:5001` | Merrick API URL |
| `MERRICK_CLI_TIMEOUT` | `30` | HTTP request timeout in seconds |

Can also be overridden with `--url` flag on the root command.

### 10.4 Files

| File | Purpose |
|---|---|
| `merrick_cli/main.py` | Click command definitions |
| `merrick_cli/client.py` | Sync HTTP client (`httpx`) for Merrick API |
| `merrick_cli/config.py` | Environment variable loading |

---

## 11. Docker

### 11.1 Standalone: `docker-compose.yml`

Runs **PostgreSQL (pgvector) + Merrick only**. For users who already run Honcho and/or mem0 elsewhere.

```bash
cp .env.example .env    # edit with your values
docker compose up -d --build
docker compose logs -f merrick
```

Services:
| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | `5433:5432` | PostgreSQL with pgvector |
| `merrick` | Built from `./Dockerfile` | `5001:5001` | Merrick daemon |

External services (Honcho, mem0) are expected to be reachable via `host.docker.internal`.

### 11.2 Full Stack: `docker-compose-full.yml`

Runs **everything**: PostgreSQL, Redis, Honcho API, Honcho Deriver, mem0, and Merrick.

```bash
docker compose -f docker-compose-full.yml up -d --build
docker compose -f docker-compose-full.yml logs -f merrick
```

Services:
| Service | Image/Build | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | `5433:5432` | PostgreSQL with pgvector |
| `redis` | `redis:alpine` | — | Honcho caching |
| `honcho-api` | Built from `/home/reposed/docker/honcho` | `8000:8000` | Honcho API |
| `honcho-deriver` | Built from `/home/reposed/docker/honcho` | — | Honcho background worker |
| `mem0` | Built from `/home/reposed/docker/mem0` | `8888:8000` | mem0 memory API |
| `merrick` | Built from `./Dockerfile` | `5001:5001` | Merrick daemon |

**NOTE:** Stop any existing Honcho/mem0 containers first:
```bash
docker stop honcho-api-1 honcho-deriver-1 mem0-api 2>/dev/null
```

### 11.3 Health Checks

Both compose files include health checks:
- **PostgreSQL:** `pg_isready`
- **Honcho:** HTTP GET `/health`
- **mem0:** HTTP GET `/health`
- **Merrick:** Python `urllib` GET `/api/health`
- **Redis:** `redis-cli ping`

---

## 12. Current Status

Merrick v2.0 is a **working daemon** with the following implemented and operational:

### What Works

- **Core memory bridge:** Bidirectional sync between mem0 and Honcho
- **API key auth:** `merrick_sk_` keys with SHA-256 hashing, rate limiting, permission scoping
- **Agent system:** Agent profiles with memory scopes, key-agent binding, token-budget-aware memory loading
- **Device provisioning:** Auto-creates Honcho peers and mem0 user mappings on first connect
- **Dreaming engine:** Background memory compaction (dedup, contradiction detection, staleness marking)
- **External API:** `/v1/*` namespace for device-authenticated memory operations
- **Internal API:** `/api/*` namespace for dashboard and local CLI
- **MCP server:** Exposes Merrick as MCP tools/resources for LM Studio, Claude Desktop, etc.
- **CLI:** Terminal interface for status, devices, keys, memory, sync, doctor
- **Docker:** Standalone and full-stack compose configurations
- **Dashboard SPA:** Browser UI for management

### What Was Planned but Not Built

- Settings cascade system (env → config file → database → API)
- Config file support (`~/.merrick/config.json`)
- Settings API routes (`/api/settings`)
- Setup wizard
- Rate limiting persistence (currently in-memory only)
- Request logging middleware
- `mem0_client.py` as a dedicated module (inline `httpx` calls remain in routes)
- `services/` layer (operations live in route handlers and `provisioning.py`)
- `schema/migrations.py` (no versioned migration system; `CREATE TABLE IF NOT EXISTS` only)
- OpenAI-compatible `/v1/chat/completions` endpoint
- Device self-service endpoints (`/v1/device/info`, `/v1/device/ping`)
- Device-scoped sync status (`/v1/sync/status`)
- `routes/v1/` directory (v1 routes are co-located with internal routes)

---

## Appendix A: File Tree

```
merrick/
├── app.py                          # FastAPI entrypoint, lifespan, router mount
├── config.py                       # Flat env-var config (os.getenv)
├── database.py                     # psycopg2 connection pool + schema init
├── dreaming.py                     # Memory compaction engine
├── honcho.py                       # Honcho HTTP client
├── provisioning.py                 # Device auto-provisioning (Honcho peers + mem0 users)
├── sync.py                         # Bidirectional mem0 ↔ Honcho sync
├── middleware/
│   ├── __init__.py
│   └── auth.py                     # API key auth, rate limiting, request.state injection
├── routes/
│   ├── __init__.py                 # Shared utilities (UUID validation, datetime conversion, SQL builder)
│   ├── agents.py                   # Agent profiles (internal CRUD + external memory)
│   ├── analytics.py                # Analytics endpoints
│   ├── categories.py               # Memory categories
│   ├── devices.py                  # Device listing
│   ├── dreaming.py                 # Dreaming trigger + stats
│   ├── export.py                   # Memory export (JSON, CSV, Markdown, full backup)
│   ├── keys.py                     # API key CRUD + rotation
│   ├── memory.py                   # Memory write (internal + /v1/memory/write)
│   ├── query.py                    # Cross-system query (internal + /v1/query)
│   ├── status.py                   # Dashboard aggregate status
│   ├── sync.py                     # Sync trigger/status/log
│   └── webhooks.py                 # Webhook CRUD + test
├── mcp_server/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point for python -m mcp_server
│   ├── client.py                   # Async HTTP client for Merrick API
│   ├── config.py                   # MCP server env-var config
│   └── server.py                   # MCPServer tools + resources
├── merrick_cli/
│   ├── __init__.py                 # __version__ = "0.1.0"
│   ├── client.py                   # Sync HTTP client for Merrick API
│   ├── config.py                   # CLI env-var config
│   └── main.py                     # Click commands: status, devices, keys, memory, sync, doctor
├── static/                         # Dashboard SPA files
├── docker-compose.yml              # Standalone: PostgreSQL + Merrick
├── docker-compose-full.yml         # Full stack: PostgreSQL + Redis + Honcho + mem0 + Merrick
├── Dockerfile
├── requirements.txt
├── ARCHITECTURE.md
├── AGENT.md
└── README.md
```

---

*Document generated by Monica Hall, VP of Business Development at Pied Piper.*
*Version: 2.0.0 | Date: 2026-08-26*

# Merrick — Developer Documentation

**Memory Bridge Service for Hermes AI — DEV Instance**

> *Named after Joseph Merrick (the Elephant Man), because elephants never forget.*

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Configuration](#configuration)
5. [Database Schema](#database-schema)
6. [Features](#features)
7. [Hermes Integration](#hermes-integration)
8. [Docker Deployment](#docker-deployment)
9. [Project Structure](#project-structure)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### What Merrick Is

Merrick is a **bidirectional memory bridge** service that synchronizes two AI memory systems:

| System | Role | Strengths | Weaknesses |
|--------|------|-----------|------------|
| **mem0** | Fast vector-based fact storage (pgvector on Supabase PostgreSQL) | Semantic search in milliseconds, simple API, ~288+ memories | Shallow reasoning, no context chaining |
| **Honcho** | Deep peer-to-peer reasoning engine | 90%+ on LongMem benchmarks, psychological modeling, conclusion generation | Slower, isolated, no native vector search |

**Before Merrick:** These systems were siloed. Hermes used mem0 for fast memory lookup, Honcho operated on its own, and they never shared data.

**After Merrick:** Every 5 minutes (configurable), facts flow from mem0 into Honcho for deep reasoning, and Honcho conclusions flow back into mem0 for fast retrieval. Hermes gets the best of both worlds — fast fact lookup AND deep cognitive reasoning — without any configuration changes.

### Why It Exists

A single AI agent needs memory that is both:

1. **Fast** — search hundreds of memories in milliseconds before every conversation turn
2. **Deep** — understand context, relationships, and psychological patterns across conversations

No single system excels at both. Merrick bridges them transparently.

### Key Capabilities

- **Bidirectional sync engine** — mem0 → Honcho and Honcho → mem0, every 5 minutes
- **Cross-system search** — query both systems simultaneously with deduplication
- **Memory write API** — write to both systems atomically (used by Hermes + Android)
- **Categories** — tag and organize memories
- **Webhooks** — event-driven notifications with HMAC signing
- **Analytics** — usage tracking, timeline, source breakdown
- **Export** — JSON, CSV, and Markdown export with category grouping
- **Dashboard UI** — dark-themed SPA for monitoring and management
- **Hermes memory provider plugin** — seamless integration with Hermes Agent

---

## Architecture

### High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Hermes Agent                             │
│    config.yaml: memory.provider = "merrick"                      │
│    Tools: merrick_search, merrick_add, merrick_list,             │
│           merrick_reasoning                                      │
└─────────────┬────────────────────────────────────┬───────────────┘
              │                                    │
              │ mem0 vector search                 │ Honcho reasoning
              ▼                                    ▼
┌─────────────────────────┐          ┌─────────────────────────────┐
│         mem0             │          │          Honcho              │
│  PostgreSQL + pgvector   │◄────────►│  Peer reasoning engine       │
│  Table: memories         │  Merrick │  Workspace: hermes           │
│  Port: 5433              │  sync    │  Peer: ron                   │
│  ~288+ memories          │  (5 min) │  Session: merrick_mem0_facts │
└─────────────────────────┘          └─────────────────────────────┘
              ▲                                    ▲
              │                                    │
              └────────────┬───────────────────────┘
                           │
              ┌────────────┴───────────────────────┐
              │            Merrick                  │
              │  FastAPI service (port 5001)        │
              │                                     │
              │  ┌──────────┐  ┌──────────────────┐ │
              │  │ sync.py  │  │   honcho.py      │ │
              │  │ (engine) │  │ (httpx HTTP      │ │
              │  │          │  │  client for      │ │
              │  │          │  │  Honcho v3 API)  │ │
              │  └──────────┘  └──────────────────┘ │
              │  ┌──────────┐  ┌──────────────────┐ │
              │  │database.py│ │   routes/         │ │
              │  │(psycopg2) │ │ (10 route files)  │ │
              │  └──────────┘  └──────────────────┘ │
              └─────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Backend** | Python FastAPI | 0.138.0 | REST API framework |
| **Server** | Uvicorn | 0.49.0 | ASGI server |
| **Database** | PostgreSQL (via Supabase) | 15+ | Primary data store |
| **Vector Engine** | pgvector | via Supabase | Semantic vector search |
| **DB Driver** | psycopg2-binary | 2.9.10 | PostgreSQL connection pooling |
| **HTTP Client** | httpx | 0.28.1 | Honcho API calls + mem0 API calls |
| **Frontend** | Vanilla HTML/CSS/JS | — | SPA dashboard |
| **Multipart** | python-multipart | 0.0.20 | Form data support |
| **Container** | Docker | — | Deployment |
| **Base Image** | python:3.12-slim | — | Container runtime |

### The Sync Engine

The sync engine (`sync.py`) runs as a **background daemon thread** started during FastAPI's lifespan startup. It operates in two independent directions:

#### Direction 1: mem0 → Honcho

```
1. Query all rows from the `memories` table in PostgreSQL
2. For each unsynced memory (checked via sync_state table):
   a. Ensure the session `merrick_mem0_facts` exists in Honcho
   b. Post the memory content as a message (peer="merrick")
   c. Record the mapping in sync_state (source='mem0', target='honcho')
3. Log synced count and errors
```

#### Direction 2: Honcho → mem0

```
1. List Honcho conclusions (limit: 100) via the Honcho v3 API
2. For each unsynced conclusion (checked via sync_state table):
   a. Generate a new UUID for the mem0 memory entry
   b. Insert into the `memories` table with payload:
      - data: conclusion content
      - source: 'honcho'
      - honcho_id: conclusion ID
      - user_id: 'ron'
   c. Record the mapping in sync_state (source='honcho', target='mem0')
3. Log synced count and errors
```

#### Fault Tolerance

- Each direction runs independently — if mem0→Honcho fails, Honcho→mem0 still runs
- Errors are logged, not fatal
- Sync results are recorded in `sync_log` with status `completed`, `completed_with_errors`, or `running`
- Duplicate prevention via `sync_state` unique constraint and `ON CONFLICT DO NOTHING`

#### Background Thread Lifecycle

```python
# app.py (simplified)
def _sync_loop():
    while True:
        time.sleep(config.SYNC_INTERVAL)     # default: 300 seconds
        try:
            result = sync.run_full_sync()
            logger.info("Background sync finished: %s", result)
        except Exception as e:
            logger.error("Background sync error: %s", e)

# Started during FastAPI lifespan startup
t = threading.Thread(target=_sync_loop, daemon=True)
t.start()
```

### The Honcho HTTP Client

`honcho.py` provides a thread-safe httpx client for the Honcho v3 API:

| Function | Honcho Endpoint | Purpose |
|----------|----------------|---------|
| `create_session()` | `POST /v3/workspaces/{ws}/sessions` | Create a Honcho session for mem0 imports |
| `post_message()` | `POST /v3/workspaces/{ws}/sessions/{id}/messages` | Post mem0 facts as messages |
| `list_conclusions()` | `POST /v3/workspaces/{ws}/conclusions/list` | Retrieve Honcho conclusions for sync |
| `search_peers()` | `POST /v3/workspaces/{ws}/peers/{id}/search` | Search peer memory (used by query + reasoning) |
| `list_sessions()` | `POST /v3/workspaces/{ws}/sessions/list` | List all sessions (used by status endpoint) |

The client is singleton-patterned with thread-locked reconnection. All responses gracefully handle Honcho's varying return formats (lists vs `{items: [...], total: N}`).

### The Hermes Memory Provider Plugin

The Merrick memory provider is a plugin for the Hermes Agent that replaces the default mem0 provider. When configured, Hermes routes all memory operations through Merrick's REST API instead of calling mem0 directly. This gives Hermes:

- **Write amplification** — facts are written to mem0 AND Honcho simultaneously
- **Deep reasoning** — `merrick_reasoning` tool queries Honcho for psychological/conceptual insights
- **Transparent enhancement** — no changes to how Hermes communicates; all the memory routing is handled by the plugin

Configuration and tool details are covered in the [Hermes Integration](#hermes-integration) section.

---

## API Reference

**Base URL:** `http://localhost:5001`

All endpoints return JSON. Successful health/status responses return HTTP 200. Errors return appropriate 4xx/5xx codes.

---

### Health & Status

#### `GET /api/health`

Service health check. Returns immediately with no database queries.

**Response (200):**
```json
{
  "status": "ok",
  "service": "merrick"
}
```

---

#### `GET /api/status`

Aggregate system status. Queries both mem0 and Honcho for counts and recent samples. Each subsystem query is independently fault-tolerant — if one fails, its value is returned as the string `"error"`.

**Response (200):**
```json
{
  "mem0_count": 288,
  "mem0_samples": [
    {
      "id": "a1b2c3d4-...",
      "text": "The user prefers dark mode and uses Vim",
      "user_id": "ron"
    }
  ],
  "honcho_sessions": 5,
  "honcho_conclusions": 12,
  "honcho_samples": [
    {
      "id": "conc_abc123",
      "text": "User demonstrates strong preference for CLI tools"
    }
  ],
  "last_sync": {
    "id": "e5f6a7b8-...",
    "direction": "mem0_to_honcho",
    "items_synced": 15,
    "errors": 0,
    "started_at": "2026-07-12T10:00:00Z",
    "completed_at": "2026-07-12T10:00:12Z",
    "status": "completed"
  },
  "sync_status": "idle",
  "sync_state_counts": [
    { "source": "mem0", "target": "honcho", "cnt": 280 },
    { "source": "honcho", "target": "mem0", "cnt": 12 }
  ]
}
```

**`sync_status` values:** `idle`, `running`, `error` — derived from the last sync log's `status` field.

---

### Memory Operations

#### `POST /api/memory/write`

Write a memory fact to **both** mem0 and Honcho simultaneously. This is the primary write path used by Hermes and Android clients.

**Request Body:**
```json
{
  "content": "User prefers dark mode terminals",
  "source": "hermes",
  "user_id": "ron",
  "metadata": {
    "conversation_id": "conv_123"
  }
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `content` | string | **Yes** | — | The memory fact text (min 1 char) |
| `source` | string | No | `"hermes"` | Origin identifier. `"hermes"` or `"android"` |
| `user_id` | string | No | `MERRICK_HONCHO_USER_PEER` | User identifier |
| `metadata` | object | No | `null` | Arbitrary metadata to attach |

**Write Flow:**
1. Authenticate with mem0 API (`POST /auth/login` with `MERRICK_MEM0_EMAIL` / `MERRICK_MEM0_PASSWORD`)
2. Write to mem0 via authenticated API (`POST /memories` with `messages: [{role: "user", content}]`)
3. Create or reuse Honcho session `merrick_{source}_{user_id}`
4. Post the content as a Honcho message
5. Fire webhooks for `memory.created` event
6. Track analytics event `memory.created` with source

**Response (200):**
```json
{
  "status": "ok",
  "results": {
    "mem0": {
      "success": true,
      "id": "a1b2c3d4-..."
    },
    "honcho": {
      "success": true,
      "id": "msg_abc123"
    }
  }
}
```

If one system fails, `status` will be `"partial"` and the failing system's result will include an `"error"` field. Both systems are attempted regardless — a failure in one does not prevent the other.

---

#### `POST /api/memory/reasoning`

Query Honcho for deep reasoning/conceptual insights. Unlike `/api/query`, this only searches Honcho (not mem0).

**Request Body:**
```json
{
  "query": "what are the user's psychological patterns",
  "peer": "ron"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | **Yes** | — | Search query |
| `peer` | string | No | `MERRICK_HONCHO_USER_PEER` | Honcho peer to search |

**Response (200):**
```json
{
  "status": "ok",
  "peer": "ron",
  "query": "what are the user's psychological patterns",
  "results": [
    {
      "id": "conclusion_123",
      "peer_id": "ron",
      "content": "User tends to prefer asynchronous communication and avoids real-time interruptions...",
      "score": 0.89
    }
  ],
  "count": 1
}
```

---

### Cross-System Query

#### `POST /api/query`

Search across **both mem0 and Honcho** simultaneously. Deduplicates results by content.

**Request Body:**
```json
{
  "query": "user preferences"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | **Yes** | Search query (min 1 char) |

**Search Behavior:**
- **mem0:** Full-text search using PostgreSQL `to_tsvector('simple', payload->>'data') @@ plainto_tsquery('simple', ?)`. Returns up to 10 results.
- **Honcho:** Peer search via Honcho's `/v3/workspaces/{ws}/peers/{peer_id}/search` endpoint.
- **Deduplication:** Results with identical `data` content are collapsed to a single entry.

**Response (200):**
```json
{
  "results": [
    {
      "source": "mem0",
      "data": "The user prefers dark mode and uses Vim",
      "user_id": "ron"
    },
    {
      "source": "honcho",
      "data": "User demonstrates strong preference for keyboard-driven workflows",
      "metadata": {
        "id": "conclusion_abc",
        "peer_id": "ron",
        "content": "User demonstrates strong preference..."
      }
    }
  ],
  "count": 2
}
```

---

### Sync Operations

#### `POST /api/sync/trigger`

Manually trigger a full bidirectional sync. The sync runs in a FastAPI background task — this endpoint returns immediately.

**Request:** No body required.

**Response (200):**
```json
{
  "status": "sync_triggered"
}
```

**Behavior:**
- Executes `sync_mem0_to_honcho()` then `sync_honcho_to_mem0()`
- Each direction is independently fault-tolerant
- Results are recorded in the `sync_log` table
- Monitor completion via `GET /api/sync/status`

---

#### `GET /api/sync/status`

Current sync state and statistics.

**Response (200):**
```json
{
  "last_sync": {
    "id": "e5f6a7b8-...",
    "direction": "mem0_to_honcho",
    "items_synced": 15,
    "errors": 0,
    "started_at": "2026-07-12T10:00:00Z",
    "completed_at": "2026-07-12T10:00:12Z",
    "status": "completed"
  },
  "running_count": 0,
  "sync_state_counts": [
    { "source": "mem0", "target": "honcho", "cnt": 280 },
    { "source": "honcho", "target": "mem0", "cnt": 12 }
  ]
}
```

**`running_count`:** Number of sync operations currently with status `'running'`.

---

#### `GET /api/sync/log`

History of sync operations. Sorted by most recent first.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `50` | Maximum entries to return |

**Response (200):**
```json
{
  "log": [
    {
      "id": "e5f6a7b8-...",
      "direction": "mem0_to_honcho",
      "items_synced": 15,
      "errors": 0,
      "started_at": "2026-07-12T10:00:00Z",
      "completed_at": "2026-07-12T10:00:12Z",
      "status": "completed"
    }
  ]
}
```

---

### Categories

Categories allow tagging and organizing memories. Each memory can belong to multiple categories.

#### `GET /api/categories`

List all categories with their memory counts.

**Response (200):**
```json
{
  "categories": [
    {
      "id": "cat-uuid-1",
      "name": "Preferences",
      "color": "#6366f1",
      "created_at": "2026-07-10T08:00:00Z",
      "memory_count": 12
    }
  ]
}
```

---

#### `POST /api/categories`

Create a new category. Names must be unique.

**Request Body:**
```json
{
  "name": "Preferences",
  "color": "#6366f1"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **Yes** | — | Category name (unique) |
| `color` | string | No | `"#6366f1"` | Hex color for UI display |

**Response (200):**
```json
{
  "id": "cat-uuid-new",
  "name": "Preferences",
  "color": "#6366f1"
}
```

**Errors:**
- `409 Conflict` — Category name already exists

---

#### `DELETE /api/categories/{category_id}`

Delete a category and all its memory associations.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category_id` | UUID | Category to delete |

**Response (200):**
```json
{
  "deleted": "cat-uuid-1"
}
```

**Errors:**
- `400 Bad Request` — Invalid UUID format
- `404 Not Found` — Category does not exist

---

#### `POST /api/categories/{category_id}/assign`

Assign a memory to a category.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category_id` | UUID | Target category |

**Request Body:**
```json
{
  "memory_id": "mem-uuid-1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `memory_id` | string | **Yes** | UUID of the memory |

**Response (200):**
```json
{
  "assigned": true,
  "memory_id": "mem-uuid-1",
  "category_id": "cat-uuid-1"
}
```

**Errors:**
- `400 Bad Request` — Invalid UUID format for either ID
- `404 Not Found` — Category or memory does not exist

---

#### `DELETE /api/categories/{category_id}/unassign/{memory_id}`

Remove a memory from a category. Idempotent — no error if the memory wasn't assigned.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category_id` | UUID | Category |
| `memory_id` | UUID | Memory to unassign |

**Response (200):**
```json
{
  "unassigned": true,
  "memory_id": "mem-uuid-1",
  "category_id": "cat-uuid-1"
}
```

---

#### `GET /api/categories/{category_id}/memories`

List all memories assigned to a category, including the category details.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `category_id` | UUID | Category |

**Response (200):**
```json
{
  "category": {
    "id": "cat-uuid-1",
    "name": "Preferences",
    "color": "#6366f1"
  },
  "memories": [
    {
      "id": "mem-uuid-1",
      "data": "User prefers dark mode terminals",
      "source": "hermes",
      "user_id": "ron",
      "category_id": "cat-uuid-1"
    }
  ],
  "count": 1
}
```

---

### Webhooks

Webhooks fire HTTP POST requests to configured URLs when memory events occur. Supports HMAC-SHA256 signing for payload verification.

#### `GET /api/webhooks`

List all configured webhooks.

**Response (200):**
```json
{
  "webhooks": [
    {
      "id": "hook-uuid-1",
      "url": "https://example.com/webhook",
      "events": ["memory.created"],
      "active": true,
      "secret": null,
      "created_at": "2026-07-10T08:00:00"
    }
  ]
}
```

---

#### `POST /api/webhooks`

Create a new webhook.

**Request Body:**
```json
{
  "url": "https://example.com/webhook",
  "events": ["memory.created"],
  "secret": "my_hmac_secret_key"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | **Yes** | — | Target URL for POST delivery |
| `events` | string[] | No | `["memory.created"]` | Events to subscribe to |
| `secret` | string | No | `null` | HMAC-SHA256 signing secret |

**Response (200):**
```json
{
  "id": "hook-uuid-new",
  "url": "https://example.com/webhook",
  "events": ["memory.created"],
  "active": true
}
```

**Webhook Delivery Format:**
```json
{
  "event": "memory.created",
  "data": {
    "id": "mem0-uuid",
    "content": "User prefers dark mode terminals",
    "source": "hermes",
    "user_id": "ron"
  }
}
```

When a `secret` is configured, the delivery includes an `X-Merrick-Signature` header containing the HMAC-SHA256 hex digest of the JSON payload body. Verify on the receiving end by computing `hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()` and comparing.

**Supported Events:**
- `memory.created` — Fired when a memory is successfully written to mem0 via `POST /api/memory/write`

---

#### `PUT /api/webhooks/{hook_id}`

Update an existing webhook. All fields are optional — only provided fields are updated.

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `hook_id` | UUID | Webhook to update |

**Request Body (all fields optional):**
```json
{
  "url": "https://new-url.example.com/webhook",
  "events": ["memory.created"],
  "active": false,
  "secret": "new_secret"
}
```

**Response (200):**
```json
{
  "updated": "hook-uuid-1"
}
```

---

#### `DELETE /api/webhooks/{hook_id}`

Delete a webhook.

**Response (200):**
```json
{
  "deleted": "hook-uuid-1"
}
```

---

#### `POST /api/webhooks/{hook_id}/test`

Send a test payload to a webhook to verify connectivity. Returns the HTTP status code from the target.

**Response (200):**
```json
{
  "sent": true,
  "status_code": 200,
  "webhook_id": "hook-uuid-1"
}
```

The test payload sent:
```json
{
  "event": "webhook.test",
  "data": {
    "message": "This is a test webhook from Merrick",
    "webhook_id": "hook-uuid-1"
  }
}
```

---

### Analytics

Analytics events are automatically tracked when memories are created. The analytics system records event type, source, and arbitrary metadata.

#### `GET /api/analytics/overview`

Aggregate statistics: total memories, categories, webhooks, sync records, and memory creation counts for today/this week/this month.

**Response (200):**
```json
{
  "total_memories": 288,
  "total_categories": 5,
  "total_webhooks": 2,
  "total_syncs": 560,
  "memories_today": 3,
  "memories_this_week": 22,
  "memories_this_month": 87
}
```

---

#### `GET /api/analytics/timeline`

Memory creation timeline grouped by day, week, or month.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `period` | string | `"day"` | Grouping: `"day"`, `"week"`, or `"month"` |
| `days` | int | `30` | Lookback window (1–365) |

**Response (200):**
```json
{
  "timeline": [
    { "date": "2026-07-01", "count": 5 },
    { "date": "2026-07-02", "count": 12 }
  ],
  "period": "day",
  "days": 30
}
```

---

#### `GET /api/analytics/sources`

Breakdown of memory creations by source (e.g., `"hermes"`, `"android"`, `"honcho"`).

**Response (200):**
```json
{
  "sources": [
    { "source": "hermes", "count": 250 },
    { "source": "honcho", "count": 35 },
    { "source": "android", "count": 3 }
  ]
}
```

---

#### `GET /api/analytics/categories`

Memory count per category (from actual category assignments, not analytics events).

**Response (200):**
```json
{
  "categories": [
    { "name": "Preferences", "color": "#6366f1", "count": 12 },
    { "name": "Technical", "color": "#10b981", "count": 8 }
  ]
}
```

---

#### `POST /api/analytics/track`

Track a custom analytics event (not automatically fired — use for manual instrumentation).

**Request Body:**
```json
{
  "event_type": "custom.event",
  "source": "admin",
  "metadata": { "note": "manual trigger" }
}
```

**Response (200):**
```json
{
  "tracked": true,
  "event_type": "custom.event"
}
```

---

### Export

Export all memories (or a filtered subset by category) in multiple formats. Categories are included in all export formats.

#### `GET /api/export/json`

Export memories as a JSON object.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `category_id` | UUID | No | Filter to a specific category |

**Response (200):**
```json
{
  "memories": [
    {
      "id": "mem-uuid-1",
      "data": "User prefers dark mode terminals",
      "source": "hermes",
      "user_id": "ron",
      "categories": ["Preferences", "Technical"]
    }
  ],
  "count": 288
}
```

---

#### `GET /api/export/csv`

Export memories as a downloadable CSV file.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `category_id` | UUID | No | Filter to a specific category |

**Response:** `Content-Type: text/csv` with `Content-Disposition: attachment; filename=merrick_export.csv`

**CSV Columns:** `id`, `data`, `source`, `user_id`, `categories` (semicolon-separated)

---

#### `GET /api/export/markdown`

Export memories as a downloadable Markdown file, grouped by category. Uncategorized memories appear under an "Uncategorized" heading.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `category_id` | UUID | No | Filter to a specific category |

**Response:** `Content-Type: text/markdown` with `Content-Disposition: attachment; filename=merrick_export.md`

**Example Output:**
```markdown
# Merrick Memory Export

## Preferences
- User prefers dark mode terminals
- User uses Vim as primary editor

## Technical
- User's primary language is Python
- User prefers async/await over callbacks

## Uncategorized
- User lives in the Pacific timezone
```

---

## Configuration

All configuration is via environment variables, typically loaded from a `.env` file.

### Environment Variables

#### Database (mem0's PostgreSQL)

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_DB_HOST` | `host.docker.internal` | PostgreSQL host address |
| `MERRICK_DB_PORT` | `5433` | PostgreSQL port |
| `MERRICK_DB_USER` | `postgres` | Database user |
| `MERRICK_DB_PASSWORD` | *(empty)* | Database password |
| `MERRICK_DB_NAME` | `postgres` | Database name |

#### Honcho

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_HONCHO_URL` | `http://host.docker.internal:8000` | Honcho API base URL |
| `MERRICK_HONCHO_WORKSPACE` | `hermes` | Honcho workspace name |
| `MERRICK_HONCHO_USER_PEER` | `ron` | Default peer ID for user data |

#### mem0 API

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_MEM0_API_URL` | `http://host.docker.internal:8888` | mem0 API base URL (for authenticated writes) |
| `MERRICK_MEM0_EMAIL` | *(empty)* | mem0 login email |
| `MERRICK_MEM0_PASSWORD` | *(empty)* | mem0 login password |

#### Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_SYNC_INTERVAL` | `300` | Sync interval in seconds (300 = 5 minutes) |
| `MERRICK_SYNC_ENABLED` | `true` | Whether to start the background sync thread |

### Full `.env` Example

```bash
# PostgreSQL (mem0's database)
MERRICK_DB_HOST=host.docker.internal
MERRICK_DB_PORT=5433
MERRICK_DB_USER=postgres
MERRICK_DB_PASSWORD=supabase_strong_password_2026!
MERRICK_DB_NAME=postgres

# Honcho reasoning engine
MERRICK_HONCHO_URL=http://host.docker.internal:8000
MERRICK_HONCHO_WORKSPACE=hermes
MERRICK_HONCHO_USER_PEER=ron

# mem0 API (for authenticated writes via /api/memory/write)
MERRICK_MEM0_API_URL=http://host.docker.internal:8888
MERRICK_MEM0_EMAIL=admin@example.com
MERRICK_MEM0_PASSWORD=your_password_here

# Background sync
MERRICK_SYNC_INTERVAL=300
MERRICK_SYNC_ENABLED=true
```

### Network Access Points

| Access Method | URL |
|---------------|-----|
| Localhost | `http://localhost:5001` |
| Tailscale | `http://<your-tailscale-ip>:5001` |
| Local Network | `http://<your-local-ip>:5001` |

---

## Database Schema

Merrick creates its own tables on startup via `database.init_schema()` (called during the FastAPI lifespan startup event). All tables live in the same PostgreSQL database as mem0's `memories` table.

### `sync_state`

Tracks which items have been synced between systems. Prevents duplicate synchronization.

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

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `source` | TEXT | Origin system: `'mem0'` or `'honcho'` |
| `source_id` | TEXT | ID of the item in the source system |
| `target` | TEXT | Destination system: `'mem0'` or `'honcho'` |
| `target_id` | TEXT | ID of the item in the target system (nullable) |
| `synced_at` | TIMESTAMPTZ | Timestamp when this mapping was recorded |

**Unique constraint:** `(source, source_id, target)` — guarantees each item is synced at most once in each direction.

---

### `sync_log`

Audit trail of all sync operations. One row per sync direction per run.

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

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `direction` | TEXT | `'mem0_to_honcho'` or `'honcho_to_mem0'` |
| `items_synced` | INTEGER | Number of items successfully synced |
| `errors` | INTEGER | Number of errors encountered |
| `started_at` | TIMESTAMPTZ | When this sync operation started |
| `completed_at` | TIMESTAMPTZ | When it completed (null if still running) |
| `status` | TEXT | `'running'`, `'completed'`, or `'completed_with_errors'` |

---

### `categories`

User-defined categories for organizing memories.

```sql
CREATE TABLE IF NOT EXISTS categories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6366f1',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `name` | TEXT | Unique category name |
| `color` | TEXT | Hex color for UI display (default: `#6366f1`) |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

---

### `memory_categories`

Join table linking memories to categories (many-to-many).

```sql
CREATE TABLE IF NOT EXISTS memory_categories (
    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (memory_id, category_id)
);
```

| Column | Type | Description |
|--------|------|-------------|
| `memory_id` | UUID | Foreign key to `memories.id` |
| `category_id` | UUID | Foreign key to `categories.id` |

**Cascading deletes:** Deleting a memory or category automatically removes the join row.

---

### `webhooks`

Configured webhook endpoints for event notifications.

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

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `url` | TEXT | Target URL for POST delivery |
| `events` | TEXT[] | Array of event types to subscribe to |
| `active` | BOOLEAN | Whether the webhook is enabled |
| `secret` | TEXT | HMAC-SHA256 signing secret (nullable) |
| `created_at` | TIMESTAMPTZ | Creation timestamp |

---

### `analytics`

Event log for usage tracking and metrics.

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

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `event_type` | TEXT | Event category (e.g., `'memory.created'`) |
| `source` | TEXT | Origin of the event (e.g., `'hermes'`, `'android'`) |
| `metadata` | JSONB | Arbitrary event metadata |
| `created_at` | TIMESTAMPTZ | Event timestamp |

**Indexes:** `idx_analytics_created` (for timeline queries), `idx_analytics_event_type` (for type filtering).

---

### External Tables (mem0)

| Table | Owner | Used By Merrick For |
|-------|-------|---------------------|
| `memories` | mem0 | Reading facts for mem0→Honcho sync; writing Honcho conclusions; search queries; category assignment; export |

Merrick connects directly to mem0's PostgreSQL database and uses the `memories` table as both a source (reading facts to push to Honcho) and a sink (writing Honcho conclusions back). The `memories` table is not created by Merrick — it must already exist via mem0's own schema management.

---

## Features

### Categories

Categories provide a lightweight tagging system for memories. They support:

- **CRUD operations** on categories (name + color)
- **Many-to-many** assignment (one memory can belong to multiple categories)
- **Memory listing** by category, with full payload details
- **Persistence** via the `categories` and `memory_categories` tables
- **UI integration** in the dashboard's Categories tab
- **Export integration** — all export formats include category membership

All category endpoints validate UUID format and return appropriate 400/404/409 error codes.

### Webhooks

Webhooks enable external systems to react to Merrick events in real time. Features:

- **Event subscriptions** — subscribe to `memory.created` events (extensible to more event types)
- **HMAC-SHA256 signing** — optional shared secret for payload integrity verification
- **Test endpoint** — verify connectivity without creating real data
- **Active/inactive toggle** — disable a webhook without deleting it
- **Automatic firing** — webhooks fire as a side effect of `POST /api/memory/write` (only when the mem0 write succeeds)
- **Fault isolation** — a failing webhook never blocks the primary operation; errors are logged as warnings

**HMAC Verification (receiving side):**

```python
import hmac
import hashlib
import json

def verify_merrick_signature(body_bytes: bytes, secret: str, signature: str) -> bool:
    expected = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

The signature is sent in the `X-Merrick-Signature` HTTP header.

### Analytics

The analytics system provides visibility into memory usage over time:

- **Automatic tracking** — `memory.created` events are tracked as a side effect of successful writes
- **Manual tracking** — `POST /api/analytics/track` for custom instrumentation
- **Overview** — totals with daily/weekly/monthly breakdowns
- **Timeline** — time-series data grouped by day, week, or month with configurable lookback
- **Sources** — breakdown of memory creation by origin (`hermes`, `android`, `honcho`)
- **Categories** — memory distribution across categories (from actual assignments)
- **Indexes** — optimized for time-range and event-type queries

### Export

The export system provides data portability in three formats:

| Format | Content-Type | File Extension | Grouping |
|--------|-------------|----------------|----------|
| JSON | `application/json` | `.json` | Flat list with category arrays |
| CSV | `text/csv` | `.csv` | Flat rows, semicolon-separated categories |
| Markdown | `text/markdown` | `.md` | Grouped by category, H2 headings |

All formats support optional `category_id` filtering. Categories are resolved via a JOIN on `memory_categories` and `categories` tables.

### Cross-Device Memory Sharing

Merrick enables memory sharing across devices and interfaces:

```
Hermes Agent (CLI) ──► mem0 (via merrick provider)
                            │
Android App ───────────────►│
                            ▼
                      Merrick API
                      POST /api/memory/write
                            │
                     ┌──────┴──────┐
                     ▼              ▼
                   mem0          Honcho
                 (fast search)  (deep reasoning)
```

When an Android device writes a memory via `POST /api/memory/write` with `source: "android"`, the memory appears in both mem0 and Honcho. Hermes automatically picks it up during its next conversation turn via mem0's vector search — no additional configuration required. The `source` field distinguishes the origin in analytics and export.

### Dashboard UI

A single-page application served directly from Merrick at `http://localhost:5001`. No build step, no framework dependencies.

**Tabs:**

| Tab | Description | Auto-Refresh |
|-----|-------------|-------------|
| **Dashboard** | Stats grid (mem0 memories, Honcho sessions/conclusions, last sync, sync status), sample cards, Sync Now button | Every 30s |
| **Query** | Cross-system search with source badges (blue=mem0, purple=Honcho), spinner during search | — |
| **Sync Log** | Table of all sync operations (time, direction, items synced, errors, status) | Every 10s |
| **Categories** | Category CRUD, memory assignment, color picker | — |
| **Analytics** | Stats grid, source breakdown, category distribution, activity timeline | — |
| **Export** | One-click downloads in JSON, CSV, and Markdown | — |

**Technical details:**
- Dark theme (CSS variables, `#0a0a0f` background)
- Responsive design (breakpoints at 768px and 640px)
- Tab-based SPA routing via `data-tab` attributes
- Toast notifications (bottom-right, auto-dismiss after 4 seconds)
- Elephant emoji favicon (SVG data URI)

---

## Hermes Integration

### How the Memory Provider Plugin Works

The Merrick memory provider replaces Hermes Agent's default mem0 provider. Instead of calling mem0's API directly, memory operations are routed through Merrick's REST API. This enables:

1. **Dual writes** — every memory fact is written to mem0 (fast search) AND Honcho (deep reasoning)
2. **Rich retrieval** — search queries check both systems
3. **Deep reasoning** — dedicated tool queries Honcho for conceptual/psychological insights

### Plugin Configuration

In Hermes Agent's `~/.hermes/config.yaml`:

```yaml
memory:
  provider: merrick
  merrick:
    base_url: http://localhost:5001
    user_id: ron
```

### Plugin Location

The plugin file is installed at:

```
~/.hermes/providers/memory/merrick.py
```

And its configuration:

```
~/.hermes/providers/memory/merrick.json
```

The `merrick.json` manifest registers the provider and declares its tools:

```json
{
  "name": "merrick",
  "version": "0.1.0",
  "description": "Bidirectional memory bridge between mem0 and Honcho",
  "tools": [
    "merrick_search",
    "merrick_add",
    "merrick_list",
    "merrick_reasoning"
  ]
}
```

### Available Tools

When the Merrick provider is active, Hermes Agent has access to these memory tools:

#### `merrick_search`

Search across both mem0 and Honcho. Equivalent to `POST /api/query`.

```
Tool: merrick_search
Description: Search memories across mem0 and Honcho
Parameters:
  - query (str): The search query
```

**Internal flow:** Calls `POST /api/query` with `{"query": "..."}`. Returns deduplicated results from both systems.

#### `merrick_add`

Add a new memory fact. Equivalent to `POST /api/memory/write`.

```
Tool: merrick_add
Description: Store a new memory fact in both mem0 and Honcho
Parameters:
  - content (str): The memory fact to store
  - source (str, optional): Origin identifier (default: "hermes")
```

**Internal flow:** Calls `POST /api/memory/write` with `{"content": "...", "source": "hermes"}`. Writes to both systems.

#### `merrick_list`

List recent memories. Equivalent to `GET /api/status` (mem0_samples).

```
Tool: merrick_list
Description: List recent memories from mem0
Parameters:
  - limit (int, optional): Number of memories to return
```

**Internal flow:** Calls `GET /api/status` and extracts the `mem0_samples` field.

#### `merrick_reasoning`

Query Honcho for deep reasoning. Equivalent to `POST /api/memory/reasoning`.

```
Tool: merrick_reasoning
Description: Deep reasoning/insights from Honcho about a topic
Parameters:
  - query (str): The search query
```

**Internal flow:** Calls `POST /api/memory/reasoning` with `{"query": "..."}`. Returns Honcho search results.

### Why It's Transparent

From Hermes' perspective, memory operations work the same regardless of the provider. The Merrick plugin:

1. Implements the same interface as the default mem0 provider
2. Calls Merrick's REST API instead of mem0's API
3. Returns results in the format Hermes expects

This means Hermes can switch between the mem0 provider and the Merrick provider by changing one line in `config.yaml` — no agent code changes required.

### Data Flow During a Conversation

```
User: "Remember I prefer dark mode"
        │
        ▼
Hermes Agent
  │
  ├──► merrick_add("User prefers dark mode", source="hermes")
  │       │
  │       ├──► mem0: Store fact (fast retrieval)
  │       └──► Honcho: Store fact (future deep reasoning)
  │
  └──► (5 min later, Merrick background sync)
          │
          ├──► Honcho conclusions → mem0 (enriched facts)
          └──► mem0 facts → Honcho (context for reasoning)

Next conversation:
User: "What editor do I use?"
        │
        ▼
Hermes Agent
  │
  ├──► merrick_search("editor")
  │       ├──► mem0: "User prefers Vim" (fast search hit)
  │       └──► Honcho: "User favors keyboard-driven tools" (deep insight)
  │
  └──► Response: "You use Vim — consistent with your preference
                 for keyboard-driven workflows."
```

---

## Docker Deployment

### `docker-compose.yml`

```yaml
services:
  merrick:
    build: .
    container_name: merrick
    ports:
      - "5001:5001"
    env_file:
      - .env
    environment:
      - MERRICK_DB_HOST=host.docker.internal
      - MERRICK_HONCHO_URL=http://host.docker.internal:8000
      - MERRICK_MEM0_API_URL=http://host.docker.internal:8888
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:5001/api/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5001
CMD ["python", "app.py"]
```

### Docker Commands

```bash
# Build and start
docker compose up -d --build

# View logs
docker compose logs -f merrick

# Check health
docker compose ps

# Stop
docker compose down

# Rebuild after code changes
docker compose up -d --build --force-recreate

# Verify health from outside the container
curl http://localhost:5001/api/health
```

### Health Check

The container includes a Docker health check:
- **Interval:** 10 seconds
- **Timeout:** 5 seconds
- **Retries:** 3 (marks unhealthy after 30 seconds of failures)
- **Test:** HTTP GET to `http://localhost:5001/api/health`

### Networking

Merrick in Docker uses `host.docker.internal` to reach services running on the host machine (Supabase PostgreSQL on 5433, Honcho on 8000, mem0 API on 8888). The `extra_hosts` directive maps `host.docker.internal` to the Docker host gateway.

---

## Project Structure

```
merrick/
├── app.py                  # FastAPI entrypoint, lifespan, CORS, route mounting
├── config.py               # Environment variable loading (all MERRICK_* vars)
├── database.py             # PostgreSQL connection pool, query helpers, schema init
├── honcho.py               # Honcho v3 API HTTP client (thread-safe singleton)
├── sync.py                 # Bidirectional sync engine + background loop
├── requirements.txt        # Python dependencies (5 packages)
├── Dockerfile              # Container build definition
├── docker-compose.yml      # Container orchestration with health check
├── .env                    # Runtime configuration (not committed)
├── .env.example            # Configuration template
├── .gitignore              # Git ignore rules
├── README.md               # Project README
├── DOCS.md                 # This file
│
├── routes/
│   ├── __init__.py         # Package marker (empty)
│   ├── sync.py             # POST /api/sync/trigger, GET /api/sync/status, GET /api/sync/log
│   ├── query.py            # POST /api/query (cross-system search with dedup)
│   ├── status.py           # GET /api/status (aggregate stats)
│   ├── memory.py           # POST /api/memory/write, POST /api/memory/reasoning
│   ├── categories.py       # CRUD + assign/unassign/list for categories
│   ├── webhooks.py         # CRUD + test for webhooks, fire_webhooks() helper
│   ├── analytics.py        # Overview/timeline/sources/categories + track_event()
│   └── export.py           # JSON/CSV/Markdown export with category grouping
│
├── schema/
│   └── merrick.sql         # Standalone DDL for sync_state + sync_log
│
└── static/
    ├── index.html          # SPA shell (6 tabs: dashboard, query, synclog, categories, analytics, export)
    ├── style.css           # Dark theme styles (responsive)
    └── app.js              # Frontend logic (tab switching, API calls, rendering)
```

### File Responsibilities

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 93 | FastAPI app, CORS, lifespan (startup thread + schema init), static file serving |
| `config.py` | 21 | Load all `MERRICK_*` env vars with sensible defaults |
| `database.py` | 124 | Threaded connection pool (2–10), `query_one`/`query_all`/`execute` helpers, `init_schema()` |
| `honcho.py` | 80 | Thread-safe httpx client singleton, 5 Honcho API wrapper functions |
| `sync.py` | 165 | Bidirectional sync logic, full sync runner, error isolation |
| `routes/memory.py` | 149 | Dual-write to mem0+Honcho, mem0 API auth, webhook + analytics side effects |
| `routes/categories.py` | 155 | Full categories CRUD with UUID validation and memory assignment |
| `routes/webhooks.py` | 194 | Webhook CRUD, HMAC signing, test endpoint, `fire_webhooks()` dispatcher |
| `routes/analytics.py` | 191 | Analytics queries (overview, timeline, sources, categories), `track_event()` helper |
| `routes/export.py` | 137 | Export engine with shared memory fetcher, 3 format renderers |
| `static/index.html` | 258 | Dashboard SPA with 6 tab sections |
| `static/style.css` | ~655 | Dark theme CSS |
| `static/app.js` | ~443 | Tab switching, API calls, rendering |

---

## Troubleshooting

### Service Won't Start

**Problem:** Merrick exits immediately after starting.

**Checks:**
1. Is Supabase PostgreSQL running on port 5433?
   ```bash
   psql -h localhost -p 5433 -U postgres -d postgres -c "SELECT 1"
   ```
2. Is Honcho running on port 8000?
   ```bash
   curl http://localhost:8000/health
   ```
3. Are `.env` values correct?
   ```bash
   cat .env
   ```

### Background Sync Returns 0 Items

**Problem:** Sync completes but `items_synced` is always 0.

**Causes:**
- mem0's `memories` table is empty
- Honcho has no conclusions
- All items are already synced (check `sync_state` table)

**Diagnostic queries:**
```bash
# Count mem0 memories
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT COUNT(*) FROM memories"

# Count synced items by direction
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT source, target, COUNT(*) FROM sync_state GROUP BY source, target"
```

### Honcho Connection Refused

**Problem:** Logs show connection refused errors from `honcho.py`.

**Causes:**
- Honcho not running on port 8000
- Docker networking issue (use `host.docker.internal` when running in Docker)
- Firewall blocking the connection

**Test connectivity from inside Docker:**
```bash
docker exec -it merrick python -c \
  "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8000').read())"
```

### Sync Shows "completed_with_errors"

**Problem:** Sync completes but with `errors > 0`.

**Check the logs:**
```bash
docker compose logs merrick | grep "ERROR"
```

**Common errors:**
- `honcho.create_session` fails → session already exists (harmless, caught and ignored)
- `honcho.post_message` fails → Honcho API issue; check Honcho logs
- Database constraint violations → check `sync_state` uniqueness; may indicate manual DB manipulation

### Dashboard Shows "error" for Counts

**Problem:** Stats show the string `"error"` instead of numbers.

**Cause:** One subsystem (mem0 or Honcho) is unreachable when the dashboard loads.

**Fix:** Ensure both Supabase PostgreSQL (5433) and Honcho (8000) are running. The dashboard auto-recovers on the next auto-refresh (30 seconds for dashboard, 10 seconds for sync log).

### Query Returns Empty Results

**Problem:** `/api/query` returns 0 results.

**Causes:**
- `memories` table is empty
- Honcho peer search returns no results
- Query doesn't match any content

**Test directly:**
```bash
# Direct search
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "user"}'

# Verify data exists
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT id, payload->>'data' FROM memories LIMIT 5"
```

### Webhook Not Firing

**Problem:** Configured webhook doesn't receive events.

**Checks:**
1. Is the webhook `active: true`?
   ```bash
   curl http://localhost:5001/api/webhooks
   ```
2. Test the webhook endpoint:
   ```bash
   curl -X POST http://localhost:5001/api/webhooks/{hook_id}/test
   ```
3. Are you writing memories through `POST /api/memory/write`? (Webhooks only fire on API writes, not on background sync)
4. Check Merrick logs for webhook delivery errors:
   ```bash
   docker compose logs merrick | grep "Webhook"
   ```

---

## Contributing

### Development Setup

```bash
# Clone
git clone https://github.com/lovethatbrandx/merrick.git
cd merrick

# Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your local Supabase/Honcho settings

# Run
python app.py
# Server starts on http://localhost:5001
```

### Code Conventions

- **Python:** PEP 8
- **Logging:** Use `logging.getLogger("merrick")` and sub-loggers (`merrick.sync`, `merrick.honcho`)
- **Error handling:** Fail gracefully — log errors, don't crash the service
- **Database:** Always use parameterized queries (`%s` placeholders), never string interpolation
- **Routes:** Each route file defines an `APIRouter` with appropriate prefix and tags; register in `app.py` via `app.include_router()`

### Adding New Routes

1. Create a new file in `routes/`
2. Define an `APIRouter` with prefix and tags:
   ```python
   from fastapi import APIRouter
   router = APIRouter(prefix="/api/my-feature", tags=["my-feature"])
   ```
3. Import and include in `app.py`:
   ```python
   from routes.my_feature import router as my_feature_router
   app.include_router(my_feature_router)
   ```

### Sync Engine Changes

When modifying `sync.py`:
- Each direction (`sync_mem0_to_honcho`, `sync_honcho_to_mem0`) must be independently fault-tolerant
- Always record synced items in `sync_state` to prevent duplicates
- Use `ON CONFLICT DO NOTHING` for idempotent inserts
- Log meaningful messages at INFO and DEBUG levels

### Testing

```bash
# Health check
curl http://localhost:5001/api/health

# Full status
curl http://localhost:5001/api/status | python -m json.tool

# Trigger sync and check results
curl -X POST http://localhost:5001/api/sync/trigger
sleep 5
curl http://localhost:5001/api/sync/status | python -m json.tool

# Search
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test"}' | python -m json.tool
```

---

> *"Elephants never forget, and neither does Merrick."*

Built with care for the Hermes AI agent. If something breaks, everything is going to be okay. I prepared a 47-page document on that.

---

*Merrick DEV instance documentation — v0.1.0*

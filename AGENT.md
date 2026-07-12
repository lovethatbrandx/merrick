# Merrick — AI Agent Guide

## Project Identity

Merrick is a **bidirectional memory bridge** between [mem0](https://mem0.ai) and [Honcho](https://honcho.dev) for the Hermes AI agent. It synchronizes conversational memories across both systems so they stay in sync regardless of which backend an agent tool writes to.

- **Stack**: Python 3.12, FastAPI, PostgreSQL via psycopg2 (`ThreadedConnectionPool`), httpx
- **Port**: 5001 (Docker-managed)
- **Image**: `ghcr.io/lovethatbrandx/merrick`

## Architecture Rules

### Write path — NEVER bypass the APIs

- **mem0 writes**: Always go through the mem0 API on port 8888 (see `routes/memory.py:_get_mem0_token`). The mem0 dashboard logs requests made via its API — direct SQL writes to the `memories` table bypass dashboard observability.
- **Honcho writes**: Always go through `honcho.py` client functions (Honcho API on port 8000). The client handles workspace scoping and peer routing.
- **Exception**: The sync engine (`sync.py: sync_honcho_to_mem0`) writes directly to the `memories` table for bulk import of historical Honcho conclusions. This is the **only** sanctioned direct write to mem0 storage and is scoped to the sync engine only.

### Database

- Schema is initialized in `database.py:init_schema()`, called once at app startup via the FastAPI lifespan.
- Connection pool: `ThreadedConnectionPool(minconn=2, maxconn=10)`.
- **All SQL queries must be parameterized** using `%s` placeholders — never f-strings or string interpolation. See any route file for examples.
- Three query helpers exist:
  - `db.query_one(sql, params)` — returns a single `RealDictRow` or `None`. **Does not commit.**
  - `db.query_all(sql, params)` — returns a list of `RealDictRow`. **Does not commit.**
  - `db.execute(sql, params)` — **commits the transaction**. Use for INSERT/UPDATE/DELETE.
- Tables managed by Merrick (created in `init_schema`): `sync_state`, `sync_log`, `categories`, `memory_categories`, `webhooks`, `analytics`.
- Merrick reads from mem0's own `memories` table but never creates/alters its schema.

### Sync engine

- Background thread runs `sync.run_full_sync()` every `SYNC_INTERVAL` seconds (default 300 = 5 min). Configurable via `MERRICK_SYNC_INTERVAL`.
- Disabled entirely if `MERRICK_SYNC_ENABLED=false`.
- Bidirectional: `mem0 → honcho` (reads mem0 memories, posts to Honcho as messages) and `honcho → mem0` (reads Honcho conclusions, inserts into mem0 `memories` table).
- Tracks sync state in `sync_state` table to avoid re-syncing already-synced items.
- Logs each run to `sync_log` with direction, counts, errors, and timing.

### Configuration

All settings come from environment variables in `config.py`, prefixed `MERRICK_*`:

| Variable | Default | Notes |
|---|---|---|
| `MERRICK_DB_HOST` | `host.docker.internal` | PostgreSQL host |
| `MERRICK_DB_PORT` | `5433` | PostgreSQL port |
| `MERRICK_DB_USER` | `postgres` | |
| `MERRICK_DB_PASSWORD` | `""` | **Never set a default password in config** |
| `MERRICK_DB_NAME` | `postgres` | |
| `MERRICK_HONCHO_URL` | `http://host.docker.internal:8000` | Honcho API base URL |
| `MERRICK_HONCHO_WORKSPACE` | `hermes` | Honcho workspace name |
| `MERRICK_HONCHO_USER_PEER` | `ron` | Peer ID for user messages |
| `MERRICK_MEM0_API_URL` | `http://host.docker.internal:8888` | mem0 API base URL |
| `MERRICK_MEM0_EMAIL` | `""` | mem0 dashboard login |
| `MERRICK_MEM0_PASSWORD` | `""` | **Never set a default password** |
| `MERRICK_SYNC_INTERVAL` | `300` | Seconds between sync runs |
| `MERRICK_SYNC_ENABLED` | `true` | Enable/disable background sync |

## Development Conventions

### Routes

- All route files live in `routes/*.py`. Each file exports an `APIRouter` named `router` with a prefix and tags.
- Register new routers in `app.py` with `app.include_router(router_name)`.
- Existing prefixes:
  - `/api/sync` — `routes/sync.py`
  - `/api` (query, status) — `routes/query.py`, `routes/status.py`
  - `/api/memory` — `routes/memory.py`
  - `/api/categories` — `routes/categories.py`
  - `/api/webhooks` — `routes/webhooks.py`
  - `/api/analytics` — `routes/analytics.py`
  - `/api/export` — `routes/export.py`

### Logging

- Root logger: `logging.getLogger("merrick")`
- Sub-loggers: `"merrick.sync"`, `"merrick.honcho"`
- Log at startup, on errors, and for significant state changes. Do not log every read.
- Format: `%(asctime)s [%(name)s] %(levelname)s: %(message)s`

### Error handling

- **Fail gracefully**: catch exceptions, log them, return appropriate HTTP status codes.
- HTTP routes should raise `HTTPException` with status codes (400 for bad input, 404 for not found, 409 for duplicate, 500 for server errors).
- Background sync catches all exceptions — it must never crash the thread.
- Re-raise `HTTPException` in `except HTTPException: raise` blocks before generic `except Exception` handlers to avoid swallowing routing errors as 500s.

### Pydantic models

- Define request bodies as Pydantic `BaseModel` subclasses inside the route file.
- Use `Field(...)` with `min_length`/`max_length` for validated fields.
- Use `Optional[type] = default` for optional fields.

### UUID validation

- Route files that accept UUIDs use a `_validate_uuid()` helper that raises `HTTPException(400)` on invalid UUIDs.
- SQL inserts with UUIDs use `%s::uuid` casting.

### Frontend

- Static SPA dashboard in `static/` (vanilla HTML/CSS/JS, dark theme).
- Event delegation: the frontend uses `addEventListener` on container elements — never inline `onclick` attributes (prevents XSS).
- Served via `StaticFiles` mount at `/static` and `FileResponse` at `/`.

## Key Files

| File | Purpose |
|---|---|
| `app.py` | FastAPI entrypoint, lifespan (schema init + sync thread), CORS, router registration, health endpoint |
| `config.py` | Environment variable loading with safe defaults |
| `database.py` | `ThreadedConnectionPool`, `query_one`/`query_all`/`execute` helpers, `init_schema()` |
| `honcho.py` | Honcho HTTP client with thread-safe singleton (`threading.Lock`); `create_session`, `post_message`, `list_conclusions`, `search_peers`, `list_sessions` |
| `sync.py` | Bidirectional sync engine: `sync_mem0_to_honcho()`, `sync_honcho_to_mem0()`, `run_full_sync()` |
| `routes/memory.py` | `POST /api/memory/write` (fans out to both systems), `POST /api/memory/reasoning` (Honcho peer search) |
| `routes/query.py` | `POST /api/query` — cross-system full-text search with deduplication |
| `routes/status.py` | `GET /api/status` — dashboard statistics (counts, samples, sync state) |
| `routes/sync.py` | `POST /api/sync/trigger` (background), `GET /api/sync/status`, `GET /api/sync/log` |
| `routes/categories.py` | Full CRUD for categories + memory assignment/unassignment |
| `routes/webhooks.py` | Webhook CRUD + HMAC-SHA256 signing + fire helper |
| `routes/analytics.py` | Usage tracking, timeline, source breakdown, per-category counts |
| `routes/export.py` | JSON/CSV/Markdown export with category filtering |
| `schema/merrick.sql` | Reference SQL for `sync_state` and `sync_log` tables |
| `static/` | Dark-themed SPA dashboard (3 files: `index.html`, `app.js`, `style.css`) |

## Deployment

```bash
docker compose up -d --build
```

- Container name: `merrick`
- Port mapping: `5001:5001`
- Health check: `GET /api/health` → `{"status": "ok", "service": "merrick"}`
- Uses `host.docker.internal` via `extra_hosts` to reach Honcho (8000), mem0 API (8888), and PostgreSQL (5433) on the host.
- `.env` is gitignored — contains `MERRICK_DB_PASSWORD`, `MERRICK_MEM0_PASSWORD`, and other secrets. Use `.env.example` as a template.

## Hermes Integration

Merrick plugs into the Hermes AI agent as a memory provider:

- **Plugin path**: `~/.hermes/hermes-agent/plugins/memory/merrick/`
- **Config**: `memory.provider: merrick` in Hermes `config.yaml`
- **Agent tools exposed**:
  - `merrick_search` — search memories across both backends
  - `merrick_add` — write a memory (fans out to mem0 + Honcho)
  - `merrick_list` — list recent memories
  - `merrick_reasoning` — deep reasoning via Honcho peer search

## Gotchas

- **`query_one()` / `query_all()` don't commit.** If you use them for an INSERT and then try to read back the row, the result won't appear because the transaction was never committed. Always use `db.execute()` for INSERT/UPDATE/DELETE. The `sync_log` INSERT bug (historical) was caused by using `query_one` where `execute` was needed.
- **`honcho.py:get_client()` uses `threading.Lock`** — it's a thread-safe singleton. Don't create separate httpx clients for Honcho; always call `honcho.get_client()`.
- **mem0 auth token**: `routes/memory.py` caches the token in a module-level `_mem0_token` variable. It regenerates on 401. Don't hardcode tokens.
- **Honcho API response shapes are inconsistent** — some endpoints return bare lists, others return `{"items": [...]}`. The `honcho.py` client normalizes these. Add new normalization patterns there, never in route files.
- **Honcho session create is idempotent with try/except pass** — the Honcho API returns an error if the session already exists, but Merrick silently ignores it. This is intentional and not a bug.
- **Frontend event delegation**: The dashboard JS uses `addEventListener` on container elements. Never add `onclick` attributes to HTML — this is an XSS vector.
- **Config defaults must never contain real passwords** — all secret defaults are empty strings (`""`). Real values come from `.env`.
- **UUID casting in SQL**: When passing UUID strings to PostgreSQL, always use `%s::uuid` in the query, not just `%s`. The `::uuid` cast is required for PostgreSQL to accept a string as a UUID.
- **`routes/webhooks.py:update_webhook` builds SQL dynamically** with parameterized values. This is an acceptable pattern because the column names are hardcoded in the route, not taken from user input. Always follow this model: build the `SET` clause from a fixed set of allowed fields, never from raw user keys.

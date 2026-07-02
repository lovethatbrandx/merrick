# Merrick

**Memory Bridge Service for Hermes AI**

> Named after Joseph Merrick (the Elephant Man), because elephants never forget.

---

## Table of Contents

- [What Merrick Is](#what-merrick-is)
- [Why Merrick Exists](#why-merrick-exists)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration Reference](#configuration-reference)
- [API Documentation](#api-documentation)
- [Web UI Walkthrough](#web-ui-walkthrough)
- [Database Schema](#database-schema)
- [How Hermes Uses Merrick](#how-hermes-uses-merrick)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## What Merrick Is

Merrick is a **bidirectional memory bridge** that keeps two AI memory systems in sync:

| System | What It Does | Strength | Weakness |
|--------|-------------|----------|----------|
| **mem0** | Fast vector-based fact storage (pgvector in Supabase) | Semantic search, ~30 second setup | Shallow reasoning |
| **Honcho** | Deep peer-to-peer reasoning engine | 90%+ on LongMem benchmarks, psychological modeling | Slower, isolated |

**Before Merrick:** These systems were siloed. Hermes used mem0 for memory, Honcho had its own data, and they never talked to each other.

**After Merrick:** Bidirectional sync every 5 minutes. Hermes gets the best of both worlds — fast fact lookup AND deep cognitive reasoning.

```
Hermes Agent
    ↓ searches
mem0 (fast facts, vector search)
    ↑↓ Merrick sync (every 5 min)
Honcho (deep reasoning engine)
```

---

## Why Merrick Exists

The Hermes AI agent needs memory that is both:
1. **Fast** — search 288+ memories in milliseconds
2. **Deep** — understand context, relationships, and psychological patterns

No single system does both well. Merrick bridges them so you don't have to choose.

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Hermes Agent                        │
│  (config: ~/.hermes/config.yaml, provider: mem0)       │
└───────────────────┬─────────────────────────────────────┘
                    │ vector search
                    ▼
┌─────────────────────────────────────────────────────────┐
│                    mem0                                  │
│  PostgreSQL + pgvector (Supabase)                       │
│  Database: postgres | Table: memories                   │
│  Port: 5433                                             │
│  ~288 memories                                          │
└───────────────────▲──────────────────┬──────────────────┘
                    │                  │
                    │                  │ write Honcho conclusions
                    │                  │ with source='honcho'
                    │                  ▼
┌───────────────────┴──────────────────────────────────┐
│                    Merrick                            │
│  FastAPI service (port 5001)                          │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ sync.py     │  │ honcho.py    │  │ database.py │ │
│  │ (engine)    │  │ (HTTP client)│  │ (psycopg2)  │ │
│  └─────────────┘  └──────────────┘  └─────────────┘ │
│                                                       │
│  Tables: sync_state, sync_log                         │
└───────────────────▲──────────────────┬──────────────┘
                    │                  │
                    │ read conclusions │ post facts as
                    │                  │ messages
                    │                  ▼
┌───────────────────┴──────────────────────────────────┐
│                    Honcho                             │
│  Reasoning engine (port 8000)                         │
│  Workspace: hermes                                    │
│  Peer: ron                                            │
│  Session: merrick_mem0_facts                          │
└──────────────────────────────────────────────────────┘
```

### Sync Flow Detail

```
┌──────────────────────────────────────────────────────┐
│                 SYNC (every 5 min)                    │
│                                                       │
│  Direction 1: mem0 → Honcho                          │
│  ─────────────────────────────                       │
│  1. Query all rows from `memories` table             │
│  2. For each unsynced memory:                        │
│     a. Create session `merrick_mem0_facts` (if needed)│
│     b. Post fact as message (peer: "merrick")        │
│     c. Record in sync_state                          │
│                                                       │
│  Direction 2: Honcho → mem0                          │
│  ─────────────────────────────                       │
│  1. List Honcho conclusions (limit: 100)             │
│  2. For each unsynced conclusion:                    │
│     a. Insert into `memories` table                  │
│     b. Set source='honcho', user_id='ron'            │
│     c. Record in sync_state                          │
│                                                       │
│  Fault tolerance: If one direction fails, the other  │
│  still runs. Errors are logged, not fatal.           │
└──────────────────────────────────────────────────────┘
```

### Data Flow Through the Stack

```
Hermes conversation
  │
  ├──▶ mem0 vector search (fast facts)
  │      ├──▶ Original mem0 memories (user-entered)
  │      └──▶ Honcho conclusions (synced by Merrick)
  │
  └──▶ Honcho reasoning (deep analysis)
         └──▶ Conclusions fed back to mem0 via Merrick
```

**Result:** Hermes automatically gets BOTH systems' data because Merrick feeds Honcho conclusions back into mem0. No config changes needed.

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Backend** | Python FastAPI | 0.138.0 |
| **Server** | Uvicorn | 0.49.0 |
| **Database** | PostgreSQL (Supabase) | 15+ |
| **Vector Engine** | pgvector | via Supabase |
| **HTTP Client** | httpx | 0.28.1 |
| **DB Driver** | psycopg2-binary | 2.9.10 |
| **Frontend** | Vanilla HTML/CSS/JS | — |
| **Container** | Docker | — |
| **Base Image** | python:3.12-slim | — |

---

## Quick Start

### Prerequisites

Before running Merrick, you need:

1. **Supabase** running locally
   - PostgreSQL on port `5433`
   - Kong on port `8001`
   - The `postgres` database with pgvector extension

2. **Honcho** running locally
   - API on port `8000`
   - Workspace `hermes` created
   - Peer `ron` created

3. **mem0** configured with pgvector
   - Connected to the same Supabase PostgreSQL instance
   - The `memories` table populated

### Option A: Docker (Recommended)

```bash
# 1. Clone the repo
git clone https://github.com/lovethatbrandx/merrick.git
cd merrick

# 2. Create your .env file
cp .env.example .env
# Edit .env with your actual values

# 3. Build and run
docker compose up -d --build

# 4. Verify it's running
curl http://localhost:5001/api/health
# {"status":"ok","service":"merrick"}
```

### Option B: Local Development

```bash
# 1. Clone the repo
git clone https://github.com/lovethatbrandx/merrick.git
cd merrick

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file
cp .env.example .env
# Edit .env with your actual values

# 5. Run the server
python app.py
# Server starts on http://localhost:5001
```

### First-Time Verification

After starting Merrick, run these checks:

```bash
# Health check
curl http://localhost:5001/api/health
# Expected: {"status":"ok","service":"merrick"}

# System status (should show mem0 memories and Honcho sessions)
curl http://localhost:5001/api/status

# Trigger a manual sync
curl -X POST http://localhost:5001/api/sync/trigger

# Check sync results
curl http://localhost:5001/api/sync/status
```

---

## Configuration Reference

All configuration is via environment variables (loaded from `.env`).

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_DB_HOST` | `host.docker.internal` | PostgreSQL host |
| `MERRICK_DB_PORT` | `5433` | PostgreSQL port |
| `MERRICK_DB_USER` | `postgres` | Database user |
| `MERRICK_DB_PASSWORD` | `supabase_strong_password_2026!` | Database password |
| `MERRICK_DB_NAME` | `postgres` | Database name |

### Honcho

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_HONCHO_URL` | `http://host.docker.internal:8000` | Honcho API base URL |
| `MERRICK_HONCHO_WORKSPACE` | `hermes` | Honcho workspace name |
| `MERRICK_HONCHO_USER_PEER` | `ron` | Peer ID for user data |

### Sync

| Variable | Default | Description |
|----------|---------|-------------|
| `MERRICK_SYNC_INTERVAL` | `300` | Sync interval in seconds (5 minutes) |
| `MERRICK_SYNC_ENABLED` | `true` | Enable/disable background sync |

### Full `.env` Example

```bash
# PostgreSQL (mem0's database)
MERRICK_DB_HOST=host.docker.internal
MERRICK_DB_PORT=5433
MERRICK_DB_USER=postgres
MERRICK_DB_PASSWORD=supabase_strong_password_2026!
MERRICK_DB_NAME=postgres

# Honcho
MERRICK_HONCHO_URL=http://host.docker.internal:8000
MERRICK_HONCHO_WORKSPACE=hermes
MERRICK_HONCHO_USER_PEER=ron

# Sync
MERRICK_SYNC_INTERVAL=300
MERRICK_SYNC_ENABLED=true
```

### Network Access Points

| Access Method | URL |
|---------------|-----|
| Localhost | http://localhost:5001 |
| Tailscale | http://<your-tailscale-ip>:5001 |
| Local Network | http://<your-local-ip>:5001 |

---

## API Documentation

### Base URL

```
http://localhost:5001
```

### Endpoints

#### `GET /api/health`

Service health check. Returns immediately.

**Response:**
```json
{
  "status": "ok",
  "service": "merrick"
}
```

---

#### `GET /api/status`

Dashboard statistics. Queries both mem0 and Honcho for counts and samples.

**Response:**
```json
{
  "mem0_memories": 288,
  "honcho_sessions": 5,
  "honcho_conclusions": 12,
  "last_sync": {
    "id": "...",
    "direction": "mem0_to_honcho",
    "items_synced": 15,
    "errors": 0,
    "started_at": "2026-07-02T10:00:00Z",
    "completed_at": "2026-07-02T10:00:12Z",
    "status": "completed"
  },
  "sync_state_counts": [
    {
      "source": "mem0",
      "target": "honcho",
      "cnt": 280
    },
    {
      "source": "honcho",
      "target": "mem0",
      "cnt": 12
    }
  ]
}
```

**Error handling:** If a subsystem is unreachable, its count returns `"error"` instead of a number.

---

#### `POST /api/sync/trigger`

Manually trigger a full bidirectional sync. Runs in a background task — returns immediately.

**Request:**
```bash
curl -X POST http://localhost:5001/api/sync/trigger
```

**Response:**
```json
{
  "status": "sync_triggered"
}
```

**Behavior:**
- Runs `sync_mem0_to_honcho()` then `sync_honcho_to_mem0()`
- If one direction fails, the other still runs
- Results are logged to the `sync_log` table
- Check `/api/sync/status` for completion

---

#### `GET /api/sync/status`

Current sync state and statistics.

**Response:**
```json
{
  "last_sync": {
    "id": "...",
    "direction": "mem0_to_honcho",
    "items_synced": 15,
    "errors": 0,
    "started_at": "2026-07-02T10:00:00Z",
    "completed_at": "2026-07-02T10:00:12Z",
    "status": "completed"
  },
  "running_count": 0,
  "sync_state_counts": [
    {
      "source": "mem0",
      "target": "honcho",
      "cnt": 280
    }
  ]
}
```

---

#### `GET /api/sync/log`

History of sync operations. Sorted by most recent first.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `50` | Max entries to return |

**Request:**
```bash
curl "http://localhost:5001/api/sync/log?limit=10"
```

**Response:**
```json
{
  "log": [
    {
      "id": "...",
      "direction": "mem0_to_honcho",
      "items_synced": 15,
      "errors": 0,
      "started_at": "2026-07-02T10:00:00Z",
      "completed_at": "2026-07-02T10:00:12Z",
      "status": "completed"
    }
  ]
}
```

---

#### `POST /api/query`

Search across both mem0 and Honcho simultaneously. Deduplicates results by content.

**Request:**
```bash
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "what is the user"}'
```

**Response:**
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
        "id": "...",
        "peer_id": "ron",
        "content": "..."
      }
    }
  ],
  "count": 2
}
```

**Search behavior:**
- mem0: Full-text search using PostgreSQL `tsvector` (`to_tsvector('simple', ...)` + `plainto_tsquery`)
- Honcho: Peer search via Honcho's `/v3/workspaces/{workspace}/peers/{peer_id}/search` endpoint
- Deduplication: Results with identical `data` content are deduplicated

---

## Web UI Walkthrough

Merrick includes a single-page dashboard at `http://localhost:5001`. Dark theme, responsive, no build step required.

### Tab 1: Dashboard

The default view. Shows:

**Stats Grid (top):**
| Stat | Description |
|------|-------------|
| mem0 Memories | Total count from `memories` table |
| Honcho Sessions | Total sessions in Honcho workspace |
| Honcho Conclusions | Total conclusions in Honcho (limit: 100) |
| Last Sync | Timestamp of most recent sync operation |
| Sync Status | `Running`, `Idle`, or `Error` badge |
| Sync Now | Button to trigger manual sync |

**Sample Cards (bottom):**
- **Recent Memories** — Sample entries from mem0's `memories` table
- **Recent Conclusions** — Sample entries from Honcho's conclusions

**Auto-refresh:** Dashboard refreshes every 30 seconds when the tab is active.

### Tab 2: Query

Cross-system search interface.

- **Search bar** — Type any query, press Enter or click "Search Both Systems"
- **Results** — Each result shows:
  - **Source badge** — Blue for mem0, purple for Honcho
  - **Content** — The matching text
  - **Relevance score** (when available from the source system)

**Behavior:**
- Searches mem0 via full-text PostgreSQL search
- Searches Honcho via peer search API
- Results are interleaved and deduplicated
- Clicking "Search Both Systems" shows a spinner while both systems are queried

### Tab 3: Sync Log

Table of all sync operations.

| Column | Description |
|--------|-------------|
| Time | When the sync started (relative: "5m ago") |
| Direction | `mem0_to_honcho` or `honcho_to_mem0` |
| Items Synced | Number of items synced in this operation |
| Errors | Error count (red badge if > 0) |
| Status | `completed`, `completed_with_errors`, or `running` |

**Auto-refresh:** Sync log refreshes every 10 seconds when the tab is active.

### UI Technical Details

- **Theme:** Dark (CSS variables, `#0a0a0f` background)
- **Framework:** Vanilla JS, no dependencies
- **SPA routing:** Tab switching via `data-tab` attributes
- **Toast notifications:** Bottom-right, auto-dismiss after 4 seconds
- **Responsive:** Grid adapts at 768px and 640px breakpoints
- **Favicon:** Elephant emoji (svg/data URI)

---

## Database Schema

Merrick creates two tables on startup via `database.init_schema()`.

### `sync_state`

Tracks which items have been synced between systems. Prevents duplicates.

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

**Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `source` | TEXT | Origin system (`mem0` or `honcho`) |
| `source_id` | TEXT | ID of the item in the source system |
| `target` | TEXT | Destination system (`mem0` or `honcho`) |
| `target_id` | TEXT | ID of the item in the target system (may be null) |
| `synced_at` | TIMESTAMPTZ | When this sync was recorded |

**Unique constraint:** `(source, source_id, target)` — prevents syncing the same item twice.

### `sync_log`

History of sync operations.

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

**Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `direction` | TEXT | `mem0_to_honcho` or `honcho_to_mem0` |
| `items_synced` | INTEGER | Number of items synced |
| `errors` | INTEGER | Number of errors during sync |
| `started_at` | TIMESTAMPTZ | When sync started |
| `completed_at` | TIMESTAMPTZ | When sync completed (null if still running) |
| `status` | TEXT | `running`, `completed`, or `completed_with_errors` |

### Supabase Tables Used

| Table | Owner | Used By |
|-------|-------|---------|
| `postgres.memories` | mem0 | Read (mem0→Honcho), Write (Honcho→mem0) |
| `postgres.sync_state` | Merrick | Read/Write (deduplication tracking) |
| `postgres.sync_log` | Merrick | Read/Write (sync history) |

---

## How Hermes Uses Merrick

### The Integration Path

```
Hermes config (~/.hermes/config.yaml)
  │
  ├── memory_provider: mem0
  │
  └── mem0 connects to Supabase PostgreSQL
        │
        └── memories table (288 entries)
              │
              ├── 285 original mem0 facts
              └── 3 synced from Honcho (via Merrick, source='honcho')
```

### Why "It Just Works"

1. Hermes searches mem0 via vector search before each conversation turn
2. Merrick feeds Honcho conclusions back into mem0 with `source: 'honcho'`
3. mem0's `memories` table now contains BOTH original facts AND Honcho insights
4. Hermes doesn't know or care where the data came from — it just gets richer memories

### No Config Changes Required

Hermes's `~/.hermes/config.yaml` doesn't need any Merrick-specific configuration. The bridge is transparent because:
- Merrick writes directly to mem0's database table
- Hermes reads from the same table
- The `source` field in the payload distinguishes origin (informational only)

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5001
CMD ["python", "app.py"]
```

### docker-compose.yml

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
    extra_hosts:
      - "host.docker.internal:host-gateway"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5001/api/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
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
```

### Health Check

The container includes a health check that hits `/api/health` every 10 seconds:
- **Interval:** 10 seconds
- **Timeout:** 5 seconds
- **Retries:** 3 (marks unhealthy after 30 seconds of failures)

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

3. Are your `.env` values correct?
   ```bash
   cat .env
   ```

### Sync Returns 0 Items

**Problem:** Sync completes but `items_synced` is always 0.

**Causes:**
- mem0's `memories` table is empty
- Honcho has no conclusions
- All items are already synced (check `sync_state` table)

**Check:**
```bash
# Count mem0 memories
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT COUNT(*) FROM memories"

# Count synced items
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT source, target, COUNT(*) FROM sync_state GROUP BY source, target"
```

### Honcho Connection Refused

**Problem:** `honcho.py` errors with connection refused.

**Causes:**
- Honcho not running on port 8000
- Docker networking issue (use `host.docker.internal` in Docker)
- Firewall blocking the connection

**Fix:**
```bash
# From inside Docker container, test Honcho connectivity
docker exec -it merrick python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8000').read())"
```

### Sync Shows "completed_with_errors"

**Problem:** Sync completes but with error count > 0.

**Check the logs:**
```bash
docker compose logs merrick | grep "ERROR"
```

**Common errors:**
- `honcho.create_session` fails → session already exists (harmless, ignored)
- `honcho.post_message` fails → Honcho API issue
- Database constraint violations → check `sync_state` uniqueness

### Dashboard Shows "error" for Counts

**Problem:** Stats show `"error"` instead of numbers.

**Cause:** One subsystem is unreachable when the dashboard loads.

**Fix:** Ensure both Supabase (5433) and Honcho (8000) are running. The dashboard will recover on the next auto-refresh (30 seconds).

### Query Returns Empty Results

**Problem:** Search finds nothing.

**Causes:**
- `memories` table is empty
- Honcho peer search returns no results
- Query doesn't match any full-text vectors

**Test:**
```bash
# Direct mem0 search
curl -X POST http://localhost:5001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "user"}'

# If still empty, check data exists
psql -h localhost -p 5433 -U postgres -d postgres \
  -c "SELECT id, payload->>'data' FROM memories LIMIT 5"
```

---

## Project Structure

```
merrick/
├── app.py                  # FastAPI entrypoint, lifespan, CORS, routing
├── config.py               # Environment variable loading
├── database.py             # PostgreSQL connection helpers, schema init
├── honcho.py               # Honcho HTTP client (sessions, messages, conclusions, search)
├── sync.py                 # Sync engine (mem0→Honcho, Honcho→mem0, full sync)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build definition
├── docker-compose.yml      # Container orchestration
├── .env                    # Configuration (not committed)
├── .env.example            # Configuration template
├── .gitignore              # Git ignore rules
│
├── routes/
│   ├── __init__.py         # (empty, makes routes a package)
│   ├── sync.py             # POST /api/sync/trigger, GET /api/sync/status, GET /api/sync/log
│   ├── query.py            # POST /api/query
│   └── status.py           # GET /api/status
│
├── schema/
│   └── merrick.sql         # Database schema (sync_state, sync_log)
│
└── static/
    ├── index.html          # SPA shell (dashboard, query, sync log tabs)
    ├── style.css           # Dark theme CSS (655 lines)
    └── app.js              # Frontend logic (443 lines)
```

### File Responsibilities

| File | Lines | Purpose |
|------|-------|---------|
| `app.py` | 73 | FastAPI app, background sync thread, lifespan management |
| `config.py` | 17 | Loads all `MERRICK_*` environment variables with defaults |
| `database.py` | 75 | `query_one`, `query_all`, `execute`, `init_schema` |
| `honcho.py` | 77 | httpx client for Honcho v3 API |
| `sync.py` | 163 | Core sync logic, fault-tolerant bidirectional sync |
| `routes/sync.py` | 39 | Sync API endpoints |
| `routes/query.py` | 54 | Cross-system search with deduplication |
| `routes/status.py` | 50 | Dashboard statistics aggregation |
| `static/index.html` | 146 | SPA HTML shell |
| `static/style.css` | 655 | Dark theme, responsive design |
| `static/app.js` | 443 | Tab switching, API calls, rendering |

### Honcho API Endpoints Used

| Endpoint | Method | Used In | Purpose |
|----------|--------|---------|---------|
| `/v3/workspaces/{ws}/sessions` | POST | `honcho.py` | Create session for mem0 imports |
| `/v3/workspaces/{ws}/sessions/{id}/messages` | POST | `honcho.py` | Post mem0 facts as messages |
| `/v3/workspaces/{ws}/conclusions/list` | POST | `honcho.py` | List Honcho conclusions |
| `/v3/workspaces/{ws}/peers/{id}/search` | POST | `honcho.py` | Search peer data |
| `/v3/workspaces/{ws}/sessions/list` | POST | `honcho.py` | List all sessions (for status) |

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
```

### Code Style

- **Python:** Standard PEP 8 conventions
- **Logging:** Use `logging.getLogger("merrick")` and sub-loggers (`merrick.sync`, `merrick.honcho`)
- **Error handling:** Fail gracefully, log errors, don't crash the service
- **Database:** Always use parameterized queries (never string interpolation)

### Adding New Routes

1. Create a new file in `routes/`
2. Define an `APIRouter` with appropriate prefix and tags
3. Import and include it in `app.py` via `app.include_router(new_router)`

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

## License

Internal project — BrandX / Pied Piper.

---

> *"Elephants never forget, and neither does Merrick."*

Built with care for the Hermes AI agent. If something breaks, everything is going to be okay. I prepared a 47-page document on that.

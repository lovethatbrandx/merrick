<div align="center">
  <img src="static/merrick_logo.png" alt="Merrick" width="400">

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)](https://developer.mozilla.org/en-US/docs/Web/CSS)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![MCP](https://img.shields.io/badge/MCP-FF6B35?style=for-the-badge&logo=datauri&logoColor=white)](https://modelcontextprotocol.io/)
[![OpenCode](https://img.shields.io/badge/~%24_OpenCode-000000?style=for-the-badge&logo=terminal&logoColor=green)](https://opencode.ai)
[![MiMo](https://img.shields.io/badge/MiMo-FF6B35?style=for-the-badge&logo=huggingface&logoColor=white)](https://huggingface.co/XiaomiMiMo/MiMo-V2.5)

</div>

<p align="center">
  <img src="static/app_screenshot.png" alt="Merrick Dashboard" width="800">
</p>

## Why This Exists

No single AI memory system does everything well. [mem0](https://mem0.ai) is fast and great for vector-based fact lookup, but it's shallow. [Honcho](https://honcho.dev) is a deep peer-to-peer reasoning engine that crushes long-context benchmarks, but it's slower and isolated. Before Merrick, if you wanted both speed and depth, you had to pick one and live with the tradeoffs.

Merrick is a bidirectional memory bridge that keeps both systems in sync. Your agent gets fast fact lookup from mem0 AND deep cognitive reasoning from Honcho — automatically, every 5 minutes. No config changes required. No choosing sides.

Built entirely with AI coding tools ([OpenCode](https://opencode.ai) + [MiMo](https://huggingface.co/XiaomiMiMo/MiMo-V2.5)). No shame about it.

## Recent Updates

This project is actively maintained. Here's what's landed recently.

### 2026.8.25 — v2.0: The Universal Memory Daemon

Merrick is no longer just a sync bridge. It's a full memory daemon with device provisioning, API key authentication, an MCP server, a CLI, and a dreaming loop that keeps memories clean.

- **Agent Profiles** — define specialized memory contexts per agent with custom system prompts and token budgets. Routes: `routes/agents.py`
- **API Key Authentication** — SHA-256 hashed keys with per-device scoping, rate limiting, and expiration. Keys look like `merrick_sk_...` and are shown once at creation time.
- **MCP Server** — full [Model Context Protocol](https://modelcontextprotocol.io/) integration. Tools: `write_memory`, `search_memories`, `list_memories`, `get_memory`, `delete_memory`, `get_status`. Resources: `merrick://status`, `merrick://memories`. Works with LM Studio, Claude Desktop, VS Code, and any MCP-compatible client.
- **CLI (`merrick_cli`)** — manage everything from the terminal: `merrick status`, `merrick devices`, `merrick keys create`, `merrick memory write/search/export`, `merrick sync`, `merrick doctor`. Rich output with tables and panels.
- **Dreaming Loop** — background compaction cycle that deduplicates memories, detects contradictions (same topic, different values), and marks stale memories as compacted. No data deleted — just flagged for recovery.
- **Device Provisioning** — auto-creates Honcho peers and mem0 users on first device connect. Thread-safe caching, graceful fallback to the global user peer for unknown devices.
- **Standalone Docker** — `docker-compose.yml` runs PostgreSQL + Merrick only. For users who already run Honcho/mem0 elsewhere. `docker-compose-full.yml` brings up everything (PostgreSQL, Redis, Honcho, mem0, Merrick) in one shot.
- **External API (`/v1/*`)** — device-scoped memory read/write/search via Bearer token auth. OpenAI-compatible `/v1/chat/completions` endpoint with memory-augmented generation.
- **Middleware Stack** — API key validation, per-key rate limiting (token bucket), request logging. All in `middleware/auth.py`.

### What's Next

- **Setup Wizard** — one-click detection and configuration of Honcho, mem0, and PostgreSQL from the dashboard.
- **PyPI Package** — `pip install merrick` for the CLI.
- **System Service** — `merrick install` for systemd/launchd integration.

## Features

- **Bidirectional Sync** — mem0 ↔ Honcho every 5 minutes (configurable). Fault-tolerant: if one direction fails, the other still runs.
- **Agent Profiles** — define per-agent memory contexts with custom system prompts and token budgets. Agents get their own scoped memories.
- **API Key Auth** — SHA-256 hashed keys (`merrick_sk_...` prefix), per-device scoping, rate limiting (RPM + RPD), optional expiration. Raw key shown once at creation.
- **MCP Server** — stdio transport. Exposes `write_memory`, `search_memories`, `list_memories`, `get_memory`, `delete_memory`, `get_status` as tools. `merrick://status` and `merrick://memories` as resources.
- **CLI** — `merrick status|devices|keys|memory|sync|doctor`. Rich output, error handling, connection diagnostics.
- **Dreaming Loop** — deduplication via Jaccard similarity + word overlap. Contradiction detection (same topic opener, different content). Stale memory compaction. Covers both `memories` and `agent_memories` tables.
- **Device Provisioning** — auto-creates Honcho peers (`device_{id}`) and mem0 users on first connect. Thread-safe in-memory cache with DB persistence.
- **External API** — `/v1/memory/write`, `/v1/query`, `/v1/agents`, `/v1/agents/{slug}/memory`, `/v1/agents/{slug}/memory/search`. All require Bearer token auth.
- **Cross-System Search** — `POST /api/query` searches both mem0 (full-text) and Honcho (peer search) simultaneously, deduplicates by content.
- **Dashboard** — dark-themed SPA with tabs for Overview, Query, Sync Log, Devices, Settings. Auto-refreshes every 30 seconds.
- **Categories** — organize memories into named categories with color coding. Assign/unassign memories via API.
- **Webhooks** — fire on `memory.created`, `sync.completed`, `device.registered`, `key.rotated`. HMAC-SHA256 signed payloads.
- **Analytics** — memory creation timeline, source breakdown, per-category counts, per-device breakdown.
- **Export** — JSON, CSV, Markdown. Full backup includes settings, devices, keys, memories, sync log, and analytics summary.
- **Rate Limiting** — in-memory token bucket per API key. Configurable RPM and RPD limits.
- **Settings Cascade** — database overrides > config file (`~/.merrick/config.json`) > env vars > hardcoded defaults.

### Additional Features

- **Soft Compaction** — dreaming marks memories as compacted rather than deleting them. Everything is recoverable.
- **Mem0 API-First** — all mem0 writes go through the mem0 API (port 8888), never direct SQL (except bulk sync import).
- **Thread-Safe Singleton** — Honcho client uses `threading.Lock`. No separate httpx clients — always `honcho.get_client()`.
- **Fire-and-Forget Analytics** — audit and analytics writes don't block user-facing responses.
- **Browser Caching Fix** — all GET requests use `cache: 'no-store'` to prevent stale data.
- **Event Loop Protection** — all synchronous I/O wrapped in `asyncio.to_thread()` to prevent event loop blocking.
- **Security Headers** — CSP, HSTS, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection.
- **UUID Validation** — all route UUID params validated with `_validate_uuid()` helper. SQL uses `%s::uuid` casting.
- **Frontend Event Delegation** — `addEventListener` on container elements only. No `onclick` attributes (XSS prevention).

## Prerequisites

You need these running before Merrick can start:

1. **PostgreSQL with pgvector** — on port `5433` (or configure `MERRICK_DB_HOST`/`MERRICK_DB_PORT`)
   - The `postgres` database with pgvector extension installed
2. **Honcho** — API on port `8000` (or configure `MERRICK_HONCHO_URL`)
   - Workspace `hermes` created, peer `ron` created
3. **mem0** — connected to the same PostgreSQL instance
   - The `memories` table populated with at least a few entries

If you're starting fresh, use `docker-compose-full.yml` which brings up everything.

## Quick Start

There are two ways to run Merrick: **from source** (good for development) and **Docker** (preferred for production). Both work perfectly fine — pick whichever fits your workflow.

### Option 1: Run from Source (Development)

Best for: active development, testing changes quickly, or running alongside Honcho on the same machine without Docker overhead.

Requires Python 3.10+.

```bash
git clone https://github.com/lovethatbrandx/merrick.git
cd merrick
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                           # Installs the `merrick` CLI command
```

Set the required environment variables:

```bash
export MERRICK_DB_HOST=localhost
export MERRICK_DB_PORT=5433
export MERRICK_DB_USER=postgres
export MERRICK_DB_PASSWORD=your_password
export MERRICK_DB_NAME=postgres
export MERRICK_HONCHO_URL=http://localhost:8000
export MERRICK_MEM0_API_URL=http://localhost:8888
```

Then run with live reload (auto-restarts on code changes):

```bash
python3 -m uvicorn app:app --host 0.0.0.0 --port 5001 --reload
```

Or without auto-reload:

```bash
python app.py
```

Dashboard runs at `http://localhost:5001`.

### Option 2: Docker (Production Preferred)

Best for: production deployments, consistent environments, zero dependency conflicts, and easy updates.

#### Standalone (default)

Runs PostgreSQL + Merrick only. Honcho and mem0 run elsewhere and are connected via `host.docker.internal`.

```bash
git clone https://github.com/lovethatbrandx/merrick.git
cd merrick
cp .env.example .env
# Edit .env with your actual values
docker compose up -d --build
```

#### Full Stack

Runs everything: PostgreSQL, Redis, Honcho, mem0, and Merrick.

```bash
docker compose -f docker-compose-full.yml up -d --build
```

#### Which Compose File?

| Scenario | File | Recommendation |
|----------|------|----------------|
| You already run Honcho + mem0 | `docker-compose.yml` | **Standalone** — connects to your existing services |
| Starting from scratch | `docker-compose-full.yml` | **Full stack** — everything in one shot |
| CI/CD or automated deployments | `docker-compose.yml` | **Standalone** — fewer dependencies, faster startup |
| Quick test of the full system | `docker-compose-full.yml` | **Full stack** — zero external setup needed |

#### Docker Commands

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

#### Update

```bash
cd your/deploy/folder/
docker compose pull
docker compose up -d
```

### Which Should I Pick?

| Scenario | Recommendation |
|----------|----------------|
| Developing Merrick itself | **Run from source** — use `--reload` for instant feedback |
| Running Merrick + Honcho on one machine | **Run from source** — less overhead, both share the same host |
| Production / daily driver | **Docker** — set it and forget it, auto-restarts if it crashes |
| Quick test without installing Python deps | **Docker** — no venv, no pip, just `docker compose up -d` |
| Full stack from scratch | **Docker full** — `docker-compose-full.yml` brings up everything |
| CI/CD or automated deployments | **Docker** — reproducible, no manual setup steps |

## Connecting Hermes Agent

Hermes Agent has built-in memory providers (Honcho, mem0). Merrick sits in front of both — you get Honcho's deep reasoning AND mem0's vector search without choosing one.

### First-Time Setup (Hermes not configured yet)

1. **Install and start Merrick** (see Quick Start above)
2. **Start Hermes setup** — when it asks "Configure a memory layer?" skip it
3. **Set env vars** for Hermes to talk to Merrick:

```bash
export MERRICK_URL=http://localhost:5001
export MERRICK_API_KEY=merrick_sk_your_key_here
```

4. **Create an API key** if you haven't:

```bash
curl -X POST http://localhost:5001/api/keys \
  -H "Content-Type: application/json" \
  -d '{"device_id": "hermes-main", "key_name": "hermes"}'
```

5. **Verify it works:**

```bash
curl -X POST http://localhost:5001/v1/memory/write \
  -H "Authorization: Bearer merrick_sk_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hermes connected to Merrick", "source": "hermes"}'
```

### Migrating from Existing Memory (Honcho or mem0 already configured)

Merrick **replaces** the single backend in your Hermes config. It does **not** delete your existing memories — they stay in the original backend. Merrick reads from both automatically.

1. **Merrick is already running** (you're here, so it is)
2. **Update Hermes config** — point it at Merrick instead of Honcho/mem0 directly:

```bash
# Old (direct to Honcho)
export HONCHO_BASE_URL=http://localhost:8000

# New (through Merrick)
export MERRICK_URL=http://localhost:5001
export MERRICK_API_KEY=merrick_sk_your_key_here
```

3. **Restart Hermes**
4. **Test** — ask Hermes to remember something, then search for it

### What Happens to Existing Memories?

They're safe. Merrick doesn't touch your old data. Once connected:
- **Reads** pull from both Honcho and mem0 (deduplicated)
- **Writes** go to both simultaneously
- **Sync** keeps them consistent every 5 minutes

### Does This Replace My Setup?

Yes and no. It **replaces the config** (where Hermes points). It **does not replace your memories**. They're still in Honcho/mem0 — Merrick just gives you a unified front door to both.

## Architecture

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

- **Sync Engine**: Background daemon thread runs `run_full_sync()` every N seconds. Bidirectional: mem0 → Honcho (posts facts as messages) and Honcho → mem0 (inserts conclusions into `memories` table). Tracks state in `sync_state` to prevent duplicates.
- **Dreaming Loop**: Separate background cycle that deduplicates memories (Jaccard similarity + word overlap), detects contradictions (same topic, different values), and marks stale memories as compacted.
- **Middleware**: API key validation via SHA-256 hash lookup, per-key rate limiting (token bucket), request logging.
- **Device Provisioning**: Auto-creates Honcho peers (`device_{id}`) and mem0 users on first connect. Thread-safe cache with DB persistence.
- **Dashboard SPA**: Vanilla HTML/CSS/JS, dark theme. Tabs: Overview, Query, Sync Log, Devices, Settings.

## Configuration

All configuration is via environment variables (loaded from `.env`).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MERRICK_DB_HOST` | Yes | `localhost` | PostgreSQL host |
| `MERRICK_DB_PORT` | Yes | `5433` | PostgreSQL port |
| `MERRICK_DB_USER` | Yes | `postgres` | Database user |
| `MERRICK_DB_PASSWORD` | Yes | *(empty)* | Database password |
| `MERRICK_DB_NAME` | Yes | `postgres` | Database name |
| `MERRICK_HONCHO_URL` | Yes | `http://localhost:8000` | Honcho API base URL |
| `MERRICK_HONCHO_WORKSPACE` | No | `hermes` | Honcho workspace name |
| `MERRICK_HONCHO_USER_PEER` | No | `ron` | Default Honcho peer ID |
| `MERRICK_MEM0_API_URL` | Yes | `http://localhost:8888` | mem0 API base URL |
| `MERRICK_MEM0_EMAIL` | No | *(empty)* | mem0 dashboard login |
| `MERRICK_MEM0_PASSWORD` | No | *(empty)* | mem0 dashboard password |
| `MERRICK_SYNC_INTERVAL` | No | `300` | Seconds between sync runs (5 min) |
| `MERRICK_SYNC_ENABLED` | No | `true` | Enable/disable background sync |
| `MERRICK_SERVER_HOST` | No | `0.0.0.0` | Bind address |
| `MERRICK_SERVER_PORT` | No | `5001` | Listen port |
| `MERRICK_LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `MERRICK_RATE_LIMIT_RPM` | No | `60` | Default requests per minute |
| `MERRICK_RATE_LIMIT_RPD` | No | `10000` | Default requests per day |
| `MERRICK_LLM_PROVIDER` | No | `openai` | LLM provider (`openai`, `anthropic`, `ollama`, `custom`) |
| `MERRICK_LLM_API_KEY` | No | *(empty)* | LLM API key |
| `MERRICK_LLM_MODEL` | No | `gpt-4` | Default model name |

> **Note:** Config cascades: database overrides > config file (`~/.merrick/config.json`) > env vars > hardcoded defaults. Real passwords must never be hardcoded.

## API Endpoints

### Internal Namespace: `/api/*`

All `/api/*` routes are **unauthenticated** (dashboard and local CLI use only).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/status` | Dashboard aggregate stats (mem0 count, honcho sessions, sync state) |
| `POST` | `/api/query` | Cross-system search with deduplication |
| `POST` | `/api/memory/write` | Write to both mem0 + Honcho (no device association) |
| `POST` | `/api/memory/reasoning` | Honcho peer search for deep reasoning |
| `POST` | `/api/sync/trigger` | Trigger a full sync run (background) |
| `GET` | `/api/sync/status` | Current sync status + state counts |
| `GET` | `/api/sync/log` | Sync history (paginated: `?limit=50&offset=0`) |
| `GET` | `/api/categories` | List all categories with memory counts |
| `POST` | `/api/categories` | Create a category |
| `DELETE` | `/api/categories/{id}` | Delete a category |
| `POST` | `/api/categories/{id}/assign` | Assign a memory to a category |
| `DELETE` | `/api/categories/{id}/unassign/{memory_id}` | Remove memory from category |
| `GET` | `/api/webhooks` | List all webhooks |
| `POST` | `/api/webhooks` | Create a webhook |
| `PUT` | `/api/webhooks/{id}` | Update a webhook |
| `DELETE` | `/api/webhooks/{id}` | Delete a webhook |
| `POST` | `/api/webhooks/{id}/test` | Test-fire a webhook |
| `GET` | `/api/analytics/overview` | Aggregate stats |
| `GET` | `/api/analytics/timeline` | Memory creation over time |
| `GET` | `/api/analytics/sources` | Breakdown by source |
| `GET` | `/api/analytics/categories` | Breakdown by category |
| `GET` | `/api/analytics/devices` | Per-device breakdown |
| `POST` | `/api/analytics/track` | Track a custom event |
| `GET` | `/api/export/json` | Export memories as JSON |
| `GET` | `/api/export/csv` | Export as CSV |
| `GET` | `/api/export/markdown` | Export as Markdown |
| `GET` | `/api/export/full` | Full backup (settings + devices + keys + memories) |
| `GET` | `/api/devices` | List all provisioned devices |
| `POST` | `/api/devices` | Register a new device |
| `GET` | `/api/devices/{id}` | Get device details + key list |
| `PUT` | `/api/devices/{id}` | Update device metadata |
| `DELETE` | `/api/devices/{id}` | Deactivate a device |
| `POST` | `/api/devices/{id}/keys` | Create an API key for a device |
| `GET` | `/api/devices/{id}/keys` | List keys for a device |
| `DELETE` | `/api/keys/{key_id}` | Revoke an API key |
| `POST` | `/api/keys/{key_id}/rotate` | Rotate an API key |
| `GET` | `/api/agents` | List agent profiles |
| `POST` | `/api/agents` | Create an agent profile |
| `PUT` | `/api/agents/{slug}` | Update an agent profile |
| `DELETE` | `/api/agents/{slug}` | Delete an agent profile |
| `POST` | `/api/agents/{slug}/memories` | Write a memory via agent context |
| `POST` | `/api/agents/{slug}/query` | Search memories via agent context |
| `POST` | `/api/dreaming/run` | Manually trigger a dreaming cycle |
| `GET` | `/api/dreaming/stats` | Get compaction statistics |

### External Namespace: `/v1/*`

All `/v1/*` routes require a valid API key via `Authorization: Bearer <key>`.

| Method | Path | Description | Scopes Required |
|--------|------|-------------|-----------------|
| `POST` | `/v1/memory/write` | Write a memory (scoped to device) | `memory.write` |
| `POST` | `/v1/query` | Cross-system search (mem0 + Honcho, deduplicated) | `memory.read` |
| `GET` | `/v1/agents` | List available agent profiles | `read` |
| `GET` | `/v1/agents/{slug}` | Get agent profile (system prompt + traits) | `read` |
| `POST` | `/v1/agents/{slug}/memory` | Write agent-specific memory | `write` |
| `POST` | `/v1/agents/{slug}/memory/search` | Search agent's memories | `read` |

## MCP Server

Merrick ships with a full [Model Context Protocol](https://modelcontextprotocol.io/) server. Any MCP-compatible client (LM Studio, Claude Desktop, VS Code, etc.) can use Merrick's memory system directly.

### Tools

| Tool | Description |
|------|-------------|
| `write_memory` | Write a memory to Merrick. Stores in both mem0 and Honcho. |
| `search_memories` | Search memories by query across mem0 and Honcho. |
| `list_memories` | List recent memories, optionally filtered by category. |
| `get_memory` | Get a specific memory by ID. |
| `delete_memory` | Delete a memory (currently returns guidance — no HTTP delete endpoint yet). |
| `get_status` | Get Merrick health status, counts, and sync info. |

### Resources

| Resource | Description |
|----------|-------------|
| `merrick://status` | Merrick health status as a readable JSON resource. |
| `merrick://memories` | The 20 most recent memories as a readable JSON resource. |

### Running the MCP Server

```bash
# stdio transport (default)
python -m mcp_server

# via MCP CLI
mcp run mcp_server/server.py
```

### MCP Client Configuration

Add to your MCP client config (e.g., `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "merrick": {
      "command": "python",
      "args": ["-m", "mcp_server"]
    }
  }
}
```

## CLI

Merrick includes a command-line interface via `merrick_cli`. Rich output with tables, panels, and color-coded status.

### Commands

```bash
merrick status                          # Health check + counts
merrick devices                         # List all provisioned devices
merrick keys list                       # List all API keys
merrick keys create                     # Create a new API key (interactive)
merrick memory write "User likes Vim"   # Write a memory
merrick memory search "dark mode"       # Search memories
merrick memory export -o backup.json    # Export memories as JSON
merrick sync                            # Trigger manual sync + show status
merrick doctor                          # Diagnose connectivity issues
```

### Configuration

```bash
# Set server URL (default: http://localhost:5001)
export MERRICK_URL=http://your-server:5001

# Or pass via flag
merrick --url http://your-server:5001 status
```

## Security

- **API Key Auth** — Bearer token via `Authorization` header. Keys are SHA-256 hashed before storage. Raw key shown once at creation time. Format: `merrick_sk_` + 40 alphanumeric characters.
- **Rate Limiting** — in-memory token bucket per API key. Configurable RPM (default: 60) and RPD (default: 10,000). Returns 429 with Retry-After header.
- **Device Scoping** — each key is bound to a device. Writes are tracked per-device. Device-scoped search returns only that device's memories (opt-in via `device_filter: true`).
- **Key Rotation** — revoke old key and create new atomically. `POST /api/keys/{key_id}/rotate`.
- **Internal vs External** — `/api/*` routes are unauthenticated (dashboard/local). `/v1/*` routes require Bearer token auth. Network binding defaults to `0.0.0.0` for Docker, `127.0.0.1` for local dev.
- **Security Headers** — CSP, HSTS, X-Content-Type-Options, X-Frame-Options, X-XSS-Protection.
- **Path Traversal Protection** — proxy validates and URL-decodes paths before forwarding.
- **Config Defaults** — passwords are always empty strings in defaults. Real values come from `.env` or database overrides.

## Project Structure

```
merrick/
├── app.py                      # FastAPI entrypoint (lifespan, CORS, router mount, health)
├── config.py                   # Environment variable loading with safe defaults
├── database.py                 # ThreadedConnectionPool, query helpers, init_schema()
├── honcho.py                   # Honcho HTTP client (thread-safe singleton)
├── sync.py                     # Bidirectional sync engine (mem0↔Honcho)
├── dreaming.py                 # Memory compaction loop (dedup, contradictions, stale)
├── provisioning.py             # Device auto-provisioning (Honcho peers + mem0 users)
├── middleware/
│   ├── __init__.py
│   └── auth.py                 # API key validation, rate limiting, request logging
├── mcp_server/
│   ├── __init__.py
│   ├── __main__.py             # python -m mcp_server entrypoint
│   ├── server.py               # MCP tools + resources
│   ├── client.py               # HTTP client for Merrick API
│   └── config.py               # MCP server configuration
├── merrick_cli/
│   ├── __init__.py
│   ├── main.py                 # Click CLI (status, devices, keys, memory, sync, doctor)
│   ├── client.py               # HTTP client for CLI
│   └── config.py               # CLI configuration
├── routes/
│   ├── __init__.py
│   ├── sync.py                 # POST /api/sync/trigger, GET /api/sync/status, GET /api/sync/log
│   ├── query.py                # POST /api/query (cross-system search)
│   ├── status.py               # GET /api/status (dashboard stats)
│   ├── memory.py               # POST /api/memory/write, POST /api/memory/reasoning
│   ├── categories.py           # Category CRUD + memory assignment
│   ├── webhooks.py             # Webhook CRUD + HMAC signing
│   ├── analytics.py            # Usage tracking, timelines, breakdowns
│   ├── export.py               # JSON/CSV/Markdown export + full backup
│   ├── devices.py              # Device CRUD, peer mapping
│   ├── keys.py                 # API key management (create, rotate, revoke)
│   ├── agents.py               # Agent profile CRUD + scoped memory ops
│   └── dreaming.py             # POST /api/dreaming/run, GET /api/dreaming/stats
├── schema/
│   └── merrick.sql             # Reference DDL (sync_state, sync_log, all tables)
├── static/
│   ├── index.html              # SPA shell (dark theme)
│   ├── style.css               # Dark theme CSS
│   └── app.js                  # Frontend logic (tabs, API calls, rendering)
├── docker-compose.yml          # Standalone: PostgreSQL + Merrick
├── docker-compose-full.yml     # Full stack: PostgreSQL + Redis + Honcho + mem0 + Merrick
├── Dockerfile                  # Container build (python:3.12-slim)
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Package metadata + CLI entrypoint
├── init-db.sh                  # PostgreSQL init script (pgvector extension)
├── .env                        # Configuration (not committed)
├── .env.example                # Configuration template
├── .gitignore                  # Git ignore rules
├── ARCHITECTURE.md             # Full v2 architecture documentation
├── AGENT.md                    # AI agent guide (gotchas, conventions)
├── DOCS.md                     # Developer documentation
└── LICENSE                     # AGPL-3.0 License
```

## License

[AGPL-3.0](LICENSE) © 2026 Brand X

---

> *"Elephants never forget, and neither does Merrick."*

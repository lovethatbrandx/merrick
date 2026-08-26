import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from psycopg2.extras import Json

import database as db
from config import logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_slug(value: str, name: str = "slug") -> str:
    """Validate that a slug looks sane (alphanumeric + hyphens)."""
    import re
    if not re.match(r"^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$", value):
        raise HTTPException(status_code=400, detail=f"Invalid {name}: must be lowercase alphanumeric with hyphens")
    return value


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token. Fast enough for a daemon."""
    return len(text) // 4


def _build_agent_response(profile: dict, memories: list, max_tokens: int) -> dict:
    """Build the agent response with token-budget-aware memory truncation."""
    profile_data = dict(profile)
    # Convert datetime objects
    for k, v in profile_data.items():
        if isinstance(v, datetime):
            profile_data[k] = v.isoformat()

    # Truncate memories to fit within token budget
    included_memories = []
    tokens_used = 0
    for mem in memories:
        mem_dict = dict(mem) if not isinstance(mem, dict) else mem
        for k, v in mem_dict.items():
            if isinstance(v, datetime):
                mem_dict[k] = v.isoformat()
        content = mem_dict.get("content", "")
        mem_tokens = _estimate_tokens(content)
        if tokens_used + mem_tokens > max_tokens:
            break
        included_memories.append(mem_dict)
        tokens_used += mem_tokens

    return {
        "profile": profile_data,
        "memories": included_memories,
        "memory_count": len(included_memories),
        "tokens_used": tokens_used,
        "max_tokens": max_tokens,
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AgentProfileCreate(BaseModel):
    name: str = Field(..., min_length=1)
    slug: str = Field(..., min_length=1, max_length=64)
    system_prompt: str = Field(..., min_length=1)
    personality: Optional[dict] = Field(default_factory=dict)
    custom_instructions: Optional[str] = None
    memory_scope: str = Field(default="shared", pattern="^(shared|agent_only)$")


class AgentProfileUpdate(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    personality: Optional[dict] = None
    custom_instructions: Optional[str] = None
    memory_scope: Optional[str] = None


class AgentMemoryWrite(BaseModel):
    content: str = Field(..., min_length=1)
    category: str = Field(default="general")


class AgentMemorySearch(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=10, ge=1, le=100)


# ===================================================================
# INTERNAL ENDPOINTS (dashboard, no auth)
# ===================================================================

_internal = APIRouter(prefix="/api/agents", tags=["agents-internal"])


@_internal.get("")
def internal_list_agents():
    """List all agent profiles with memory counts."""
    try:
        rows = db.query_all("""
            SELECT ap.*,
                   COALESCE(COUNT(am.id), 0) as memory_count
            FROM agent_profiles ap
            LEFT JOIN agent_memories am ON ap.id = am.profile_id
            GROUP BY ap.id
            ORDER BY ap.name
        """)
        result = []
        for r in (rows or []):
            item = dict(r)
            for k, v in item.items():
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
            result.append(item)
        return {"agents": result}
    except Exception as e:
        logger.error("internal list agents failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@_internal.post("", status_code=201)
def internal_create_agent(req: AgentProfileCreate):
    """Create a new agent profile."""
    slug = _validate_slug(req.slug)
    profile_id = str(uuid.uuid4())

    try:
        db.execute(
            """INSERT INTO agent_profiles (id, name, slug, system_prompt, personality, custom_instructions, memory_scope)
               VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)""",
            (profile_id, req.name, slug, req.system_prompt, req.personality, req.custom_instructions, req.memory_scope),
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Agent with slug '{slug}' already exists")
        logger.error("create agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    row = db.query_one("SELECT * FROM agent_profiles WHERE id = %s::uuid", (profile_id,))
    return {"agent": dict(row) if row else {"id": profile_id, "slug": slug}}


@_internal.get("/{slug}")
def internal_get_agent(slug: str):
    """Get full agent profile with recent memories."""
    slug = _validate_slug(slug)
    try:
        profile = db.query_one(
            "SELECT * FROM agent_profiles WHERE slug = %s", (slug,)
        )
        if not profile:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

        memories = db.query_all(
            """SELECT * FROM agent_memories
               WHERE profile_id = %s::uuid
               ORDER BY created_at DESC LIMIT 20""",
            (str(profile["id"]),),
        )

        return _build_agent_response(profile, memories or [], 100000)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("internal get agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@_internal.put("/{slug}")
def internal_update_agent(slug: str, req: AgentProfileUpdate):
    """Update an agent profile."""
    slug = _validate_slug(slug)
    existing = db.query_one("SELECT id FROM agent_profiles WHERE slug = %s", (slug,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

    updates = []
    params = []
    fields = req.model_dump(exclude_unset=True)

    for field, value in fields.items():
        updates.append(f"{field} = %s")
        params.append(value)

    # Always bump updated_at
    updates.append("updated_at = NOW()")

    if not updates:
        return {"updated": slug}

    params.append(slug)
    try:
        db.execute(
            f"UPDATE agent_profiles SET {', '.join(updates)} WHERE slug = %s",
            tuple(params),
        )
    except Exception as e:
        logger.error("update agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    row = db.query_one("SELECT * FROM agent_profiles WHERE slug = %s", (slug,))
    return {"updated": slug, "agent": dict(row) if row else None}


@_internal.delete("/{slug}")
def internal_delete_agent(slug: str):
    """Delete agent profile and cascade (memories, device assignments)."""
    slug = _validate_slug(slug)
    existing = db.query_one("SELECT id FROM agent_profiles WHERE slug = %s", (slug,))
    if not existing:
        raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

    try:
        # CASCADE handles agent_memories and agent_profile_devices automatically
        db.execute("DELETE FROM agent_profiles WHERE id = %s::uuid", (str(existing["id"]),))
    except Exception as e:
        logger.error("delete agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": slug}


# ===================================================================
# EXTERNAL ENDPOINTS (authenticated via API key, /v1/agents)
# ===================================================================

_external = APIRouter(prefix="/v1/agents", tags=["agents-external"])


@_external.get("")
def external_list_agents(request: Request):
    """List available agent profiles, filtered by the key's scope."""
    agent_slug = getattr(request.state, "agent_slug", None)

    try:
        if agent_slug:
            # Key is scoped to a specific agent — only return that one
            rows = db.query_all(
                """SELECT ap.*, COALESCE(COUNT(am.id), 0) as memory_count
                   FROM agent_profiles ap
                   LEFT JOIN agent_memories am ON ap.id = am.profile_id
                   WHERE ap.slug = %s
                   GROUP BY ap.id""",
                (agent_slug,),
            )
        else:
            # No agent restriction — return all
            rows = db.query_all(
                """SELECT ap.*, COALESCE(COUNT(am.id), 0) as memory_count
                   FROM agent_profiles ap
                   LEFT JOIN agent_memories am ON ap.id = am.profile_id
                   GROUP BY ap.id
                   ORDER BY ap.name"""
            )

        result = []
        for r in (rows or []):
            item = dict(r)
            for k, v in item.items():
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
            result.append(item)

        return {"agents": result}
    except Exception as e:
        logger.error("external list agents failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@_external.get("/{slug}")
def external_get_agent(slug: str, request: Request):
    """
    Get agent profile with memories — the main endpoint devices call.
    Filters memories by key's memory_categories and max_memory_tokens.
    """
    slug = _validate_slug(slug)
    agent_slug = getattr(request.state, "agent_slug", None)

    # If key is scoped to a different agent, deny
    if agent_slug and agent_slug != slug:
        raise HTTPException(status_code=403, detail=f"Key is scoped to agent '{agent_slug}', not '{slug}'")

    max_tokens = getattr(request.state, "max_memory_tokens", 2000)
    categories = getattr(request.state, "memory_categories", None)
    exclude_categories = getattr(request.state, "memory_exclude_categories", []) or []
    memory_scope = getattr(request.state, "memory_scope", "shared")
    device_id = getattr(request.state, "device_id", None)

    try:
        profile = db.query_one(
            "SELECT * FROM agent_profiles WHERE slug = %s", (slug,)
        )
        if not profile:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

        # Build the memory query based on scope and category filters
        profile_id = str(profile["id"])

        if memory_scope == "agent_only":
            # Only agent-specific memories
            memories = _fetch_agent_memories(profile_id, categories, exclude_categories, limit=500)
        elif memory_scope == "both":
            # Agent memories + shared memories
            agent_mems = _fetch_agent_memories(profile_id, categories, exclude_categories, limit=500)
            shared_mems = _fetch_shared_memories(categories, exclude_categories, device_id, limit=500)
            memories = agent_mems + shared_mems
        else:
            # Default: shared only
            memories = _fetch_shared_memories(categories, exclude_categories, device_id, limit=500)

        return _build_agent_response(profile, memories, max_tokens)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("external get agent failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================================================
# AGENT MEMORY ENDPOINTS (/v1/agents/{slug}/memory)
# ===================================================================

_memory = APIRouter(prefix="/v1/agents", tags=["agent-memory"])


@_memory.post("/{slug}/memory", status_code=201)
def write_agent_memory(slug: str, req: AgentMemoryWrite, request: Request):
    """Write a memory to a specific agent. Tags with source_device from key scope."""
    slug = _validate_slug(slug)
    agent_slug = getattr(request.state, "agent_slug", None)
    device_id = getattr(request.state, "device_id", "unknown")

    if agent_slug and agent_slug != slug:
        raise HTTPException(status_code=403, detail=f"Key is scoped to agent '{agent_slug}', not '{slug}'")

    try:
        profile = db.query_one(
            "SELECT id FROM agent_profiles WHERE slug = %s", (slug,)
        )
        if not profile:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

        memory_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO agent_memories (id, profile_id, content, category, source_device, context)
               VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s)""",
            (
                memory_id,
                str(profile["id"]),
                req.content,
                req.category,
                device_id,
                Json({}),  # context JSONB — can be extended later
            ),
        )

        return {
            "id": memory_id,
            "content": req.content,
            "category": req.category,
            "source_device": device_id,
            "profile_slug": slug,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("write agent memory failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@_memory.post("/{slug}/memory/search")
def search_agent_memory(slug: str, req: AgentMemorySearch, request: Request):
    """Search agent memories by full-text query, filtered by key scope."""
    slug = _validate_slug(slug)
    agent_slug = getattr(request.state, "agent_slug", None)

    if agent_slug and agent_slug != slug:
        raise HTTPException(status_code=403, detail=f"Key is scoped to agent '{agent_slug}', not '{slug}'")

    categories = getattr(request.state, "memory_categories", None)
    exclude_categories = getattr(request.state, "memory_exclude_categories", []) or []

    try:
        profile = db.query_one(
            "SELECT id FROM agent_profiles WHERE slug = %s", (slug,)
        )
        if not profile:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")

        profile_id = str(profile["id"])

        # Build category filter
        cat_filter = ""
        params: list = [profile_id, req.query]

        if categories:
            placeholders = ", ".join(["%s"] * len(categories))
            cat_filter = f"AND category IN ({placeholders})"
            params.extend(categories)

        if exclude_categories:
            ex_placeholders = ", ".join(["%s"] * len(exclude_categories))
            cat_filter += f" AND category NOT IN ({ex_placeholders})"
            params.extend(exclude_categories)

        params.append(req.limit)

        memories = db.query_all(
            f"""SELECT * FROM agent_memories
                WHERE profile_id = %s::uuid
                  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', %s)
                  {cat_filter}
                ORDER BY created_at DESC
                LIMIT %s""",
            tuple(params),
        )

        result = []
        for m in (memories or []):
            item = dict(m)
            for k, v in item.items():
                if isinstance(v, datetime):
                    item[k] = v.isoformat()
            result.append(item)

        return {"results": result, "count": len(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("search agent memory failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Internal helpers for memory fetching
# ---------------------------------------------------------------------------

def _fetch_agent_memories(
    profile_id: str,
    categories: Optional[List[str]],
    exclude_categories: List[str],
    limit: int = 500,
) -> list:
    """Fetch agent-scoped memories with optional category filters."""
    where = ["profile_id = %s::uuid"]
    params: list = [profile_id]

    if categories:
        placeholders = ", ".join(["%s"] * len(categories))
        where.append(f"category IN ({placeholders})")
        params.extend(categories)

    if exclude_categories:
        ex_placeholders = ", ".join(["%s"] * len(exclude_categories))
        where.append(f"category NOT IN ({ex_placeholders})")
        params.extend(exclude_categories)

    params.append(limit)

    return db.query_all(
        f"""SELECT * FROM agent_memories
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC
            LIMIT %s""",
        tuple(params),
    ) or []


def _fetch_shared_memories(
    categories: Optional[List[str]],
    exclude_categories: List[str],
    device_id: Optional[str],
    limit: int = 500,
) -> list:
    """
    Fetch shared memories from the global memories table (mem0 sync).
    Filters by category via memory_categories junction table.
    """
    params: list = []
    cat_join = ""
    cat_where = ""

    if categories:
        placeholders = ", ".join(["%s"] * len(categories))
        cat_join = f"""
            JOIN memory_categories mc ON m.id = mc.memory_id
            JOIN categories c ON mc.category_id = c.id"""
        cat_where = f"AND c.name IN ({placeholders})"
        params.extend(categories)

    if exclude_categories:
        if not cat_join:
            cat_join = """
                LEFT JOIN memory_categories mc ON m.id = mc.memory_id
                LEFT JOIN categories c ON mc.category_id = c.id"""
        ex_placeholders = ", ".join(["%s"] * len(exclude_categories))
        cat_where += f" AND (c.name IS NULL OR c.name NOT IN ({ex_placeholders}))"
        params.extend(exclude_categories)

    params.append(limit)

    try:
        rows = db.query_all(
            f"""SELECT m.id, m.payload->>'data' as content,
                       COALESCE(c.name, 'general') as category,
                       m.payload->>'source' as source_device
                FROM memories m
                {cat_join}
                WHERE 1=1 {cat_where}
                ORDER BY
                  CASE WHEN m.payload->>'compacted' = 'true' THEN 1 ELSE 0 END,
                  m.id DESC
                LIMIT %s""",
            tuple(params),
        )
        return rows or []
    except Exception as e:
        logger.warning("Shared memory fetch failed (memories table may not exist): %s", e)
        return []


# ---------------------------------------------------------------------------
# Merge internal + external routers
# ---------------------------------------------------------------------------

# Re-export as a single router for app.py to mount
# app.py will mount: _internal, _external, _memory separately
# but we also export a combined one for convenience

agent_internal_router = _internal
agent_external_router = _external
agent_memory_router = _memory

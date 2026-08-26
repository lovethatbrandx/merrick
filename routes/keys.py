import uuid
import secrets
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List

import database as db
from config import logger
from routes import _validate_uuid, convert_datetimes, _build_update_sql

router = APIRouter(prefix="/api/keys", tags=["keys"])

# ---------------------------------------------------------------------------
# Allowlist of columns that may be updated via PUT /api/keys/{id}.
# Prevents SQL injection through field-name interpolation in model_dump().
# ---------------------------------------------------------------------------
VALID_UPDATE_COLUMNS: set[str] = {
    "key_name",
    "device_id",
    "agent_slug",
    "load_memories",
    "memory_categories",
    "memory_exclude_categories",
    "memory_scope",
    "max_memory_tokens",
    "permissions",
    "rate_limit",
    "active",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    Returns (full_secret, key_hash, key_prefix).
    """
    secret = f"merrick_sk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()
    # Prefix for dashboard display: first 20 chars
    key_prefix = secret[:20] + "..."
    return secret, key_hash, key_prefix


def _sanitize_key(row: dict) -> dict:
    """Strip key_hash from a row before returning it. Never leak the hash."""
    safe = dict(row)
    safe.pop("key_hash", None)
    convert_datetimes(safe)
    return safe


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class KeyCreate(BaseModel):
    device_id: str = Field(..., min_length=1)
    key_name: str = Field(..., min_length=1)
    agent_slug: Optional[str] = None
    load_memories: bool = True
    memory_categories: Optional[List[str]] = None
    memory_exclude_categories: Optional[List[str]] = None
    memory_scope: str = Field(default="shared", pattern="^(shared|agent_only|both)$")
    max_memory_tokens: int = Field(default=2000, ge=100, le=100000)
    permissions: List[str] = Field(default=["read", "write"])
    rate_limit: int = Field(default=100, ge=1, le=10000)


class KeyUpdate(BaseModel):
    key_name: Optional[str] = None
    device_id: Optional[str] = None
    agent_slug: Optional[str] = None
    load_memories: Optional[bool] = None
    memory_categories: Optional[List[str]] = None
    memory_exclude_categories: Optional[List[str]] = None
    memory_scope: Optional[str] = None
    max_memory_tokens: Optional[int] = None
    permissions: Optional[List[str]] = None
    rate_limit: Optional[int] = None
    active: Optional[bool] = None


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_keys():
    """List all API keys (dashboard only — never returns key_hash or secret)."""
    try:
        rows = db.query_all(
            "SELECT * FROM api_keys ORDER BY created_at DESC"
        )
        return {"keys": [_sanitize_key(r) for r in (rows or [])]}
    except Exception as e:
        logger.error("list keys failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201)
def create_key(req: KeyCreate):
    """
    Create a new API key. Returns the plaintext secret ONCE.
    The secret is never stored — only the SHA-256 hash is persisted.
    """
    secret, key_hash, key_prefix = _generate_key()
    key_id = str(uuid.uuid4())

    try:
        db.execute(
            """INSERT INTO api_keys
               (id, key_hash, key_prefix, key_name, device_id, agent_slug,
                load_memories, memory_categories, memory_exclude_categories,
                memory_scope, max_memory_tokens, permissions, rate_limit)
               VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                key_id, key_hash, key_prefix, req.key_name, req.device_id,
                req.agent_slug, req.load_memories, req.memory_categories,
                req.memory_exclude_categories, req.memory_scope,
                req.max_memory_tokens, req.permissions, req.rate_limit,
            ),
        )
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail="Key hash collision — extremely unlikely, but try again")
        logger.error("create key failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Fetch the created row (minus hash) for the response
    row = db.query_one("SELECT * FROM api_keys WHERE id = %s::uuid", (key_id,))

    return {
        "id": key_id,
        "secret": secret,  # RETURNED ONCE — client must store this
        "key_prefix": key_prefix,
        "key_name": req.key_name,
        "device_id": req.device_id,
        "agent_slug": req.agent_slug,
        "permissions": req.permissions,
        "rate_limit": req.rate_limit,
        "active": True,
        **{k: v for k, v in (dict(row) if row else {}).items()
           if k in ("memory_categories", "max_memory_tokens", "created_at")},
    }


@router.put("/{key_id}")
def update_key(key_id: str, req: KeyUpdate):
    """Update key scope (agent, categories, permissions, rate_limit, active)."""
    _validate_uuid(key_id, "key_id")

    existing = db.query_one("SELECT id FROM api_keys WHERE id = %s::uuid", (key_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Key not found")

    updates, params = _build_update_sql(req.model_dump(exclude_unset=True), VALID_UPDATE_COLUMNS)

    if not updates:
        return {"updated": key_id}

    params.append(key_id)
    try:
        db.execute(
            f"UPDATE api_keys SET {', '.join(updates)} WHERE id = %s::uuid",
            tuple(params),
        )
    except Exception as e:
        logger.error("update key failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    row = db.query_one("SELECT * FROM api_keys WHERE id = %s::uuid", (key_id,))
    return {"updated": key_id, "key": _sanitize_key(row) if row else None}


@router.delete("/{key_id}")
def delete_key(key_id: str):
    """Soft delete: set active=false, revoked_at=NOW()."""
    _validate_uuid(key_id, "key_id")

    existing = db.query_one("SELECT id FROM api_keys WHERE id = %s::uuid", (key_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Key not found")

    try:
        db.execute(
            "UPDATE api_keys SET active = false, revoked_at = NOW() WHERE id = %s::uuid",
            (key_id,),
        )
    except Exception as e:
        logger.error("delete key failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"deleted": key_id, "active": False}


@router.post("/{key_id}/rotate")
def rotate_key(key_id: str):
    """
    Generate a new secret, invalidate the old one.
    Returns the new plaintext secret ONCE.
    """
    _validate_uuid(key_id, "key_id")

    existing = db.query_one("SELECT * FROM api_keys WHERE id = %s::uuid AND active = true", (key_id,))
    if not existing:
        raise HTTPException(status_code=404, detail="Active key not found")

    secret, new_hash, new_prefix = _generate_key()

    try:
        db.execute(
            """UPDATE api_keys
               SET key_hash = %s, key_prefix = %s, last_used_at = NULL
               WHERE id = %s::uuid""",
            (new_hash, new_prefix, key_id),
        )
    except Exception as e:
        logger.error("rotate key failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "id": key_id,
        "secret": secret,  # RETURNED ONCE
        "key_prefix": new_prefix,
        "rotated_at": datetime.now(timezone.utc).isoformat(),
    }

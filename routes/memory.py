import uuid

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional

import database as db
import honcho
from config import HONCHO_USER_PEER, MEM0_API_URL, MEM0_EMAIL, MEM0_PASSWORD, logger
from routes.webhooks import fire_webhooks
from routes.analytics import track_event

router = APIRouter(prefix="/api/memory", tags=["memory"])

# Cached mem0 auth token
_mem0_token = None


def _get_mem0_token() -> str:
    """Get a fresh mem0 API token for authenticated writes."""
    global _mem0_token
    if MEM0_EMAIL and MEM0_PASSWORD:
        try:
            resp = httpx.post(
                f"{MEM0_API_URL}/auth/login",
                json={"email": MEM0_EMAIL, "password": MEM0_PASSWORD},
                timeout=10.0,
            )
            resp.raise_for_status()
            _mem0_token = resp.json().get("access_token", "")
        except Exception as e:
            logger.warning("Failed to get mem0 auth token: %s", e)
    return _mem0_token or ""


class MemoryWriteRequest(BaseModel):
    content: str = Field(..., min_length=1)
    source: str = "hermes"  # "hermes" or "android"
    user_id: Optional[str] = None
    metadata: Optional[dict] = None


class MemoryReasoningRequest(BaseModel):
    query: str
    peer: Optional[str] = None


@router.post("/write")
def write_memory(req: MemoryWriteRequest):
    """Write to BOTH mem0 (via mem0 API) and Honcho (via Honcho API)."""
    user_id = req.user_id or HONCHO_USER_PEER
    results = {"mem0": {"success": False, "error": None}, "honcho": {"success": False, "error": None}}

    # --- Write to mem0 (via authenticated API so dashboard logs it) ---
    try:
        token = _get_mem0_token()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = httpx.post(
            f"{MEM0_API_URL}/memories",
            json={
                "messages": [{"role": "user", "content": req.content}],
                "user_id": user_id,
                "agent_id": f"merrick_{req.source}",
                "infer": False,
                "metadata": {"source": req.source, "merrick": True},
            },
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # mem0 returns {"results": [{"id": "...", "memory": "...", ...}]}
        results_list = data.get("results", [])
        mem0_id = results_list[0].get("id", "") if results_list else ""
        results["mem0"] = {"success": True, "id": mem0_id}
        logger.info("mem0 write OK (via API): %s", mem0_id)
    except Exception as e:
        results["mem0"]["error"] = str(e)
        logger.error("mem0 write failed (via API): %s", e)

    # --- Write to Honcho (create session if needed, then post message) ---
    session_id = f"merrick_{req.source}_{user_id}"
    try:
        try:
            honcho.create_session(session_id, f"Merrick {req.source} Import")
        except Exception:
            pass  # Session may already exist — that's fine

        result = honcho.post_message(
            session_id=session_id,
            peer=user_id,
            content=req.content,
        )
        results["honcho"] = {"success": True, "id": result.get("id", "")}
        logger.info("honcho write OK: %s", result.get("id", ""))
    except Exception as e:
        results["honcho"]["error"] = str(e)
        logger.error("honcho write failed: %s", e)

    both_ok = results["mem0"]["success"] and results["honcho"]["success"]
    mem0_id = results["mem0"].get("id", "")

    # Fire webhooks if mem0 write succeeded
    if results["mem0"]["success"]:
        try:
            fire_webhooks("memory.created", {
                "id": mem0_id,
                "content": req.content,
                "source": req.source,
                "user_id": user_id,
            })
        except Exception as e:
            logger.warning("Webhook fire failed: %s", e)

        # Track analytics
        track_event("memory.created", req.source, {"mem0_id": mem0_id, "content": req.content})

    return {
        "status": "ok" if both_ok else "partial",
        "results": results,
    }


@router.post("/reasoning")
def reasoning_query(req: MemoryReasoningRequest):
    """Query Honcho for deep reasoning/insights on a topic."""
    peer = req.peer or HONCHO_USER_PEER
    try:
        honcho_results = honcho.search_peers(peer, req.query)
        return {
            "status": "ok",
            "peer": peer,
            "query": req.query,
            "results": honcho_results,
            "count": len(honcho_results),
        }
    except Exception as e:
        logger.error("honcho reasoning query failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "peer": peer,
            "query": req.query,
            "results": [],
            "count": 0,
        }

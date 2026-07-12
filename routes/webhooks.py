import uuid
import json
import hmac
import hashlib

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

import database as db
from config import logger

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _validate_uuid(value: str, name: str = "id") -> str:
    """Validate UUID format and raise 400 if invalid."""
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {name} format: must be a valid UUID")


def _sign_payload(payload: dict, secret: str) -> str:
    body_bytes = json.dumps(payload, default=str).encode()
    return hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


class WebhookCreate(BaseModel):
    url: str
    events: Optional[List[str]] = ["memory.created"]
    secret: Optional[str] = None


class WebhookUpdate(BaseModel):
    url: Optional[str] = None
    events: Optional[List[str]] = None
    active: Optional[bool] = None
    secret: Optional[str] = None


def fire_webhooks(event: str, payload: dict):
    """Fire all active webhooks for the given event."""
    try:
        hooks = db.query_all(
            "SELECT * FROM webhooks WHERE active=true AND %s = ANY(events)",
            (event,),
        )
    except Exception as e:
        logger.error("Failed to query webhooks: %s", e)
        return

    for hook in (hooks or []):
        try:
            headers = {"Content-Type": "application/json"}
            if hook.get("secret"):
                sig = _sign_payload(payload, hook["secret"])
                headers["X-Merrick-Signature"] = sig
            httpx.post(
                hook["url"],
                json={"event": event, "data": payload},
                headers=headers,
                timeout=10.0,
            )
            logger.info("Webhook %s fired for event %s", hook["id"], event)
        except Exception as e:
            logger.warning("Webhook %s failed: %s", hook["id"], e)


@router.get("")
def list_webhooks():
    """List all webhooks."""
    try:
        hooks = db.query_all("SELECT * FROM webhooks ORDER BY created_at DESC")
        result = []
        for h in (hooks or []):
            item = dict(h)
            if item.get("created_at"):
                item["created_at"] = str(item["created_at"])
            result.append(item)
        return {"webhooks": result}
    except Exception as e:
        logger.error("list webhooks failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
def create_webhook(req: WebhookCreate):
    """Create a new webhook."""
    try:
        hook_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO webhooks (id, url, events, secret)
               VALUES (%s::uuid, %s, %s, %s)""",
            (hook_id, req.url, req.events, req.secret),
        )
        return {"id": hook_id, "url": req.url, "events": req.events, "active": True}
    except Exception as e:
        logger.error("create webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{hook_id}")
def update_webhook(hook_id: str, req: WebhookUpdate):
    """Update a webhook."""
    _validate_uuid(hook_id, "hook_id")
    try:
        existing = db.query_one("SELECT id FROM webhooks WHERE id = %s::uuid", (hook_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Webhook not found")

        updates = []
        params = []
        if req.url is not None:
            updates.append("url = %s")
            params.append(req.url)
        if req.events is not None:
            updates.append("events = %s")
            params.append(req.events)
        if req.active is not None:
            updates.append("active = %s")
            params.append(req.active)
        if req.secret is not None:
            updates.append("secret = %s")
            params.append(req.secret)

        if not updates:
            return {"updated": hook_id}

        params.append(hook_id)
        db.execute(
            f"UPDATE webhooks SET {', '.join(updates)} WHERE id = %s::uuid",
            tuple(params),
        )
        return {"updated": hook_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{hook_id}")
def delete_webhook(hook_id: str):
    """Delete a webhook."""
    _validate_uuid(hook_id, "hook_id")
    try:
        existing = db.query_one("SELECT id FROM webhooks WHERE id = %s::uuid", (hook_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Webhook not found")
        db.execute("DELETE FROM webhooks WHERE id = %s::uuid", (hook_id,))
        return {"deleted": hook_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{hook_id}/test")
def test_webhook(hook_id: str):
    """Send a test payload to a webhook."""
    _validate_uuid(hook_id, "hook_id")
    try:
        hook = db.query_one("SELECT * FROM webhooks WHERE id = %s::uuid", (hook_id,))
        if not hook:
            raise HTTPException(status_code=404, detail="Webhook not found")

        payload = {
            "event": "webhook.test",
            "data": {
                "message": "This is a test webhook from Merrick",
                "webhook_id": hook_id,
            },
        }

        headers = {"Content-Type": "application/json"}
        if hook.get("secret"):
            sig = _sign_payload(payload, hook["secret"])
            headers["X-Merrick-Signature"] = sig

        resp = httpx.post(hook["url"], json=payload, headers=headers, timeout=10.0)
        return {
            "sent": True,
            "status_code": resp.status_code,
            "webhook_id": hook_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("test webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

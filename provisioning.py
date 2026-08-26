"""
Device provisioning: auto-creates Honcho peers and mem0 users on first connect.

When a new device_id hits any /v1/* endpoint, this module:
1. Checks if device_id exists in device_identities table
2. If not, provisions:
   - A Honcho peer (via POST /v3/workspaces/{workspace}/peers)
   - A mem0 user (implicit on first memory write, but we create the mapping)
3. Stores the mapping in device_identities
4. Returns the device's storage IDs for use in write/query
"""

import json
import logging
import threading
from typing import Optional

import database as db
import honcho
from config import HONCHO_WORKSPACE, HONCHO_USER_PEER

logger = logging.getLogger("merrick.provisioning")

# Thread-safe cache: device_id -> {honcho_peer_id, mem0_user_id}
_cache: dict = {}
_lock = threading.Lock()


def _derive_ids(device_id: str) -> tuple[str, str]:
    """Derive Honcho peer ID and mem0 user ID from device_id.
    
    Convention: device_{device_id}
    This keeps device memories isolated from the main user's memories
    while still being queryable.
    """
    safe_id = device_id.replace(" ", "_").replace("/", "_").replace("@", "_at_")
    honcho_peer_id = f"device_{safe_id}"
    mem0_user_id = f"device_{safe_id}"
    return honcho_peer_id, mem0_user_id


def _provision_honcho_peer(peer_id: str, device_id: str) -> bool:
    """Create a peer in Honcho for this device.
    
    Honcho peers are created via POST /v3/workspaces/{workspace}/peers.
    If the peer already exists, Honcho returns 200/201 or 409 (conflict).
    """
    try:
        client = honcho.get_client()
        resp = client.post(
            f"/v3/workspaces/{HONCHO_WORKSPACE}/peers",
            json={
                "id": peer_id,
                "name": f"Device: {device_id}",
                "metadata": {"source": "merrick", "device_id": device_id},
            },
        )
        if resp.status_code in (200, 201):
            logger.info("Provisioned Honcho peer: %s", peer_id)
            return True
        elif resp.status_code == 409:
            # Peer already exists — that's fine
            logger.debug("Honcho peer already exists: %s", peer_id)
            return True
        else:
            logger.warning("Honcho peer creation returned %d: %s", resp.status_code, resp.text)
            # Don't fail — we can still write to Honcho with any peer_id
            return True
    except Exception as e:
        logger.warning("Honcho peer provisioning failed (non-fatal): %s", e)
        # Non-fatal: Honcho accepts messages with any peer_id
        return True


def _ensure_db_row(device_id: str, honcho_peer_id: str, mem0_user_id: str, metadata: dict) -> None:
    """Insert or update the device_identities row."""
    try:
        db.execute(
            """INSERT INTO device_identities (device_id, honcho_peer_id, mem0_user_id, metadata)
               VALUES (%s, %s, %s, %s::jsonb)
               ON CONFLICT (device_id) DO UPDATE SET
                   last_seen_at = NOW(),
                   metadata = EXCLUDED.metadata""",
            (device_id, honcho_peer_id, mem0_user_id, json.dumps(metadata) if metadata else '{}'),
        )
    except Exception as e:
        logger.error("Failed to upsert device_identities for %s: %s", device_id, e)


def get_or_provision(device_id: str, metadata: Optional[dict] = None) -> dict:
    """Get or auto-provision storage identities for a device.
    
    Returns:
        {
            "honcho_peer_id": "device_hermes_phone_abc123",
            "mem0_user_id": "device_hermes_phone_abc123",
            "is_new": True/False
        }
    """
    if not device_id or device_id == "unknown":
        # Fallback: use the global user peer
        return {
            "honcho_peer_id": HONCHO_USER_PEER,
            "mem0_user_id": HONCHO_USER_PEER,
            "is_new": False,
        }

    # Check cache first
    with _lock:
        if device_id in _cache:
            cached = _cache[device_id]
            # Update last_seen (fire-and-forget)
            try:
                db.execute(
                    "UPDATE device_identities SET last_seen_at = NOW() WHERE device_id = %s",
                    (device_id,),
                )
            except Exception:
                pass
            return {**cached, "is_new": False}

    # Check database
    try:
        row = db.query_one(
            "SELECT honcho_peer_id, mem0_user_id FROM device_identities WHERE device_id = %s",
            (device_id,),
        )
        if row:
            result = {
                "honcho_peer_id": row["honcho_peer_id"],
                "mem0_user_id": row["mem0_user_id"],
                "is_new": False,
            }
            with _lock:
                _cache[device_id] = result
            # Update last_seen (fire-and-forget)
            try:
                db.execute(
                    "UPDATE device_identities SET last_seen_at = NOW() WHERE device_id = %s",
                    (device_id,),
                )
            except Exception:
                pass
            return result
    except Exception as e:
        logger.warning("device_identities query failed: %s", e)

    # Not found — provision new device
    honcho_peer_id, mem0_user_id = _derive_ids(device_id)

    # Create Honcho peer
    _provision_honcho_peer(honcho_peer_id, device_id)

    # Store in database
    _ensure_db_row(device_id, honcho_peer_id, mem0_user_id, metadata or {})

    result = {
        "honcho_peer_id": honcho_peer_id,
        "mem0_user_id": mem0_user_id,
        "is_new": True,
    }
    with _lock:
        _cache[device_id] = result

    logger.info("Provisioned new device: %s -> honcho=%s, mem0=%s", device_id, honcho_peer_id, mem0_user_id)
    return result


def get_device_identities(device_id: str) -> Optional[dict]:
    """Look up device identities without provisioning (read-only)."""
    # Check cache
    with _lock:
        if device_id in _cache:
            return _cache[device_id]

    # Check database
    try:
        row = db.query_one(
            "SELECT honcho_peer_id, mem0_user_id, honcho_workspace, provisioned_at, last_seen_at, metadata FROM device_identities WHERE device_id = %s",
            (device_id,),
        )
        if row:
            result = {
                "honcho_peer_id": row["honcho_peer_id"],
                "mem0_user_id": row["mem0_user_id"],
                "honcho_workspace": row.get("honcho_workspace"),
                "provisioned_at": row["provisioned_at"],
                "last_seen_at": row["last_seen_at"],
                "metadata": row.get("metadata", {}),
            }
            with _lock:
                _cache[device_id] = {
                    "honcho_peer_id": row["honcho_peer_id"],
                    "mem0_user_id": row["mem0_user_id"],
                }
            return result
    except Exception as e:
        logger.warning("device_identities lookup failed: %s", e)

    return None


def list_devices() -> list:
    """List all provisioned devices."""
    try:
        rows = db.query_all(
            "SELECT device_id, honcho_peer_id, mem0_user_id, provisioned_at, last_seen_at, metadata FROM device_identities ORDER BY last_seen_at DESC"
        )
        return [dict(row) for row in (rows or [])]
    except Exception as e:
        logger.error("Failed to list devices: %s", e)
        return []

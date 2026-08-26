from fastapi import APIRouter
import database as db
import honcho
import dreaming
from config import logger, DB_HOST, DB_PORT, DB_NAME, HONCHO_URL, HONCHO_WORKSPACE, HONCHO_USER_PEER, MEM0_API_URL, SYNC_INTERVAL, SYNC_ENABLED

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def system_status():
    status = {}

    # --- mem0 memory count ---
    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM memories")
        status["mem0_count"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("mem0 count failed: %s", e)
        status["mem0_count"] = "error"

    # --- mem0 memory samples (recent 5) ---
    try:
        samples = db.query_all(
            """SELECT id, payload->>'data' as data, payload->>'user_id' as user_id
               FROM memories ORDER BY id DESC LIMIT 5"""
        )
        status["mem0_samples"] = [
            {"id": str(s["id"]), "text": s["data"], "user_id": s.get("user_id")}
            for s in (samples or [])
        ]
    except Exception as e:
        logger.error("mem0 samples failed: %s", e)
        status["mem0_samples"] = []

    # --- Honcho sessions ---
    try:
        sessions = honcho.list_sessions()
        status["honcho_sessions"] = len(sessions)
    except Exception as e:
        logger.error("honcho sessions list failed: %s", e)
        status["honcho_sessions"] = "error"

    # --- Honcho conclusions (count + samples) ---
    try:
        conclusions = honcho.list_conclusions(limit=100)
        status["honcho_conclusions"] = len(conclusions)
        status["honcho_samples"] = [
            {"id": c.get("id", ""), "text": c.get("content", "") or c.get("text", "")}
            for c in (conclusions or [])[:5]
        ]
    except Exception as e:
        logger.error("honcho conclusions list failed: %s", e)
        status["honcho_conclusions"] = "error"
        status["honcho_samples"] = []

    # --- Last sync + sync_status ---
    try:
        last = db.query_one("SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 1")
        status["last_sync"] = dict(last) if last else None
        raw_status = (last.get("status") if last else None) or "idle"
        # normalise DB status values to what the frontend expects
        if raw_status == "completed":
            status["sync_status"] = "idle"
        elif raw_status == "running":
            status["sync_status"] = "running"
        elif raw_status in ("completed_with_errors", "error"):
            status["sync_status"] = "error"
        else:
            status["sync_status"] = "idle"
    except Exception as e:
        logger.error("last sync query failed: %s", e)
        status["last_sync"] = None
        status["sync_status"] = "idle"

    # --- Sync state counts ---
    try:
        counts = db.query_all(
            "SELECT source, target, COUNT(*) as cnt FROM sync_state GROUP BY source, target"
        )
        status["sync_state_counts"] = [dict(r) for r in counts] if counts else []
    except Exception as e:
        logger.error("sync state counts failed: %s", e)
        status["sync_state_counts"] = []

    # --- Dreaming stats ---
    try:
        status["dreaming"] = dreaming.get_dreaming_stats()
    except Exception as e:
        logger.error("dreaming stats failed: %s", e)
        status["dreaming"] = {"error": str(e)}

    # --- Health object for dashboard cards ---
    status["health"] = {
        "api": {"status": "healthy", "uptime": "active"},
        "db": {"status": "healthy", "host": f"{db.DB_HOST}:{db.DB_PORT}", "name": db.DB_NAME},
        "honcho": {
            "status": "healthy" if status.get("honcho_sessions") != "error" else "error",
            "workspace": HONCHO_WORKSPACE,
        },
        "mem0": {
            "status": "healthy" if status.get("mem0_count") != "error" else "error",
        },
    }

    # --- Config for developer settings ---
    status["db_host"] = DB_HOST
    status["db_port"] = DB_PORT
    status["honcho_url"] = HONCHO_URL
    status["honcho_workspace"] = HONCHO_WORKSPACE
    status["honcho_user_peer"] = HONCHO_USER_PEER
    status["mem0_api_url"] = MEM0_API_URL
    status["sync_interval"] = SYNC_INTERVAL
    status["sync_enabled"] = SYNC_ENABLED

    return status

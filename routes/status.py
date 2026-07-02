from fastapi import APIRouter
import database as db
import honcho
from config import HONCHO_WORKSPACE, logger

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status")
def system_status():
    status = {}

    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM memories")
        status["mem0_memories"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("mem0 count failed: %s", e)
        status["mem0_memories"] = "error"

    try:
        sessions = honcho.list_sessions()
        status["honcho_sessions"] = len(sessions)
    except Exception as e:
        logger.error("honcho sessions list failed: %s", e)
        status["honcho_sessions"] = "error"

    try:
        conclusions = honcho.list_conclusions(limit=100)
        status["honcho_conclusions"] = len(conclusions)
    except Exception as e:
        logger.error("honcho conclusions list failed: %s", e)
        status["honcho_conclusions"] = "error"

    try:
        last = db.query_one("SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 1")
        status["last_sync"] = dict(last) if last else None
    except Exception as e:
        logger.error("last sync query failed: %s", e)
        status["last_sync"] = None

    try:
        counts = db.query_all(
            "SELECT source, target, COUNT(*) as cnt FROM sync_state GROUP BY source, target"
        )
        status["sync_state_counts"] = [dict(r) for r in counts] if counts else []
    except Exception as e:
        logger.error("sync state counts failed: %s", e)
        status["sync_state_counts"] = []

    return status

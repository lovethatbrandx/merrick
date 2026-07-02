from fastapi import APIRouter, BackgroundTasks
import database as db
import sync
from config import logger

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/trigger")
def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync.run_full_sync)
    return {"status": "sync_triggered"}


@router.get("/status")
def sync_status():
    last = db.query_one(
        "SELECT * FROM sync_log ORDER BY started_at DESC LIMIT 1"
    )
    running = db.query_one(
        "SELECT COUNT(*) as cnt FROM sync_log WHERE status='running'"
    )
    state_counts = db.query_all(
        "SELECT source, target, COUNT(*) as cnt FROM sync_state GROUP BY source, target"
    )

    return {
        "last_sync": dict(last) if last else None,
        "running_count": running["cnt"] if running else 0,
        "sync_state_counts": [dict(r) for r in state_counts] if state_counts else [],
    }


@router.get("/log")
def sync_log(limit: int = 50):
    rows = db.query_all(
        "SELECT * FROM sync_log ORDER BY started_at DESC LIMIT %s", (limit,)
    )
    return {"log": [dict(r) for r in rows] if rows else []}

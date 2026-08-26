from fastapi import APIRouter
import dreaming
from config import logger

router = APIRouter(prefix="/api/dreaming", tags=["dreaming"])


@router.post("/run")
def trigger_dreaming():
    """Manually trigger a dreaming cycle."""
    try:
        result = dreaming.run_dreaming_cycle()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error("Manual dreaming trigger failed: %s", e)
        return {"status": "error", "error": str(e)}


@router.get("/stats")
def dreaming_stats():
    """Get compaction statistics."""
    try:
        return {"status": "ok", "stats": dreaming.get_dreaming_stats()}
    except Exception as e:
        logger.error("Dreaming stats failed: %s", e)
        return {"status": "error", "error": str(e)}

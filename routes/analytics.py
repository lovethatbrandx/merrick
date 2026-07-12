import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import database as db
from config import logger

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class TrackEvent(BaseModel):
    event_type: str
    source: Optional[str] = None
    metadata: Optional[dict] = None


def track_event(event_type: str, source: str = None, metadata: dict = None):
    """Track an analytics event."""
    try:
        db.execute(
            "INSERT INTO analytics (event_type, source, metadata) VALUES (%s, %s, %s)",
            (event_type, source, json.dumps(metadata or {}, default=str)),
        )
    except Exception as e:
        logger.warning("Analytics track failed for %s: %s", event_type, e)


@router.get("/overview")
def analytics_overview():
    """Total memories, categories, webhooks, sync stats."""
    result = {}

    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM memories")
        result["total_memories"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview memories count failed: %s", e)
        result["total_memories"] = 0

    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM categories")
        result["total_categories"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview categories count failed: %s", e)
        result["total_categories"] = 0

    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM webhooks")
        result["total_webhooks"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview webhooks count failed: %s", e)
        result["total_webhooks"] = 0

    try:
        row = db.query_one("SELECT COUNT(*) as cnt FROM sync_state")
        result["total_syncs"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview sync count failed: %s", e)
        result["total_syncs"] = 0

    try:
        row = db.query_one("""
            SELECT COUNT(*) as cnt FROM analytics
            WHERE event_type = 'memory.created'
            AND created_at >= CURRENT_DATE
        """)
        result["memories_today"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview today count failed: %s", e)
        result["memories_today"] = 0

    try:
        row = db.query_one("""
            SELECT COUNT(*) as cnt FROM analytics
            WHERE event_type = 'memory.created'
            AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        """)
        result["memories_this_week"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview week count failed: %s", e)
        result["memories_this_week"] = 0

    try:
        row = db.query_one("""
            SELECT COUNT(*) as cnt FROM analytics
            WHERE event_type = 'memory.created'
            AND created_at >= CURRENT_DATE - INTERVAL '30 days'
        """)
        result["memories_this_month"] = row["cnt"] if row else 0
    except Exception as e:
        logger.error("analytics overview month count failed: %s", e)
        result["memories_this_month"] = 0

    return result


@router.get("/timeline")
def analytics_timeline(period: str = "day", days: int = 30):
    """Memory creation timeline grouped by day/week/month."""
    days = max(1, min(days, 365))
    if period not in ("day", "week", "month"):
        period = "day"

    try:
        if period == "day":
            rows = db.query_all("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM analytics
                WHERE event_type = 'memory.created'
                AND created_at >= NOW() - %s * INTERVAL '1 day'
                GROUP BY DATE(created_at)
                ORDER BY date
            """, (days,))
        elif period == "week":
            rows = db.query_all("""
                SELECT DATE_TRUNC('week', created_at) as date, COUNT(*) as count
                FROM analytics
                WHERE event_type = 'memory.created'
                AND created_at >= NOW() - %s * INTERVAL '1 day'
                GROUP BY DATE_TRUNC('week', created_at)
                ORDER BY date
            """, (days,))
        else:  # month
            rows = db.query_all("""
                SELECT DATE_TRUNC('month', created_at) as date, COUNT(*) as count
                FROM analytics
                WHERE event_type = 'memory.created'
                AND created_at >= NOW() - %s * INTERVAL '1 day'
                GROUP BY DATE_TRUNC('month', created_at)
                ORDER BY date
            """, (days,))

        timeline = []
        for row in (rows or []):
            timeline.append({
                "date": str(row["date"]),
                "count": row["count"],
            })
        return {"timeline": timeline, "period": period, "days": days}
    except Exception as e:
        logger.error("analytics timeline failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources")
def analytics_sources():
    """Breakdown by source."""
    try:
        rows = db.query_all("""
            SELECT COALESCE(source, 'unknown') as source, COUNT(*) as count
            FROM analytics
            WHERE event_type = 'memory.created'
            GROUP BY source
            ORDER BY count DESC
        """)
        sources = [{"source": r["source"], "count": r["count"]} for r in (rows or [])]
        return {"sources": sources}
    except Exception as e:
        logger.error("analytics sources failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def analytics_categories():
    """Memory count per category."""
    try:
        rows = db.query_all("""
            SELECT c.name, c.color, COUNT(mc.memory_id) as count
            FROM categories c
            LEFT JOIN memory_categories mc ON c.id = mc.category_id
            GROUP BY c.id, c.name, c.color
            ORDER BY count DESC
        """)
        categories = [{"name": r["name"], "color": r["color"], "count": r["count"]} for r in (rows or [])]
        return {"categories": categories}
    except Exception as e:
        logger.error("analytics categories failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/track")
def track_custom_event(req: TrackEvent):
    """Track a custom analytics event."""
    try:
        track_event(req.event_type, req.source, req.metadata)
        return {"tracked": True, "event_type": req.event_type}
    except Exception as e:
        logger.error("track event failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

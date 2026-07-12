import csv
import io
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import database as db
from config import logger

router = APIRouter(prefix="/api/export", tags=["export"])


def _get_memories(category_id: str = None):
    """Fetch memories, optionally filtered by category."""
    if category_id:
        rows = db.query_all("""
            SELECT m.id, m.payload->>'data' as data, m.payload->>'source' as source,
                   m.payload->>'user_id' as user_id,
                   ARRAY_AGG(c.name) FILTER (WHERE c.name IS NOT NULL) as categories
            FROM memories m
            LEFT JOIN memory_categories mc ON m.id = mc.memory_id
            LEFT JOIN categories c ON mc.category_id = c.id
            WHERE m.id IN (
                SELECT memory_id FROM memory_categories WHERE category_id = %s::uuid
            )
            GROUP BY m.id, m.payload
            ORDER BY m.id DESC
        """, (category_id,))
    else:
        rows = db.query_all("""
            SELECT m.id, m.payload->>'data' as data, m.payload->>'source' as source,
                   m.payload->>'user_id' as user_id,
                   ARRAY_AGG(c.name) FILTER (WHERE c.name IS NOT NULL) as categories
            FROM memories m
            LEFT JOIN memory_categories mc ON m.id = mc.memory_id
            LEFT JOIN categories c ON mc.category_id = c.id
            GROUP BY m.id, m.payload
            ORDER BY m.id DESC
        """)
    return rows or []


@router.get("/json")
def export_json(category_id: str = None):
    """Export memories as JSON."""
    try:
        memories = _get_memories(category_id)
        result = []
        for m in memories:
            cats = m.get("categories") or []
            cats = [c for c in cats if c is not None]
            result.append({
                "id": str(m["id"]),
                "data": m["data"],
                "source": m.get("source"),
                "user_id": m.get("user_id"),
                "categories": cats,
            })
        return {"memories": result, "count": len(result)}
    except Exception as e:
        logger.error("export json failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/csv")
def export_csv(category_id: str = None):
    """Export memories as CSV."""
    try:
        memories = _get_memories(category_id)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "data", "source", "user_id", "categories"])
        for m in memories:
            cats = m.get("categories") or []
            cats = [c for c in cats if c is not None]
            writer.writerow([
                str(m["id"]),
                m["data"],
                m.get("source", ""),
                m.get("user_id", ""),
                "; ".join(cats),
            ])
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=merrick_export.csv"},
        )
    except Exception as e:
        logger.error("export csv failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/markdown")
def export_markdown(category_id: str = None):
    """Export memories as Markdown."""
    try:
        memories = _get_memories(category_id)

        # Group by categories
        categorized = {}
        uncategorized = []
        for m in memories:
            cats = m.get("categories") or []
            cats = [c for c in cats if c is not None]
            if not cats:
                uncategorized.append(m)
            else:
                for cat in cats:
                    if cat not in categorized:
                        categorized[cat] = []
                    categorized[cat].append(m)

        lines = ["# Merrick Memory Export\n"]

        # Categorized memories
        for cat_name in sorted(categorized.keys()):
            lines.append(f"\n## {cat_name}\n")
            for m in categorized[cat_name]:
                lines.append(f"- {m['data'] or '(empty)'}")

        # Uncategorized
        if uncategorized:
            lines.append("\n## Uncategorized\n")
            for m in uncategorized:
                lines.append(f"- {m['data'] or '(empty)'}")

        content = "\n".join(lines) + "\n"
        return StreamingResponse(
            iter([content]),
            media_type="text/markdown",
            headers={"Content-Disposition": "attachment; filename=merrick_export.md"},
        )
    except Exception as e:
        logger.error("export markdown failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

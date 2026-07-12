import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

import database as db
from config import logger

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _validate_uuid(value: str, name: str = "id") -> str:
    """Validate UUID format and raise 400 if invalid."""
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {name} format: must be a valid UUID")


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1)
    color: Optional[str] = "#6366f1"


class CategoryAssign(BaseModel):
    memory_id: str


@router.get("")
def list_categories():
    """List all categories with memory counts."""
    try:
        categories = db.query_all("""
            SELECT c.id, c.name, c.color, c.created_at,
                   COALESCE(COUNT(mc.memory_id), 0) as memory_count
            FROM categories c
            LEFT JOIN memory_categories mc ON c.id = mc.category_id
            GROUP BY c.id, c.name, c.color, c.created_at
            ORDER BY c.name
        """)
        return {"categories": [dict(c) for c in (categories or [])]}
    except Exception as e:
        logger.error("list categories failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
def create_category(req: CategoryCreate):
    """Create a new category."""
    try:
        cat_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO categories (id, name, color) VALUES (%s::uuid, %s, %s)",
            (cat_id, req.name, req.color),
        )
        return {"id": cat_id, "name": req.name, "color": req.color}
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Category '{req.name}' already exists")
        logger.error("create category failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{category_id}")
def delete_category(category_id: str):
    """Delete a category and its associations."""
    _validate_uuid(category_id, "category_id")
    try:
        existing = db.query_one("SELECT id FROM categories WHERE id = %s::uuid", (category_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Category not found")
        db.execute("DELETE FROM memory_categories WHERE category_id = %s::uuid", (category_id,))
        db.execute("DELETE FROM categories WHERE id = %s::uuid", (category_id,))
        return {"deleted": category_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete category failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{category_id}/assign")
def assign_memory(category_id: str, req: CategoryAssign):
    """Assign a memory to a category."""
    _validate_uuid(category_id, "category_id")
    _validate_uuid(req.memory_id, "memory_id")
    try:
        cat = db.query_one("SELECT id FROM categories WHERE id = %s::uuid", (category_id,))
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        mem = db.query_one("SELECT id FROM memories WHERE id = %s::uuid", (req.memory_id,))
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")

        db.execute(
            """INSERT INTO memory_categories (memory_id, category_id)
               VALUES (%s::uuid, %s::uuid)
               ON CONFLICT (memory_id, category_id) DO NOTHING""",
            (req.memory_id, category_id),
        )
        return {"assigned": True, "memory_id": req.memory_id, "category_id": category_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("assign memory failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{category_id}/unassign/{memory_id}")
def unassign_memory(category_id: str, memory_id: str):
    """Remove a memory from a category."""
    _validate_uuid(category_id, "category_id")
    _validate_uuid(memory_id, "memory_id")
    try:
        db.execute(
            "DELETE FROM memory_categories WHERE memory_id = %s::uuid AND category_id = %s::uuid",
            (memory_id, category_id),
        )
        return {"unassigned": True, "memory_id": memory_id, "category_id": category_id}
    except Exception as e:
        logger.error("unassign memory failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{category_id}/memories")
def list_memories_in_category(category_id: str):
    """List all memories in a category."""
    _validate_uuid(category_id, "category_id")
    try:
        cat = db.query_one("SELECT id, name, color FROM categories WHERE id = %s::uuid", (category_id,))
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        memories = db.query_all("""
            SELECT m.id, m.payload->>'data' as data, m.payload->>'source' as source,
                   m.payload->>'user_id' as user_id, mc.category_id
            FROM memories m
            JOIN memory_categories mc ON m.id = mc.memory_id
            WHERE mc.category_id = %s::uuid
            ORDER BY m.id DESC
        """, (category_id,))

        return {
            "category": dict(cat),
            "memories": [dict(m) for m in (memories or [])],
            "count": len(memories) if memories else 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list memories in category failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

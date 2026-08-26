"""Shared utilities for route modules."""

import uuid
from datetime import datetime

from fastapi import HTTPException


def _validate_uuid(value: str, name: str = "id") -> str:
    """Validate UUID format and raise 400 if invalid."""
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {name} format: must be a valid UUID")


def convert_datetimes(item: dict) -> dict:
    """Convert any datetime values in a dict to ISO format strings."""
    for k, v in item.items():
        if isinstance(v, datetime):
            item[k] = v.isoformat()
    return item


def _build_update_sql(
    fields: dict,
    allowed_columns: set | None = None,
) -> tuple[list[str], list]:
    """Build SET clauses and params from a model_dump dict.

    If allowed_columns is provided, rejects fields not in the set.
    Returns (update_clauses, params).
    """
    updates: list[str] = []
    params: list = []
    for field, value in fields.items():
        if allowed_columns is not None and field not in allowed_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid field: {field} is not an updatable column",
            )
        updates.append(f"{field} = %s")
        params.append(value)
    return updates, params

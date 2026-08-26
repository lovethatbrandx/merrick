from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import database as db
import honcho
import provisioning
from config import HONCHO_USER_PEER, logger

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


def _search_honcho_and_dedupe(query: str, existing_results: list, peer_id: str = HONCHO_USER_PEER) -> list:
    """Search Honcho and deduplicate against existing results.

    Appends honcho hits to existing_results, then dedupes on the 'data' field.
    """
    try:
        honcho_results = honcho.search_peers(peer_id, query)
        for item in honcho_results:
            existing_results.append({
                "source": "honcho",
                "data": item.get("content", "") or item.get("text", ""),
                "metadata": item,
            })
    except Exception as e:
        logger.error("honcho search failed: %s", e)

    seen = set()
    deduped = []
    for r in existing_results:
        key = r.get("data", "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)

    return deduped


@router.post("/query")
def query_memories(req: QueryRequest):
    results = []

    try:
        rows = db.query_all(
            """SELECT payload->>'data' as data, payload->>'user_id' as user_id
               FROM memories
               WHERE to_tsvector('simple', payload->>'data') @@ plainto_tsquery('simple', %s)
               ORDER BY
                 CASE WHEN payload->>'compacted' = 'true' THEN 1 ELSE 0 END,
                 id DESC
               LIMIT 10""",
            (req.query,),
        )
        for row in rows:
            results.append({
                "source": "mem0",
                "data": row["data"],
                "user_id": row.get("user_id"),
            })
    except Exception as e:
        logger.error("mem0 query failed: %s", e)

    deduped = _search_honcho_and_dedupe(req.query, results)
    return {"results": deduped, "count": len(deduped)}


# ===================================================================
# EXTERNAL: Authenticated query via /v1/query
# ===================================================================

v1_query_router = APIRouter(prefix="/v1", tags=["query-external"])


@v1_query_router.post("/query")
def v1_query_memories(req: QueryRequest, request: Request):
    """
    Authenticated query.
    Same as /api/query but filters results based on the key's memory_categories.
    """
    device_id = getattr(request.state, "device_id", "unknown")
    categories = getattr(request.state, "memory_categories", None)
    exclude_categories = getattr(request.state, "memory_exclude_categories", []) or []
    max_tokens = getattr(request.state, "max_memory_tokens", 2000)

    # Provision device-specific storage identities
    identities = provisioning.get_or_provision(device_id)
    honcho_peer_id = identities["honcho_peer_id"]

    results = []

    # --- Query local memories (mem0 sync table) with category filtering ---
    try:
        if categories or exclude_categories:
            # Build combined category filter
            cat_joins = []
            cat_wheres = []
            params: list = [req.query]
            
            if categories:
                cat_placeholders = ", ".join(["%s"] * len(categories))
                cat_joins.append("JOIN memory_categories mc ON m.id = mc.memory_id")
                cat_joins.append("JOIN categories c ON mc.category_id = c.id")
                cat_wheres.append(f"c.name IN ({cat_placeholders})")
                params.extend(categories)
            
            if exclude_categories:
                ex_placeholders = ", ".join(["%s"] * len(exclude_categories))
                if not cat_joins:
                    cat_joins.append("LEFT JOIN memory_categories mc ON m.id = mc.memory_id")
                    cat_joins.append("LEFT JOIN categories c ON mc.category_id = c.id")
                cat_wheres.append(f"(c.name IS NULL OR c.name NOT IN ({ex_placeholders}))")
                params.extend(exclude_categories)
            
            join_clause = " ".join(cat_joins)
            where_clause = " AND ".join(cat_wheres)
            
            rows = db.query_all(
                f"""SELECT m.payload->>'data' as data, m.payload->>'user_id' as user_id
                    FROM memories m
                    {join_clause}
                    WHERE to_tsvector('simple', m.payload->>'data') @@ plainto_tsquery('simple', %s)
                      AND {where_clause}
                    ORDER BY
                      CASE WHEN m.payload->>'compacted' = 'true' THEN 1 ELSE 0 END,
                      m.id DESC
                    LIMIT 10""",
                tuple(params),
            )
        else:
            # No category filter — return all
            rows = db.query_all(
                """SELECT payload->>'data' as data, payload->>'user_id' as user_id
                   FROM memories
                   WHERE to_tsvector('simple', payload->>'data') @@ plainto_tsquery('simple', %s)
                   ORDER BY
                     CASE WHEN payload->>'compacted' = 'true' THEN 1 ELSE 0 END,
                     id DESC
                   LIMIT 10""",
                (req.query,),
            )

        for row in (rows or []):
            results.append({
                "source": "mem0",
                "data": row["data"],
                "user_id": row.get("user_id"),
            })
    except Exception as e:
        logger.error("v1 mem0 query failed: %s", e)

    deduped = _search_honcho_and_dedupe(req.query, results, peer_id=honcho_peer_id)

    # --- Token-budget truncation (v1-specific) ---
    included = []
    tokens_used = 0
    for r in deduped:
        content = r.get("data", "")
        mem_tokens = len(content) // 4  # rough estimate
        if tokens_used + mem_tokens > max_tokens:
            break
        included.append(r)
        tokens_used += mem_tokens

    return {
        "results": included,
        "count": len(included),
        "tokens_used": tokens_used,
        "max_tokens": max_tokens,
        "filtered_by_categories": categories,
    }

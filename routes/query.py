from fastapi import APIRouter
from pydantic import BaseModel
import database as db
import honcho
from config import HONCHO_USER_PEER, logger

router = APIRouter(prefix="/api", tags=["query"])


class QueryRequest(BaseModel):
    query: str


@router.post("/query")
def query_memories(req: QueryRequest):
    results = []

    try:
        rows = db.query_all(
            """SELECT payload->>'data' as data, payload->>'user_id' as user_id
               FROM memories
               WHERE to_tsvector('simple', payload->>'data') @@ plainto_tsquery('simple', %s)
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

    try:
        honcho_results = honcho.search_peers(HONCHO_USER_PEER, req.query)
        for item in honcho_results:
            results.append({
                "source": "honcho",
                "data": item.get("content", "") or item.get("text", ""),
                "metadata": item,
            })
    except Exception as e:
        logger.error("honcho search failed: %s", e)

    seen = set()
    deduped = []
    for r in results:
        key = r.get("data", "")
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)

    return {"results": deduped, "count": len(deduped)}

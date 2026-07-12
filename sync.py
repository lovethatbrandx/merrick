import uuid
import json
import logging
from datetime import datetime, timezone

import database as db
import honcho

logger = logging.getLogger("merrick.sync")

MEM0_TO_HONCHO_SESSION = "merrick_mem0_facts"


def sync_mem0_to_honcho() -> tuple[int, int]:
    logger.info("Starting mem0 -> honcho sync")
    items_synced = 0
    errors = 0

    try:
        rows = db.query_all(
            "SELECT id, payload->>'data' as data, payload->>'user_id' as user_id FROM memories"
        )
    except Exception as e:
        logger.error("Failed to query mem0 memories: %s", e)
        return 0, 1

    try:
        honcho.create_session(MEM0_TO_HONCHO_SESSION, "Merrick Mem0 Import")
    except Exception:
        pass

    for row in rows:
        mem0_id = str(row["id"])
        data = row["data"]
        if not data:
            continue

        existing = db.query_one(
            "SELECT id FROM sync_state WHERE source='mem0' AND source_id=%s AND target='honcho'",
            (mem0_id,),
        )
        if existing:
            continue

        try:
            result = honcho.post_message(
                session_id=MEM0_TO_HONCHO_SESSION,
                peer="merrick",
                content=data,
            )
            target_id = result.get("id", "")
            db.execute(
                """INSERT INTO sync_state (source, source_id, target, target_id)
                   VALUES ('mem0', %s, 'honcho', %s)
                   ON CONFLICT (source, source_id, target) DO NOTHING""",
                (mem0_id, target_id),
            )
            items_synced += 1
            logger.debug("Synced mem0 %s -> honcho %s", mem0_id, target_id)
        except Exception as e:
            errors += 1
            logger.error("Failed to sync mem0 %s to honcho: %s", mem0_id, e)

    logger.info("mem0 -> honcho complete: %d synced, %d errors", items_synced, errors)
    return items_synced, errors


def sync_honcho_to_mem0() -> tuple[int, int]:
    logger.info("Starting honcho -> mem0 sync")
    items_synced = 0
    errors = 0

    try:
        conclusions = honcho.list_conclusions(limit=100)
    except Exception as e:
        logger.error("Failed to list honcho conclusions: %s", e)
        return 0, 1

    for conclusion in conclusions:
        conclusion_id = conclusion.get("id", "")
        content = conclusion.get("content", "") or conclusion.get("text", "")
        if not conclusion_id or not content:
            continue

        existing = db.query_one(
            "SELECT id FROM sync_state WHERE source='honcho' AND source_id=%s AND target='mem0'",
            (conclusion_id,),
        )
        if existing:
            continue

        try:
            new_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO memories (id, vector, payload)
                   VALUES (%s::uuid, NULL, jsonb_build_object(
                       'data', %s,
                       'source', 'honcho',
                       'honcho_id', %s,
                       'user_id', 'ron'
                   ))""",
                (new_id, content, conclusion_id),
            )
            db.execute(
                """INSERT INTO sync_state (source, source_id, target, target_id)
                   VALUES ('honcho', %s, 'mem0', %s)
                   ON CONFLICT (source, source_id, target) DO NOTHING""",
                (conclusion_id, new_id),
            )
            items_synced += 1
            logger.debug("Synced honcho %s -> mem0 %s", conclusion_id, new_id)
        except Exception as e:
            errors += 1
            logger.error("Failed to sync honcho %s to mem0: %s", conclusion_id, e)

    logger.info("honcho -> mem0 complete: %d synced, %d errors", items_synced, errors)
    return items_synced, errors


def run_full_sync() -> dict:
    db.execute(
        """INSERT INTO sync_log (direction, status) VALUES ('mem0_to_honcho', 'running')"""
    )
    log_row = db.query_one(
        "SELECT id FROM sync_log ORDER BY started_at DESC LIMIT 1"
    )
    log_id_val = str(log_row["id"]) if log_row else None

    total_synced = 0
    total_errors = 0
    started = datetime.now(timezone.utc)

    try:
        s1, e1 = sync_mem0_to_honcho()
        total_synced += s1
        total_errors += e1
    except Exception as e:
        total_errors += 1
        logger.error("mem0_to_honcho direction failed: %s", e)

    try:
        s2, e2 = sync_honcho_to_mem0()
        total_synced += s2
        total_errors += e2
    except Exception as e:
        total_errors += 1
        logger.error("honcho_to_mem0 direction failed: %s", e)

    completed = datetime.now(timezone.utc)
    status = "completed" if total_errors == 0 else "completed_with_errors"

    if log_id_val:
        db.execute(
            """UPDATE sync_log SET items_synced=%s, errors=%s, completed_at=%s, status=%s
               WHERE id=%s::uuid""",
            (total_synced, total_errors, completed, status, log_id_val),
        )

    return {
        "items_synced": total_synced,
        "errors": total_errors,
        "status": status,
        "started_at": started.isoformat(),
        "completed_at": completed.isoformat(),
    }

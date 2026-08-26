"""
dreaming.py — Memory compaction loop for Merrick.

Periodically compacts, deduplicates, and summarizes memories to prevent
prompt pollution. Marks memories as compacted rather than deleting them,
so users can recover anything that was touched.

I sold my soul to Satan for this job. Worst trade ever.
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import database as db
from config import (
    DREAMING_ENABLED,
    DREAMING_INTERVAL,
    DREAMING_STALE_DAYS,
    DREAMING_SIMILARITY_THRESHOLD,
)

# ── Logging ────────────────────────────────────────────────────────────────
dream_logger = logging.getLogger("merrick.dreaming")


# ── Text normalization ─────────────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "don", "now", "and", "but", "or", "if", "while", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who", "whom",
})


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, remove stop words, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    return " ".join(w for w in words if w not in _STOP_WORDS)


def _tokenize(text: str) -> set:
    """Return normalized token set."""
    return set(_normalize(text).split())


# ── Similarity ─────────────────────────────────────────────────────────────

def _jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity on tokenized text. Conservative — good for dedup."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _word_overlap_ratio(a: str, b: str) -> float:
    """What fraction of the shorter text's tokens appear in the longer."""
    tokens_a = _tokenize(a)
    tokens_b = _tokenize(b)
    if not tokens_a or not tokens_b:
        return 0.0
    shorter, longer = (tokens_a, tokens_b) if len(tokens_a) <= len(tokens_b) else (tokens_b, tokens_a)
    if not shorter:
        return 0.0
    return len(shorter & longer) / len(shorter)


def _is_similar(a: str, b: str, threshold: Optional[float] = None) -> bool:
    """True if two memory texts are similar enough to consider duplicates.

    Uses combined Jaccard + word overlap with configurable threshold.
    Conservative: both metrics must be above threshold to flag.
    """
    if threshold is None:
        threshold = DREAMING_SIMILARITY_THRESHOLD
    jaccard = _jaccard_similarity(a, b)
    overlap = _word_overlap_ratio(a, b)
    # Both must exceed threshold — better to miss a duplicate than merge different things
    return jaccard >= threshold and overlap >= threshold


# ── Compaction metadata helpers ────────────────────────────────────────────

def _is_compacted(payload: dict) -> bool:
    """Check if a memory is already compacted."""
    return payload.get("compacted", False) is True


def _mark_compacted(payload: dict, reason: str, **extra) -> dict:
    """Return a new payload dict with compaction metadata added."""
    merged = dict(payload)
    merged["compacted"] = True
    merged["compacted_at"] = datetime.now(timezone.utc).isoformat()
    merged["compacted_reason"] = reason
    merged.update(extra)
    return merged


# ── Core dreaming functions ────────────────────────────────────────────────

def _find_duplicates(threshold: Optional[float] = None) -> list[dict]:
    """Find pairs of memories with very similar content.

    Returns list of {keep_id, duplicate_id, similarity, content_a, content_b}.
    """
    rows = db.query_all(
        """SELECT id, payload->>'data' as data, payload
           FROM memories
           WHERE (payload->>'compacted' IS NULL OR payload->>'compacted' != 'true')
           ORDER BY id DESC"""
    )

    if not rows:
        return []

    # Index by normalized content for fast exact-match first pass
    seen: dict[str, dict] = {}
    duplicates = []

    for row in rows:
        mem_id = str(row["id"])
        content = row["data"] or ""
        if not content.strip():
            continue

        norm = _normalize(content)

        # Exact match after normalization — immediate duplicate
        if norm in seen:
            keep = seen[norm]
            duplicates.append({
                "keep_id": keep["id"],
                "duplicate_id": mem_id,
                "similarity": 1.0,
                "content_a": keep["content"],
                "content_b": content,
            })
            continue

        # Fuzzy match against all seen memories — O(n²) but memories table is small
        for existing in seen.values():
            if _is_similar(content, existing["content"], threshold):
                # Keep the more recent one (lower UUID = older in practice,
                # but we ordered DESC so `existing` came first = newer)
                duplicates.append({
                    "keep_id": existing["id"],
                    "duplicate_id": mem_id,
                    "similarity": _jaccard_similarity(content, existing["content"]),
                    "content_a": existing["content"],
                    "content_b": content,
                })
                break  # Only match against the first similar one
        else:
            seen[norm] = {"id": mem_id, "content": content}

    return duplicates


def _find_contradictions() -> list[dict]:
    """Find memories with same topic but different values.

    Strategy: memories whose first ~10 words are similar but whose full
    content diverges significantly. This catches cases like:
      "Project deadline is July 25" vs "Project deadline is August 1"

    Returns list of {keep_id, superseded_id, topic_overlap, content_a, content_b}.
    """
    rows = db.query_all(
        """SELECT id, payload->>'data' as data, payload
           FROM memories
           WHERE (payload->>'compacted' IS NULL OR payload->>'compacted' != 'true')
           ORDER BY id DESC"""
    )

    if not rows:
        return []

    contradictions = []
    seen = []

    for row in rows:
        mem_id = str(row["id"])
        content = row["data"] or ""
        if not content.strip():
            continue

        words = content.split()
        # Take first 10 words as "topic" signature
        topic = " ".join(words[:10])
        norm_topic = _normalize(topic)

        for existing in seen:
            existing_words = existing["content"].split()
            existing_topic = " ".join(existing_words[:10])
            existing_norm = _normalize(existing_topic)

            # Topics must be similar (same subject) but full content different
            topic_sim = _jaccard_similarity(topic, existing_topic)
            content_sim = _jaccard_similarity(content, existing["content"])

            # Contradiction heuristic: similar topic opener, different full content
            if topic_sim >= 0.6 and content_sim < 0.8:
                contradictions.append({
                    "keep_id": existing["id"],      # Keep the more recent one
                    "superseded_id": mem_id,         # Mark older one as superseded
                    "topic_overlap": topic_sim,
                    "content_a": existing["content"],
                    "content_b": content,
                })
                break

        seen.append({"id": mem_id, "content": content})

    return contradictions


def _detect_stale() -> list[str]:
    """Find memories older than DREAMING_STALE_DAYS that haven't been accessed.

    Returns list of stale memory IDs.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=DREAMING_STALE_DAYS)

    rows = db.query_all(
        """SELECT id
           FROM memories
           WHERE (payload->>'compacted' IS NULL OR payload->>'compacted' != 'true')
             AND (payload->>'last_accessed_at' IS NULL
                  OR (payload->>'last_accessed_at')::timestamptz < %s)
           ORDER BY id ASC""",
        (cutoff,),
    )

    return [str(row["id"]) for row in (rows or [])]


def _compact_memory(table: str, mem_id: str, payload: dict, reason: str, **extra) -> bool:
    """Mark a memory as compacted in the database.

    For `memories` table: updates the payload JSONB column.
    For `agent_memories` table: updates the context JSONB column.

    Returns True on success, False on failure.
    """
    try:
        if table == "memories":
            new_payload = _mark_compacted(payload, reason, **extra)
            db.execute(
                "UPDATE memories SET payload = %s WHERE id = %s::uuid",
                (new_payload, mem_id),
            )
        elif table == "agent_memories":
            new_context = _mark_compacted(payload, reason, **extra)
            db.execute(
                "UPDATE agent_memories SET context = %s WHERE id = %s::uuid",
                (new_context, mem_id),
            )
        else:
            dream_logger.error("Unknown table for compaction: %s", table)
            return False

        dream_logger.info("Compacted %s memory %s (reason: %s)", table, mem_id, reason)
        return True
    except Exception as e:
        dream_logger.error("Failed to compact %s memory %s: %s", table, mem_id, e)
        return False


# ── Main dreaming cycle ────────────────────────────────────────────────────

def run_dreaming_cycle() -> dict:
    """Run one cycle of memory compaction.

    Returns stats: {deduplicated, contradictions, stale, errors, duration_ms}.
    """
    start = datetime.now(timezone.utc)
    dream_logger.info("=== Dreaming cycle started ===")

    stats = {
        "deduplicated": 0,
        "contradictions": 0,
        "stale": 0,
        "errors": 0,
        "started_at": start.isoformat(),
    }

    # ── Phase 1: Deduplication ─────────────────────────────────────────
    try:
        duplicates = _find_duplicates()
        dream_logger.info("Found %d potential duplicates", len(duplicates))
        for pair in duplicates:
            try:
                # Fetch the duplicate's payload so we can mark it
                row = db.query_one(
                    "SELECT id, payload FROM memories WHERE id = %s::uuid",
                    (pair["duplicate_id"],),
                )
                if not row:
                    continue
                payload = row["payload"] or {}
                if _is_compacted(payload):
                    continue

                success = _compact_memory(
                    "memories",
                    pair["duplicate_id"],
                    payload,
                    "duplicate",
                    compacted_from=[pair["keep_id"]],
                    similarity_score=pair["similarity"],
                )
                if success:
                    stats["deduplicated"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                dream_logger.error("Duplicate compaction failed for %s: %s", pair.get("duplicate_id"), e)
    except Exception as e:
        stats["errors"] += 1
        dream_logger.error("Deduplication phase failed: %s", e)

    # ── Phase 2: Contradiction detection ───────────────────────────────
    try:
        contradictions = _find_contradictions()
        dream_logger.info("Found %d potential contradictions", len(contradictions))
        for pair in contradictions:
            try:
                row = db.query_one(
                    "SELECT id, payload FROM memories WHERE id = %s::uuid",
                    (pair["superseded_id"],),
                )
                if not row:
                    continue
                payload = row["payload"] or {}
                if _is_compacted(payload):
                    continue

                success = _compact_memory(
                    "memories",
                    pair["superseded_id"],
                    payload,
                    "contradiction",
                    superseded_by=pair["keep_id"],
                    topic_overlap=pair["topic_overlap"],
                )
                if success:
                    stats["contradictions"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                dream_logger.error("Contradiction compaction failed for %s: %s", pair.get("superseded_id"), e)
    except Exception as e:
        stats["errors"] += 1
        dream_logger.error("Contradiction detection phase failed: %s", e)

    # ── Phase 3: Staleness detection ───────────────────────────────────
    try:
        stale_ids = _detect_stale()
        dream_logger.info("Found %d potentially stale memories", len(stale_ids))
        for mem_id in stale_ids:
            try:
                row = db.query_one(
                    "SELECT id, payload FROM memories WHERE id = %s::uuid",
                    (mem_id,),
                )
                if not row:
                    continue
                payload = row["payload"] or {}
                if _is_compacted(payload):
                    continue

                success = _compact_memory(
                    "memories",
                    mem_id,
                    payload,
                    "stale",
                    stale_threshold_days=DREAMING_STALE_DAYS,
                )
                if success:
                    stats["stale"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                dream_logger.error("Stale marking failed for %s: %s", mem_id, e)
    except Exception as e:
        stats["errors"] += 1
        dream_logger.error("Staleness detection phase failed: %s", e)

    # ── Phase 4: Agent memory compaction (same logic, different table) ─
    try:
        agent_stats = _dream_agent_memories()
        stats["agent_deduplicated"] = agent_stats.get("deduplicated", 0)
        stats["agent_stale"] = agent_stats.get("stale", 0)
    except Exception as e:
        stats["errors"] += 1
        dream_logger.error("Agent memory compaction failed: %s", e)

    # ── Finalize ───────────────────────────────────────────────────────
    end = datetime.now(timezone.utc)
    duration_ms = int((end - start).total_seconds() * 1000)
    stats["completed_at"] = end.isoformat()
    stats["duration_ms"] = duration_ms

    dream_logger.info(
        "=== Dreaming cycle complete: %d deduplicated, %d contradictions, "
        "%d stale, %d errors (%dms) ===",
        stats["deduplicated"],
        stats["contradictions"],
        stats["stale"],
        stats["errors"],
        duration_ms,
    )

    return stats


def _dream_agent_memories() -> dict:
    """Compact agent_memories table (internal, full control)."""
    stats = {"deduplicated": 0, "stale": 0, "errors": 0}

    # Deduplicate agent memories
    rows = db.query_all(
        """SELECT id, profile_id, content, context
           FROM agent_memories
           WHERE (context->>'compacted' IS NULL OR context->>'compacted' != 'true')
           ORDER BY created_at DESC"""
    )

    if rows:
        seen: dict[str, dict] = {}
        for row in rows:
            mem_id = str(row["id"])
            content = row["content"] or ""
            context = row["context"] or {}
            if not content.strip():
                continue

            norm = _normalize(content)
            if norm in seen:
                # Duplicate — mark the older one
                try:
                    new_ctx = _mark_compacted(context, "duplicate", compacted_from=[seen[norm]["id"]])
                    db.execute(
                        "UPDATE agent_memories SET context = %s WHERE id = %s::uuid",
                        (new_ctx, mem_id),
                    )
                    stats["deduplicated"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    dream_logger.error("Agent memory dedup failed for %s: %s", mem_id, e)
            else:
                seen[norm] = {"id": mem_id, "content": content}

    # Stale agent memories (30 days for agent memories — shorter than global)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stale_rows = db.query_all(
        """SELECT id, context
           FROM agent_memories
           WHERE (context->>'compacted' IS NULL OR context->>'compacted' != 'true')
             AND created_at < %s
           ORDER BY created_at ASC""",
        (cutoff,),
    )

    for row in (stale_rows or []):
        mem_id = str(row["id"])
        context = row["context"] or {}
        try:
            new_ctx = _mark_compacted(context, "stale", stale_threshold_days=30)
            db.execute(
                "UPDATE agent_memories SET context = %s WHERE id = %s::uuid",
                (new_ctx, mem_id),
            )
            stats["stale"] += 1
        except Exception as e:
            stats["errors"] += 1
            dream_logger.error("Agent memory stale marking failed for %s: %s", mem_id, e)

    return stats


# ── Query helpers (for status endpoint) ────────────────────────────────────

def get_dreaming_stats() -> dict:
    """Get compaction statistics for the status endpoint."""
    stats = {}

    try:
        row = db.query_one(
            """SELECT COUNT(*) as total,
                      COUNT(*) FILTER (WHERE payload->>'compacted' = 'true') as compacted
               FROM memories"""
        )
        stats["memories_total"] = row["total"] if row else 0
        stats["memories_compacted"] = row["compacted"] if row else 0
    except Exception as e:
        dream_logger.error("Dreaming stats query failed: %s", e)
        stats["memories_total"] = "error"
        stats["memories_compacted"] = "error"

    try:
        row = db.query_one(
            """SELECT COUNT(*) as total,
                      COUNT(*) FILTER (WHERE context->>'compacted' = 'true') as compacted
               FROM agent_memories"""
        )
        stats["agent_memories_total"] = row["total"] if row else 0
        stats["agent_memories_compacted"] = row["compacted"] if row else 0
    except Exception as e:
        dream_logger.error("Agent dreaming stats query failed: %s", e)
        stats["agent_memories_total"] = "error"
        stats["agent_memories_compacted"] = "error"

    stats["dreaming_enabled"] = DREAMING_ENABLED
    stats["dreaming_interval"] = DREAMING_INTERVAL
    stats["dreaming_stale_days"] = DREAMING_STALE_DAYS

    return stats

import os
import logging

logger = logging.getLogger("merrick")

DB_HOST = os.getenv("MERRICK_DB_HOST", "host.docker.internal")
DB_PORT = int(os.getenv("MERRICK_DB_PORT", "5433"))
DB_USER = os.getenv("MERRICK_DB_USER", "postgres")
DB_PASSWORD = os.getenv("MERRICK_DB_PASSWORD", "")
DB_NAME = os.getenv("MERRICK_DB_NAME", "postgres")

HONCHO_URL = os.getenv("MERRICK_HONCHO_URL", "http://host.docker.internal:8000")
HONCHO_WORKSPACE = os.getenv("MERRICK_HONCHO_WORKSPACE", "hermes")
HONCHO_USER_PEER = os.getenv("MERRICK_HONCHO_USER_PEER", "ron")

MEM0_API_URL = os.getenv("MERRICK_MEM0_API_URL", "http://host.docker.internal:8888")
MEM0_EMAIL = os.getenv("MERRICK_MEM0_EMAIL", "")
MEM0_PASSWORD = os.getenv("MERRICK_MEM0_PASSWORD", "")

SYNC_INTERVAL = int(os.getenv("MERRICK_SYNC_INTERVAL", "300"))
SYNC_ENABLED = os.getenv("MERRICK_SYNC_ENABLED", "true").lower() == "true"

# ── Dreaming (memory compaction) ──────────────────────────────────────────
DREAMING_ENABLED = os.getenv("MERRICK_DREAMING_ENABLED", "true").lower() == "true"
DREAMING_INTERVAL = int(os.getenv("MERRICK_DREAMING_INTERVAL", "3600"))  # seconds (default: 1 hour)
DREAMING_STALE_DAYS = int(os.getenv("MERRICK_DREAMING_STALE_DAYS", "90"))
DREAMING_SIMILARITY_THRESHOLD = float(os.getenv("MERRICK_DREAMING_SIMILARITY_THRESHOLD", "0.7"))

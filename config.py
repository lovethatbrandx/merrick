import os
import logging

logger = logging.getLogger("merrick")

DB_HOST = os.getenv("MERRICK_DB_HOST", "host.docker.internal")
DB_PORT = int(os.getenv("MERRICK_DB_PORT", "5433"))
DB_USER = os.getenv("MERRICK_DB_USER", "postgres")
DB_PASSWORD = os.getenv("MERRICK_DB_PASSWORD", "supabase_strong_password_2026!")
DB_NAME = os.getenv("MERRICK_DB_NAME", "postgres")

HONCHO_URL = os.getenv("MERRICK_HONCHO_URL", "http://host.docker.internal:8000")
HONCHO_WORKSPACE = os.getenv("MERRICK_HONCHO_WORKSPACE", "hermes")
HONCHO_USER_PEER = os.getenv("MERRICK_HONCHO_USER_PEER", "ron")

SYNC_INTERVAL = int(os.getenv("MERRICK_SYNC_INTERVAL", "300"))
SYNC_ENABLED = os.getenv("MERRICK_SYNC_ENABLED", "true").lower() == "true"

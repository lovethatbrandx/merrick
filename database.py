import psycopg2
import psycopg2.extras
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, logger


def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )


def query_one(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


def query_all(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
    finally:
        conn.close()


def init_schema():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    source TEXT NOT NULL CHECK (source IN ('mem0', 'honcho')),
                    source_id TEXT NOT NULL,
                    target TEXT NOT NULL CHECK (target IN ('mem0', 'honcho')),
                    target_id TEXT,
                    synced_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(source, source_id, target)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    direction TEXT NOT NULL CHECK (direction IN ('mem0_to_honcho', 'honcho_to_mem0')),
                    items_synced INTEGER DEFAULT 0,
                    errors INTEGER DEFAULT 0,
                    started_at TIMESTAMPTZ DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    status TEXT DEFAULT 'running'
                );
            """)
            conn.commit()
            logger.info("Merrick schema initialized")
    finally:
        conn.close()

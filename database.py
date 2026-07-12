import psycopg2
import psycopg2.extras
from psycopg2 import pool
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, logger

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, dbname=DB_NAME,
        )
    return _pool


def get_conn():
    return _get_pool().getconn()


def put_conn(conn):
    _pool.putconn(conn)


def query_one(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        put_conn(conn)


def query_all(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    finally:
        put_conn(conn)


def execute(sql, params=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
    finally:
        put_conn(conn)


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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS categories (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    color TEXT DEFAULT '#6366f1',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memory_categories (
                    memory_id UUID NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
                    category_id UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    PRIMARY KEY (memory_id, category_id)
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS webhooks (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    url TEXT NOT NULL,
                    events TEXT[] DEFAULT ARRAY['memory.created'],
                    active BOOLEAN DEFAULT true,
                    secret TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analytics (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    source TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_analytics_created ON analytics(created_at);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_analytics_event_type ON analytics(event_type);")
            conn.commit()
            logger.info("Merrick schema initialized")
    finally:
        put_conn(conn)

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
            # --- Core memories table (shared with mem0) ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    vector FLOAT8[],
                    payload JSONB DEFAULT '{}'
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_payload ON memories USING GIN (payload);")

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

            # --- API keys (key-first auth model) ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL,
                    key_name TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    agent_slug TEXT,
                    load_memories BOOLEAN DEFAULT true,
                    memory_categories TEXT[],
                    memory_exclude_categories TEXT[] DEFAULT '{}',
                    memory_scope TEXT DEFAULT 'shared'
                        CHECK (memory_scope IN ('shared', 'agent_only', 'both')),
                    max_memory_tokens INTEGER DEFAULT 2000,
                    permissions TEXT[] DEFAULT ARRAY['read', 'write'],
                    rate_limit INTEGER DEFAULT 100,
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    last_used_at TIMESTAMPTZ,
                    revoked_at TIMESTAMPTZ
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE active = true;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_device ON api_keys(device_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(id) WHERE active = true;")

            # --- Agent profiles ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_profiles (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    system_prompt TEXT NOT NULL,
                    personality JSONB DEFAULT '{}',
                    custom_instructions TEXT,
                    memory_scope TEXT DEFAULT 'shared'
                        CHECK (memory_scope IN ('shared', 'agent_only')),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            # --- Agent memories ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    source_device TEXT,
                    context JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_profile ON agent_memories(profile_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_category ON agent_memories(category);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_memories_profile_category ON agent_memories(profile_id, category);")

            # --- Agent profile device assignments ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_profile_devices (
                    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
                    device_id TEXT NOT NULL,
                    active BOOLEAN DEFAULT true,
                    loaded_at TIMESTAMPTZ,
                    PRIMARY KEY (profile_id, device_id)
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_agent_profile_devices_device ON agent_profile_devices(device_id);")

            # --- Device identities (auto-provisioned per device) ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS device_identities (
                    device_id TEXT PRIMARY KEY,
                    honcho_peer_id TEXT NOT NULL,
                    mem0_user_id TEXT NOT NULL,
                    honcho_workspace TEXT,
                    provisioned_at TIMESTAMPTZ DEFAULT NOW(),
                    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
                    metadata JSONB DEFAULT '{}'::jsonb
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_device_identities_last_seen ON device_identities(last_seen_at);")

            conn.commit()
            logger.info("Merrick schema initialized")
    finally:
        put_conn(conn)

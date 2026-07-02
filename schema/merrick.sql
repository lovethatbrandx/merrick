CREATE TABLE IF NOT EXISTS sync_state (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('mem0', 'honcho')),
    source_id TEXT NOT NULL,
    target TEXT NOT NULL CHECK (target IN ('mem0', 'honcho')),
    target_id TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, source_id, target)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    direction TEXT NOT NULL CHECK (direction IN ('mem0_to_honcho', 'honcho_to_mem0')),
    items_synced INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running'
);

-- Migration 001: API Keys table
-- Key-first model: the token itself carries all scope and configuration
-- Each key maps to a device, agent, memory categories, and permissions

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    
    -- Key identity & authentication
    key_hash TEXT NOT NULL UNIQUE,              -- bcrypt hash of the secret (never store plaintext)
    key_prefix TEXT NOT NULL,                   -- "merrick_sk_a1b2c3d4..." for dashboard display
    key_name TEXT NOT NULL,                     -- human-readable name: "Phone - Personal Assistant"
    device_id TEXT NOT NULL,                    -- stable device identifier: "phone_gemini"
    
    -- Scope: what this specific token is allowed to see/do
    agent_slug TEXT,                            -- NULL = no agent persona, or "richard"
    load_memories BOOLEAN DEFAULT true,         -- false = agent-only mode, no memory injection
    memory_categories TEXT[],                   -- NULL = all categories, or ['personal', 'schedule']
    memory_exclude_categories TEXT[] DEFAULT '{}',
    memory_scope TEXT DEFAULT 'shared'          -- 'shared' = global memories, 'agent_only' = agent-specific, 'both'
        CHECK (memory_scope IN ('shared', 'agent_only', 'both')),
    max_memory_tokens INTEGER DEFAULT 2000,     -- cap on memory context size per request
    
    -- Permissions & security
    permissions TEXT[] DEFAULT ARRAY['read', 'write'],  -- 'read', 'write', 'admin'
    rate_limit INTEGER DEFAULT 100,             -- max requests per minute
    
    -- Lifecycle
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

-- Fast lookup by key hash (the hot path on every request)
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE active = true;

-- Device queries (list all keys for a device)
CREATE INDEX IF NOT EXISTS idx_api_keys_device ON api_keys(device_id);

-- Active keys only (partial index for performance)
CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys(id) WHERE active = true;

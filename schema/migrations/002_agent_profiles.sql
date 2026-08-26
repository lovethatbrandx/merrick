-- Migration 002: Agent profiles, memories, and device assignments
-- Agents are portable personas that can be loaded by any device via API key

-- Core agent profiles (identities)
CREATE TABLE IF NOT EXISTS agent_profiles (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,                         -- "Richard Hendricks"
    slug TEXT NOT NULL UNIQUE,                  -- "richard" (used in API URLs and key scope)
    system_prompt TEXT NOT NULL,                -- full system prompt for this agent
    personality JSONB DEFAULT '{}',             -- structured traits: speech patterns, quirks, expertise
    custom_instructions TEXT,                   -- additional guardrails or user preferences
    memory_scope TEXT DEFAULT 'shared'          -- 'shared' = uses global memories, 'agent_only' = isolated
        CHECK (memory_scope IN ('shared', 'agent_only')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Agent-scoped memories (memories tied to a specific agent, not just a device)
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',   -- 'technical', 'personal', 'schedule', 'projects', etc.
    source_device TEXT,                         -- which device wrote this memory
    context JSONB DEFAULT '{}',                 -- conversation context, timestamp, etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Which devices have loaded which agent profiles
CREATE TABLE IF NOT EXISTS agent_profile_devices (
    profile_id UUID REFERENCES agent_profiles(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    active BOOLEAN DEFAULT true,
    loaded_at TIMESTAMPTZ,
    PRIMARY KEY (profile_id, device_id)
);

-- Indexes for agent memory queries (filtered by profile + category)
CREATE INDEX IF NOT EXISTS idx_agent_memories_profile ON agent_memories(profile_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_category ON agent_memories(category);
CREATE INDEX IF NOT EXISTS idx_agent_memories_profile_category ON agent_memories(profile_id, category);

-- Device assignment lookups
CREATE INDEX IF NOT EXISTS idx_agent_profile_devices_device ON agent_profile_devices(device_id);

-- Migration 003: Device Identities
-- Maps each device_id to its storage identities in Honcho and mem0.
-- Auto-provisioned on first connect.

CREATE TABLE IF NOT EXISTS device_identities (
    device_id TEXT PRIMARY KEY,
    honcho_peer_id TEXT NOT NULL,          -- peer ID in Honcho (e.g. "device_hermes_phone_abc123")
    mem0_user_id TEXT NOT NULL,            -- user ID in mem0 (e.g. "device_hermes_phone_abc123")
    honcho_workspace TEXT,                 -- optional: per-device Honcho workspace (NULL = use default)
    provisioned_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb     -- device info: platform, app version, etc.
);

-- Index for quick lookups during auth
CREATE INDEX IF NOT EXISTS idx_device_identities_last_seen ON device_identities (last_seen_at);

-- Update last_seen_at on every auth hit (trigger)
CREATE OR REPLACE FUNCTION update_device_last_seen()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE device_identities SET last_seen_at = NOW() WHERE device_id = NEW.device_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger on api_keys to update device last_seen
-- (We'll update this in app code instead for simplicity)

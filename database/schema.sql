-- OpenClaw Database Schema (V1.0)
-- Optimized for SQLite-vec & Agentic Factory Pipeline

-- SECURITY: Explicitly enforce Write-Ahead Logging (WAL) to prevent lockouts.
PRAGMA journal_mode=WAL;

-- Main Task Queue Table
-- Used for background processing and HITL-guarded routing.
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    is_sensitive BOOLEAN NOT NULL DEFAULT 0,
    required_tier TEXT NOT NULL,
    status TEXT CHECK(status IN ('queued', 'processing', 'completed', 'failed', 'pending_hitl')) NOT NULL DEFAULT 'queued',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Index for status filtering and background processing
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

-- Factory Audit Log (Enhanced Discovery)
CREATE TABLE IF NOT EXISTS factory_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_name TEXT UNIQUE NOT NULL,
    description TEXT,
    capabilities TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

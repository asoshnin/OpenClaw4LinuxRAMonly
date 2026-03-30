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

-- Artifacts Index (LIB-01.1)
-- Unified index of both Factory-managed and OpenClaw-native artifacts.
-- source='agentic_factory'  -> owned by this factory, writable.
-- source='openclaw_native'  -> read-only external dependency; managed by OpenClaw runtime.
-- is_readonly=0 -> mutable  |  is_readonly=1 -> immutable (guard enforced in librarian_ctl.py)
CREATE TABLE IF NOT EXISTS artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT UNIQUE NOT NULL,
    artifact_type TEXT,
    path          TEXT,
    description   TEXT,
    source        TEXT DEFAULT 'agentic_factory',
    is_readonly   INTEGER DEFAULT 0,
    capabilities  TEXT,
    dependencies  TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source);
CREATE INDEX IF NOT EXISTS idx_artifacts_readonly ON artifacts(is_readonly);

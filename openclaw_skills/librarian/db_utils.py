"""
db_utils.py — Shared Database Schema Helpers (PR-06)
======================================================
Central source of truth for project-scoped schema creation.
Used by:
  - migrate_bl00c.py   (Global Hub bootstrap)
  - project_init.py    (factory-init new-project CLI)

NEVER duplicate table DDL across scripts — always import from here.

SCHEMA AUTHORITY:
  This file is the canonical definition of the tasks table.
  Before modifying any INSERT/UPDATE in any Python script, you MUST:
    1. Verify the physical schema: PRAGMA table_info(tasks);
    2. Ensure your change matches this DDL.
    3. If a column is missing, run migrate_lib01_2.py FIRST.
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)


def initialize_project_schema(conn: sqlite3.Connection) -> None:
    """Create all project-scoped tables in *conn* if they do not exist.

    Tables created (idempotent — uses CREATE TABLE IF NOT EXISTS):
      - sprints
      - tasks   (canonical post-RT-SCHEMA-01 schema)

    Sets WAL mode and enables foreign-key enforcement for the connection.

    Args:
        conn: An open sqlite3.Connection pointing to a project or global DB.
    """
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sprints (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            goal       TEXT,
            status     TEXT CHECK(status IN ('planned', 'active', 'complete')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    log.info("sprints table ready.")

    # ── Canonical tasks DDL (RT-SCHEMA-01) ──────────────────────────────────
    # KEY CHANGES from legacy schema:
    #   - `description` renamed to `payload`
    #   - Added: is_sensitive BOOLEAN DEFAULT 0
    #   - Added: required_tier TEXT DEFAULT 'cpu'
    #   - Added: attempt_count, max_retries, last_error, session_id, baseline_commit
    #   - CHECK constraint extended to include all runtime statuses
    # DO NOT revert to the old `description` column — run migrate_lib01_2.py
    # against existing databases to bring them up to this schema.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id               TEXT PRIMARY KEY,
            sprint_id        INTEGER REFERENCES sprints(id),
            depends_on       TEXT,
            assigned_to      TEXT,
            domain           TEXT,
            payload          TEXT,
            is_sensitive     BOOLEAN DEFAULT 0,
            required_tier    TEXT DEFAULT 'cpu',
            status           TEXT DEFAULT 'queued'
                             CHECK(status IN (
                                 'queued', 'pending', 'processing', 'processing_subagent',
                                 'blocked', 'in_progress', 'awaiting_review',
                                 'complete', 'completed', 'failed', 'pending_hitl'
                             )),
            priority         TEXT,
            source_doc       TEXT,
            test_summary     TEXT,
            attempt_count    INTEGER DEFAULT 0,
            max_retries      INTEGER DEFAULT 3,
            last_error       TEXT,
            session_id       TEXT,
            baseline_commit  TEXT,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    log.info("tasks table ready.")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"
    )
    log.info("idx_tasks_status ready.")

    conn.commit()
    log.info("initialize_project_schema: schema committed.")

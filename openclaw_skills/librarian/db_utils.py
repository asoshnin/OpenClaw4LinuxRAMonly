"""
db_utils.py — Shared Database Schema Helpers (PR-06)
======================================================
Central source of truth for project-scoped schema creation.
Used by:
  - migrate_bl00c.py   (Global Hub bootstrap)
  - project_init.py    (factory-init new-project CLI)

NEVER duplicate table DDL across scripts — always import from here.
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)


def initialize_project_schema(conn: sqlite3.Connection) -> None:
    """Create all project-scoped tables in *conn* if they do not exist.

    Tables created (idempotent — uses CREATE TABLE IF NOT EXISTS):
      - sprints
      - tasks

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           TEXT PRIMARY KEY,
            sprint_id    INTEGER REFERENCES sprints(id),
            depends_on   TEXT,
            assigned_to  TEXT,
            domain       TEXT,
            description  TEXT,
            status       TEXT DEFAULT 'pending'
                         CHECK(status IN (
                             'pending', 'in_progress', 'awaiting_review',
                             'complete', 'failed', 'blocked'
                         )),
            priority     TEXT,
            source_doc   TEXT,
            test_summary TEXT,
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    log.info("tasks table ready.")

    conn.commit()
    log.info("initialize_project_schema: schema committed.")

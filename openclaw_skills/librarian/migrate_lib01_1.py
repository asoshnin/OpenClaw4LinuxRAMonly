"""
Migration LIB-01.1: Extend artifacts table with source + is_readonly columns.

Design:
  - Non-destructive: uses CREATE TABLE IF NOT EXISTS + ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
  - Idempotent: safe to re-run on an already-migrated DB.
  - Does NOT touch any existing tables or columns.

Run directly:
    python3 openclaw_skills/librarian/migrate_lib01_1.py workspace/factory.db
"""

import os
import sys
import sqlite3
import logging
import argparse

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if 'column' already exists in 'table'."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def run_migration(db_path: str) -> None:
    """Apply the LIB-01.1 migration to the given database file."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")

        # ── Step 1: Create artifacts table if it does not exist ──────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artifacts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                artifact_type TEXT,
                path        TEXT,
                description TEXT,
                source      TEXT DEFAULT 'agentic_factory',
                is_readonly INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("artifacts table: ensured.")

        # ── Step 2: Add 'source' column (idempotent) ─────────────────────────
        if not _column_exists(conn, "artifacts", "source"):
            conn.execute(
                "ALTER TABLE artifacts ADD COLUMN source TEXT DEFAULT 'agentic_factory';"
            )
            logger.info("artifacts.source column: added.")
        else:
            logger.info("artifacts.source column: already present.")

        # ── Step 3: Add 'is_readonly' column (idempotent) ────────────────────
        if not _column_exists(conn, "artifacts", "is_readonly"):
            conn.execute(
                "ALTER TABLE artifacts ADD COLUMN is_readonly INTEGER DEFAULT 0;"
            )
            logger.info("artifacts.is_readonly column: added.")
        else:
            logger.info("artifacts.is_readonly column: already present.")

        conn.commit()
        logger.info("Migration LIB-01.1 complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LIB-01.1 migration: adds source + is_readonly to artifacts table."
    )
    parser.add_argument("db_path", help="Path to factory.db")
    args = parser.parse_args()

    try:
        run_migration(args.db_path)
        print(f"LIB-01.1 migration applied to {args.db_path}")
        sys.exit(0)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

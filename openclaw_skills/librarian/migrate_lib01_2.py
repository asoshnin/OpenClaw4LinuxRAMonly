"""
Migration LIB-01.2: Add capabilities and dependencies to artifacts table.

Design:
  - Non-destructive: uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
  - Idempotent: safe to re-run on an already-migrated DB.
  - Does NOT drop existing tables. Existing rows default to NULL.
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
    """Apply the LIB-01.2 migration to the given database file."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")

        # ── Add capabilities ─────────────────────────────────────────
        if not _column_exists(conn, "artifacts", "capabilities"):
            conn.execute("ALTER TABLE artifacts ADD COLUMN capabilities TEXT;")
            logger.info("artifacts.capabilities column: added.")
        else:
            logger.info("artifacts.capabilities column: already present.")

        # ── Add dependencies ────────────────────────────────────
        if not _column_exists(conn, "artifacts", "dependencies"):
            conn.execute("ALTER TABLE artifacts ADD COLUMN dependencies TEXT;")
            logger.info("artifacts.dependencies column: added.")
        else:
            logger.info("artifacts.dependencies column: already present.")

        conn.commit()
        logger.info("Migration LIB-01.2 complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LIB-01.2 migration: adds capabilities/dependencies to artifacts table."
    )
    parser.add_argument("db_path", help="Path to factory.db")
    args = parser.parse_args()

    try:
        run_migration(args.db_path)
        print(f"LIB-01.2 migration applied to {args.db_path}")
        sys.exit(0)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)

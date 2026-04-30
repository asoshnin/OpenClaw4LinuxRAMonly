"""
Migration RT-SCHEMA-01 (repurposed from LIB-01.2):
Rebuild the `tasks` table to fix the schema-code desync.

ROOT CAUSE:
  intake.py inserts (payload, is_sensitive, required_tier, status='queued') but
  the live factory.db / project.db still have the legacy DDL with:
    - column `description` (no `payload`, `is_sensitive`, `required_tier`)
    - CHECK(status IN ('pending', ...)) that excludes 'queued'

STRATEGY — SQLite Table Rebuild:
  SQLite does NOT support ALTER TABLE DROP/MODIFY CONSTRAINT.
  The only safe path is:
    1. CREATE tasks_new with the correct schema.
    2. INSERT INTO tasks_new SELECT ... mapping description -> payload.
    3. DROP TABLE tasks.
    4. ALTER TABLE tasks_new RENAME TO tasks.

IDEMPOTENCY:
  If `payload` column already exists → migration already applied → exit cleanly.

USAGE:
  python3 openclaw_skills/librarian/migrate_lib01_2.py workspace/factory.db [workspace/project.db ...]
"""

import argparse
import logging
import os
import sqlite3
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

# ---------------------------------------------------------------------------
# Canonical target DDL
# ---------------------------------------------------------------------------

_TASKS_NEW_DDL = """
CREATE TABLE tasks_new (
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
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _column_names(conn: sqlite3.Connection, table: str) -> list:
    """Return a list of column names for *table* (empty list if table absent)."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def run_migration(db_path: str) -> None:
    """Apply the RT-SCHEMA-01 tasks-table rebuild to *db_path*.

    Raises:
        FileNotFoundError: If *db_path* does not exist.
    """
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    logger.info("Opening %s …", db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=OFF;")  # Required during table rebuild

        # ── Idempotency check ────────────────────────────────────────────────
        existing_cols = _column_names(conn, "tasks")
        if not existing_cols:
            logger.info("No tasks table found in %s — nothing to migrate.", db_path)
            return

        if "payload" in existing_cols:
            logger.info(
                "tasks.payload already present in %s — migration already applied.", db_path
            )
            return

        # ── Introspect existing columns for safe SELECT mapping ───────────────
        # We only SELECT columns that exist in the old schema to avoid errors
        # on databases that may be at different migration checkpoints.
        old_cols = set(existing_cols)

        # Build the SELECT expression: map description → payload, fill new cols
        # with safe defaults for every column in tasks_new.
        def _coalesce_or_default(new_col: str, default: str = "NULL") -> str:
            """Return the SQL expression mapping the old schema to a new column."""
            mapping = {
                "id":              "id",
                "sprint_id":       "sprint_id"       if "sprint_id"       in old_cols else "NULL",
                "depends_on":      "depends_on"      if "depends_on"      in old_cols else "NULL",
                "assigned_to":     "assigned_to"     if "assigned_to"     in old_cols else "NULL",
                "domain":          "domain"          if "domain"          in old_cols else "NULL",
                # Core rename: description → payload
                "payload":         "description"     if "description"     in old_cols else "NULL",
                "is_sensitive":    "0",
                "required_tier":   "'cpu'",
                # Map old 'pending' status to 'queued' so new CHECK passes;
                # keep any other values that are already valid.
                "status":          (
                    "CASE WHEN status = 'pending' THEN 'queued' ELSE status END"
                    if "status" in old_cols else "'queued'"
                ),
                "priority":        "priority"        if "priority"        in old_cols else "NULL",
                "source_doc":      "source_doc"      if "source_doc"      in old_cols else "NULL",
                "test_summary":    "test_summary"    if "test_summary"    in old_cols else "NULL",
                "attempt_count":   "attempt_count"   if "attempt_count"   in old_cols else "0",
                "max_retries":     "max_retries"     if "max_retries"     in old_cols else "3",
                "last_error":      "last_error"      if "last_error"      in old_cols else "NULL",
                "session_id":      "session_id"      if "session_id"      in old_cols else "NULL",
                "baseline_commit": "baseline_commit" if "baseline_commit" in old_cols else "NULL",
                "created_at":      "updated_at"      if "updated_at"      in old_cols else "CURRENT_TIMESTAMP",
                "updated_at":      "updated_at"      if "updated_at"      in old_cols else "CURRENT_TIMESTAMP",
            }
            return mapping.get(new_col, default)

        new_col_order = [
            "id", "sprint_id", "depends_on", "assigned_to", "domain",
            "payload", "is_sensitive", "required_tier", "status",
            "priority", "source_doc", "test_summary",
            "attempt_count", "max_retries", "last_error",
            "session_id", "baseline_commit", "created_at", "updated_at",
        ]
        select_exprs = ", ".join(_coalesce_or_default(c) for c in new_col_order)
        insert_cols  = ", ".join(new_col_order)

        # ── Step 1: Create tasks_new ─────────────────────────────────────────
        if _table_exists(conn, "tasks_new"):
            logger.warning("tasks_new already exists — dropping stale copy.")
            conn.execute("DROP TABLE tasks_new;")

        conn.execute(_TASKS_NEW_DDL)
        logger.info("tasks_new created.")

        # ── Step 2: Copy data ────────────────────────────────────────────────
        conn.execute(
            f"INSERT INTO tasks_new ({insert_cols}) SELECT {select_exprs} FROM tasks;"
        )
        row_count = conn.execute("SELECT COUNT(*) FROM tasks_new;").fetchone()[0]
        logger.info("Copied %d rows into tasks_new.", row_count)

        # ── Step 3: Drop old tasks ───────────────────────────────────────────
        conn.execute("DROP TABLE tasks;")
        logger.info("Old tasks table dropped.")

        # ── Step 4: Rename ───────────────────────────────────────────────────
        conn.execute("ALTER TABLE tasks_new RENAME TO tasks;")
        logger.info("tasks_new renamed to tasks.")

        # ── Re-create the status index if it existed ──────────────────────────
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"
        )

        conn.execute("PRAGMA foreign_keys=ON;")
        conn.commit()
        logger.info("RT-SCHEMA-01 migration complete on %s.", db_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="migrate_lib01_2",
        description=(
            "RT-SCHEMA-01: Rebuild tasks table to fix schema-code desync. "
            "Pass one or more database paths; each is migrated in sequence."
        ),
    )
    parser.add_argument(
        "db_paths",
        nargs="+",
        metavar="DB_PATH",
        help="Path(s) to SQLite database file(s) to migrate (e.g. workspace/factory.db).",
    )
    args = parser.parse_args()

    exit_code = 0
    for db_path in args.db_paths:
        try:
            run_migration(db_path)
            print(f"OK  {db_path}")
        except FileNotFoundError as e:
            print(f"SKIP  {db_path}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"FAIL  {db_path}: {e}", file=sys.stderr)
            logger.exception("Migration failed on %s", db_path)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())

"""
sync_backlog.py — LIB-02: Backlog Sync Utility
================================================
Synchronises factory.db task status into the human-readable Markdown backlog
file using a fail-safe HTML-marker injection model.

Safety invariants:
  • Exactly ONE START and ONE END marker per zone — exit 1 otherwise.
  • Atomic write: temp file + os.replace() — no partial writes.
  • Size-Guard: abort if generated file would shrink original by >20%.
  • Dry-Run: --dry-run prints output without touching the file.
  • Verified-Completion Gate: task LIB-02 is only marked 'complete' by
    update_task_status() after a *successful* file sync AND idempotency check.
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap sys.path so this script can find openclaw_skills/config.py
# whether run directly or via pytest.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent   # repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.config import BACKLOG_UPDATE_PATH, DEFAULT_DB_PATH  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(message)s",
)
log = logging.getLogger("sync_backlog")


# ---------------------------------------------------------------------------
# Zone definitions
#   SYNC_ZONES   — content is replaced from DB on every run
#   GUARD_ZONES  — markers are verified to exist but content is NOT replaced
#                  (human-authored documentation; DB has only short descriptions)
# ---------------------------------------------------------------------------
SYNC_ZONES = {
    "status_table": (
        "<!-- START_STATUS_TABLE -->",
        "<!-- END_STATUS_TABLE -->",
    ),
}

GUARD_ZONES = {
    "appendix_specs": (
        "<!-- START_APPENDIX_SPECS -->",
        "<!-- END_APPENDIX_SPECS -->",
    ),
}

# All zones used for marker assertion
ZONES = {**SYNC_ZONES, **GUARD_ZONES}


# ---------------------------------------------------------------------------
# Marker assertion helper
# ---------------------------------------------------------------------------

def _assert_markers(content: str) -> None:
    """Raise SystemExit(1) if any zone has missing or duplicated markers."""
    for zone, (start, end) in ZONES.items():
        s_count = content.count(start)
        e_count = content.count(end)
        if s_count != 1 or e_count != 1:
            log.error(
                "Marker assertion FAILED for zone '%s': "
                "found %d START and %d END markers (expected exactly 1 each).",
                zone, s_count, e_count,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ensure_extended_columns(conn: sqlite3.Connection) -> None:
    """Idempotently add priority and source_doc columns if absent."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "priority" not in existing:
        conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT")
        log.info("Added 'priority' column to tasks.")
    if "source_doc" not in existing:
        conn.execute("ALTER TABLE tasks ADD COLUMN source_doc TEXT")
        log.info("Added 'source_doc' column to tasks.")
    conn.commit()


def _load_tasks(conn: sqlite3.Connection) -> list[dict]:
    """Return all tasks enriched with wave name, ordered by sprint then id.

    Selects `payload` (the post-RT-SCHEMA-01 column name). The COALESCE
    provides an empty-string default for rows where payload IS NULL.
    Databases must be migrated via migrate_lib01_2.py before calling this.
    """
    cur = conn.execute("""
        SELECT
            t.id,
            t.domain,
            COALESCE(t.payload, '') AS payload,
            t.status,
            COALESCE(t.priority, '') AS priority,
            COALESCE(t.source_doc, '') AS source_doc,
            s.name                   AS wave
        FROM tasks t
        JOIN sprints s ON t.sprint_id = s.id
        ORDER BY s.id, t.id
    """)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Markdown generators
# ---------------------------------------------------------------------------

_WAVE_LABEL = {
    "Wave 1 Foundation": "1",
    "Wave 2 Perception": "2",
    "Wave 3 Evolution": "3",
    "Wave 4 Governance": "4",
}


def _status_display(status: str) -> str:
    """Capitalise status for display."""
    return status.replace("_", " ").title()


def _build_status_table(tasks: list[dict]) -> str:
    header = (
        "| ID | Wave | Domain | Task Description | Source Doc | Priority | Status |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    rows = []
    for t in tasks:
        wave_num = _WAVE_LABEL.get(t["wave"], t["wave"])
        rows.append(
            f"| **{t['id']}** | {wave_num} | {t['domain']} | {t['payload']} "
            f"| {t['source_doc'] or ''} | {t['priority'] or ''} | {_status_display(t['status'])} |"
        )
    return header + "\n".join(rows)


def _build_appendix_specs(tasks: list[dict]) -> str:
    header = "| ID | Requirements and Specifications |\n|---|---|\n"
    rows = []
    for t in tasks:
        spec = t["payload"]
        rows.append(f"| **{t['id']}** | {spec} |")
    return header + "\n".join(rows)


# ---------------------------------------------------------------------------
# Zone injection
# ---------------------------------------------------------------------------

def _inject_zone(content: str, zone: str, new_body: str) -> str:
    """Replace the content between START/END markers for *zone*."""
    start_tag, end_tag = ZONES[zone]
    # Non-greedy replacement between the markers (markers themselves preserved)
    pattern = re.compile(
        re.escape(start_tag) + r".*?" + re.escape(end_tag),
        re.DOTALL,
    )
    replacement = f"{start_tag}\n{new_body}\n{end_tag}"
    return pattern.sub(replacement, content)


# ---------------------------------------------------------------------------
# Size-Guard
# ---------------------------------------------------------------------------

def _size_guard(original: str, updated: str) -> None:
    orig_len = len(original.encode("utf-8"))
    new_len = len(updated.encode("utf-8"))
    if orig_len > 0:
        reduction = (orig_len - new_len) / orig_len
        if reduction > 0.20:
            log.error(
                "Size-Guard REJECTED write: file would shrink by %.1f%% "
                "(original=%d bytes, new=%d bytes). Aborting.",
                reduction * 100, orig_len, new_len,
            )
            sys.exit(1)


# ---------------------------------------------------------------------------
# Core sync logic
# ---------------------------------------------------------------------------

def sync(
    db_path: Path,
    backlog_path: Path,
    *,
    dry_run: bool = False,
) -> str:
    """Perform the full sync. Returns the final file content string."""

    if not db_path.exists():
        log.error("DB not found: %s", db_path)
        sys.exit(1)

    if not backlog_path.exists():
        log.error("Backlog file not found: %s", backlog_path)
        sys.exit(1)

    # --- Read original ---
    original = backlog_path.read_text(encoding="utf-8")

    # --- Marker assertion ---
    _assert_markers(original)
    log.info("Marker assertion passed for all zones.")

    # --- DB query ---
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    _ensure_extended_columns(conn)
    tasks = _load_tasks(conn)
    conn.close()
    log.info("Loaded %d tasks from DB.", len(tasks))

    # --- Build new zone content (status table only — appendix is human-authored) ---
    status_md = _build_status_table(tasks)

    # --- Inject SYNC_ZONES only ---
    updated = original
    updated = _inject_zone(updated, "status_table", status_md)

    # --- Size-Guard ---
    _size_guard(original, updated)
    log.info("Size-Guard passed.")

    if dry_run:
        print("=" * 60)
        print("DRY-RUN: generated content (no file written)")
        print("=" * 60)
        print(updated)
        log.info("Dry-run complete. No changes written to disk.")
        return updated

    # --- Atomic write ---
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=backlog_path.parent, suffix=".tmp", prefix=".sync_backlog_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(updated)
        os.replace(tmp_path, backlog_path)
    except Exception:
        # Clean up temp on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    log.info("Backlog synced successfully → %s", backlog_path)
    return updated


# ---------------------------------------------------------------------------
# Task status update (Verified-Completion Gate)
# ---------------------------------------------------------------------------

def update_task_status(
    db_path: Path,
    task_id: str,
    new_status: str,
    test_summary: str,
) -> None:
    """Update a task's status in factory.db per the Verified-Completion invariant.

    A task must have a non-empty test_summary when being marked complete.
    """
    if new_status == "complete" and not test_summary.strip():
        raise ValueError(
            f"Verified-Completion Gate: test_summary is required to mark '{task_id}' complete."
        )
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        "UPDATE tasks SET status=?, test_summary=?, updated_at=CURRENT_TIMESTAMP "
        "WHERE id=?",
        (new_status, test_summary, task_id),
    )
    if conn.total_changes == 0:
        conn.close()
        raise ValueError(f"Task '{task_id}' not found in DB.")
    conn.commit()
    conn.close()
    log.info("Task %s → status=%s", task_id, new_status)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sync_backlog",
        description="Sync factory.db task statuses into the Markdown backlog file.",
    )
    p.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="Path to factory.db (default: %(default)s)",
    )
    p.add_argument(
        "--backlog-path",
        type=Path,
        default=BACKLOG_UPDATE_PATH,
        help="Path to the Markdown backlog file (default: %(default)s)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated content to stdout without writing the file.",
    )
    p.add_argument(
        "--mark-complete",
        metavar="TASK_ID",
        default=None,
        help="After a successful sync, mark this task ID as 'complete' in the DB.",
    )
    p.add_argument(
        "--test-summary",
        default="",
        help="test_summary string required when using --mark-complete.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    sync(args.db_path, args.backlog_path, dry_run=args.dry_run)

    if args.mark_complete and not args.dry_run:
        update_task_status(
            args.db_path,
            args.mark_complete,
            "complete",
            args.test_summary,
        )
        log.info("Sovereign Verification Gate passed. Task %s is COMPLETE.", args.mark_complete)

    return 0


if __name__ == "__main__":
    sys.exit(main())

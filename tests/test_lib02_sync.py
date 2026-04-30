"""
tests/test_lib02_sync.py
========================
Functional and idempotency tests for sync_backlog.py (LIB-02).

Key guarantees verified:
  1. Marker assertion exits on missing / duplicate markers.
  2. Size-Guard rejects writes that shrink the file by >20%.
  3. Dry-run logs output but does NOT mutate the file.
  4. A full sync produces valid output containing known task IDs.
  5. IDEMPOTENCY: running sync twice on an already-synced file produces
     zero bytes of change (the core LIB-02 Verified-Completion invariant).
  6. update_task_status() enforces the Verified-Completion Gate.
"""

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.librarian.sync_backlog import (
    _assert_markers,
    _build_appendix_specs,
    _build_status_table,
    _inject_zone,
    _size_guard,
    sync,
    update_task_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_BACKLOG = """\
# Test Backlog

## Status Table

<!-- START_STATUS_TABLE -->
| ID | Old content |
|---|---|
| OLD-01 | stale |
<!-- END_STATUS_TABLE -->

## Appendix

<!-- START_APPENDIX_SPECS -->
| ID | Old specs |
|---|---|
| OLD-01 | stale specs |
<!-- END_APPENDIX_SPECS -->
"""


def _make_db(path: Path) -> None:
    """Create a minimal factory.db with sprints and tasks populated."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sprints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            goal TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            sprint_id INTEGER REFERENCES sprints(id),
            depends_on TEXT,
            assigned_to TEXT,
            domain TEXT,
            payload TEXT,
            is_sensitive BOOLEAN DEFAULT 0,
            required_tier TEXT DEFAULT 'cpu',
            status TEXT DEFAULT 'queued'
                CHECK(status IN (
                    'queued', 'pending', 'processing', 'processing_subagent',
                    'blocked', 'in_progress', 'awaiting_review',
                    'complete', 'completed', 'failed', 'pending_hitl'
                )),
            test_summary TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT OR IGNORE INTO sprints (name, goal, status) VALUES (?, ?, ?)",
        ("Wave 1 Foundation", "Harden DB schema.", "active"),
    )
    conn.commit()
    wave_id = conn.execute("SELECT id FROM sprints WHERE name='Wave 1 Foundation'").fetchone()[0]
    conn.executemany(
        "INSERT OR IGNORE INTO tasks (id, sprint_id, domain, payload, status) VALUES (?, ?, ?, ?, ?)",
        [
            ("BL-00",  wave_id, "DB",       "Epistemic backlog migration",   "complete"),
            ("LIB-02", wave_id, "Librarian","Implement sync_backlog utility", "in_progress"),
        ],
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def tmp_db(tmp_path) -> Path:
    db = tmp_path / "factory.db"
    _make_db(db)
    return db


@pytest.fixture()
def tmp_backlog(tmp_path) -> Path:
    f = tmp_path / "backlog.md"
    f.write_text(MINIMAL_BACKLOG, encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# 1. Marker assertion tests
# ---------------------------------------------------------------------------

def test_assert_markers_passes_on_valid_content():
    _assert_markers(MINIMAL_BACKLOG)  # must not raise or exit


def test_assert_markers_exits_on_missing_start(tmp_path):
    bad = MINIMAL_BACKLOG.replace("<!-- START_STATUS_TABLE -->", "")
    with pytest.raises(SystemExit) as exc:
        _assert_markers(bad)
    assert exc.value.code == 1


def test_assert_markers_exits_on_duplicate_end(tmp_path):
    bad = MINIMAL_BACKLOG + "\n<!-- END_APPENDIX_SPECS -->\n"
    with pytest.raises(SystemExit) as exc:
        _assert_markers(bad)
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# 2. Size-Guard tests
# ---------------------------------------------------------------------------

def test_size_guard_passes_on_similar_size():
    original = "x" * 1000
    updated = "x" * 900   # 10% reduction — allowed
    _size_guard(original, updated)  # must not exit


def test_size_guard_rejects_large_shrinkage():
    original = "x" * 1000
    updated = "x" * 750   # 25% reduction — rejected
    with pytest.raises(SystemExit) as exc:
        _size_guard(original, updated)
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# 3. Dry-run test
# ---------------------------------------------------------------------------

def test_dry_run_does_not_modify_file(tmp_db, tmp_backlog, capsys):
    original_content = tmp_backlog.read_text(encoding="utf-8")
    original_mtime = tmp_backlog.stat().st_mtime

    result = sync(tmp_db, tmp_backlog, dry_run=True)

    # File must be unchanged
    assert tmp_backlog.read_text(encoding="utf-8") == original_content
    assert tmp_backlog.stat().st_mtime == original_mtime

    # Output must contain known task ID
    captured = capsys.readouterr()
    assert "BL-00" in captured.out or "BL-00" in result


# ---------------------------------------------------------------------------
# 4. Full sync correctness
# ---------------------------------------------------------------------------

def test_sync_writes_task_ids(tmp_db, tmp_backlog):
    sync(tmp_db, tmp_backlog)
    result = tmp_backlog.read_text(encoding="utf-8")

    assert "BL-00" in result
    assert "LIB-02" in result
    # Markers preserved
    assert "<!-- START_STATUS_TABLE -->" in result
    assert "<!-- END_STATUS_TABLE -->" in result
    assert "<!-- START_APPENDIX_SPECS -->" in result
    assert "<!-- END_APPENDIX_SPECS -->" in result


def test_sync_replaces_stale_content(tmp_db, tmp_backlog):
    sync(tmp_db, tmp_backlog)
    result = tmp_backlog.read_text(encoding="utf-8")
    # Only the STATUS_TABLE zone is injected from DB; OLD-01 must be gone from it.
    start = result.index("<!-- START_STATUS_TABLE -->")
    end = result.index("<!-- END_STATUS_TABLE -->")
    status_zone = result[start:end]
    assert "OLD-01" not in status_zone, "Stale content survived in status table zone"


# ---------------------------------------------------------------------------
# 5. IDEMPOTENCY TEST (core LIB-02 invariant)
# ---------------------------------------------------------------------------

def test_idempotency_zero_byte_change(tmp_db, tmp_backlog):
    """Running sync twice must produce zero bytes of change."""
    sync(tmp_db, tmp_backlog)
    content_after_first = tmp_backlog.read_text(encoding="utf-8")

    sync(tmp_db, tmp_backlog)
    content_after_second = tmp_backlog.read_text(encoding="utf-8")

    assert content_after_first == content_after_second, (
        "Idempotency FAILED: second sync produced different output."
    )


# ---------------------------------------------------------------------------
# 6. Verified-Completion Gate
# ---------------------------------------------------------------------------

def test_update_task_status_requires_test_summary(tmp_db):
    with pytest.raises(ValueError, match="test_summary is required"):
        update_task_status(tmp_db, "LIB-02", "complete", "")


def test_update_task_status_succeeds_with_summary(tmp_db):
    update_task_status(tmp_db, "LIB-02", "complete", "Idempotency test passed.")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT status, test_summary FROM tasks WHERE id='LIB-02'").fetchone()
    conn.close()
    assert row[0] == "complete"
    assert "Idempotency" in row[1]


def test_update_task_status_raises_on_unknown_id(tmp_db):
    with pytest.raises(ValueError, match="not found"):
        update_task_status(tmp_db, "DOES-NOT-EXIST", "complete", "some summary")


if __name__ == "__main__":
    pytest.main(["-v", __file__])

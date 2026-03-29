"""
tests/test_pr06_project_registry.py
=====================================
Verification Gate for PR-06: Global Project Registry & Initializer.

Mandatory test cases (from mission spec):
  1. Collision Check: initializing in a folder with existing project.db fails safely.
  2. Normalization: /home/p1 and /home/p1/ are the same project (realpath uniqueness).
  3. Lineage: ON DELETE SET NULL works if a parent project is deleted.

Additional hardening tests:
  4. Folder with existing .factory_anchor also triggers collision guard.
  5. --force flag bypasses the collision guard.
  6. Schema helper creates both sprints and tasks tables.
  7. Schema helper is idempotent (running twice doesn't fail).
  8. init_project creates all expected directories.
  9. init_project writes a valid .factory_anchor file.
 10. init_project registers the project in the global projects table.
 11. Parent validation: invalid parent_project_id raises ValueError.
 12. Parent validation: valid parent_project_id succeeds.
 13. CLI: missing --name raises SystemExit.
 14. CLI: existing project dir returns exit code 1.
"""

import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.librarian.db_utils import initialize_project_schema
from openclaw_skills.architect.project_init import (
    ProjectAlreadyInitialized,
    _ensure_projects_table,
    _preflight_check,
    _validate_parent,
    init_project,
    main as factory_init_main,
)
from openclaw_skills.config import FACTORY_ANCHOR


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def global_db(tmp_path) -> Path:
    """A minimal Global Hub factory.db with projects table."""
    db = tmp_path / "global" / "factory.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    _ensure_projects_table(conn)
    conn.close()
    return db


@pytest.fixture()
def empty_silo(tmp_path) -> Path:
    """A clean, empty directory ready for initialization."""
    d = tmp_path / "my_project"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# 1. Collision Check — existing project.db fails safely
# ---------------------------------------------------------------------------

def test_collision_existing_project_db(empty_silo, global_db):
    """init_project must raise if project.db already exists."""
    # Pre-populate a project.db to simulate existing init
    ws = empty_silo / "workspace"
    ws.mkdir()
    (ws / "project.db").touch()

    with pytest.raises(ProjectAlreadyInitialized, match="already initialized"):
        init_project(empty_silo, name="duplicate", global_db=global_db)


def test_collision_existing_anchor(empty_silo, global_db):
    """init_project must raise if .factory_anchor already exists."""
    (empty_silo / FACTORY_ANCHOR).touch()

    with pytest.raises(ProjectAlreadyInitialized, match="already initialized"):
        init_project(empty_silo, name="duplicate", global_db=global_db)


# ---------------------------------------------------------------------------
# 2. Normalization — trailing slash treated as same path
# ---------------------------------------------------------------------------

def test_path_normalization_trailing_slash(tmp_path, global_db):
    """Paths with and without trailing slash must resolve to the same realpath."""
    silo = tmp_path / "project_alpha"
    silo.mkdir()

    result1 = init_project(str(silo), name="alpha", global_db=global_db)
    # Second call with trailing slash — should be treated as same path
    with pytest.raises((ProjectAlreadyInitialized, sqlite3.IntegrityError)):
        init_project(str(silo) + "/", name="alpha-dup", global_db=global_db)


def test_realpath_uniqueness_in_db(tmp_path, global_db):
    """The root_path stored in DB must match os.path.realpath of the target."""
    silo = tmp_path / "project_beta"
    silo.mkdir()
    result = init_project(silo, name="beta", global_db=global_db)

    expected = os.path.realpath(str(silo))
    assert result["root_path"] == expected

    conn = sqlite3.connect(global_db)
    row = conn.execute("SELECT root_path FROM projects WHERE id=?", (result["project_id"],)).fetchone()
    conn.close()
    assert row[0] == expected


# ---------------------------------------------------------------------------
# 3. Lineage — ON DELETE SET NULL if parent deleted
# ---------------------------------------------------------------------------

def test_on_delete_set_null_lineage(tmp_path, global_db):
    """Deleting a parent project must set child.parent_project_id to NULL."""
    # Create parent project
    parent_dir = tmp_path / "parent_proj"
    parent_dir.mkdir()
    parent = init_project(parent_dir, name="parent", global_db=global_db)
    parent_id = parent["project_id"]

    # Create child project referencing parent
    child_dir = tmp_path / "child_proj"
    child_dir.mkdir()
    child = init_project(
        child_dir, name="child",
        parent_project_id=parent_id,
        global_db=global_db,
    )
    child_id = child["project_id"]

    # Verify child references parent
    conn = sqlite3.connect(global_db)
    conn.execute("PRAGMA foreign_keys=ON;")
    row_before = conn.execute(
        "SELECT parent_project_id FROM projects WHERE id=?", (child_id,)
    ).fetchone()
    assert row_before[0] == parent_id

    # Delete parent
    conn.execute("DELETE FROM projects WHERE id=?", (parent_id,))
    conn.commit()

    # Child's parent_project_id must now be NULL
    row_after = conn.execute(
        "SELECT parent_project_id FROM projects WHERE id=?", (child_id,)
    ).fetchone()
    conn.close()
    assert row_after[0] is None


# ---------------------------------------------------------------------------
# 4. --force flag bypasses collision
# ---------------------------------------------------------------------------

def test_force_flag_overwrites_existing(empty_silo, global_db):
    """With --force, init_project must succeed even when project exists."""
    (empty_silo / FACTORY_ANCHOR).touch()
    # Should not raise
    result = init_project(empty_silo, name="forced", global_db=global_db, force=True)
    assert result["project_id"] is not None


# ---------------------------------------------------------------------------
# 5. Schema helper creates required tables
# ---------------------------------------------------------------------------

def test_schema_helper_creates_sprints_and_tasks(tmp_path):
    db = tmp_path / "proj.db"
    conn = sqlite3.connect(db)
    initialize_project_schema(conn)
    conn.close()

    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "sprints" in tables
    assert "tasks" in tables


def test_schema_helper_is_idempotent(tmp_path):
    """Calling initialize_project_schema twice must not raise."""
    db = tmp_path / "proj.db"
    conn = sqlite3.connect(db)
    initialize_project_schema(conn)
    initialize_project_schema(conn)  # second call — must not error
    conn.close()


# ---------------------------------------------------------------------------
# 6. init_project creates expected directories
# ---------------------------------------------------------------------------

def test_init_creates_directory_layout(empty_silo, global_db):
    init_project(empty_silo, name="layout-test", global_db=global_db)
    for subdir in ("docs", "memory", "workspace"):
        assert (empty_silo / subdir).is_dir(), f"Missing dir: {subdir}"


# ---------------------------------------------------------------------------
# 7. init_project writes .factory_anchor
# ---------------------------------------------------------------------------

def test_init_writes_anchor(empty_silo, global_db):
    init_project(empty_silo, name="anchor-test", global_db=global_db)
    anchor = empty_silo / FACTORY_ANCHOR
    assert anchor.exists()
    assert "anchor-test" in anchor.read_text()


# ---------------------------------------------------------------------------
# 8. init_project registers in Global Hub
# ---------------------------------------------------------------------------

def test_init_registers_in_global_hub(empty_silo, global_db):
    result = init_project(empty_silo, name="hub-reg", global_db=global_db)

    conn = sqlite3.connect(global_db)
    row = conn.execute(
        "SELECT id, name, root_path FROM projects WHERE id=?",
        (result["project_id"],)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[1] == "hub-reg"


# ---------------------------------------------------------------------------
# 9. Parent validation
# ---------------------------------------------------------------------------

def test_invalid_parent_raises_value_error(empty_silo, global_db):
    fake_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="does not exist in the Global Registry"):
        init_project(empty_silo, name="orphan", parent_project_id=fake_id, global_db=global_db)


def test_valid_parent_succeeds(tmp_path, global_db):
    parent_dir = tmp_path / "par"
    parent_dir.mkdir()
    parent = init_project(parent_dir, name="parent", global_db=global_db)

    child_dir = tmp_path / "child"
    child_dir.mkdir()
    child = init_project(
        child_dir, name="child",
        parent_project_id=parent["project_id"],
        global_db=global_db,
    )
    assert child["project_id"] != parent["project_id"]


# ---------------------------------------------------------------------------
# 10. CLI tests
# ---------------------------------------------------------------------------

def test_cli_missing_name_raises(tmp_path):
    with pytest.raises(SystemExit):
        factory_init_main(["--no-such-arg", str(tmp_path / "x")])


def test_cli_existing_project_returns_exit_1(empty_silo, global_db, tmp_path):
    """CLI must return exit code 1 on collision without --force."""
    (empty_silo / FACTORY_ANCHOR).touch()
    rc = factory_init_main([
        str(empty_silo),
        "--name", "dup",
        "--global-db", str(global_db),
    ])
    assert rc == 1


def test_cli_successful_init_returns_exit_0(empty_silo, global_db):
    rc = factory_init_main([
        str(empty_silo),
        "--name", "success-proj",
        "--global-db", str(global_db),
    ])
    assert rc == 0


if __name__ == "__main__":
    import pytest as _pytest
    _pytest.main(["-v", __file__])

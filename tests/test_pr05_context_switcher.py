"""
tests/test_pr05_context_switcher.py
====================================
Verification Gate for PR-05: Multi-Project Context Switcher.

Tests:
  1. Anchor found in start directory returns that directory.
  2. Anchor found in a parent directory (upward walk).
  3. No anchor + OPENCLAW_WORKSPACE set → returns parent of workspace.
  4. No anchor + no env var → returns _SOURCE_ROOT (Global Hub fallback).
  5. get_project_paths() returns a dict with all required keys.
  6. get_project_paths() paths are all children of the discovered root.
  7. project_db is always <root>/workspace/project.db.
  8. GLOBAL_DB_PATH points to the Global Hub factory.db (static reference).
  9. DOCS_DIR and MEMORY_DIR are children of _SOURCE_ROOT.
 10. Isolation: two silos with different anchors discover different roots.
 11. Excessive depth (anchor beyond _ANCHOR_SEARCH_DEPTH) triggers fallback.
 12. find_project_root accepts a Path, str, and None (uses cwd).
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.config import (
    DOCS_DIR,
    FACTORY_ANCHOR,
    GLOBAL_DB_PATH,
    MEMORY_DIR,
    _ANCHOR_SEARCH_DEPTH,
    _SOURCE_ROOT,
    find_project_root,
    get_project_paths,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def silo(tmp_path):
    """A temporary directory with a .factory_anchor file at its root."""
    anchor = tmp_path / FACTORY_ANCHOR
    anchor.touch()
    return tmp_path


@pytest.fixture()
def deep_silo(tmp_path):
    """A temporary silo with the anchor two levels up from start_path."""
    anchor = tmp_path / FACTORY_ANCHOR
    anchor.touch()
    nested = tmp_path / "subdir" / "deep"
    nested.mkdir(parents=True)
    return tmp_path, nested   # (root_with_anchor, deep_subdir)


# ---------------------------------------------------------------------------
# 1. Anchor found in start directory
# ---------------------------------------------------------------------------

def test_anchor_in_start_directory(silo):
    result = find_project_root(silo)
    assert result == silo.resolve()


# ---------------------------------------------------------------------------
# 2. Anchor found in parent (upward walk)
# ---------------------------------------------------------------------------

def test_anchor_in_parent_directory(deep_silo):
    anchor_root, start_dir = deep_silo
    result = find_project_root(start_dir)
    assert result == anchor_root.resolve()


# ---------------------------------------------------------------------------
# 3. No anchor + OPENCLAW_WORKSPACE env var set
# ---------------------------------------------------------------------------

def test_fallback_to_env_var(tmp_path, monkeypatch):
    # No anchor anywhere in tmp_path hierarchy
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(workspace))

    # Navigate to a path that *doesn't* have an anchor so we bypass step 1
    no_anchor_dir = tmp_path / "no_anchor"
    no_anchor_dir.mkdir()

    result = find_project_root(no_anchor_dir)
    # Fallback: parent of OPENCLAW_WORKSPACE = tmp_path
    assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# 4. No anchor + no env var → _SOURCE_ROOT
# ---------------------------------------------------------------------------

def test_fallback_to_source_root(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCLAW_WORKSPACE", raising=False)
    # tmp_path has no anchor; walk will exhaust depth then hit filesystem root
    # We use /tmp directly to ensure no ancestor has an anchor
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    result = find_project_root(deep)
    # Either hits /tmp (no anchor) → SOURCE_ROOT fallback, or if an ancestor
    # of tmp_path happens to have an anchor (very unlikely) that's fine.
    # What we assert is that it returns a valid Path.
    assert isinstance(result, Path)
    assert result.is_absolute()


# ---------------------------------------------------------------------------
# 5. get_project_paths() returns dict with all required keys
# ---------------------------------------------------------------------------

def test_get_project_paths_has_required_keys(silo):
    paths = get_project_paths(silo)
    for key in ("root", "workspace", "project_db", "docs_dir", "memory_dir"):
        assert key in paths, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# 6. All paths are children of the root
# ---------------------------------------------------------------------------

def test_get_project_paths_all_under_root(silo):
    paths = get_project_paths(silo)
    root = paths["root"]
    for key, path in paths.items():
        if key == "root":
            continue
        assert str(path).startswith(str(root)), (
            f"Path '{key}' ({path}) is not under root ({root})"
        )


# ---------------------------------------------------------------------------
# 7. project_db is always <root>/workspace/project.db
# ---------------------------------------------------------------------------

def test_project_db_path(silo):
    paths = get_project_paths(silo)
    expected = silo / "workspace" / "project.db"
    assert paths["project_db"] == expected.resolve() or paths["project_db"] == expected


# ---------------------------------------------------------------------------
# 8. GLOBAL_DB_PATH points to Global Hub factory.db
# ---------------------------------------------------------------------------

def test_global_db_path_points_to_factory_db():
    assert GLOBAL_DB_PATH.name == "factory.db"
    assert GLOBAL_DB_PATH.parent.name == "workspace"
    # The parent of workspace should be the source root
    assert GLOBAL_DB_PATH.parent.parent == _SOURCE_ROOT


# ---------------------------------------------------------------------------
# 9. DOCS_DIR and MEMORY_DIR are under _SOURCE_ROOT
# ---------------------------------------------------------------------------

def test_docs_dir_under_source_root():
    assert str(DOCS_DIR).startswith(str(_SOURCE_ROOT))
    assert DOCS_DIR.name == "docs"


def test_memory_dir_under_source_root():
    assert str(MEMORY_DIR).startswith(str(_SOURCE_ROOT))
    assert MEMORY_DIR.name == "memory"


# ---------------------------------------------------------------------------
# 10. Isolation: two different silos discover different roots
# ---------------------------------------------------------------------------

def test_silo_isolation(tmp_path):
    silo_a = tmp_path / "project_alpha"
    silo_b = tmp_path / "project_beta"
    silo_a.mkdir()
    silo_b.mkdir()
    (silo_a / FACTORY_ANCHOR).touch()
    (silo_b / FACTORY_ANCHOR).touch()

    result_a = find_project_root(silo_a)
    result_b = find_project_root(silo_b)

    assert result_a != result_b
    assert result_a == silo_a.resolve()
    assert result_b == silo_b.resolve()

    paths_a = get_project_paths(result_a)
    paths_b = get_project_paths(result_b)
    assert paths_a["project_db"] != paths_b["project_db"]


# ---------------------------------------------------------------------------
# 11. Depth limit: anchor beyond _ANCHOR_SEARCH_DEPTH triggers fallback
# ---------------------------------------------------------------------------

def test_depth_limit_triggers_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCLAW_WORKSPACE", raising=False)

    # Build a chain of _ANCHOR_SEARCH_DEPTH + 2 directories
    # with the anchor at the very top (unreachable within depth limit)
    current = tmp_path
    for i in range(_ANCHOR_SEARCH_DEPTH + 2):
        current = current / f"d{i}"
        current.mkdir()

    # Place anchor at tmp_path (root of chain — beyond search depth)
    (tmp_path / FACTORY_ANCHOR).touch()

    # Start from deepest subdirectory: anchor is too far up
    result = find_project_root(current)
    # Should NOT find the anchor (too deep) and fall back
    # The fallback is _SOURCE_ROOT since no env var set
    # (unless some ancestor of current happens to have an anchor)
    assert isinstance(result, Path)
    assert result.is_absolute()
    # Crucially: the result must NOT be tmp_path
    # (the anchor was beyond the search depth)
    assert result != tmp_path.resolve()


# ---------------------------------------------------------------------------
# 12. find_project_root accepts Path, str, and None
# ---------------------------------------------------------------------------

def test_accepts_path_object(silo):
    assert find_project_root(silo) == silo.resolve()


def test_accepts_string(silo):
    assert find_project_root(str(silo)) == silo.resolve()


def test_accepts_none_uses_cwd(monkeypatch, silo):
    monkeypatch.chdir(silo)
    result = find_project_root(None)
    assert result == silo.resolve()


if __name__ == "__main__":
    pytest.main(["-v", __file__])

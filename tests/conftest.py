"""
conftest.py — Shared pytest fixtures for OpenClaw test suite.

All fixtures use temporary directories — no test ever touches the real
OPENCLAW_WORKSPACE or live factory.db.
"""
import os
import sys
import sqlite3
import pytest
from pathlib import Path

# Ensure openclaw_skills is importable from tests/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "openclaw_skills"))          # router, kb, config, obsidian_bridge
sys.path.insert(0, str(ROOT / "openclaw_skills" / "librarian"))  # self_healing, safety_engine
sys.path.insert(0, str(ROOT / "openclaw_skills" / "architect"))  # architect_tools


def _patch_workspace_on_module(mod, ws: Path, monkeypatch):
    """
    Patch WORKSPACE_ROOT (and TOKEN_FILE if present) on an already-imported module.
    This is necessary because the module binds these at import time from config.
    """
    if hasattr(mod, "WORKSPACE_ROOT"):
        monkeypatch.setattr(mod, "WORKSPACE_ROOT", ws)
    if hasattr(mod, "TOKEN_FILE"):
        monkeypatch.setattr(mod, "TOKEN_FILE", ws / ".hitl_token")


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch):
    """
    Core isolation fixture — runs for EVERY test automatically.

    1. Creates a fresh temp workspace directory.
    2. Sets OPENCLAW_WORKSPACE env var.
    3. Patches WORKSPACE_ROOT and TOKEN_FILE on config, librarian_ctl,
       architect_tools (and any other already-loaded openclaw module)
       so that validate_path uses the tmp workspace for the duration of the test.
    """
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(ws))

    # Patch config first
    import openclaw_skills.config as cfg
    monkeypatch.setattr(cfg, "WORKSPACE_ROOT", ws)
    monkeypatch.setattr(cfg, "TOKEN_FILE", ws / ".hitl_token")
    monkeypatch.setattr(cfg, "DEFAULT_DB_PATH", ws / "factory.db")
    monkeypatch.setattr(cfg, "DEFAULT_REGISTRY_PATH", ws / "REGISTRY.md")

    # Patch librarian_ctl (imports WORKSPACE_ROOT at module level)
    try:
        import librarian_ctl as lctl
        _patch_workspace_on_module(lctl, ws, monkeypatch)
    except ImportError:
        pass

    # Patch architect_tools (same pattern)
    try:
        import architect_tools as at
        _patch_workspace_on_module(at, ws, monkeypatch)
    except ImportError:
        pass

    # Patch router (imports WORKSPACE_ROOT at module level)
    try:
        import router
        _patch_workspace_on_module(router, ws, monkeypatch)
    except ImportError:
        pass

    # Patch kb (imports WORKSPACE_ROOT at module level)
    try:
        import kb
        _patch_workspace_on_module(kb, ws, monkeypatch)
    except ImportError:
        pass

    # Patch obsidian_bridge module-level constants so tests can construct ObsidianBridge
    # without needing a live Obsidian instance or real env vars
    try:
        import obsidian_bridge as ob
        monkeypatch.setattr(ob, "OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")
        monkeypatch.setattr(ob, "OBSIDIAN_API_KEY", "test-api-key")
    except ImportError:
        pass

    yield ws


@pytest.fixture
def tmp_db(isolated_workspace):
    """
    Provides a fully initialised + migrated factory.db inside the temp workspace.
    init_db → bootstrap_factory → (init_vector_db if sqlite-vec available) → migrate_database
    Returns the db_path string.
    """
    db_path = str(isolated_workspace / "factory.db")

    import librarian_ctl as lctl
    import migrate_db as mdb

    lctl.init_db(db_path)
    lctl.bootstrap_factory(db_path)

    # Initialise vector tables if sqlite-vec is available (needed for archive_log tests)
    try:
        from vector_archive import init_vector_db
        init_vector_db(db_path)
    except (ImportError, Exception):
        pass  # sqlite-vec not installed — vector tests will skip or mock

    mdb.migrate_database(db_path)

    return db_path

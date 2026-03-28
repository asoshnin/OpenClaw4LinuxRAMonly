"""
tests/test_register_agent.py

Unit tests for register_agent() and the 'register-agent' CLI subcommand.

Coverage:
  - New agent registration (INSERT)
  - Duplicate without --force → ValueError (exit 2)
  - Duplicate with --force → UPDATE succeeds, version changed
  - System agent (is_system=1) absolute protection — PermissionError even with force=True
  - Audit log: AGENT_REGISTERED vs AGENT_UPDATED
  - Airlock: PermissionError for db_path outside workspace

All tests use a temporary in-memory/tmp DB; never touch factory.db.
"""

import os
import sys
import sqlite3
import tempfile
import pytest

# ---------------------------------------------------------------------------
# Path setup — ensure librarian_ctl is importable without installing
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIBRARIAN = os.path.join(_REPO_ROOT, "openclaw_skills", "librarian")
sys.path.insert(0, _LIBRARIAN)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "openclaw_skills"))


# ---------------------------------------------------------------------------
# Fixture: isolated temp workspace + pre-initialised DB
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    """
    Creates a temp workspace dir, patches WORKSPACE_ROOT in librarian_ctl
    and config so validate_path() accepts paths within tmp_path, then
    initialises a minimal DB schema (agents + audit_logs + is_system column).
    Returns the db_path string.
    """
    import config as cfg
    monkeypatch.setattr(cfg, "WORKSPACE_ROOT", tmp_path)

    # Re-import librarian_ctl after patching WORKSPACE_ROOT
    import importlib
    import librarian_ctl as lc
    monkeypatch.setattr(lc, "WORKSPACE_ROOT", tmp_path)

    db_path = str(tmp_path / "factory.db")

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                persona_hash TEXT,
                state_blob JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_system INTEGER DEFAULT 0,
                description TEXT,
                tool_names TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                pipeline_id TEXT,
                action TEXT,
                rationale TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Insert a system-protected agent
        conn.execute(
            "INSERT INTO agents (agent_id, name, is_system) VALUES (?, ?, ?)",
            ("sys-core-01", "System Core", 1),
        )
        conn.commit()

    return db_path


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_agent(db_path, agent_id):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT agent_id, name, version, description, tool_names "
            "FROM agents WHERE agent_id = ?",
            (agent_id,),
        ).fetchone()


def _get_audit_actions(db_path, agent_id):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT action FROM audit_logs WHERE agent_id = ? ORDER BY log_id",
            (agent_id,),
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegisterAgent:

    def test_register_new_agent_inserts_row(self, tmp_db):
        """New agent → row present in DB with correct values."""
        import librarian_ctl as lc
        lc.register_agent(
            db_path=tmp_db,
            agent_id="test-analyst-01",
            name="Test Analyst",
            version="1.5",
            description="Reads reports",
            tool_names="vault-route,vault-validate",
        )
        row = _get_agent(tmp_db, "test-analyst-01")
        assert row is not None
        assert row[1] == "Test Analyst"
        assert row[2] == "1.5"
        assert row[3] == "Reads reports"
        assert row[4] == "vault-route,vault-validate"

    def test_register_new_agent_writes_audit_log(self, tmp_db):
        """New agent → audit_logs contains AGENT_REGISTERED."""
        import librarian_ctl as lc
        lc.register_agent(tmp_db, "audit-check-01", "Audit Checker")
        actions = _get_audit_actions(tmp_db, "audit-check-01")
        assert "AGENT_REGISTERED" in actions

    def test_register_duplicate_without_force_raises_value_error(self, tmp_db):
        """Duplicate agent_id without force → ValueError (caller maps to exit 2)."""
        import librarian_ctl as lc
        lc.register_agent(tmp_db, "dup-agent-01", "Dup Agent")
        with pytest.raises(ValueError, match="already exists"):
            lc.register_agent(tmp_db, "dup-agent-01", "Dup Agent Again")

    def test_register_duplicate_with_force_updates_version(self, tmp_db):
        """Duplicate agent_id with force=True → UPDATE succeeds, version changed."""
        import librarian_ctl as lc
        lc.register_agent(tmp_db, "update-agent-01", "Update Agent", version="1.0")
        lc.register_agent(tmp_db, "update-agent-01", "Update Agent v2", version="2.0", force=True)
        row = _get_agent(tmp_db, "update-agent-01")
        assert row[1] == "Update Agent v2"
        assert row[2] == "2.0"

    def test_force_cannot_modify_system_agent_raises_permission_error(self, tmp_db):
        """System agent (is_system=1) → PermissionError even with force=True."""
        import librarian_ctl as lc
        with pytest.raises(PermissionError, match="system-protected"):
            lc.register_agent(tmp_db, "sys-core-01", "Hijacked System", force=True)

    def test_force_false_also_cannot_modify_system_agent(self, tmp_db):
        """System agent → PermissionError even without force (system check is prior to existence check)."""
        import librarian_ctl as lc
        with pytest.raises(PermissionError, match="system-protected"):
            lc.register_agent(tmp_db, "sys-core-01", "Attempt Without Force", force=False)

    def test_audit_log_action_registered_vs_updated(self, tmp_db):
        """Audit log contains AGENT_REGISTERED on first insert, AGENT_UPDATED on force overwrite."""
        import librarian_ctl as lc
        lc.register_agent(tmp_db, "audit-action-01", "Audit Action Agent", version="1.0")
        lc.register_agent(tmp_db, "audit-action-01", "Audit Action Agent", version="2.0", force=True)
        actions = _get_audit_actions(tmp_db, "audit-action-01")
        assert actions[0] == "AGENT_REGISTERED"
        assert actions[1] == "AGENT_UPDATED"

    def test_airlock_rejects_db_path_outside_workspace(self, tmp_path, monkeypatch):
        """db_path outside WORKSPACE_ROOT → PermissionError (Airlock breach)."""
        import config as cfg
        # Create a dedicated workspace sub-dir so the sibling path is outside it
        workspace = tmp_path / "ws_inner"
        workspace.mkdir(exist_ok=True)
        monkeypatch.setattr(cfg, "WORKSPACE_ROOT", workspace)

        import librarian_ctl as lc
        monkeypatch.setattr(lc, "WORKSPACE_ROOT", workspace)

        bad_db = str(tmp_path / "outside.db")  # sibling of workspace — outside
        with pytest.raises(PermissionError, match="Airlock"):
            lc.register_agent(bad_db, "any-agent", "Any Name")

    def test_empty_agent_id_raises_value_error(self, tmp_db):
        """Empty agent_id → ValueError before any DB operation."""
        import librarian_ctl as lc
        with pytest.raises(ValueError, match="agent_id must not be empty"):
            lc.register_agent(tmp_db, "", "Some Name")

    def test_empty_name_raises_value_error(self, tmp_db):
        """Empty name → ValueError before any DB operation."""
        import librarian_ctl as lc
        with pytest.raises(ValueError, match="name must not be empty"):
            lc.register_agent(tmp_db, "valid-id-01", "")

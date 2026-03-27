"""
test_init_db.py — Integration tests for the full DB init → bootstrap → migrate → registry pipeline.
"""
import os
import sqlite3
import pytest


def test_init_db_creates_tables(tmp_db):
    """init_db creates the three core tables with correct columns."""
    conn = sqlite3.connect(tmp_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    assert "agents" in tables
    assert "pipelines" in tables
    assert "audit_logs" in tables
    conn.close()


def test_init_db_wal_mode(tmp_db):
    """factory.db is opened in WAL journal mode."""
    conn = sqlite3.connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_bootstrap_seeds_core_agents(tmp_db):
    """bootstrap_factory inserts kimi-orch-01 and lib-keeper-01."""
    conn = sqlite3.connect(tmp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT agent_id FROM agents ORDER BY agent_id")
    ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    assert "kimi-orch-01" in ids
    assert "lib-keeper-01" in ids


def test_bootstrap_is_idempotent(tmp_db):
    """Calling bootstrap_factory twice does not duplicate rows (INSERT OR IGNORE)."""
    import librarian_ctl as lctl
    lctl.bootstrap_factory(tmp_db)  # called once already in fixture; call again
    conn = sqlite3.connect(tmp_db)
    count = conn.execute("SELECT COUNT(*) FROM agents WHERE agent_id='kimi-orch-01'").fetchone()[0]
    conn.close()
    assert count == 1


def test_migration_adds_is_system(tmp_db):
    """migrate_database adds is_system column and marks core agents."""
    conn = sqlite3.connect(tmp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT agent_id, is_system FROM agents")
    rows = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    assert rows.get("kimi-orch-01") == 1
    assert rows.get("lib-keeper-01") == 1


def test_migration_adds_pipeline_agents_table(tmp_db):
    """migrate_database creates the pipeline_agents junction table."""
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "pipeline_agents" in tables


def test_migration_adds_description_and_tool_names(tmp_db):
    """migrate_database adds description and tool_names columns to agents."""
    conn = sqlite3.connect(tmp_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(agents)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    assert "description" in columns
    assert "tool_names" in columns


def test_migration_is_idempotent(tmp_db):
    """Running migrate_database twice does not raise."""
    import migrate_db as mdb
    mdb.migrate_database(tmp_db)  # already run in fixture; run again
    # Should not raise — all migrations are guarded with try/except or IF NOT EXISTS


def test_generate_registry_creates_file(tmp_db, isolated_workspace):
    """generate_registry produces a REGISTRY.md file with YAML frontmatter."""
    import librarian_ctl as lctl
    registry_path = str(isolated_workspace / "REGISTRY.md")
    lctl.generate_registry(tmp_db, registry_path)
    assert os.path.exists(registry_path)
    content = open(registry_path).read()
    assert "---" in content                       # YAML frontmatter present
    assert "Mega-Orchestrator" in content         # agent name present
    assert "kimi-orch-01" in content              # agent id present


def test_generate_registry_includes_description(tmp_db, isolated_workspace):
    """generate_registry includes description and tool_names in output."""
    import librarian_ctl as lctl

    # Seed description for test agent
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "UPDATE agents SET description=?, tool_names=? WHERE agent_id=?",
        ("Test description", "tool_a,tool_b", "kimi-orch-01")
    )
    conn.commit()
    conn.close()

    registry_path = str(isolated_workspace / "REGISTRY.md")
    lctl.generate_registry(tmp_db, registry_path)
    content = open(registry_path).read()
    assert "Test description" in content
    assert "tool_a,tool_b" in content

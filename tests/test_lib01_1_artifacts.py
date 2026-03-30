"""
Tests for LIB-01.1: artifacts table migration, scanner, readonly guard, and registry output.

Coverage:
  - Migration idempotency (safe to re-run)
  - Factory artifact scan (skips symlinks, captures .py/.md/.json)
  - OpenClaw native artifact scan (is_readonly=1, prefixed with 'openclaw::')
  - Namespace collision prevention (unique names via prefix)
  - Readonly guard (assert_artifact_writable blocks is_readonly=1)
  - Registry generation (two sections present and non-empty as expected)
  - Dry-run mode produces no DB mutations
"""

import os
import json
import sqlite3
import tempfile
import shutil
import pytest

# Path bootstrap
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "openclaw_skills"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "openclaw_skills", "librarian"))

from migrate_lib01_1 import run_migration
from sync_openclaw_artifacts import sync_artifacts, _scan_directory
from librarian_ctl import assert_artifact_writable, generate_registry, validate_path


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_workspace(tmp_path, monkeypatch):
    """Isolated temporary workspace with a minimal factory.db."""
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    db_path = str(ws / "factory.db")

    # Minimal DB with WAL + agents/pipelines + apply LIB-01.1 migration
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                description TEXT DEFAULT '',
                tool_names TEXT DEFAULT '',
                is_system BOOLEAN DEFAULT 0
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipelines (
                pipeline_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT
            );
        """)
        conn.execute("INSERT INTO agents (agent_id, name) VALUES ('test-agent-01', 'Test Agent');")
        conn.execute("INSERT INTO pipelines (pipeline_id, name, status) VALUES ('pipe-01', 'Test Pipeline', 'active');")
        conn.commit()

    run_migration(db_path)

    # Patch WORKSPACE_ROOT so Airlock accepts our tmp ws
    import config
    monkeypatch.setattr(config, "WORKSPACE_ROOT", ws)

    return {"ws": str(ws), "db": db_path, "tmp": tmp_path}


@pytest.fixture()
def fake_factory_dir(tmp_path):
    """A fake openclaw_skills-like directory for scanning."""
    d = tmp_path / "factory_skills"
    d.mkdir()
    
    # Must match: SKILL.md, *.plugin.json, package.json with openclaw
    r = d / "router"
    r.mkdir()
    (r / "SKILL.md").write_text("# router\ndescription: core router")
    
    c = d / "config"
    c.mkdir()
    (c / "package.json").write_text('{"openclaw": {"description": "config block"}}')

    sub = d / "librarian"
    sub.mkdir()
    (sub / "librarian.plugin.json").write_text('{"description": "migrate"}')
    (sub / "notes.md").write_text("# notes") # will be ignored

    # Symlink — must be skipped
    link = d / "evil_link.plugin.json"
    link.symlink_to(sub / "librarian.plugin.json")
    return str(d)


@pytest.fixture()
def fake_native_dir(tmp_path):
    """A fake OpenClaw native workspace for scanning."""
    d = tmp_path / "native"
    d.mkdir()
    skills = d / "skills"
    skills.mkdir()
    
    (skills / "weather.plugin.json").write_text('{"description": "weather"}')
    (skills / "healthcheck.md").write_text("# healthcheck") # ignored
    
    h = skills / "health"
    h.mkdir()
    (h / "SKILL.md").write_text("# health check")

    # Symlink inside native — must be skipped
    link = skills / "loop_link.plugin.json"
    link.symlink_to(skills / "weather.plugin.json")
    return str(skills)


# ── Migration Tests ───────────────────────────────────────────────────────────

class TestMigrationLIB011:

    def test_migration_creates_artifacts_table(self, tmp_workspace):
        db = tmp_workspace["db"]
        with sqlite3.connect(db) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        assert "artifacts" in tables

    def test_migration_columns_present(self, tmp_workspace):
        db = tmp_workspace["db"]
        with sqlite3.connect(db) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(artifacts)").fetchall()}
        assert "source" in cols
        assert "is_readonly" in cols

    def test_migration_is_idempotent(self, tmp_workspace):
        """Running twice must not raise or duplicate anything."""
        db = tmp_workspace["db"]
        run_migration(db)   # second run
        run_migration(db)   # third run
        with sqlite3.connect(db) as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(artifacts)").fetchall()]
        # source and is_readonly should appear exactly once
        assert cols.count("source") == 1
        assert cols.count("is_readonly") == 1

    def test_migration_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_migration(str(tmp_path / "nonexistent.db"))


# ── Scanner Tests ─────────────────────────────────────────────────────────────

class TestScanDirectory:

    def test_factory_scan_finds_semantic_manifests(self, fake_factory_dir):
        results = _scan_directory(fake_factory_dir, name_prefix="", source="agentic_factory")
        names = {r["name"] for r in results}
        assert "router" in names
        assert "config" in names
        assert "librarian" in names
        assert "notes" not in names

    def test_factory_scan_skips_symlinks(self, fake_factory_dir):
        results = _scan_directory(fake_factory_dir, name_prefix="", source="agentic_factory")
        names = {r["name"] for r in results}
        # evil_link.py is a symlink — must NOT appear
        assert "evil_link" not in names

    def test_factory_scan_source_and_readonly(self, fake_factory_dir):
        results = _scan_directory(fake_factory_dir, source="agentic_factory", is_readonly=0)
        for r in results:
            assert r["source"] == "agentic_factory"
            assert r["is_readonly"] == 0

    def test_native_scan_applies_prefix_and_readonly(self, fake_native_dir):
        results = _scan_directory(
            fake_native_dir, name_prefix="openclaw::",
            source="openclaw_native", is_readonly=1
        )
        names = {r["name"] for r in results}
        assert "openclaw::weather" in names
        assert "openclaw::health" in names
        assert "openclaw::healthcheck" not in names

    def test_native_scan_skips_symlinks(self, fake_native_dir):
        results = _scan_directory(fake_native_dir, name_prefix="openclaw::")
        names = {r["name"] for r in results}
        assert "openclaw::loop_link" not in names

    def test_scan_nonexistent_dir_returns_empty(self, tmp_path):
        results = _scan_directory(str(tmp_path / "nope"))
        assert results == []

    def test_scan_symlink_root_returns_empty(self, tmp_path, fake_factory_dir):
        """A symlink passed as root must be skipped entirely."""
        link = tmp_path / "factory_link"
        link.symlink_to(fake_factory_dir)
        results = _scan_directory(str(link))
        assert results == []


# ── Namespace Collision Tests ─────────────────────────────────────────────────

class TestNamespaceCollision:

    def test_openclaw_prefix_prevents_clash(self, tmp_workspace, fake_factory_dir, fake_native_dir):
        """A factory artifact 'weather' and native 'openclaw::weather' must coexist as distinct rows."""
        db = tmp_workspace["db"]
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) VALUES ('weather', 'agentic_factory', 0)"
            )
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) VALUES ('openclaw::weather', 'openclaw_native', 1)"
            )
            conn.commit()
            rows = conn.execute("SELECT name FROM artifacts").fetchall()
        names = {r[0] for r in rows}
        assert "weather" in names
        assert "openclaw::weather" in names


# ── Readonly Guard Tests ──────────────────────────────────────────────────────

class TestReadonlyGuard:

    def test_writable_artifact_passes(self, tmp_workspace):
        db = tmp_workspace["db"]
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) VALUES ('my-tool', 'agentic_factory', 0)"
            )
            conn.commit()
        # Must not raise
        assert_artifact_writable(db, "my-tool")

    def test_readonly_artifact_raises_permission_error(self, tmp_workspace):
        db = tmp_workspace["db"]
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) VALUES "
                "('openclaw::weather', 'openclaw_native', 1)"
            )
            conn.commit()
        with pytest.raises(PermissionError, match="is_readonly=1"):
            assert_artifact_writable(db, "openclaw::weather")

    def test_nonexistent_artifact_passes(self, tmp_workspace):
        """An artifact not in the DB should not block (can be created)."""
        db = tmp_workspace["db"]
        assert_artifact_writable(db, "does-not-exist")


# ── Registry Generation Tests ─────────────────────────────────────────────────

class TestRegistryGeneration:

    def test_registry_has_two_artifact_sections(self, tmp_workspace):
        db = tmp_workspace["db"]
        ws = tmp_workspace["ws"]
        out = os.path.join(ws, "REGISTRY.md")

        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) "
                "VALUES ('my_skill', 'agentic_factory', 0)"
            )
            conn.execute(
                "INSERT INTO artifacts (name, source, is_readonly) "
                "VALUES ('openclaw::healthcheck', 'openclaw_native', 1)"
            )
            conn.commit()

        generate_registry(db, out)
        content = open(out).read()

        assert "## Factory Managed Artifacts" in content
        assert "## OpenClaw Native Artifacts (Read-Only)" in content

    def test_registry_factory_section_lists_artifact(self, tmp_workspace):
        db = tmp_workspace["db"]
        ws = tmp_workspace["ws"]
        out = os.path.join(ws, "REGISTRY.md")

        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, artifact_type, source, is_readonly) "
                "VALUES ('router', 'py', 'agentic_factory', 0)"
            )
            conn.commit()

        generate_registry(db, out)
        content = open(out).read()
        assert "router" in content

    def test_registry_native_section_lists_native(self, tmp_workspace):
        db = tmp_workspace["db"]
        ws = tmp_workspace["ws"]
        out = os.path.join(ws, "REGISTRY.md")

        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO artifacts (name, artifact_type, source, is_readonly) "
                "VALUES ('openclaw::weather', 'json', 'openclaw_native', 1)"
            )
            conn.commit()

        generate_registry(db, out)
        content = open(out).read()
        assert "openclaw::weather" in content
        # Warning note must appear
        assert "⚠️" in content or "warning" in content.lower() or "Read-Only" in content

    def test_registry_empty_sections_show_placeholder(self, tmp_workspace):
        db = tmp_workspace["db"]
        ws = tmp_workspace["ws"]
        out = os.path.join(ws, "REGISTRY.md")
        generate_registry(db, out)
        content = open(out).read()
        assert "No factory-managed artifacts indexed yet" in content
        assert "No OpenClaw native artifacts indexed yet" in content

    def test_registry_write_is_atomic(self, tmp_workspace):
        """tmp file must not remain after a successful write."""
        db = tmp_workspace["db"]
        ws = tmp_workspace["ws"]
        out = os.path.join(ws, "REGISTRY.md")
        generate_registry(db, out)
        assert not os.path.exists(out + ".tmp")
        assert os.path.exists(out)


# ── Dry-Run Mode Tests ────────────────────────────────────────────────────────

class TestDryRun:

    def test_dry_run_does_not_modify_db(self, tmp_workspace, fake_factory_dir):
        """Dry-run must not insert any rows. Tests by calling _upsert_artifacts directly."""
        db = tmp_workspace["db"]
        # Get artifacts from our controlled fake dir
        artifacts = _scan_directory(fake_factory_dir, source="agentic_factory", is_readonly=0)
        assert len(artifacts) > 0, "Fixture must produce at least one artifact"

        import sync_openclaw_artifacts as soa
        with __import__("sqlite3").connect(db) as conn:
            soa._upsert_artifacts(conn, artifacts, dry_run=True)
            # DRY RUN → no commit should have happened, so count should be 0
            count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        assert count == 0, "Dry-run must not insert any rows"

    def test_dry_run_returns_summary(self, tmp_workspace, fake_factory_dir, fake_native_dir, monkeypatch):
        """sync_artifacts with dry_run=True must return a summary dict without writing."""
        db = tmp_workspace["db"]

        import sync_openclaw_artifacts as soa

        # Override discovery: only scan our known controlled directories
        def _mock_native_paths():
            return [fake_native_dir]

        monkeypatch.setattr(soa, "_resolve_native_openclaw_paths", _mock_native_paths)
        monkeypatch.setattr(soa, "_SKILLS_ROOT", fake_factory_dir)
        monkeypatch.setattr(soa, "_PROJECT_ROOT", os.path.dirname(fake_factory_dir))

        summary = soa.sync_artifacts(db, dry_run=True)
        assert "factory_inserted" in summary
        assert "native_inserted" in summary
        # Nothing should be written
        with __import__("sqlite3").connect(db) as conn:
            count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        assert count == 0

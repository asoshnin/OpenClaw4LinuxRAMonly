"""
test_vault_health_check.py — Sprint 9 test suite for vault_health_check.

All ObsidianBridge HTTP calls are mocked — no live Obsidian instance required.
"""

import json
import os
import sys
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "openclaw_skills"))
sys.path.insert(0, str(ROOT / "openclaw_skills" / "vault_tools"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bridge(
    ping=True,
    notes=None,
    note_content=None,
    read_side_effect=None,
):
    """Build a mock ObsidianBridge."""
    bridge = MagicMock()
    bridge.ping.return_value = ping
    bridge.list_notes.return_value = notes or []
    if read_side_effect is not None:
        bridge.read_note.side_effect = read_side_effect
    elif note_content is not None:
        bridge.read_note.return_value = note_content
    return bridge


_VALID_CONTENT = (
    "---\n"
    'id: "23.01-202603271200"\n'
    "type: note\n"
    "status: active\n"
    'summary: "A valid test note."\n'
    "keywords: [test]\n"
    "tags: [openclaw]\n"
    'domain: "ai"\n'
    "---\n"
    "# Content\n\nBody.\n"
)

_INVALID_CONTENT = "# No frontmatter\n\nJust text.\n"


# ===========================================================================
# run_vault_health_check() tests
# ===========================================================================

class TestRunVaultHealthCheck:

    def test_all_notes_valid_returns_empty_errors_and_warnings(self, tmp_path, monkeypatch):
        """When all notes are valid, errors and warnings should be empty."""
        from vault_health_check import run_vault_health_check

        notes = ["20 - AREAS/23 - AI/Note.md", "30 - RESOURCES/Guide.md"]
        mock_bridge = _make_bridge(
            ping=True,
            notes=notes,
            note_content=_VALID_CONTENT,
        )

        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        assert result["errors"] == []
        assert result["warnings"] == []
        assert len(result["passed"]) == 2

    def test_note_with_missing_yaml_appears_in_errors(self, tmp_path, monkeypatch):
        """A note without YAML frontmatter appears in errors."""
        from vault_health_check import run_vault_health_check

        def _side_effect(path):
            if path == "broken.md":
                return _INVALID_CONTENT
            return _VALID_CONTENT

        mock_bridge = _make_bridge(
            ping=True,
            notes=["20 - AREAS/23 - AI/Note.md", "broken.md"],
            read_side_effect=_side_effect,
        )

        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        error_paths = [e["path"] for e in result["errors"]]
        assert "broken.md" in error_paths
        # valid note should be in passed
        passed_paths = [p["path"] for p in result["passed"]]
        assert "20 - AREAS/23 - AI/Note.md" in passed_paths

    def test_archived_note_appears_in_skipped(self, tmp_path):
        """Notes in 40 - ARCHIVE/ are excluded from scanning."""
        from vault_health_check import run_vault_health_check

        notes = ["40 - ARCHIVE/Old_Note.md", "20 - AREAS/23 - AI/Active.md"]
        mock_bridge = _make_bridge(ping=True, notes=notes, note_content=_VALID_CONTENT)

        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        skipped_paths = [s["path"] for s in result["skipped"]]
        assert "40 - ARCHIVE/Old_Note.md" in skipped_paths
        # Archived note should NOT appear in errors or passed
        all_scanned = (
            [p["path"] for p in result["passed"]]
            + [e["path"] for e in result["errors"]]
            + [w["path"] for w in result["warnings"]]
        )
        assert "40 - ARCHIVE/Old_Note.md" not in all_scanned

    def test_obsidian_not_running_raises_runtime_error(self, tmp_path):
        """If Obsidian is not running, RuntimeError is raised."""
        from vault_health_check import run_vault_health_check

        mock_bridge = _make_bridge(ping=False)
        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            with pytest.raises(RuntimeError, match="Obsidian is not running"):
                run_vault_health_check(str(tmp_path))

    def test_duplicate_jd_prefix_classified_as_error(self, tmp_path):
        """Duplicate NN- prefix in 20 - AREAS/ → classified as ERROR per Navigator directive."""
        from vault_health_check import run_vault_health_check

        # Create duplicate prefix folders in a real temp vault structure
        areas = tmp_path / "20 - AREAS"
        areas.mkdir()
        (areas / "26 - Politics").mkdir()
        (areas / "26 - POLITICS").mkdir()

        # No notes to scan
        mock_bridge = _make_bridge(ping=True, notes=[])
        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        assert len(result["errors"]) >= 1
        error_issues = " ".join(
            " ".join(e["issues"]) for e in result["errors"]
        )
        assert "26" in error_issues
        assert "duplicate" in error_issues.lower() or "Duplicate" in error_issues

    def test_oversized_note_appears_in_warnings(self, tmp_path):
        """A note larger than VAULT_INGEST_MAX_BYTES appears in warnings, not errors."""
        from vault_health_check import run_vault_health_check
        import vault_health_check as vhc

        big_content = "x" * (vhc.VAULT_INGEST_MAX_BYTES + 100)
        notes = ["huge.md"]
        mock_bridge = _make_bridge(ping=True, notes=notes, note_content=big_content)

        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        warning_paths = [w["path"] for w in result["warnings"]]
        assert "huge.md" in warning_paths
        assert "huge.md" not in [e["path"] for e in result["errors"]]

    def test_audit_log_written_when_db_path_provided(self, tmp_db):
        """When db_path is provided, VAULT_HEALTH_CHECK is logged to audit_logs."""
        from vault_health_check import run_vault_health_check

        mock_bridge = _make_bridge(ping=True, notes=[], note_content="")
        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            run_vault_health_check("/fake/vault", db_path=tmp_db)

        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT rationale FROM audit_logs WHERE action = 'VAULT_HEALTH_CHECK' "
                "ORDER BY log_id DESC LIMIT 1"
            ).fetchone()
        assert row is not None
        assert "Scanned" in row[0]

    def test_note_read_error_appears_in_warnings(self, tmp_path):
        """If bridge.read_note raises unexpectedly, note appears in warnings."""
        from vault_health_check import run_vault_health_check

        def _fail_read(path):
            raise RuntimeError("Unexpected read error")

        mock_bridge = _make_bridge(ping=True, notes=["error.md"], read_side_effect=_fail_read)
        with patch("vault_health_check.ObsidianBridge", return_value=mock_bridge):
            result = run_vault_health_check(str(tmp_path))

        warning_paths = [w["path"] for w in result["warnings"]]
        assert "error.md" in warning_paths


# ===========================================================================
# format_health_report() tests
# ===========================================================================

class TestFormatHealthReport:

    def test_report_has_yaml_frontmatter(self, tmp_path):
        """Formatted report starts with valid YAML frontmatter."""
        from vault_health_check import format_health_report
        result = {"passed": [], "warnings": [], "errors": [], "skipped": []}
        report = format_health_report(result)
        assert report.startswith("---")
        assert "title:" in report
        assert "tags:" in report
        assert "vault-health" in report

    def test_report_shows_error_section(self, tmp_path):
        """Error notes appear in the ❌ Errors section."""
        from vault_health_check import format_health_report
        result = {
            "passed": [],
            "warnings": [],
            "errors": [{"path": "bad.md", "issues": ["Missing 'id'"]}],
            "skipped": [],
        }
        report = format_health_report(result)
        assert "bad.md" in report
        assert "Missing 'id'" in report

    def test_report_shows_zero_errors_message(self):
        """When no errors, report shows a positive message."""
        from vault_health_check import format_health_report
        result = {
            "passed": [{"path": "ok.md"}],
            "warnings": [],
            "errors": [],
            "skipped": [],
        }
        report = format_health_report(result)
        assert "intact" in report.lower() or "No errors" in report

"""
test_vault_taxonomy_guard.py — Sprint 9 test suite for vault_taxonomy_guard.

No external dependencies or filesystem required.
"""

import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "openclaw_skills"))
sys.path.insert(0, str(ROOT / "openclaw_skills" / "vault_tools"))


class TestValidateTaxonomyCompliance:

    def test_valid_jd_path_passes(self):
        """Standard JD path returns (True, [])."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("20 - AREAS/23 - AI/LLM_Notes.md")
        assert ok is True
        assert issues == []

    def test_missing_jd_prefix_fails(self):
        """Folder without NN - prefix → (False, [violation])."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("UNSORTED/Random.md")
        assert ok is False
        assert any("UNSORTED" in i for i in issues)

    def test_single_non_jd_folder_fails(self):
        """Even a single non-prefixed folder in an otherwise valid path fails."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("20 - AREAS/AI/Note.md")
        assert ok is False
        assert any("AI" in i for i in issues)

    def test_obsidian_system_folder_skipped(self):
        """.obsidian is an allowed system component — no violation raised."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance(".obsidian/plugins/config.json")
        assert ok is True, f"Expected PASS for .obsidian path, got issues: {issues}"

    def test_openclaw_folder_skipped(self):
        """'openclaw' sub-folder inside INBOX is exempt from JD rule."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("00 - INBOX/openclaw/Agent_Run.md")
        assert ok is True, f"Expected PASS, got issues: {issues}"

    def test_templates_folder_skipped(self):
        """'templates' is a new allowed system component (Sprint 9 addition)."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("90 - TEMPLATES/templates/daily.md")
        assert ok is True, f"Expected templates to be exempt, got: {issues}"

    def test_dashboards_folder_skipped(self):
        """'dashboards' is a new allowed system component (Sprint 9 addition)."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("99 - META/dashboards/home.md")
        assert ok is True, f"Expected dashboards to be exempt, got: {issues}"

    def test_md_extension_file_not_checked(self):
        """File component (ends in .md) is not checked for JD prefix."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("20 - AREAS/23 - AI/UnprefixedFile.md")
        assert ok is True

    def test_file_only_path_passes(self):
        """A bare filename with no folder components should pass."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("Note.md")
        assert ok is True

    def test_multiple_violations_reported(self):
        """Multiple non-JD folders → multiple violation messages."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("BadFolder/AnotherBad/Note.md")
        assert ok is False
        assert len(issues) == 2

    def test_inbox_path_passes(self):
        """Standard 00 - INBOX path is valid."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance("00 - INBOX/capture.md")
        assert ok is True

    def test_git_folder_skipped(self):
        """.git is exempt (it's in ALLOWED_SYSTEM_COMPONENTS)."""
        from vault_taxonomy_guard import validate_taxonomy_compliance
        ok, issues = validate_taxonomy_compliance(".git/config")
        assert ok is True

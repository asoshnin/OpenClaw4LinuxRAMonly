"""
test_vault_intelligent_router.py — Sprint 9 test suite for vault_intelligent_router.

All filesystem calls are mocked — no live vault on disk required.
"""

import logging
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "openclaw_skills"))
sys.path.insert(0, str(ROOT / "openclaw_skills" / "vault_tools"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dir_entry(name: str, is_dir: bool = True) -> MagicMock:
    """Build a mock os.DirEntry."""
    entry = MagicMock()
    entry.name = name
    entry.is_dir.return_value = is_dir
    return entry


# ===========================================================================
# discover_domains() tests
# ===========================================================================

class TestDiscoverDomains:

    def test_returns_correct_slug_map(self, tmp_path):
        """discover_domains() maps folder names to lowercase slugs correctly."""
        from vault_intelligent_router import discover_domains

        areas = tmp_path / "20 - AREAS"
        areas.mkdir()
        (areas / "21 - Finance").mkdir()
        (areas / "22 - Health").mkdir()
        (areas / "23 - AI").mkdir()

        result = discover_domains(str(tmp_path))
        assert result == {
            "finance": "21 - Finance",
            "health": "22 - Health",
            "ai": "23 - AI",
        }

    def test_skips_non_jd_entries(self, tmp_path):
        """Folders without NN - prefix are silently skipped."""
        from vault_intelligent_router import discover_domains

        areas = tmp_path / "20 - AREAS"
        areas.mkdir()
        (areas / "21 - Finance").mkdir()
        (areas / "random_folder").mkdir()  # no JD prefix
        (areas / "notes.md").write_text("file")  # file, not dir

        result = discover_domains(str(tmp_path))
        assert list(result.keys()) == ["finance"]

    def test_duplicate_prefix_logs_warning_and_uses_first(self, tmp_path, caplog):
        """Duplicate numerical prefix: WARNING logged, first entry retained."""
        from vault_intelligent_router import discover_domains

        areas = tmp_path / "20 - AREAS"
        areas.mkdir()
        # Sorted alphabetically: "26 - Politics" comes before "26 - POLITICS"
        (areas / "26 - Politics").mkdir()
        (areas / "26 - POLITICS").mkdir()

        with caplog.at_level(logging.WARNING):
            result = discover_domains(str(tmp_path))

        assert "26" in "\n".join(caplog.messages)
        assert "politics" in result
        assert result["politics"] == "26 - Politics"
        # POLITICS (duplicate) must NOT appear separately
        assert len([k for k in result if k.startswith("politic")]) == 1

    def test_vault_root_none_returns_empty(self, caplog):
        """vault_root=None → returns {} and logs WARNING."""
        from vault_intelligent_router import discover_domains

        with caplog.at_level(logging.WARNING):
            result = discover_domains(None)

        assert result == {}
        assert any("empty" in m.lower() or "vault_root" in m.lower() for m in caplog.messages)

    def test_vault_root_empty_string_returns_empty(self, caplog):
        """vault_root='' → returns {} and logs WARNING."""
        from vault_intelligent_router import discover_domains

        with caplog.at_level(logging.WARNING):
            result = discover_domains("")

        assert result == {}

    def test_areas_dir_missing_returns_empty(self, tmp_path, caplog):
        """If 20 - AREAS/ does not exist → returns {} and logs WARNING."""
        from vault_intelligent_router import discover_domains

        # tmp_path exists but has no "20 - AREAS" subdirectory
        with caplog.at_level(logging.WARNING):
            result = discover_domains(str(tmp_path))

        assert result == {}
        assert any("20 - AREAS" in m for m in caplog.messages)


# ===========================================================================
# suggest_vault_path() tests
# ===========================================================================

class TestSuggestVaultPath:

    def _vault(self, tmp_path, domains=None):
        """Create a minimal vault structure with given domains."""
        areas = tmp_path / "20 - AREAS"
        areas.mkdir(exist_ok=True)
        (tmp_path / "10 - PROJECTS").mkdir(exist_ok=True)
        (tmp_path / "30 - RESOURCES").mkdir(exist_ok=True)
        for folder in (domains or []):
            (areas / folder).mkdir(exist_ok=True)
        return str(tmp_path)

    def test_project_type_routes_to_projects(self, tmp_path):
        """type: project → 10 - PROJECTS/"""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path)
        result = suggest_vault_path({"type": "project"}, "Plan.md", vault)
        assert result == "10 - PROJECTS/Plan.md"

    def test_project_field_routes_to_projects(self, tmp_path):
        """'project' field set → priority route to 10 - PROJECTS/"""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path)
        result = suggest_vault_path({"type": "note", "project": "HiveForge"}, "Sprint.md", vault)
        assert result == "10 - PROJECTS/Sprint.md"

    def test_domain_ai_routes_to_areas_case_insensitive(self, tmp_path):
        """domain: 'AI' routes to 20 - AREAS/23 - AI/ (case-insensitive)."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["23 - AI"])
        result = suggest_vault_path({"type": "note", "domain": "AI"}, "LLM.md", vault)
        assert result == "20 - AREAS/23 - AI/LLM.md"

    def test_domain_lowercase_ai_routes_correctly(self, tmp_path):
        """domain: 'ai' (lowercase) routes same as 'AI'."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["23 - AI"])
        result = suggest_vault_path({"type": "note", "domain": "ai"}, "LLM.md", vault)
        assert result == "20 - AREAS/23 - AI/LLM.md"

    def test_domain_finance_routes_to_areas(self, tmp_path):
        """domain: 'Finance' routes to 20 - AREAS/21 - Finance/"""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["21 - Finance"])
        result = suggest_vault_path({"type": "note", "domain": "Finance"}, "Budget.md", vault)
        assert result == "20 - AREAS/21 - Finance/Budget.md"

    def test_resource_type_routes_to_resources(self, tmp_path):
        """type: resource → 30 - RESOURCES/"""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path)
        result = suggest_vault_path({"type": "resource"}, "Guide.md", vault)
        assert result == "30 - RESOURCES/Guide.md"

    def test_resource_with_unmatched_domain_routes_to_resources(self, tmp_path):
        """type: resource + unknown domain → 30 - RESOURCES/ (not INBOX)."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path)  # no domain folders
        result = suggest_vault_path({"type": "resource", "domain": "Unknown"}, "Guide.md", vault)
        assert result == "30 - RESOURCES/Guide.md"

    def test_unknown_domain_falls_back_to_inbox(self, tmp_path):
        """Unmatched domain → 00 - INBOX/ fallback."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["21 - Finance"])
        result = suggest_vault_path({"type": "note", "domain": "MartialArts"}, "Judo.md", vault)
        assert result == "00 - INBOX/Judo.md"

    def test_vault_root_none_falls_back_to_inbox(self, monkeypatch):
        """vault_root=None (and no env var) → 00 - INBOX/ without raising."""
        from vault_intelligent_router import suggest_vault_path
        monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)
        result = suggest_vault_path({"type": "note", "domain": "AI"}, "X.md", None)
        assert result == "00 - INBOX/X.md"

    def test_old_hardcoded_key_ai_research_no_longer_special(self, tmp_path):
        """Regression: 'AI-Research' is NOT a hardcoded constant anymore.
        A vault with '23 - AI' folder must resolve 'ai' domain, NOT 'ai-research'."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["23 - AI"])
        # The old DOMAIN_MAP had "AI-Research" → "23 - AI-Research"
        # The new live vault has "23 - AI" → slug "ai"
        # domain="AI-Research" should NOT silently match "ai" slug
        result = suggest_vault_path({"type": "note", "domain": "AI-Research"}, "Note.md", vault)
        # "ai-research" slug does not match "ai" folder → INBOX fallback
        assert result == "00 - INBOX/Note.md"

    def test_output_path_has_no_leading_slash(self, tmp_path):
        """Output is a relative vault path — no leading slash."""
        from vault_intelligent_router import suggest_vault_path
        vault = self._vault(tmp_path, ["23 - AI"])
        result = suggest_vault_path({"type": "note", "domain": "AI"}, "X.md", vault)
        assert not result.startswith("/")

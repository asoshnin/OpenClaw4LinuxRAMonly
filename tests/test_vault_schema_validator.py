"""
test_vault_schema_validator.py — Sprint 9 test suite for vault_schema_validator.

No external dependencies required — all tests use in-memory strings.
"""

import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "openclaw_skills"))
sys.path.insert(0, str(ROOT / "openclaw_skills" / "vault_tools"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_note(extra_fields: str = "") -> str:
    """Return a minimal fully-valid note with all mandatory fields."""
    return (
        "---\n"
        'id: "23.01-202603271200"\n'
        "type: note\n"
        "status: active\n"
        'summary: "A valid test note."\n'
        "keywords: [test, valid]\n"
        "tags: [openclaw, sprint9]\n"
        'domain: "ai"\n'
        f"{extra_fields}"
        "---\n"
        "# Content\n\n"
        "Body text here.\n"
    )


# ===========================================================================
# validate_vault_metadata() tests
# ===========================================================================

class TestValidateVaultMetadata:

    def test_valid_note_all_mandatory_fields_passes(self):
        """A note with all mandatory fields (incl. tags) is valid."""
        from vault_schema_validator import validate_vault_metadata
        result = validate_vault_metadata(_valid_note())
        assert result["is_valid"] is True
        assert result["errors"] == []

    def test_missing_tags_fails(self):
        """Missing 'tags' field → is_valid=False with specific error."""
        from vault_schema_validator import validate_vault_metadata
        note = (
            "---\n"
            'id: "23.01-202603271200"\n'
            "type: note\n"
            "status: active\n"
            'summary: "No tags."\n'
            "keywords: [test]\n"
            # tags field intentionally omitted
            "---\n# Content\n"
        )
        result = validate_vault_metadata(note)
        assert result["is_valid"] is False
        assert any("tags" in e for e in result["errors"])

    def test_missing_id_fails(self):
        """Missing 'id' field → is_valid=False."""
        from vault_schema_validator import validate_vault_metadata
        note = (
            "---\n"
            "type: note\n"
            "status: active\n"
            'summary: "No id."\n'
            "keywords: []\n"
            "tags: [openclaw]\n"
            "---\n# Content\n"
        )
        result = validate_vault_metadata(note)
        assert result["is_valid"] is False
        assert any("id" in e for e in result["errors"])

    def test_missing_summary_fails(self):
        """Missing 'summary' field → is_valid=False."""
        from vault_schema_validator import validate_vault_metadata
        note = (
            "---\n"
            'id: "23.01-202603271200"\n'
            "type: note\n"
            "status: active\n"
            "keywords: []\n"
            "tags: [openclaw]\n"
            "---\n# Content\n"
        )
        result = validate_vault_metadata(note)
        assert result["is_valid"] is False
        assert any("summary" in e for e in result["errors"])

    def test_empty_domain_is_warning_not_error(self):
        """domain: '' → warning added but is_valid stays True (if all other fields present)."""
        from vault_schema_validator import validate_vault_metadata
        note = _valid_note('domain: ""\n')  # override the domain field
        # The _valid_note already has domain, re-build without it
        note_no_domain = (
            "---\n"
            'id: "23.01-202603271200"\n'
            "type: note\n"
            "status: active\n"
            'summary: "Empty domain."\n'
            "keywords: [test]\n"
            "tags: [openclaw]\n"
            'domain: ""\n'
            "---\n# Content\n"
        )
        result = validate_vault_metadata(note_no_domain)
        # domain being empty should not cause an error
        domain_errors = [e for e in result["errors"] if "domain" in e.lower()]
        assert domain_errors == [], f"Expected no domain errors, got: {domain_errors}"
        # But it should be a warning
        domain_warnings = [w for w in result["warnings"] if "domain" in w.lower()]
        assert domain_warnings, "Expected a domain warning for empty domain field"

    def test_malformed_yaml_returns_invalid(self):
        """Malformed YAML → is_valid=False with YAML Parse Error."""
        from vault_schema_validator import validate_vault_metadata
        note = "---\nid: : broken yaml\ntype: note\n---\n# Content\n"
        result = validate_vault_metadata(note)
        assert result["is_valid"] is False
        assert any("Parse Error" in e or "YAML" in e for e in result["errors"])

    def test_missing_frontmatter_returns_invalid(self):
        """No YAML frontmatter block → is_valid=False."""
        from vault_schema_validator import validate_vault_metadata
        note = "# Just a heading\n\nNo frontmatter here.\n"
        result = validate_vault_metadata(note)
        assert result["is_valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_suggested_frontmatter_always_present_on_valid(self):
        """suggested_frontmatter key is present in all valid responses."""
        from vault_schema_validator import validate_vault_metadata
        result = validate_vault_metadata(_valid_note())
        assert "suggested_frontmatter" in result
        assert result["suggested_frontmatter"].startswith("---")
        assert "tags:" in result["suggested_frontmatter"]

    def test_suggested_frontmatter_always_present_on_invalid(self):
        """suggested_frontmatter key is present even when validation fails."""
        from vault_schema_validator import validate_vault_metadata
        result = validate_vault_metadata("# No frontmatter\n")
        assert "suggested_frontmatter" in result
        assert result["suggested_frontmatter"].startswith("---")

    def test_non_standard_id_produces_warning(self):
        """Non-standard ID format produces a warning (not an error)."""
        from vault_schema_validator import validate_vault_metadata
        note = (
            "---\n"
            'id: "NONSTANDARD-ID"\n'
            "type: note\n"
            "status: active\n"
            'summary: "Test."\n'
            "keywords: []\n"
            "tags: [openclaw]\n"
            "---\n# Content\n"
        )
        result = validate_vault_metadata(note)
        # ID format mismatch → warning, not error
        assert any("ID" in w for w in result["warnings"])

    def test_path_alignment_warning_for_missing_jd_prefix(self):
        """Folder in expected_path without NN - prefix triggers alignment warning."""
        from vault_schema_validator import validate_vault_metadata
        result = validate_vault_metadata(
            _valid_note(),
            expected_path="UNSORTED/Note.md",
        )
        assert any("UNSORTED" in w for w in result["warnings"])

    def test_path_alignment_no_warning_for_valid_jd_path(self):
        """Valid JD path produces no alignment warnings."""
        from vault_schema_validator import validate_vault_metadata
        result = validate_vault_metadata(
            _valid_note(),
            expected_path="20 - AREAS/23 - AI/Note.md",
        )
        # Only possible warnings should be about ID format or domain
        alignment_warnings = [w for w in result["warnings"] if "lacks" in w.lower()]
        assert alignment_warnings == []

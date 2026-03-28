"""
vault_schema_validator.py — OpenClaw Vault Schema Validator (Sprint 9)

Validates Obsidian note YAML frontmatter against the Universal Note Template.
Migrated from src/tools/ and hardened per Sprint 9 spec.

Changes from prototype:
  - 'tags' added to mandatory fields.
  - Empty 'domain' field emits a WARNING (not an error).
  - Result dict now includes 'suggested_frontmatter' for auto-repair workflows.
  - Full public API preserved: validate_vault_metadata(content, expected_path)
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import yaml  # pyyaml — already in requirements.txt

logger = logging.getLogger(__name__)

# Mandatory fields per Universal Note Template
_MANDATORY_FIELDS = ["id", "type", "status", "summary", "keywords", "tags"]

# Johnny.Decimal prefix for folder components
_JD_FOLDER_PATTERN = re.compile(r"^\d{2} - ")

# ID format: prefix-YYYYMMDDHHmm  (e.g. "23.01-202603271200")
_ID_FORMAT_PATTERN = re.compile(r"^\d+\.\d+-\d{12}$")


def _build_suggested_frontmatter() -> str:
    """Return a minimal valid YAML frontmatter block for repair suggestions."""
    now_str = datetime.now().strftime("%Y%m%d%H%M")
    return (
        "---\n"
        f'id: "XX.YY-{now_str}"\n'
        "type: note\n"
        "status: active\n"
        'summary: ""\n'
        "keywords: []\n"
        "tags: [openclaw]\n"
        'domain: ""\n'
        "---\n"
    )


def validate_vault_metadata(
    content: str,
    expected_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate Markdown note content against the Universal Note Template schema.

    Checks performed:
    1. Presence of YAML frontmatter (``---`` block at top of file).
    2. Mandatory fields: id, type, status, summary, keywords, tags.
    3. ID format adherence (prefix-YYYYMMDDHHmm).
    4. Johnny.Decimal folder alignment for each path component (if expected_path given).
    5. Empty ``domain`` field warns but does not fail validation.

    Args:
        content:       Full raw markdown string (including frontmatter).
        expected_path: Optional vault-relative path used for folder alignment check.

    Returns:
        dict with keys:
            is_valid (bool):            True iff no errors were found.
            errors (list[str]):         Validation errors (cause is_valid=False).
            warnings (list[str]):       Non-fatal notices.
            metadata (dict):            Parsed YAML frontmatter (or {} on parse failure).
            suggested_frontmatter (str): Minimal valid frontmatter template for repair.
    """
    results: Dict[str, Any] = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "metadata": {},
        "suggested_frontmatter": _build_suggested_frontmatter(),
    }

    # ── 1. Extract YAML frontmatter ─────────────────────────────────────────
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        results["is_valid"] = False
        results["errors"].append("Missing or malformed YAML frontmatter.")
        return results

    try:
        data = yaml.safe_load(match.group(1)) or {}
        results["metadata"] = data
    except yaml.YAMLError as exc:
        results["is_valid"] = False
        results["errors"].append(f"YAML Parse Error: {exc}")
        return results

    # ── 2. Mandatory field validation ───────────────────────────────────────
    for field in _MANDATORY_FIELDS:
        if field not in data or data[field] is None or data[field] == "":
            results["is_valid"] = False
            results["errors"].append(f"Missing mandatory field: '{field}'")

    # ── 3. ID format validation ─────────────────────────────────────────────
    if "id" in data and data["id"] is not None:
        id_val = str(data["id"])
        if not _ID_FORMAT_PATTERN.match(id_val):
            results["warnings"].append(
                f"ID '{id_val}' does not strictly follow Johnny.Decimal-Timestamp "
                "format (e.g. 23.01-202603271200)."
            )

    # ── 4. Empty domain warning (not an error) ──────────────────────────────
    if "domain" in data and (data["domain"] == "" or data["domain"] is None):
        results["warnings"].append(
            "Field 'domain' is present but empty. "
            "Set a domain slug for correct vault routing."
        )

    # ── 5. Folder alignment (Johnny.Decimal enforcement) ───────────────────
    if expected_path:
        from pathlib import Path  # lazy import for optional check
        path_parts = Path(expected_path).parts
        for part in path_parts:
            if part in (".", "/"):
                continue
            if part.endswith(".md"):
                continue
            if "openclaw" in part.lower():
                continue
            if not _JD_FOLDER_PATTERN.match(part):
                results["warnings"].append(
                    f"Path component '{part}' lacks standard Johnny.Decimal "
                    "numerical prefix (e.g. '23 - AI')."
                )

    return results

"""
vault_health_check.py — OpenClaw ObsidianVaultArchitect Autonomous Validator (Sprint 9)

Performs a read-only health scan of the entire Obsidian vault:
  - Enumerates all notes via ObsidianBridge.list_notes()
  - Validates YAML schema (vault_schema_validator)
  - Checks taxonomy compliance (vault_taxonomy_guard)
  - Skips 40 - ARCHIVE/ (excluded from AI index by design)
  - Flags duplicate JD numerical prefixes in 20 - AREAS/ as ERRORS
    (structural integrity failure — Navigator directive)
  - Notes > VAULT_INGEST_MAX_BYTES are flagged as warnings, not scanned

Security:
  - Read-only — never modifies any vault note
  - All writes (report output) are done by the caller via ObsidianBridge
  - vault_root NOT passed through validate_path() (lives outside OPENCLAW_WORKSPACE)
"""

import os
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Local imports ────────────────────────────────────────────────────────────
_skills_root = Path(__file__).resolve().parent.parent
if str(_skills_root) not in sys.path:
    sys.path.insert(0, str(_skills_root))

from vault_tools.vault_schema_validator import validate_vault_metadata
from vault_tools.vault_taxonomy_guard import validate_taxonomy_compliance
from vault_tools.vault_intelligent_router import discover_domains

try:
    from obsidian_bridge import ObsidianBridge, VAULT_INGEST_MAX_BYTES
except ImportError:
    ObsidianBridge = None  # type: ignore
    VAULT_INGEST_MAX_BYTES = 50000

# Notes whose path starts with this prefix are excluded from scanning
_ARCHIVE_PREFIX = "40 - ARCHIVE"


def _check_duplicate_prefixes(vault_root: str) -> List[Dict[str, Any]]:
    """Detect duplicate numerical prefixes in the 20 - AREAS/ directory.

    Navigator directive: duplicate prefixes are ERRORS in the health report
    (they represent a structural integrity failure of the Johnny.Decimal taxonomy).

    Returns:
        list of error dicts:  {"path": str, "issues": [str]}
    """
    errors: List[Dict[str, Any]] = []

    if not vault_root:
        return errors

    areas_dir = os.path.join(vault_root, "20 - AREAS")
    if not os.path.isdir(areas_dir):
        return errors

    import re
    _JD_AREA = re.compile(r"^(\d{2}) - .+")
    prefix_seen: Dict[str, str] = {}

    try:
        for entry in sorted(os.scandir(areas_dir), key=lambda e: e.name):
            if not entry.is_dir(follow_symlinks=False):
                continue
            m = _JD_AREA.match(entry.name)
            if not m:
                continue
            prefix = m.group(1)
            if prefix in prefix_seen:
                first = prefix_seen[prefix]
                errors.append({
                    "path": f"20 - AREAS/{entry.name}",
                    "issues": [
                        f"Duplicate JD prefix '{prefix}': folder '{first}' and "
                        f"'{entry.name}' share the same numerical prefix. "
                        "This is a structural integrity error — rename one folder "
                        "to use a unique two-digit prefix."
                    ],
                })
                logger.warning(
                    "vault_health_check: duplicate JD prefix '%s' — '%s' and '%s'",
                    prefix, first, entry.name,
                )
            else:
                prefix_seen[prefix] = entry.name
    except OSError as exc:
        logger.warning("vault_health_check: cannot scan %s — %s", areas_dir, exc)

    return errors


def run_vault_health_check(
    vault_root: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Perform an autonomous, read-only health scan of the Obsidian vault.

    Aggregates results from YAML schema validation and taxonomy checks
    for every non-archived note in the vault.

    Args:
        vault_root:  Absolute path to the Obsidian vault root directory.
                     Read from $OBSIDIAN_VAULT_PATH if not provided.
        db_path:     Optional path to factory.db for audit logging.

    Returns:
        {
            "passed":   [{"path": str}, ...],
            "warnings": [{"path": str, "issues": [str]}, ...],
            "errors":   [{"path": str, "issues": [str]}, ...],
            "skipped":  [{"path": str, "reason": str}, ...],
        }

    Raises:
        RuntimeError: If Obsidian is not running (scan requires live bridge).
        ImportError:  If ObsidianBridge is not available (Sprint 7 not installed).
    """
    if ObsidianBridge is None:
        raise ImportError(
            "ObsidianBridge not available — ensure Sprint 7 is installed "
            "(openclaw_skills/obsidian_bridge.py)."
        )

    if not vault_root:
        vault_root = os.environ.get("OBSIDIAN_VAULT_PATH", "")

    bridge = ObsidianBridge()
    if not bridge.ping():
        raise RuntimeError(
            "Obsidian is not running. Start Obsidian and ensure the "
            "Local REST API plugin is active before running a vault health check."
        )

    result: Dict[str, Any] = {
        "passed": [],
        "warnings": [],
        "errors": [],
        "skipped": [],
    }

    # ── Phase 0: Check for duplicate JD prefixes (errors by Navigator directive) ──
    dup_errors = _check_duplicate_prefixes(vault_root)
    result["errors"].extend(dup_errors)

    # ── Phase 1: Enumerate all notes ────────────────────────────────────────
    all_notes: List[str] = bridge.list_notes()
    logger.info("vault_health_check: found %d notes to scan", len(all_notes))

    # ── Phase 2: Scan each note ──────────────────────────────────────────────
    for note_path in all_notes:
        # Skip archived notes
        if note_path.startswith(_ARCHIVE_PREFIX):
            result["skipped"].append({"path": note_path, "reason": "archived"})
            continue

        # Read content
        try:
            content = bridge.read_note(note_path)
        except FileNotFoundError:
            result["warnings"].append({
                "path": note_path,
                "issues": ["Note listed by Obsidian but returned 404 on read — may have been deleted."],
            })
            continue
        except Exception as exc:
            result["warnings"].append({
                "path": note_path,
                "issues": [f"Could not read note: {exc}"],
            })
            continue

        # Size gate (warn, not error)
        content_bytes = len(content.encode("utf-8", errors="replace"))
        if content_bytes > VAULT_INGEST_MAX_BYTES:
            result["warnings"].append({
                "path": note_path,
                "issues": [
                    f"Note is {content_bytes} bytes (exceeds VAULT_INGEST_MAX_BYTES={VAULT_INGEST_MAX_BYTES}). "
                    "Will not be ingested into the vector archive."
                ],
            })
            continue

        # Schema validation
        schema_result = validate_vault_metadata(content, expected_path=note_path)

        # Taxonomy check
        tax_ok, tax_issues = validate_taxonomy_compliance(note_path)

        # Aggregate
        all_errors = list(schema_result.get("errors", []))
        all_warnings = list(schema_result.get("warnings", []))
        if not tax_ok:
            all_errors.extend(tax_issues)

        if all_errors:
            result["errors"].append({"path": note_path, "issues": all_errors})
        elif all_warnings:
            result["warnings"].append({"path": note_path, "issues": all_warnings})
        else:
            result["passed"].append({"path": note_path})

    # ── Phase 3: Audit log if db_path provided ───────────────────────────────
    if db_path:
        try:
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, ?, ?)",
                    (
                        "obsidian-vault-architect",
                        "VAULT_HEALTH_CHECK",
                        (
                            f"Scanned {len(all_notes)} notes: "
                            f"{len(result['passed'])} passed, "
                            f"{len(result['warnings'])} warnings, "
                            f"{len(result['errors'])} errors, "
                            f"{len(result['skipped'])} skipped."
                        ),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("vault_health_check: audit log failed: %s", exc)

    logger.info(
        "vault_health_check complete: %d passed, %d warnings, %d errors, %d skipped",
        len(result["passed"]),
        len(result["warnings"]),
        len(result["errors"]),
        len(result["skipped"]),
    )
    return result


def format_health_report(health_result: Dict[str, Any], vault_root: str = "") -> str:
    """Render a vault health check result as Obsidian-ready Markdown.

    Args:
        health_result: dict returned by run_vault_health_check().
        vault_root:    Optional vault root string for report metadata.

    Returns:
        Full Markdown string with YAML frontmatter ready for vault write.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    now_iso = datetime.now().isoformat()

    passed = health_result.get("passed", [])
    warnings = health_result.get("warnings", [])
    errors = health_result.get("errors", [])
    skipped = health_result.get("skipped", [])
    total_scanned = len(passed) + len(warnings) + len(errors)

    lines = [
        "---",
        f'title: "Vault Health Report {today}"',
        "type: report",
        "tags: [openclaw, vault-health]",
        "domain: ai",
        "status: active",
        "---",
        "",
        f"# Vault Health Report — {today}",
        "",
        (
            f"**Scanned:** {total_scanned} notes  "
            f"**Passed:** {len(passed)}  "
            f"**Warnings:** {len(warnings)}  "
            f"**Errors:** {len(errors)}  "
            f"**Skipped:** {len(skipped)} (archived)"
        ),
        "",
        "---",
        "",
    ]

    if errors:
        lines.append(f"## ❌ Errors ({len(errors)})")
        lines.append("")
        for item in errors:
            lines.append(f"### `{item['path']}`")
            for issue in item.get("issues", []):
                lines.append(f"- {issue}")
            lines.append("")
    else:
        lines.append("## ❌ Errors (0)")
        lines.append("")
        lines.append("_(No errors found — vault structure is intact.)_")
        lines.append("")

    lines.append("---")
    lines.append("")

    if warnings:
        lines.append(f"## ⚠️ Warnings ({len(warnings)})")
        lines.append("")
        for item in warnings:
            lines.append(f"### `{item['path']}`")
            for issue in item.get("issues", []):
                lines.append(f"- {issue}")
            lines.append("")
    else:
        lines.append("## ⚠️ Warnings (0)")
        lines.append("")
        lines.append("_(No warnings.)_")
        lines.append("")

    lines.append("---")
    lines.append("")

    if passed:
        lines.append(f"## ✅ Passed ({len(passed)})")
        lines.append("")
        lines.append(f"_({len(passed)} notes passed all checks)_")
        lines.append("")

    if skipped:
        lines.append(f"## ⏭️ Skipped ({len(skipped)})")
        lines.append("")
        for item in skipped:
            lines.append(f"- `{item['path']}` — {item.get('reason', 'skipped')}")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by OpenClaw `vault-health-check` on {now_iso}*")
    lines.append("")

    return "\n".join(lines)

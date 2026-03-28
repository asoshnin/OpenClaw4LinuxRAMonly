"""
vault_intelligent_router.py — OpenClaw Vault Intelligent Router (Sprint 9)

Routes note YAML metadata to the correct Johnny.Decimal folder path by
performing a RUNTIME scan of the live vault's 20 - AREAS/ directory.

Design constraints:
  - NO hardcoded DOMAIN_MAP.  The map is derived from the filesystem at call
    time so it stays in sync with any folder renames/additions in the vault.
  - Case-insensitive domain lookup (e.g. 'AI', 'ai', 'Ai' all resolve).
  - Duplicate numerical prefix detection: logs WARNING, keeps first match.
  - vault_root must NOT go through validate_path() — the vault lives outside
    OPENCLAW_WORKSPACE by design (OBSIDIAN_VAULT_PATH env var).
"""

import os
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Regex that a valid Johnny.Decimal area folder must match
_JD_AREA_PATTERN = re.compile(r"^\d{2} - .+")


def discover_domains(vault_root: str) -> Dict[str, str]:
    """Scan {vault_root}/20 - AREAS/ and return a slug → folder-name map.

    Args:
        vault_root: Absolute path to the Obsidian vault root.

    Returns:
        dict mapping lowercase domain slug to folder name, e.g.
        {"ai": "23 - AI", "finance": "21 - Finance", "health": "22 - Health"}

    Behaviour:
        - Only entries matching ``^\\d{2} - .+`` are included.
        - Non-directory entries are skipped.
        - Slug = folder name with the "NN - " prefix stripped, lowercased,
          and whitespace-stripped (e.g. "23 - AI" → "ai").
        - Duplicate numerical prefix: logs WARNING and skips the second entry
          (first-in-filesystem-order wins).
        - If vault_root is falsy or 20 - AREAS/ does not exist: logs WARNING
          and returns {}.
    """
    if not vault_root:
        logger.warning(
            "discover_domains: vault_root is empty — no domain map available."
        )
        return {}

    areas_dir = os.path.join(vault_root, "20 - AREAS")
    if not os.path.isdir(areas_dir):
        logger.warning(
            "discover_domains: '20 - AREAS' directory not found at %s — "
            "domain routing will fall back to INBOX.",
            areas_dir,
        )
        return {}

    domain_map: Dict[str, str] = {}
    prefix_seen: Dict[str, str] = {}  # two-digit prefix → first folder name seen

    try:
        entries = sorted(os.scandir(areas_dir), key=lambda e: e.name.lower())
    except OSError as exc:
        logger.warning("discover_domains: cannot scan %s — %s", areas_dir, exc)
        return {}

    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        if not _JD_AREA_PATTERN.match(entry.name):
            logger.debug(
                "discover_domains: skipping non-JD entry '%s'", entry.name
            )
            continue

        prefix = entry.name[:2]  # "23"
        # Derive slug: strip the "NN - " prefix (first 5 chars), lowercase, strip
        # e.g. "23 - AI" → "ai",  "21 - Finance" → "finance"
        slug = entry.name[5:].strip().lower()

        if prefix in prefix_seen:
            logger.warning(
                "discover_domains: Duplicate numerical prefix '%s' — "
                "found '%s' and '%s'. Using '%s'.",
                prefix,
                prefix_seen[prefix],
                entry.name,
                prefix_seen[prefix],
            )
            continue  # First-seen wins; skip the duplicate

        prefix_seen[prefix] = entry.name
        domain_map[slug] = entry.name
        logger.debug(
            "discover_domains: registered domain '%s' → '%s'", slug, entry.name
        )

    return domain_map


def suggest_vault_path(
    metadata: Dict[str, Any],
    filename: str,
    vault_root: Optional[str] = None,
) -> str:
    """Suggest the correct Johnny.Decimal vault path for a note.

    Routing priority (highest → lowest):
    1. note type == 'project' OR 'project' field is set  →  10 - PROJECTS/
    2. 'domain' matches a discovered AREA folder (case-insensitive)  →  20 - AREAS/{folder}/
    3. note type == 'resource'  →  30 - RESOURCES/
    4. Fallback  →  00 - INBOX/ (requires manual triage)

    Args:
        metadata:   Dict of YAML frontmatter fields from the note.
        filename:   Target note filename (e.g. 'LLM_Notes.md').
        vault_root: Absolute path to vault root; falls back to
                    $OBSIDIAN_VAULT_PATH env var if not provided.
                    If neither is available, domain routing is skipped
                    and the function falls back gracefully.

    Returns:
        A relative, Obsidian-ready vault path string (no leading slash),
        safe to pass to ObsidianBridge.write_note().
    """
    # Resolve vault root
    if vault_root is None:
        vault_root = os.environ.get("OBSIDIAN_VAULT_PATH", "")

    note_type = str(metadata.get("type", "note")).lower().strip()
    domain_raw = str(metadata.get("domain", "")).strip()
    project_field = metadata.get("project", "")

    # ── Rule 1: Projects ────────────────────────────────────────────────────
    if note_type == "project" or project_field:
        return f"10 - PROJECTS/{filename}"

    # ── Rule 2: Domain → AREA ───────────────────────────────────────────────
    if domain_raw and vault_root:
        domain_slug = domain_raw.lower()
        domain_map = discover_domains(vault_root)
        area_folder = domain_map.get(domain_slug)
        if area_folder:
            return f"20 - AREAS/{area_folder}/{filename}"
        else:
            logger.debug(
                "suggest_vault_path: domain '%s' not found in discovered map "
                "(%s). Continuing to next rule.",
                domain_raw,
                list(domain_map.keys()),
            )

    # ── Rule 3: Resources ────────────────────────────────────────────────────
    if note_type == "resource":
        return f"30 - RESOURCES/{filename}"

    # ── Rule 4: Fallback ────────────────────────────────────────────────────
    if vault_root and domain_raw:
        logger.debug(
            "suggest_vault_path: '%s' domain='%s' — no match found, "
            "routing to INBOX fallback.",
            filename,
            domain_raw,
        )
    return f"00 - INBOX/{filename}"

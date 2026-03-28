"""
vault_taxonomy_guard.py — OpenClaw Vault Taxonomy Guard (Sprint 9)

Hard enforcement of Johnny.Decimal naming conventions for vault paths.
Migrated from src/tools/ and hardened per Sprint 9 spec.

Changes from prototype:
  - ALLOWED_SYSTEM_COMPONENTS extended with 'templates', 'dashboards',
    'ai logs' (matching 90 - TEMPLATES, 99 - META vault structure).
  - Public API preserved: validate_taxonomy_compliance(vault_path)
"""

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Regex: exactly two digits, space, dash, space (e.g. "10 - ")
JD_PREFIX_PATTERN = re.compile(r"^\d{2} - ")

# Path components that are exempt from the JD naming rule.
# Compared case-insensitively via 'any(s in part.lower() ...)'.
ALLOWED_SYSTEM_COMPONENTS = [
    "openclaw",
    ".obsidian",
    ".git",
    "memory",
    "templates",     # e.g. inside 90 - TEMPLATES/
    "dashboards",    # e.g. inside 99 - META/dashboards/
    "ai logs",       # e.g. inside 99 - META/ai logs/
]


def validate_taxonomy_compliance(vault_path: str) -> Tuple[bool, List[str]]:
    """Check whether a vault path complies with Johnny.Decimal standards.

    Compliance rules:
    1. Every *directory* component must start with "NN - " (two digits, space, dash, space).
    2. Components matching ALLOWED_SYSTEM_COMPONENTS are exempt (case-insensitive).
    3. Files (components ending with '.md' or containing '.') are not checked.

    Args:
        vault_path: Vault-relative or absolute path string to check.

    Returns:
        (is_compliant: bool, issues: list[str])
        is_compliant is True iff issues is empty.
    """
    from pathlib import Path

    issues: List[str] = []
    parts = Path(vault_path).parts

    # Short-circuit: if any ancestor component is an allowed system folder,
    # skip the entire path — everything inside .obsidian/, .git/ etc. is exempt.
    for part in parts:
        if any(sys_comp in part.lower() for sys_comp in ALLOWED_SYSTEM_COMPONENTS):
            return True, []

    for part in parts:
        # Skip filesystem root and current-dir markers
        if part in (".", "/"):
            continue

        # Skip file components (anything with an extension or ending in .md)
        if "." in part and not part.startswith("."):
            continue
        if part.endswith(".md"):
            continue

        # Enforce JD prefix on all remaining directory components
        if not JD_PREFIX_PATTERN.match(part):
            issues.append(
                f"Taxonomy Violation: Folder '{part}' is missing the mandatory "
                "'NN - ' Johnny.Decimal prefix."
            )

    is_compliant = len(issues) == 0
    return is_compliant, issues

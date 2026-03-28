"""
vault_tools — OpenClaw Vault Tools Package (Sprint 9)

Public API:
    discover_domains(vault_root)         — runtime scan of 20 - AREAS/
    suggest_vault_path(meta, fn, root)   — route note to correct JD folder
    validate_vault_metadata(content)     — check YAML frontmatter schema
    validate_taxonomy_compliance(path)   — enforce NN - prefix on all dirs
"""

from .vault_intelligent_router import discover_domains, suggest_vault_path
from .vault_schema_validator import validate_vault_metadata
from .vault_taxonomy_guard import validate_taxonomy_compliance

__all__ = [
    "discover_domains",
    "suggest_vault_path",
    "validate_vault_metadata",
    "validate_taxonomy_compliance",
]

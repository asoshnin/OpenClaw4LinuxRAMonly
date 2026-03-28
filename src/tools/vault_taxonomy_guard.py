"""
Vault Taxonomy Guard Tool - Sprint 8
Hard enforcement of Johnny.Decimal naming conventions for folders and files.
"""

import re
from pathlib import Path
from typing import Tuple, List

# Regex for Johnny.Decimal Prefix: Exactly two digits, a space, a dash, and another space (e.g., "10 - ")
JD_PREFIX_PATTERN = r"^\d{2} - "

# Allowed exceptions (system folders that don't need prefixes)
ALLOWED_SYSTEM_COMPONENTS = ["openclaw", ".obsidian", ".git", "memory"]

def validate_taxonomy_compliance(vault_path: str) -> Tuple[bool, List[str]]:
    """
    Checks if a given vault path (folder or file) complies with Johnny.Decimal standards.
    
    Compliance Rules:
    1. Every folder level must start with "NN - " (e.g., "20 - AREAS").
    2. Exceptions allowed for specific system directories.
    3. Files inside valid folders are compliant.
    """
    issues = []
    path_obj = Path(vault_path)
    
    # We only care about the directory components
    # If the path is just a filename, we check the parent if it exists
    parts = path_obj.parts
    
    for part in parts:
        # Skip root and allowed system components
        if part == "." or part == "/" or any(sys in part.lower() for sys in ALLOWED_SYSTEM_COMPONENTS):
            continue
            
        # Check if the component is a directory (or looks like one in the path)
        # Note: In the bridge, we often see paths like "20 - AREAS/23 - AI-Research/Note.md"
        # We only enforce the prefix on the folders.
        if part.endswith(".md"):
            continue
            
        if not re.match(JD_PREFIX_PATTERN, part):
            issues.append(f"Taxonomy Violation: Folder '{part}' is missing the mandatory 'NN - ' Johnny.Decimal prefix.")

    is_compliant = len(issues) == 0
    return is_compliant, issues

if __name__ == "__main__":
    # Test cases
    test_paths = [
        "20 - AREAS/23 - AI-Research/Quantum_Routing.md",
        "My-Unsorted-Notes/Random.md",
        "00 - INBOX/openclaw/Handshake.md",
        "PROJECTS/HiveForge/Plan.md"
    ]
    
    for p in test_paths:
        compliant, errors = validate_taxonomy_compliance(p)
        status = "PASS" if compliant else "FAIL"
        print(f"Path: {p:<50} | Status: {status}")
        for err in errors:
            print(f"  -> {err}")

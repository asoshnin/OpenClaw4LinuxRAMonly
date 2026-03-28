"""
Vault Intelligent Router Tool - Sprint 8
Maps note metadata to the Johnny.Decimal folder taxonomy.
"""

import os
from typing import Optional, Dict, Any

# Domain to Folder Mapping based on the Master Obsidian Manual (Gist)
DOMAIN_MAP = {
    "Finance": "21 - Finance",
    "Health": "22 - Health",
    "AI-Research": "23 - AI-Research",
    "Tourism": "24 - Tourism",
    "Cooking": "25 - Cooking",
    "Professional": "20 - AREAS" # Fallback for general area
}

def suggest_vault_path(metadata: Dict[str, Any], filename: str) -> str:
    """
    Suggests the correct Johnny.Decimal path for a note based on its YAML metadata.
    
    Rules:
    1. If type is 'project', move to 10 - PROJECTS.
    2. If domain matches a known AREA, move to 20 - AREAS/[Subfolder].
    3. If type is 'resource', move to 30 - RESOURCES.
    4. Default fallback: 00 - INBOX (requires manual triage).
    """
    note_type = metadata.get("type", "note").lower()
    domain = metadata.get("domain", "")
    project = metadata.get("project", "")

    # 1. Route Projects
    if note_type == "project" or project:
        # We assume projects are organized numerically in 10 - PROJECTS
        # If we had a project registry, we could be more specific.
        return f"10 - PROJECTS/{filename}"

    # 2. Route Areas (Domains)
    if domain in DOMAIN_MAP:
        area_folder = DOMAIN_MAP[domain]
        # Check if it's a specific sub-area folder or just the root 20
        if area_folder.startswith("2"):
            return f"20 - AREAS/{area_folder}/{filename}"
        return f"{area_folder}/{filename}"

    # 3. Route Resources
    if note_type == "resource":
        return f"30 - RESOURCES/{filename}"

    # 4. Fallback
    return f"00 - INBOX/{filename}"

if __name__ == "__main__":
    # Test cases
    test_meta_1 = {"type": "note", "domain": "AI-Research"}
    print(f"Test 1 (AI Note): {suggest_vault_path(test_meta_1, 'LLM_Basics.md')}")
    
    test_meta_2 = {"type": "project", "project": "HiveForge"}
    print(f"Test 2 (Project): {suggest_vault_path(test_meta_2, 'Sprint_Plan.md')}")
    
    test_meta_3 = {"type": "resource", "domain": "Cooking"}
    print(f"Test 3 (Resource): {suggest_vault_path(test_meta_3, 'Dutch_Oven_Guide.md')}")

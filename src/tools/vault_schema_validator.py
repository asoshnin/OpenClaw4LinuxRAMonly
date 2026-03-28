"""
Vault Schema Validator Tool - Sprint 8
Enforces YAML frontmatter integrity and Johnny.Decimal folder alignment.
"""

import re
import yaml
from pathlib import Path

def validate_vault_metadata(content: str, expected_path: str = None) -> dict:
    """
    Validates Markdown content against the Universal Note Template schema.
    
    Checks:
    1. Presence of YAML frontmatter.
    2. Mandatory fields: id, type, status, summary, keywords.
    3. Johnny.Decimal folder alignment (if path provided).
    4. ID format (prefix-YYYYMMDDHHmm).
    """
    results = {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "metadata": {}
    }

    # 1. Extract YAML
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        results["is_valid"] = False
        results["errors"].append("Missing or malformed YAML frontmatter.")
        return results

    try:
        data = yaml.safe_load(match.group(1))
        results["metadata"] = data
    except Exception as e:
        results["is_valid"] = False
        results["errors"].append(f"YAML Parse Error: {str(e)}")
        return results

    # 2. Field Validation
    mandatory_fields = ["id", "type", "status", "summary", "keywords"]
    for field in mandatory_fields:
        if field not in data or not data[field]:
            results["is_valid"] = False
            results["errors"].append(f"Missing mandatory field: '{field}'")

    # 3. ID Format Validation (prefix-YYYYMMDDHHmm)
    if "id" in data:
        id_val = str(data["id"])
        if not re.match(r"^\d+\.\d+-\d{12}$", id_val):
            results["warnings"].append(f"ID '{id_val}' does not strictly follow Johnny.Decimal-Timestamp format (e.g. 23.01-202603271200)")

    # 4. Folder Alignment (Johnny.Decimal enforcement)
    if expected_path:
        path_parts = Path(expected_path).parts
        for part in path_parts:
            # Check if folders have the "NN - " prefix
            if part != "." and not re.match(r"^\d{2} - ", part) and "openclaw" not in part.lower():
                results["warnings"].append(f"Path component '{part}' lacks standard Johnny.Decimal numerical prefix.")

    return results

if __name__ == "__main__":
    # Quick test
    sample = """---
id: "23.01-202603271200"
type: note
status: active
summary: "Testing the validator tool."
keywords: [test, validator]
---
# Content here
"""
    print(validate_vault_metadata(sample, "20 - AREAS/23 - AI-Research/test.md"))

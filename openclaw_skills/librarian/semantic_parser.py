"""
Semantic Extractor Tool (LIB-01.2)
Standalone deterministic module to extract a strict capability graph from raw file content.
Zero-shot LLM parsing is used for markdown, and strict JSON parsing for manifest files.
"""

import json
import logging
import sys
import os

from config import call_inference, LOCAL_MODEL

# Safe import for self_healing inside the factory environment
try:
    from librarian.self_healing import parse_json_with_retry
except ImportError:
    try:
        from openclaw_skills.librarian.self_healing import parse_json_with_retry
    except ImportError:
        # Fallback if run directly in the dir
        from self_healing import parse_json_with_retry

logger = logging.getLogger(__name__)

def extract_semantics(file_content: str, file_type: str) -> dict:
    """
    Extract a deterministic semantic schema from file_content.
    
    If file_type is 'json', parses description/capabilities/dependencies directly.
    If file_type is 'md', invokes zero-shot LLM parsing using LOCAL_MODEL.
    
    Returns:
        {"description": str, "capabilities": list, "dependencies": list}
    """
    default_out = {"description": "", "capabilities": [], "dependencies": []}
    
    if not file_content.strip():
        return default_out

    if file_type.lower() == "json":
        try:
            data = json.loads(file_content)
            # handle package.json with openclaw metadata vs plugin.json
            oc = data.get("openclaw", data)
            desc = oc.get("description") or data.get("description") or ""
            caps = oc.get("capabilities", [])
            deps = oc.get("dependencies", [])
            if isinstance(deps, dict):
                deps = list(deps.keys())
            return {
                "description": str(desc).strip(),
                "capabilities": caps if isinstance(caps, list) else [],
                "dependencies": deps if isinstance(deps, list) else []
            }
        except Exception as e:
            logger.warning("Error parsing JSON for semantics: %s", e)
            return default_out

    # Handle Markdown (SKILL.md) using zero-shot LLM
    prompt = f"""Extract the core semantics from the following markdown file.
You must output ONLY raw JSON formatted EXACTLY to this schema, with no additional text or markdown formatting:
{{
  "description": "A concise 1-2 sentence summary of the primary purpose.",
  "capabilities": ["capability one", "capability two"],
  "dependencies": ["dependency one", "dependency two"]
}}

File Content:
{file_content[:4000]}
"""

    def _model_call(p: str) -> str:
        # LLM repair call for self-healing, always targeting Local Model per requirements.
        return call_inference("cpu", LOCAL_MODEL, p)

    try:
        raw = call_inference("cpu", LOCAL_MODEL, prompt)
        
        # Cleanup potential markdown hallucination around JSON string
        raw_clean = raw.strip()
        if raw_clean.startswith("```json"):
            raw_clean = raw_clean[7:]
        if raw_clean.endswith("```"):
            raw_clean = raw_clean[:-3]
        raw_clean = raw_clean.strip()

        parsed = parse_json_with_retry(raw_clean, _model_call, max_retries=2)

        raw_desc = parsed.get("description", "")
        raw_caps = parsed.get("capabilities", [])
        raw_deps = parsed.get("dependencies", [])

        # Strict coercion
        if not isinstance(raw_caps, list):
            raw_caps = []
        if not isinstance(raw_deps, list):
            raw_deps = []

        return {
            "description": str(raw_desc).strip(),
            "capabilities": raw_caps,
            "dependencies": raw_deps
        }
    except Exception as e:
        logger.warning("LLM semantic extraction failed: %s", e)
        # Attempt minimal fallback on total failure
        desc = ""
        lines = file_content.splitlines()
        for idx, line in enumerate(lines):
            if line.startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        return {"description": desc, "capabilities": [], "dependencies": []}


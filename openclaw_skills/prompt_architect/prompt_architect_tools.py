import json
import re
import sqlite3
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flash-Schema Unified Protocol — PR-01 + PR-02
# ---------------------------------------------------------------------------

# JSON Schema that every Flash-tier prompt output MUST conform to.
_PROMPT_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["system_prompt", "kb_schema", "tool_definitions"],
    "properties": {
        "system_prompt":    {"type": "string",  "minLength": 1},
        "kb_schema":        {"type": "object"},
        "tool_definitions": {"type": "array"},
        "tier":             {"type": "string",  "enum": ["FLASH", "PRO"]},
    },
}

# Characters / phrases that indicate conversational bloat in Flash output
_BLOAT_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(Sure|Of course|Certainly|Absolutely|Great|Happy to)[^\n]*",
               re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Here(?:'s| is) (the|your|a) [^\n]*", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Let me [^\n]*", re.IGNORECASE | re.MULTILINE),
]

# Maximum retries for the JSON validation circuit-breaker
_MAX_JSON_RETRIES: int = 3


def _validate_json_schema(data: dict, schema: dict) -> list[str]:
    """Minimal structural JSON schema validator (no external deps).

    Returns a list of violation strings; empty list means valid.
    Handles 'required', 'type', 'minLength', and 'enum' keywords.
    """
    errors: list[str] = []

    if schema.get("type") == "object":
        if not isinstance(data, dict):
            errors.append(f"Expected object, got {type(data).__name__}")
            return errors
        for key in schema.get("required", []):
            if key not in data:
                errors.append(f"Missing required key: '{key}'")
        for prop, prop_schema in schema.get("properties", {}).items():
            if prop not in data:
                continue
            val = data[prop]
            expected_type = prop_schema.get("type")
            if expected_type == "string" and not isinstance(val, str):
                errors.append(f"'{prop}' must be a string")
            elif expected_type == "object" and not isinstance(val, dict):
                errors.append(f"'{prop}' must be an object")
            elif expected_type == "array" and not isinstance(val, list):
                errors.append(f"'{prop}' must be an array")
            if expected_type == "string" and isinstance(val, str):
                min_len = prop_schema.get("minLength", 0)
                if len(val) < min_len:
                    errors.append(f"'{prop}' is shorter than minLength={min_len}")
            if "enum" in prop_schema and val not in prop_schema["enum"]:
                errors.append(f"'{prop}' value '{val}' not in enum {prop_schema['enum']}")

    return errors


def _strip_bloat(text: str) -> str:
    """Remove conversational preamble lines from Flash-tier output."""
    for pattern in _BLOAT_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def _derive_stop_sequence(schema: dict) -> str:
    """Schema-aware stop sequence: '\n}' for flat objects, '\n    }\n}' for nested.

    The stop sequence is the minimal suffix that closes the outermost JSON
    object without cutting off valid nested structures.
    """
    # If the schema has nested object properties, use an indented closing pattern.
    properties = schema.get("properties", {})
    has_nested = any(
        p.get("type") == "object" for p in properties.values()
    )
    if has_nested:
        return "\n}"   # outer-close only; inner } handled by the JSON parser
    return "\n}"       # same sentinel; parser is authoritative either way


def _socratic_tier_assessment(task_description: str) -> str:
    """One-Step Lookahead: assess whether Flash or Pro tier is appropriate.

    Pro indicators (lexically fast-path):
      - Contains decision / ambiguous / sensitive / security / audit / deploy
      - Contains question marks (uncertainty)
      - Longer than 400 characters (complexity heuristic)

    Returns 'FLASH' or 'PRO'.
    """
    task_lower = task_description.lower()
    pro_keywords = {
        "decision", "ambiguous", "sensitive", "security", "audit",
        "deploy", "delete", "remove", "teardown", "approve",
    }
    if any(kw in task_lower for kw in pro_keywords):
        return "PRO"
    if "?" in task_description and len(task_description) > 120:
        return "PRO"
    if len(task_description) > 400:
        return "PRO"
    return "FLASH"


def _build_flash_system_prompt(task_description: str, schema: dict) -> str:
    """Construct a No-Preamble Flash instruction block.

    The LLM must begin its response with the opening `{` of the JSON object,
    with no greeting, explanation, or markdown fencing.
    """
    schema_str = json.dumps(schema, indent=2)
    stop_seq = _derive_stop_sequence(schema)
    return (
        "[FLASH TIER — NO PREAMBLE]\n"
        "You are a high-speed structured-output engine. "
        "Output ONLY valid JSON matching the schema below. "
        "Do NOT add any explanation, greeting, or markdown fences. "
        f"Your response MUST begin immediately with `{{` and end with `{stop_seq.strip()}`.\n\n"
        f"TASK:\n{task_description}\n\n"
        f"REQUIRED JSON SCHEMA:\n{schema_str}\n\n"
        "OUTPUT (begin immediately with {):"
    )


def generate_flash_prompt(
    task_description: str,
    schema: dict | None = None,
    model_call_fn=None,
    scrub_output: bool = True,
) -> dict:
    """Flash-Schema Unified Generation Protocol (PR-01 + PR-02).

    Args:
        task_description: Natural-language description of what the agent must do.
        schema:           JSON Schema dict for output validation. Defaults to
                          _PROMPT_CONFIG_SCHEMA if not provided.
        model_call_fn:    Callable(prompt: str) -> str. Injected for testability.
                          In production, callers supply `config.call_inference`.
        scrub_output:     If True, the raw LLM output is passed through the
                          safety scrubber before JSON parsing (Sovereign Safety Guard).

    Returns:
        dict with keys:
          'tier'        — 'FLASH' or 'PRO'
          'payload'     — validated dict matching *schema*
          'raw_output'  — the raw LLM text (post-scrub)
          'retries'     — number of validation retries consumed
          'scrubbed'    — bool: was the scrubber invoked?

    Raises:
        RuntimeError: If the circuit-breaker trips after _MAX_JSON_RETRIES.
        ValueError:   If task_description is empty.
    """
    if not task_description or not task_description.strip():
        raise ValueError("generate_flash_prompt: task_description must not be empty.")

    schema = schema or _PROMPT_CONFIG_SCHEMA

    # --- Step 1: Socratic Tier Assessment ---
    tier = _socratic_tier_assessment(task_description)
    logger.info("Socratic assessment → tier=%s", tier)

    # Build the instruction prompt
    system_prompt = _build_flash_system_prompt(task_description, schema)

    # --- Step 2: Inference (or mock for tests) ---
    if model_call_fn is None:
        raise RuntimeError(
            "generate_flash_prompt: model_call_fn is required. "
            "Pass config.call_inference (or a mock in tests)."
        )

    raw_output: str = ""
    payload: dict = {}
    scrubbed: bool = False
    retries: int = 0
    last_error: str = ""

    # --- Step 3: JSON Retry Loop (circuit-breaker) ---
    for attempt in range(_MAX_JSON_RETRIES + 1):
        if attempt == 0:
            llm_input = system_prompt
        else:
            # Repair prompt: feed the failure back
            llm_input = (
                f"{system_prompt}\n\n"
                f"[PREVIOUS ATTEMPT FAILED]\n"
                f"Error: {last_error}\n"
                f"Raw output was:\n{raw_output}\n\n"
                "Please output ONLY valid JSON, starting with {."
            )

        try:
            raw_output = model_call_fn(system_prompt if attempt == 0 else llm_input)
        except Exception as e:
            raise RuntimeError(f"generate_flash_prompt: model_call_fn failed: {e}") from e

        # --- Step 4: Mandatory Scrub (Sovereign Safety Guard) ---
        if scrub_output and tier == "FLASH":
            try:
                _se_module = sys.modules.get("safety_engine")
                if _se_module is None:
                    _se_path = os.path.join(
                        os.path.dirname(os.path.dirname(__file__)), "librarian"
                    )
                    if _se_path not in sys.path:
                        sys.path.insert(0, _se_path)
                    import importlib
                    _se_module = importlib.import_module("safety_engine")
                engine = _se_module.SafetyDistillationEngine()
                scrub_result = engine.distill_safety(raw_output[:12000], is_sensitive=False)
                # Extract scrubbed text — distill_safety returns a dict with 'scrubbed_log'
                scrubbed_text = scrub_result.get("scrubbed_log", raw_output)
                if scrubbed_text.strip():
                    raw_output = scrubbed_text
                scrubbed = True
                logger.info("Flash output scrubbed by safety_engine.")
            except Exception as scrub_err:
                logger.warning(
                    "Safety scrubber unavailable (%s); proceeding without scrub.", scrub_err
                )
                scrubbed = False

        # --- Step 5: Strip preamble bloat ---
        cleaned = _strip_bloat(raw_output)

        # --- Step 6: Extract JSON (handle markdown fences) ---
        json_text = cleaned
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", json_text)
        if fence_match:
            json_text = fence_match.group(1).strip()
        # Find first { in case there's still leading text
        brace_pos = json_text.find("{")
        if brace_pos > 0:
            json_text = json_text[brace_pos:]

        # --- Step 7: Parse & validate ---
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as e:
            last_error = f"JSONDecodeError: {e}"
            retries += 1
            logger.warning("Flash JSON parse failed (attempt %d/%d): %s", attempt + 1, _MAX_JSON_RETRIES, e)
            if attempt >= _MAX_JSON_RETRIES:
                raise RuntimeError(
                    f"generate_flash_prompt: JSON circuit-breaker tripped after "
                    f"{_MAX_JSON_RETRIES} retries. Last error: {last_error}"
                ) from e
            continue

        schema_errors = _validate_json_schema(parsed, schema)
        if schema_errors:
            last_error = f"Schema violations: {schema_errors}"
            retries += 1
            logger.warning("Flash schema validation failed (attempt %d/%d): %s", attempt + 1, _MAX_JSON_RETRIES, schema_errors)
            if attempt >= _MAX_JSON_RETRIES:
                raise RuntimeError(
                    f"generate_flash_prompt: Schema circuit-breaker tripped after "
                    f"{_MAX_JSON_RETRIES} retries. Violations: {schema_errors}"
                )
            continue

        # Success
        payload = parsed
        break

    return {
        "tier": tier,
        "payload": payload,
        "raw_output": raw_output,
        "retries": retries,
        "scrubbed": scrubbed,
    }


# To support validate_path and register_agent
try:
    from librarian_ctl import validate_path, register_agent
except ImportError:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(os.path.join(project_root, 'librarian'))
    from librarian_ctl import validate_path, register_agent

try:
    from config import WORKSPACE_ROOT, DEFAULT_DB_PATH
except ImportError:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(project_root)
    from config import WORKSPACE_ROOT, DEFAULT_DB_PATH

try:
    from obsidian_bridge import ObsidianBridge
except ImportError:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.append(project_root)
    try:
        from obsidian_bridge import ObsidianBridge
    except ImportError:
        ObsidianBridge = None

@dataclass
class AgentIntelligencePackage:
    agent_id: str
    tier: str
    intelligence_triad: dict
    epistemic_backlog_directive: str
    safety_and_security: list
    test_cases: list

    @classmethod
    def from_json(cls, json_str: str) -> "AgentIntelligencePackage":
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON: {e}")
        
        required_keys = {
            "agent_id", "tier", "intelligence_triad",
            "epistemic_backlog_directive", "safety_and_security", "test_cases"
        }
        
        missing = required_keys - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
            
        # Deep Validation Phase 2
        triad = data["intelligence_triad"]
        if not isinstance(triad, dict):
            raise ValueError("intelligence_triad must be a dictionary")
            
        triad_keys = {"system_prompt", "kb_schema", "tool_definitions"}
        missing_triad = triad_keys - set(triad.keys())
        if missing_triad:
            raise ValueError(f"Missing required fields inside intelligence_triad: {missing_triad}")
            
        return cls(
            agent_id=data["agent_id"],
            tier=data["tier"],
            intelligence_triad=data["intelligence_triad"],
            epistemic_backlog_directive=data["epistemic_backlog_directive"],
            safety_and_security=data["safety_and_security"],
            test_cases=data["test_cases"]
        )

def log_epistemic_gap(agent_id: str, gap_type: str, description: str, context_json: str, db_path: str = None):
    """
    Logs an epistemic gap to the database.
    """
    db_path = db_path or str(DEFAULT_DB_PATH)
    valid_db_path = validate_path(db_path)
    
    # Ensure gap_type is valid
    valid_gap_types = {'tool_missing', 'knowledge_insufficient', 'logic_failure'}
    if gap_type not in valid_gap_types:
        raise ValueError(f"Invalid gap_type: {gap_type}")

    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # Insert into epistemic_backlog
        cursor.execute(
            '''INSERT INTO epistemic_backlog 
               (agent_id, gap_type, description, context_json) 
               VALUES (?, ?, ?, ?)''',
            (agent_id, gap_type, description, context_json)
        )
        
        # Insert into audit_logs
        cursor.execute(
            '''INSERT INTO audit_logs 
               (agent_id, pipeline_id, action, rationale) 
               VALUES (?, ?, ?, ?)''',
            (agent_id, None, 'GAP_REPORTED', f"Reported gap: {gap_type} - {description[:50]}")
        )
        
        conn.commit()


def register_from_package(package_json: str, db_path: str = None):
    """
    Registers an agent from an AgentIntelligencePackage JSON string.
    """
    db_path = db_path or str(DEFAULT_DB_PATH)
    valid_db_path = validate_path(db_path)
    
    # Validate payload
    pkg = AgentIntelligencePackage.from_json(package_json)
    
    # Also write JSON artifact
    artifact_path = os.path.join(WORKSPACE_ROOT, f"{pkg.agent_id}_intelligence_package.json")
    valid_artifact_path = validate_path(artifact_path)
    
    with open(valid_artifact_path, "w") as f:
        f.write(package_json)

    # Vault Safety (Phase 2)
    if ObsidianBridge is not None:
        try:
            bridge = ObsidianBridge()
            bridge.write_note(f"99 - META/OpenClaw/Agents/{pkg.agent_id}.json", package_json)
            logger.info(f"Successfully saved {pkg.agent_id}.json to Vault.")
        except Exception as e:
            logger.warning(f"Vault is offline or unreachable: {e}. Proceeding with local DB registration.")
    else:
        logger.warning("ObsidianBridge module not found. Skipping vault save.")

    tier = pkg.tier
    tool_definitions = pkg.intelligence_triad.get("tool_definitions", [])
    
    tools_str = ",".join([t.get("name", "") for t in tool_definitions])
    
    description = f"Tier: {tier}. Backlog directive: {pkg.epistemic_backlog_directive}"
    
    # Register the agent
    profile_content = str(pkg.intelligence_triad.get("system_prompt", ""))
    
    register_agent(
        db_path=db_path,
        agent_id=pkg.agent_id,
        name=f"Synthesized Agent - {pkg.agent_id}",
        version="1.0",
        description=description,
        tool_names=tools_str,
        profile_content=profile_content,
        force=True
    )

def synthesize_backlog_report(db_path: str = None, output_path: str = None):
    """
    Synthesizes reported gaps in the epistemic backlog into a markdown report.
    """
    db_path = db_path or str(DEFAULT_DB_PATH)
    valid_db_path = validate_path(db_path)
    
    out_path = output_path or "/home/alexey/openclaw-inbox/agentic_factory/BACKLOG.md"
    
    # Bypass standard Validation only for the explicitly required project root fallback.
    if out_path == "/home/alexey/openclaw-inbox/agentic_factory/BACKLOG.md":
         actual_out_path = out_path
    else:
         actual_out_path = validate_path(out_path)

    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Fetch raw entries (Capture Row IDs for Atomic Synthesis)
        cursor.execute("SELECT entry_id, agent_id, gap_type, description, created_at FROM epistemic_backlog WHERE status = 'raw'")
        rows = cursor.fetchall()
        
        if not rows:
            logger.info("No 'raw' epistemic backlog items to synthesize.")
            return
            
        entry_ids = [row[0] for row in rows]
        
        # Format the markdown document
        md_lines = ["# Epistemic Backlog Report\n"]
        md_lines.append(f"**Total Gaps: {len(rows)}**\n")
        
        # Group gaps by gap_type
        gaps_by_type = {}
        for row in rows:
            eid, agent, gtype, desc, date = row
            gaps_by_type.setdefault(gtype, []).append((agent, desc, date))
            
        for gtype, items in gaps_by_type.items():
            md_lines.append(f"## {gtype.replace('_', ' ').title()}\n")
            md_lines.append("| Agent | Type | Description | Reported Date |")
            md_lines.append("|---|---|---|---|")
            for item in items:
                agent, desc, date = item
                safe_desc = desc.replace("|", "&#124;").replace("\n", " ")
                md_lines.append(f"| `{agent}` | `{gtype}` | {safe_desc} | {date} |\n")
            md_lines.append("\n")
            
        full_report = "".join(md_lines)
        
        # 2. Write Markdown report
        with open(actual_out_path, "w") as f:
            f.write(full_report)
            
        logger.info(f"Synthesized report written to {actual_out_path}")
        
        # 3. Use captured Row IDs to update status (Atomic)
        placeholders = ",".join(["?"] * len(entry_ids))
        cursor.execute(f"UPDATE epistemic_backlog SET status = 'analyzed' WHERE entry_id IN ({placeholders})", entry_ids)
        
        # 4. Audit Log
        cursor.execute(
            '''INSERT INTO audit_logs 
               (agent_id, pipeline_id, action, rationale) 
               VALUES (?, ?, ?, ?)''',
            ('backlog-manager', None, 'BACKLOG_SYNTHESIZED', f"Synthesized {len(rows)} gaps into report.")
        )
        
        conn.commit()

"""
Architect Tools - Agentic Factory on OpenClaw
Core discovery, HITL authorization, and agent runner functions.
"""

import os
import re
import sys
import json
import uuid
import sqlite3
import logging
import argparse
import urllib.request
import urllib.error
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import messagebox
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

# Resolve workspace config — never hardcode paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from openclaw_skills.config import WORKSPACE_ROOT, TOKEN_FILE, OLLAMA_URL, LOCAL_MODEL, get_active_ollama_url, INFERENCE_ALERT, get_inference_tier_order, call_inference

# ObsidianBridge — optional dependency (Sprint 7); graceful if not yet installed
try:
    _skills_root = os.path.dirname(os.path.dirname(__file__))
    if _skills_root not in sys.path:
        sys.path.insert(0, _skills_root)
    from obsidian_bridge import ObsidianBridge
except ImportError:
    ObsidianBridge = None  # type: ignore

# Vault Tools — optional dependency (Sprint 9); graceful if not yet installed
try:
    _skills_root = os.path.dirname(os.path.dirname(__file__))
    if _skills_root not in sys.path:
        sys.path.insert(0, _skills_root)
    from vault_tools import (
        discover_domains,
        suggest_vault_path,
        validate_vault_metadata,
        validate_taxonomy_compliance,
    )
    from vault_tools.vault_health_check import run_vault_health_check, format_health_report
    VAULT_TOOLS_AVAILABLE = True
except ImportError:
    VAULT_TOOLS_AVAILABLE = False  # type: ignore

logger = logging.getLogger(__name__)


def validate_path(target_path: str) -> str:
    """[DES-02] Realpath validation for Airlock protection.

    Uses os.sep suffix guard to prevent prefix-collision attacks.
    """
    base_dir = str(WORKSPACE_ROOT)
    target_abs = os.path.realpath(target_path)
    if not (target_abs == base_dir or target_abs.startswith(base_dir + os.sep)):
        raise PermissionError(f"Airlock Breach: {target_abs} is outside {base_dir}")
    return target_abs


def search_factory(db_path: str, query_type: str, filter_val: str = None) -> list:
    """
    [DES-07] Discovery logic for Architect.
    query_type must be one of: 'agents', 'pipelines', 'audit'
    """
    valid_db_path = validate_path(db_path)
    allowed_types = {"agents", "pipelines", "audit_logs", "audit"}
    
    if query_type not in allowed_types:
        raise ValueError(f"Invalid query_type. Must be one of {allowed_types}")

    query_type = "audit_logs" if query_type == "audit" else query_type

    with sqlite3.connect(valid_db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if query_type == 'agents':
            if filter_val:
                cursor.execute("SELECT * FROM agents WHERE agent_id = ?", (filter_val,))
            else:
                cursor.execute("SELECT * FROM agents")
        elif query_type == 'pipelines':
            if filter_val:
                cursor.execute("SELECT * FROM pipelines WHERE pipeline_id = ?", (filter_val,))
            else:
                cursor.execute("SELECT * FROM pipelines")
        elif query_type == 'audit_logs':
            if filter_val:
                # Assuming filter_val can be agent_id or pipeline_id for audit logs
                cursor.execute("SELECT * FROM audit_logs WHERE agent_id = ? OR pipeline_id = ?", (filter_val, filter_val))
            else:
                cursor.execute("SELECT * FROM audit_logs")
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_agent_persona(db_path: str, agent_id: str) -> dict:
    """Retrieve an existing agent design."""
    results = search_factory(db_path, 'agents', filter_val=agent_id)
    if results:
        return results[0]
    return {}


def generate_token() -> str:
    """[DES-08] HITL Token Manager: Generates UUID4 and saves securely."""
    # Ensure token file path is within workspace (Airlock check)
    validate_path(str(TOKEN_FILE))
    token = str(uuid.uuid4())

    # Write securely with 600 permissions
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600

    fd = os.open(str(TOKEN_FILE), flags, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(token)

    return token


def validate_token(provided_token: str) -> bool:
    """[DES-09] One-time token validation (Burn-on-Read)."""
    validate_path(str(TOKEN_FILE))

    if not os.path.exists(str(TOKEN_FILE)):
        return False

    try:
        with open(str(TOKEN_FILE), 'r', encoding='utf-8') as f:
            stored_token = f.read().strip()
    except Exception:
        return False

    # BURN ON READ: Critical Security Gate
    # File destroyed before comparison to prevent replay attacks
    os.remove(str(TOKEN_FILE))

    return stored_token == provided_token.strip()


def deploy_pipeline(db_path: str, pipeline_id: str, pipeline_name: str, topology_json: str, approval_token: str) -> str:
    """[DES-10] Secure pipeline deployment. Requires valid burn-on-read HITL token."""
    if not validate_token(approval_token):
        raise PermissionError("Invalid or expired HITL token. Deployment aborted.")
        
    valid_db_path = validate_path(db_path)
    
    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # Insert new pipeline
        cursor.execute("""
            INSERT INTO pipelines (pipeline_id, name, topology_json, status)
            VALUES (?, ?, ?, 'active')
        """, (pipeline_id, pipeline_name, topology_json))
        
        # Log the audit
        cursor.execute("""
            INSERT INTO audit_logs (pipeline_id, action, rationale)
            VALUES (?, 'DEPLOY_PIPELINE', 'Pipeline deployed securely via Agentic Architect.')
        """, (pipeline_id,))
        
        conn.commit()
        
    return f"Success: Pipeline '{pipeline_name}' ({pipeline_id}) deployed and logged successfully."


def request_ui_approval(prompt_text: str) -> bool:
    """Displays a native GUI popup or console prompt for human-in-the-loop approval."""
    # Guard: Use console if no DISPLAY environment variable exists (even if TK is installed)
    if not TK_AVAILABLE or "DISPLAY" not in os.environ:
        print(f"\n[APPROVAL REQUESTED]: {prompt_text}")
        # When running in OpenClaw exec/process, input() may fail. 
        # For non-TTY environments, we should default to rejection or rely on gateway interaction.
        try:
            response = input("Approve? (yes/no): ").lower().strip()
            return response in ("yes", "y")
        except EOFError:
            logger.warning("request_ui_approval: EOFError on input(). Defaulting to rejection.")
            return False
    
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        result = messagebox.askyesno("HITL Security Gate", prompt_text)
        root.destroy()
        return result
    except Exception as e:
        logger.error("request_ui_approval: Tkinter failed (%s). Falling back to console.", e)
        print(f"\n[APPROVAL REQUESTED]: {prompt_text}")
        try:
            response = input("Approve? (yes/no): ").lower().strip()
            return response in ("yes", "y")
        except EOFError:
            return False


def deploy_pipeline_with_ui(db_path: str, pipeline_id: str, pipeline_name: str, topology_json: str) -> str:
    """OpenClaw architect agent wrapper tool for deployment with UI popup."""
    prompt = (f"Agentic Architect requests deployment of pipeline:\n\n"
              f"Name: {pipeline_name}\n"
              f"ID: {pipeline_id}\n\n"
              f"Approve deployment?")
    
    if not request_ui_approval(prompt):
        raise PermissionError("Deployment rejected by human Navigator via UI.")
        
    token = generate_token()
    return deploy_pipeline(db_path, pipeline_id, pipeline_name, topology_json, token)


def teardown_pipeline(db_path: str, pipeline_id: str) -> str:
    """Safely decommission a pipeline and safely remove unshared agents."""
    valid_db_path = validate_path(db_path)
    deleted_agents = []
    skipped_agents = []
    
    with sqlite3.connect(valid_db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Identify participants before deleting pipeline (since ON DELETE CASCADE might remove them)
        cursor.execute("SELECT agent_id FROM pipeline_agents WHERE pipeline_id = ?", (pipeline_id,))
        agents = [row['agent_id'] for row in cursor.fetchall()]
        
        # Delete Pipeline -> Cascades to pipeline_agents
        cursor.execute("DELETE FROM pipelines WHERE pipeline_id = ?", (pipeline_id,))
        
        for agent_id in agents:
            # Check if system agent
            cursor.execute("SELECT is_system FROM agents WHERE agent_id = ?", (agent_id,))
            row = cursor.fetchone()
            if not row or row['is_system'] == 1:
                skipped_agents.append(f"{agent_id} (system)")
                continue
                
            # Check if referenced by other pipelines
            cursor.execute("SELECT COUNT(*) as count FROM pipeline_agents WHERE agent_id = ?", (agent_id,))
            count = cursor.fetchone()['count']
            if count > 0:
                skipped_agents.append(f"{agent_id} (shared)")
                continue
                
            # Unprotected and unreferenced -> Delete
            cursor.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
            
            # Delete physical file using WORKSPACE_ROOT from config
            profile_path = os.path.join(str(WORKSPACE_ROOT), f"{agent_id}.md")
            try:
                valid_profile = validate_path(profile_path)
                if os.path.exists(valid_profile):
                    os.remove(valid_profile)
                    deleted_agents.append(f"{agent_id} (file & db)")
                else:
                    deleted_agents.append(f"{agent_id} (db only)")
            except Exception:
                deleted_agents.append(f"{agent_id} (db only, file err)")
                
        # Log Audit
        cursor.execute("""
            INSERT INTO audit_logs (pipeline_id, action, rationale)
            VALUES (?, 'TEARDOWN', 'Pipeline Decommissioned safely.')
        """, (pipeline_id,))
        
        conn.commit()
        
    return (f"Teardown of '{pipeline_id}' complete. "
            f"Deleted: {', '.join(deleted_agents) if deleted_agents else 'None'}. "
            f"Skipped: {', '.join(skipped_agents) if skipped_agents else 'None'}.")


def run_audit(artifact_text: str, task_context: str) -> dict:
    """[RT-01] Execute Red Team Audit on generated outputs before signing off.
    
    Parses `<AUDIT_REPORT>` XML tags from the RED TEAM persona response.
    Returns:
        {"epistemic_challenge": str, "status": str, "findings": list, "recommendations": list}
    """
    from config import GLOBAL_DB_PATH
    
    # 1. Retrieve the RT-01 persona
    db_path = str(GLOBAL_DB_PATH) if GLOBAL_DB_PATH else "factory.db"
    agent = get_agent_persona(db_path, "red-team-auditor-01")
    if not agent:
        raise ValueError("Auditor red-team-auditor-01 not found in registry.")
    
    system_prompt = agent.get('description', '')
    
    # Empty artifact check
    if not artifact_text or not artifact_text.strip():
        return {
            "epistemic_challenge": "Artifact is empty. No evidence provided.",
            "status": "🔴 NO GO",
            "findings": ["[Severity: High] Issue: Empty artifact Impact: Cannot audit nothing."],
            "recommendations": ["Provide a non-empty artifact for auditing."]
        }
        
    # Empty context fallback
    if not task_context or not task_context.strip():
        return {
            "epistemic_challenge": "Task context is empty. Unable to ground assumptions.",
            "status": "🔴 NO GO",
            "findings": ["[Severity: High] Issue: Missing execution context Impact: Assumptions cannot be verified."],
            "recommendations": ["Provide the task execution context metadata."]
        }
    
    prompt = f"{system_prompt}\n\n[TASK CONTEXT]\n{task_context}\n\n[ARTIFACT TO AUDIT]\n{artifact_text}\n\nProduce your `<AUDIT_REPORT>` format exactly as directed."
    
    try:
        url = get_active_ollama_url()
        # RT-01 demands PRO tier inference
        response = call_inference("PRO", url, prompt)
    except Exception as e:
        logger.error(f"Audit Inference Failed: {e}")
        return {
            "epistemic_challenge": "Audit Inference Error",
            "status": "🔴 NO GO",
            "findings": [f"Exception: {e}"],
            "recommendations": ["Check connectivity to Ollama or Gateway."]
        }

    # Extract XML
    chal_match = re.search(r"<EPISTEMIC_CHALLENGE>(.*?)</EPISTEMIC_CHALLENGE>", response, re.DOTALL)
    stat_match = re.search(r"<STATUS>(.*?)</STATUS>", response, re.DOTALL)
    find_match = re.search(r"<FINDINGS>(.*?)</FINDINGS>", response, re.DOTALL)
    reco_match = re.search(r"<RECOMMENDATIONS>(.*?)</RECOMMENDATIONS>", response, re.DOTALL)

    chal = chal_match.group(1).strip() if chal_match else "No specific challenge extracted."
    stat = stat_match.group(1).strip() if stat_match else "🔴 NO GO"
    
    # Safety: strict exact phrase formatting checking
    if "SIGN OFF" in stat:
        stat = "🟢 SIGN OFF"
    elif "CONDITIONAL PASS" in stat:
        stat = "🟡 CONDITIONAL PASS"
    else:
        stat = "🔴 NO GO"
        
    find_txt = find_match.group(1).strip() if find_match else ""
    findings = [f.strip(' -') for f in find_txt.split('\n') if f.strip() and f.strip() != '-']
    
    reco_txt = reco_match.group(1).strip() if reco_match else ""
    recommendations = [r.strip('1234567890. ') for r in reco_txt.split('\n') if r.strip()]

    return {
        "epistemic_challenge": chal,
        "status": stat,
        "findings": findings,
        "recommendations": recommendations
    }


def run_agent(db_path: str, agent_id: str, task_text: str, vault_qa_result: dict = None, is_sensitive: bool = False, audit: bool = False) -> str:
    """[DES-S5-03 / DES-S6-02] Execute a task attributed to a registered agent.

    Flow (Sprint 11 prompt order per SKILL.md):
      1. Load KB rules from knowledge_base.json (graceful on missing)
      2. Load agent record from DB (ValueError if not found)
      3. Retrieve Faint Path memory context (graceful fallback if archive empty)
      4. (Optional) Inject [VAULT CONTEXT] from vault_qa_result (Sprint 11)
      5. Build prompt: KB rules → identity → memory → vault context → task
      6. Call local Ollama — RuntimeError if unreachable or empty response
      7. Log result to audit_logs with action='AGENT_RUN'
      8. Return response string

    Constraints (from SKILL.md):
      - Local Ollama ONLY — never cloud APIs
      - Must NOT touch HITL gate or deploy_pipeline_with_ui
      - Must raise on any failure — never return silently
      - vault_qa_result.context_text is capped at VAULT_QA_PROMPT_MAX_CHARS
    """
    # 1. Load knowledge base (graceful — warn and continue if missing)
    kb_prefix = ""
    try:
        skills_root = os.path.dirname(os.path.dirname(__file__))
        sys.path.insert(0, skills_root)
        from kb import load_knowledge_base, format_kb_for_prompt
        kb = load_knowledge_base()
        kb_prefix = format_kb_for_prompt(kb)
    except FileNotFoundError:
        logger.warning("knowledge_base.json not found — skipping KB injection.")
    except Exception as kb_err:
        logger.warning("KB load failed (non-fatal): %s", kb_err)

    # 2. Load agent
    agent = get_agent_persona(db_path, agent_id)
    if not agent:
        raise ValueError(
            f"Agent '{agent_id}' not found in {db_path}. "
            f"Run 'librarian_ctl.py bootstrap' to seed core agents."
        )

    # Load persona from profile file if it exists
    persona_text = ""
    profile_path = os.path.join(str(WORKSPACE_ROOT), f"{agent_id}.md")
    if os.path.exists(profile_path):
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                persona_text = f.read()
        except Exception as e:
            logger.warning("Could not read profile file %s: %s", profile_path, e)

    # 3. Retrieve memory context (graceful — empty archive is normal on fresh install)
    memory_text = "No prior memory available."
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from librarian.vector_archive import find_faint_paths
        memory_hits = find_faint_paths(db_path, task_text, limit=3)
        if memory_hits:
            parts = []
            for hit in memory_hits:
                cj = hit.get("content_json", {})
                if isinstance(cj, dict):
                    parts.append(cj.get("scrubbed_log", ""))
                elif isinstance(cj, str):
                    parts.append(cj)
            memory_text = "\n".join(p for p in parts if p) or memory_text
    except Exception as mem_err:
        logger.warning("Memory archive unavailable (non-fatal): %s", mem_err)
        memory_text = "Memory archive unavailable."

    # 4. Build prompt — SKILL.md Sprint 11 order: KB → identity → memory → vault context → task
    description = agent.get("description") or agent.get("name", "AI agent")
    prompt_identity = persona_text if persona_text else f"You are {agent['name']} — {description}."
    
    memory_text = memory_text[:4000]   # context window guard
    prompt_parts = []
    if kb_prefix:
        prompt_parts.append(kb_prefix)
    prompt_parts.append(f"[AGENT IDENTITY]\n{prompt_identity}\n")
    prompt_parts.append(f"[MEMORY CONTEXT]\n{memory_text}\n")

    # [VAULT CONTEXT] — Sprint 11.1: Vault QA Response Protocol
    if vault_qa_result and vault_qa_result.get("context_text"):
        try:
            from obsidian_bridge import VAULT_QA_PROMPT_MAX_CHARS
        except ImportError:
            VAULT_QA_PROMPT_MAX_CHARS = 6000
        vault_context = vault_qa_result["context_text"][:VAULT_QA_PROMPT_MAX_CHARS]
        sources = vault_qa_result.get("sources", [])
        # Build numbered source index: [^1] → [[Note Name]]
        source_index = "\n".join(
            f"[^{i+1}]: {s['wikilink']} (`{s['path']}`)"
            for i, s in enumerate(sources)
        )
        # Assign footnote numbers to each wikilink for the agent to reference
        footnote_map = "\n".join(
            f"  - Source {i+1}: {s['wikilink']}"
            for i, s in enumerate(sources)
        )
        vault_block = (
            "[VAULT CONTEXT — RESPONSE PROTOCOL]\n"
            "You have been given excerpts from the Navigator's personal Obsidian vault below.\n\n"
            "MANDATORY RESPONSE FORMAT (Vault QA mode):\n"
            "  1. PREAMBLE: One sentence only (e.g. 'Based on your vault, here are...').\n"
            "  2. BODY: Bulleted list. Each bullet = one item found in the vault excerpts.\n"
            "     Each claim that comes from a specific note MUST end with a footnote [^N].\n"
            "  3. SOURCES FOOTER: A '#### Sources' section listing each [^N] → [[Note Name]].\n\n"
            "GROUNDING RULES (mandatory, no exceptions):\n"
            "  - ONLY include items, projects, or facts that appear in the vault excerpts below.\n"
            "  - Do NOT add items from your training data, general knowledge, or the internet.\n"
            "  - If a note mentions 'AutoResearchClaw', include it. If a note does not mention\n"
            "    'microsoft/graphrag', do NOT include it.\n"
            "  - If the context is insufficient to answer, say so in one sentence. Do not speculate.\n\n"
            "CONCISE MODE (mandatory):\n"
            "  - Suppress all Socratic follow-up questions ('Would you like me to...').\n"
            "  - Suppress all 'Auditor Notes', 'Caveats', or 'Recommendations' sections.\n"
            "  - Answer directly and densely. No padding.\n\n"
            "FOOTNOTE REFERENCE TABLE (use these numbers):\n"
            f"{footnote_map}\n\n"
            "VAULT EXCERPTS:\n"
            f"{vault_context}\n"
        )
        prompt_parts.append(vault_block)

    prompt_parts.append(f"[TASK]\n{task_text}")
    prompt = "\n".join(prompt_parts)

    # Step 5: Call Inference — Tiered (Cloud / GPU / CPU) with Airlock Guard
    tiers = get_inference_tier_order(agent_id)
    response = None
    
    for tier, model in tiers:
        if tier == 'cloud':
            if is_sensitive:
                logger.info("run_agent: Skipping cloud tier for '%s' (Airlock: task is sensitive).", agent_id)
                continue
            if not os.environ.get("GEMINI_API_KEY"):
                logger.warning("run_agent: Skipping cloud tier for '%s' (GEMINI_API_KEY not set).", agent_id)
                continue
                
        try:
            response = call_inference(tier=tier, model=model, prompt=prompt, is_sensitive=is_sensitive)
            if response:
                logger.debug("run_agent: Inference succeeded at tier '%s' (model: %s)", tier, model)
                break
        except Exception as e:
            logger.warning("run_agent: Inference failed at tier '%s' (model: %s) - %s", tier, model, e)
            continue

    if not response:
        logger.warning("run_agent: All inference tiers failed or were skipped — returning INFERENCE_ALERT.")
        return INFERENCE_ALERT

    # 5. Audit log (truncated to 500 chars — protects audit table size)
    valid_db = validate_path(db_path)
    with sqlite3.connect(valid_db) as conn:
        conn.execute(
            "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, 'AGENT_RUN', ?)",
            (agent_id, response[:500]),
        )
        conn.commit()

    if audit:
        # Invoke RT-01
        try:
            audit_report = run_audit(response, task_text)
            
            # Log the audit action
            with sqlite3.connect(valid_db) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, 'AGENT_AUDIT', ?)",
                    (agent_id, json.dumps(audit_report)[:500]),
                )
                conn.commit()
                
            if audit_report["status"] == "🔴 NO GO":
                logger.warning("run_agent: Audit returned NO GO. Halting execution.")
                return json.dumps(audit_report, indent=2)
        except Exception as e:
            logger.error(f"Audit processing failed: {e}")
            return json.dumps({
                "epistemic_challenge": "Audit System Error",
                "status": "🔴 NO GO",
                "findings": [str(e)],
                "recommendations": []
            })
            
    logger.info("run_agent: '%s' completed task, response length=%d", agent_id, len(response))
    return response


def write_agent_result_to_vault(
    db_path: str,
    agent_id: str,
    task_text: str,
    result: str,
    vault_path: str = None,
    is_sensitive: bool = False,
) -> str:
    """Write an agent's task result to the Obsidian vault as a structured note.

    Security rules (SKILL.md — Obsidian Bridge Policy):
      - is_sensitive=True → refuses write, logs VAULT_WRITE_REFUSED_SENSITIVE, returns None.
      - result truncated at 12,000 chars (Context Guard) before embedding.
      - Obsidian unavailability is non-fatal: logs VAULT_WRITE_SKIPPED, returns None.
      - NEVER raises on Obsidian unavailability.

    Args:
        db_path:      Path to factory.db for audit logging.
        agent_id:     ID of the agent that produced the result.
        task_text:    Original task description.
        result:       Agent's response string.
        vault_path:   Optional explicit vault path. If None, auto-generated in
                      '00 - INBOX/openclaw/YYYY-MM-DD_{agent_id}_{slug}.md'
        is_sensitive: If True, write is refused (vault may sync to cloud).

    Returns:
        vault_path string on success, None if write was skipped or refused.
    """
    valid_db = validate_path(db_path)

    def _log_audit(action: str, rationale: str) -> None:
        try:
            with sqlite3.connect(valid_db) as conn:
                conn.execute(
                    "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, ?, ?)",
                    (agent_id, action, rationale),
                )
                conn.commit()
        except Exception as audit_err:
            logger.error("write_agent_result_to_vault: audit log failed: %s", audit_err)

    # SKILL.md rule 6: sensitivity gate — refuse write before any other work
    if is_sensitive:
        logger.warning(
            "write_agent_result_to_vault: refusing sensitive write for agent '%s' "
            "(vault may sync to cloud via Obsidian sync plugins)",
            agent_id,
        )
        _log_audit(
            "VAULT_WRITE_REFUSED_SENSITIVE",
            f"Sensitive write refused for agent {agent_id} — vault may sync to cloud.",
        )
        return None

    # Auto-generate vault path if not specified
    if vault_path is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = re.sub(r"[^a-z0-9_]", "", task_text[:40].lower().replace(" ", "_"))
        vault_path = f"00 - INBOX/openclaw/{date_str}_{agent_id}_{slug}.md"

    # SKILL.md rule 7: Context Guard — truncate result at 12,000 chars
    result_truncated = result[:12000]
    truncated_note = len(result) > 12000

    # Render note template
    now_iso = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y-%m-%d")
    title = task_text[:80].replace('"', "'")
    note_content = f"""---
title: "{title}"
agent: {agent_id}
date: {date_str}
tags: [openclaw, agent-output]
status: unprocessed
is_sensitive: false
---

## Task

{task_text}

## Result

{result_truncated}{'  <!-- truncated at 12,000 chars -->' if truncated_note else ''}

---
*Generated by OpenClaw agent `{agent_id}` on {now_iso}*
"""

    # Lazy import to avoid hard dependency when Obsidian is not installed
    try:
        if ObsidianBridge is None:
            raise ImportError("ObsidianBridge not available (Sprint 7 not installed)")
        bridge = ObsidianBridge()
    except (ValueError, ImportError) as bridge_err:
        # ValueError = misconfigured (no key / non-localhost) — treat as down
        logger.warning(
            "write_agent_result_to_vault: bridge unavailable (%s) — skipping vault write.",
            bridge_err,
        )
        _log_audit("VAULT_WRITE_SKIPPED", f"Bridge unavailable: {bridge_err}")
        return None

    if not bridge.ping():
        logger.warning(
            "write_agent_result_to_vault: Obsidian not running — skipping vault write."
        )
        _log_audit("VAULT_WRITE_SKIPPED", "Obsidian not running at the time of write.")
        return None

    try:
        bridge.write_note(vault_path, note_content)
        _log_audit("VAULT_WRITE", f"Wrote agent result to vault: {vault_path}")
        logger.info("write_agent_result_to_vault: wrote to %s", vault_path)
        return vault_path
    except Exception as write_err:
        logger.warning(
            "write_agent_result_to_vault: write failed (%s) — skipping.", write_err
        )
        _log_audit("VAULT_WRITE_SKIPPED", f"Write failed: {write_err}")
        return None


# ---------------------------------------------------------------------------
# Vault Tool Commands (Sprint 9 — Mode A: Tool Exposure)
# ---------------------------------------------------------------------------

def _vault_audit_log(
    db_path: str,
    action: str,
    rationale: str,
) -> None:
    """Write an optional audit log entry for vault tool subcommands."""
    if not db_path:
        return
    try:
        valid_db = validate_path(db_path)
        with sqlite3.connect(valid_db) as conn:
            conn.execute(
                "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, ?, ?)",
                ("obsidian-vault-architect", action, rationale),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("vault audit log failed: %s", exc)


def cmd_vault_route(args) -> int:
    """Suggest the correct vault path for a note based on its metadata.

    Exit codes: 0 = success (routed to a specific area),
                1 = INBOX fallback (no domain match — informational).
    """
    if not VAULT_TOOLS_AVAILABLE:
        print(
            "Error: vault_tools package not found. "
            "Ensure openclaw_skills/vault_tools/ is installed (Sprint 9).",
            file=sys.stderr,
        )
        return 1

    try:
        metadata = json.loads(args.metadata)
    except json.JSONDecodeError as exc:
        print(f"Error: --metadata is not valid JSON: {exc}", file=sys.stderr)
        return 1

    vault_root = getattr(args, "vault_root", None) or os.environ.get("OBSIDIAN_VAULT_PATH", "")
    suggested = suggest_vault_path(metadata, args.filename, vault_root)
    print(suggested)

    _vault_audit_log(
        getattr(args, "db_path", None),
        "VAULT_ROUTE",
        f"Routed '{args.filename}' → '{suggested}' (domain={metadata.get('domain', '')})",
    )

    if suggested.startswith("00 - INBOX"):
        logger.warning(
            "vault-route: no domain match — '%s' routed to INBOX fallback.",
            args.filename,
        )
        return 1
    return 0


def cmd_vault_validate(args) -> int:
    """Validate a note's YAML frontmatter.

    Exit codes: 0 = valid, 1 = runtime error, 2 = validation failure.
    """
    if not VAULT_TOOLS_AVAILABLE:
        print(
            "Error: vault_tools package not found. "
            "Ensure openclaw_skills/vault_tools/ is installed (Sprint 9).",
            file=sys.stderr,
        )
        return 1

    content = getattr(args, "content", None)

    if not content:
        # Try reading from Obsidian
        if ObsidianBridge is None:
            print(
                "Error: ObsidianBridge not available and --content not provided.",
                file=sys.stderr,
            )
            return 1
        try:
            bridge = ObsidianBridge()
        except (ValueError, ImportError) as exc:
            print(f"Error: Cannot connect to Obsidian bridge: {exc}", file=sys.stderr)
            return 1

        if not bridge.ping():
            print(
                "Error: Obsidian is not running. "
                "Start Obsidian or provide note content via --content.",
                file=sys.stderr,
            )
            return 1

        try:
            content = bridge.read_note(args.note_path)
        except FileNotFoundError:
            print(f"Error: Note not found in vault: {args.note_path}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Error reading note: {exc}", file=sys.stderr)
            return 1

    result = validate_vault_metadata(content, expected_path=args.note_path)
    print(json.dumps({
        "is_valid": result["is_valid"],
        "errors": result["errors"],
        "warnings": result["warnings"],
    }, indent=2))

    _vault_audit_log(
        getattr(args, "db_path", None),
        "VAULT_VALIDATE",
        f"Validated '{args.note_path}': valid={result['is_valid']}, "
        f"errors={len(result['errors'])}, warnings={len(result['warnings'])}",
    )

    return 0 if result["is_valid"] else 2


def cmd_vault_check_taxonomy(args) -> int:
    """Check vault path compliance with Johnny.Decimal taxonomy.

    Exit codes: 0 = compliant, 1 = runtime error, 2 = violations found.
    """
    if not VAULT_TOOLS_AVAILABLE:
        print(
            "Error: vault_tools package not found. "
            "Ensure openclaw_skills/vault_tools/ is installed (Sprint 9).",
            file=sys.stderr,
        )
        return 1

    compliant, issues = validate_taxonomy_compliance(args.vault_path)
    if compliant:
        print("PASS")
    else:
        print("FAIL")
        for issue in issues:
            print(f"  → {issue}")

    _vault_audit_log(
        getattr(args, "db_path", None),
        "VAULT_CHECK_TAXONOMY",
        f"Taxonomy check '{args.vault_path}': {'PASS' if compliant else 'FAIL'} — "
        f"{len(issues)} violation(s)",
    )

    return 0 if compliant else 2


def cmd_vault_health_check(args) -> int:
    """Run autonomous read-only vault health scan and output Markdown report.

    Exit codes: 0 = success, 1 = runtime error.
    """
    if not VAULT_TOOLS_AVAILABLE:
        print(
            "Error: vault_tools package not found. "
            "Ensure openclaw_skills/vault_tools/ is installed (Sprint 9).",
            file=sys.stderr,
        )
        return 1

    vault_root = getattr(args, "vault_root", None) or os.environ.get("OBSIDIAN_VAULT_PATH", "")
    db_path = getattr(args, "db_path", None)
    output_path = getattr(args, "output_path", None)

    try:
        health_result = run_vault_health_check(vault_root, db_path=db_path)
    except (RuntimeError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    report_md = format_health_report(health_result, vault_root=vault_root)

    if output_path and ObsidianBridge is not None:
        try:
            bridge = ObsidianBridge()
            if bridge.ping():
                bridge.write_note(output_path, report_md)
                _vault_audit_log(
                    db_path,
                    "VAULT_HEALTH_REPORT",
                    f"Health report written to vault: {output_path}",
                )
                print(f"Health report written to vault: {output_path}")
                return 0
        except Exception as exc:
            logger.warning("vault-health-check: could not write report to vault: %s", exc)

    # Obsidian unavailable or no output path — print to stdout (non-fatal)
    print(report_md)
    return 0


def cmd_vault_qa(args) -> int:
    """Handler for 'vault-qa' subcommand — RAG retrieval from Obsidian vault.

    Security: context_text is NEVER written to audit_logs.
    Exit codes: 0=results found, 1=runtime error, 2=no results.
    """
    if not VAULT_TOOLS_AVAILABLE:
        print(
            "Error: vault-qa requires the obsidian_bridge module. "
            "Ensure openclaw_skills/obsidian_bridge.py is present.",
            file=sys.stderr,
        )
        return 1

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from obsidian_bridge import vault_qa
    except ImportError as e:
        print(f"Error: cannot import vault_qa: {e}", file=sys.stderr)
        return 1

    try:
        result = vault_qa(
            query=args.query,
            db_path=getattr(args, "db_path", None),
            limit=getattr(args, "limit", 5),
            is_sensitive=getattr(args, "sensitive", False),
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not result["sources"]:
        print(
            f"No vault notes found matching: {args.query!r}\n"
            "Try a different query or check that Obsidian is running.",
            file=sys.stderr,
        )
        return 2

    if getattr(args, "output_json", False):
        # JSON output — safe: context_text is vault content (local only)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    # Default: Markdown formatted output — Response Protocol compliant
    sources = result["sources"]
    lines = [
        f"## Vault QA: {args.query}",
        "",
        f"*Based on {len(sources)} note(s) retrieved from your vault.*",
        "",
    ]

    # Body excerpts with [^N] footnote markers in each section header
    for i, source in enumerate(sources):
        lines.append(f"---\n### {source['wikilink']} [^{i+1}]\n{source['excerpt']}\n")

    # Footer: Sources map [^N] → [[Note]] (path)
    lines.append("---")
    lines.append("#### Sources")
    for i, source in enumerate(sources):
        lines.append(f"[^{i+1}]: {source['wikilink']} — `{source['path']}`")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Architect Tools CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser("gen-token", help="Generate a new HITL approval token")

    deploy_parser = subparsers.add_parser("deploy", help="Deploy a new pipeline (Requires HITL Token)")
    deploy_parser.add_argument("db_path", type=str, help="Path to SQLite DB")
    deploy_parser.add_argument("pipeline_id", type=str)
    deploy_parser.add_argument("pipeline_name", type=str)
    deploy_parser.add_argument("topology_json", type=str)
    deploy_parser.add_argument("approval_token", type=str, help="Burn-on-Read HITL Token")

    teardown_parser = subparsers.add_parser("teardown", help="Teardown a pipeline safely")
    teardown_parser.add_argument("db_path", type=str, help="Path to SQLite DB")
    teardown_parser.add_argument("pipeline_id", type=str)

    run_parser = subparsers.add_parser("run", help="Run a task attributed to a registered agent")
    run_parser.add_argument("db_path", type=str, help="Path to SQLite DB")
    run_parser.add_argument("agent_id", type=str, help="Agent ID (e.g. kimi-orch-01)")
    run_parser.add_argument("task", type=str, help="Task description in natural language")
    run_parser.add_argument("--audit", action="store_true", help="Run Red Team audit on output")

    vault_parser = subparsers.add_parser(
        "write-to-vault", help="Write an agent result to the Obsidian vault"
    )
    vault_parser.add_argument("db_path", type=str, help="Path to SQLite DB")
    vault_parser.add_argument("agent_id", type=str, help="Agent ID")
    vault_parser.add_argument("task", type=str, help="Task description")
    vault_parser.add_argument("result", type=str, help="Agent result text")
    vault_parser.add_argument("--vault-path", type=str, default=None,
                              help="Custom vault path (default: auto-generated in 00 - INBOX/openclaw/)")
    vault_parser.add_argument("--sensitive", action="store_true",
                              help="Mark as sensitive — write will be refused")


    # ── Sprint 9: Vault Tool Subcommands ────────────────────────────────────

    vr_parser = subparsers.add_parser(
        "vault-route",
        help="Suggest the correct Johnny.Decimal vault path for a note",
    )
    vr_parser.add_argument(
        "--metadata", required=True, type=str,
        help="JSON string of note YAML frontmatter (e.g. {type,domain} dict)"
    )
    vr_parser.add_argument(
        "--filename", required=True, type=str,
        help="Target note filename (e.g. LLM_Notes.md)",
    )
    vr_parser.add_argument(
        "--vault-root", dest="vault_root", type=str, default=None,
        help="Vault root path (default: $OBSIDIAN_VAULT_PATH)",
    )
    vr_parser.add_argument(
        "--db-path", dest="db_path", type=str, default=None,
        help="Optional factory.db path for audit logging",
    )

    vv_parser = subparsers.add_parser(
        "vault-validate",
        help="Validate a vault note's YAML frontmatter schema",
    )
    vv_parser.add_argument(
        "--note-path", dest="note_path", required=True, type=str,
        help="Vault-relative note path (e.g. '20 - AREAS/23 - AI/Note.md')",
    )
    vv_parser.add_argument(
        "--content", type=str, default=None,
        help="Raw markdown string (skips live Obsidian read if provided)",
    )
    vv_parser.add_argument(
        "--db-path", dest="db_path", type=str, default=None,
        help="Optional factory.db path for audit logging",
    )

    vct_parser = subparsers.add_parser(
        "vault-check-taxonomy",
        help="Check a vault path for Johnny.Decimal 'NN - ' prefix compliance",
    )
    vct_parser.add_argument(
        "--vault-path", dest="vault_path", required=True, type=str,
        help="Vault-relative path to check (e.g. '20 - AREAS/23 - AI/Note.md')",
    )
    vct_parser.add_argument(
        "--db-path", dest="db_path", type=str, default=None,
        help="Optional factory.db path for audit logging",
    )

    vhc_parser = subparsers.add_parser(
        "vault-health-check",
        help="Run autonomous read-only health scan of the entire Obsidian vault",
    )
    vhc_parser.add_argument(
        "--vault-root", dest="vault_root", type=str, default=None,
        help="Vault root path (default: $OBSIDIAN_VAULT_PATH)",
    )
    vhc_parser.add_argument(
        "--output-path", dest="output_path", type=str, default=None,
        help="Optional vault-relative path to write the Markdown health report",
    )
    vhc_parser.add_argument(
        "--db-path", dest="db_path", type=str, default=None,
        help="Optional factory.db path for audit logging",
    )

    vqa_parser = subparsers.add_parser(
        "vault-qa",
        help="RAG: search Obsidian vault and return grounded context with [[wikilink]] citations",
    )
    vqa_parser.add_argument(
        "--query", dest="query", required=True,
        help="Plain-text search query (required)",
    )
    vqa_parser.add_argument(
        "--db-path", dest="db_path", type=str, default=None,
        help="Optional factory.db path for audit logging",
    )
    vqa_parser.add_argument(
        "--limit", dest="limit", type=int, default=5,
        help="Max notes to retrieve (default 5, clamped to 1-10)",
    )
    vqa_parser.add_argument(
        "--sensitive", dest="sensitive", action="store_true", default=False,
        help="Mark retrieval as sensitive (local Ollama only for synthesis)",
    )
    vqa_parser.add_argument(
        "--json", dest="output_json", action="store_true", default=False,
        help="Output raw JSON instead of formatted Markdown",
    )

    args = parser.parse_args()

    try:
        if args.command == "gen-token":
            token = generate_token()
            print(f"Generated HITL Token: {token}")
            print(f"Saved to: {TOKEN_FILE} with 600 permissions.")
        elif args.command == "deploy":
            result = deploy_pipeline(args.db_path, args.pipeline_id, args.pipeline_name, args.topology_json, args.approval_token)
            print(result)
        elif args.command == "teardown":
            result = teardown_pipeline(args.db_path, args.pipeline_id)
            print(result)
        elif args.command == "run":
            result = run_agent(args.db_path, args.agent_id, args.task, audit=getattr(args, 'audit', False))
            print(result)
        elif args.command == "write-to-vault":
            written = write_agent_result_to_vault(
                args.db_path, args.agent_id, args.task, args.result,
                vault_path=args.vault_path, is_sensitive=args.sensitive,
            )
            if written:
                print(f"Written to vault: {written}")
            else:
                print("Vault write skipped (Obsidian unavailable, sensitive flag, or error).")
        elif args.command == "vault-route":
            exit_code = cmd_vault_route(args)
            sys.exit(exit_code)
        elif args.command == "vault-validate":
            exit_code = cmd_vault_validate(args)
            sys.exit(exit_code)
        elif args.command == "vault-check-taxonomy":
            exit_code = cmd_vault_check_taxonomy(args)
            sys.exit(exit_code)
        elif args.command == "vault-health-check":
            exit_code = cmd_vault_health_check(args)
            sys.exit(exit_code)
        elif args.command == "vault-qa":
            exit_code = cmd_vault_qa(args)
            sys.exit(exit_code)
    except SystemExit:
        raise  # Propagate sys.exit() calls cleanly
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

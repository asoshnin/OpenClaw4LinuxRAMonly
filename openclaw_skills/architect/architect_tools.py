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
try:
    from config import WORKSPACE_ROOT, TOKEN_FILE, OLLAMA_URL, LOCAL_MODEL
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import WORKSPACE_ROOT, TOKEN_FILE, OLLAMA_URL, LOCAL_MODEL

# ObsidianBridge — optional dependency (Sprint 7); graceful if not yet installed
try:
    _skills_root = os.path.dirname(os.path.dirname(__file__))
    if _skills_root not in sys.path:
        sys.path.insert(0, _skills_root)
    from obsidian_bridge import ObsidianBridge
except ImportError:
    ObsidianBridge = None  # type: ignore

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
    """Displays a native GUI popup to request human-in-the-loop approval."""
    if not TK_AVAILABLE:
        print(f"\n[APPROVAL REQUESTED]: {prompt_text}")
        response = input("Approve? (yes/no): ").lower().strip()
        return response in ("yes", "y")
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    result = messagebox.askyesno("HITL Security Gate", prompt_text)
    root.destroy()
    return result


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


def run_agent(db_path: str, agent_id: str, task_text: str) -> str:
    """[DES-S5-03 / DES-S6-02] Execute a task attributed to a registered agent.

    Flow (Sprint 6 prompt order per SKILL.md):
      1. Load KB rules from knowledge_base.json (graceful on missing)
      2. Load agent record from DB (ValueError if not found)
      3. Retrieve Faint Path memory context (graceful fallback if archive empty)
      4. Build prompt: KB rules → agent identity → memory → task
      5. Call local Ollama — RuntimeError if unreachable or empty response
      6. Log result to audit_logs with action='AGENT_RUN'
      7. Return response string

    Constraints (from SKILL.md):
      - Local Ollama ONLY — never cloud APIs
      - Must NOT touch HITL gate or deploy_pipeline_with_ui
      - Must raise on any failure — never return silently
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

    # 4. Build prompt — SKILL.md order: KB → identity → memory → task
    description = agent.get("description") or agent.get("name", "AI agent")
    memory_text = memory_text[:4000]   # context window guard
    prompt_parts = []
    if kb_prefix:
        prompt_parts.append(kb_prefix)
    prompt_parts.append(f"[AGENT IDENTITY]\nYou are {agent['name']} — {description}.\n")
    prompt_parts.append(f"[MEMORY CONTEXT]\n{memory_text}\n")
    prompt_parts.append(f"[TASK]\n{task_text}")
    prompt = "\n".join(prompt_parts)

    # 4. Call local Ollama (synchronous, no cloud)
    payload = json.dumps({
        "model": LOCAL_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response = result.get("response", "").strip()
            if not response:
                raise RuntimeError(
                    f"Ollama returned an empty response for model '{LOCAL_MODEL}'. "
                    "Ensure the model is pulled: ollama pull " + LOCAL_MODEL
                )
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Ollama unreachable at {OLLAMA_URL}: {e}. "
            "Ensure Ollama is running: ollama serve"
        ) from e

    # 5. Audit log (truncated to 500 chars — protects audit table size)
    valid_db = validate_path(db_path)
    with sqlite3.connect(valid_db) as conn:
        conn.execute(
            "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, 'AGENT_RUN', ?)",
            (agent_id, response[:500]),
        )
        conn.commit()

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
            result = run_agent(args.db_path, args.agent_id, args.task)
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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

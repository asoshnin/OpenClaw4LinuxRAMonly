"""
Architect Tools - Agentic Factory on OpenClaw
Core discovery and HITL authorization functions for Sprint 2.
"""

import os
import sys
import uuid
import sqlite3
import argparse
try:
    import tkinter as tk
    from tkinter import messagebox
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

# Hardcoded boundaries
WORKSPACE_DIR = "/home/alexey/openclaw-inbox/workspace/"
TOKEN_FILE = os.path.join(WORKSPACE_DIR, ".hitl_token")


def validate_path(target_path: str) -> str:
    """[DES-02] ported from Librarian: Realpath validation for Airlock protection."""
    base_dir = os.path.realpath(WORKSPACE_DIR)
    target_abs = os.path.realpath(target_path)
    if not target_abs.startswith(base_dir):
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
    validate_path(TOKEN_FILE)
    token = str(uuid.uuid4())
    
    # Write securely with 600 permissions
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    mode = 0o600
    
    fd = os.open(TOKEN_FILE, flags, mode)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(token)
        
    return token


def validate_token(provided_token: str) -> bool:
    """[DES-09] One-time token validation (Burn-on-Read)."""
    validate_path(TOKEN_FILE)
    
    if not os.path.exists(TOKEN_FILE):
        return False
        
    try:
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            stored_token = f.read().strip()
    except Exception:
        return False
        
    # BURN ON READ: Critical Security Gate
    # Must run and possibly raise exception if removal fails to prevent replay loops
    os.remove(TOKEN_FILE)
    
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
            
            # Delete physical file
            profile_path = os.path.join(WORKSPACE_DIR, f"{agent_id}.md")
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
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

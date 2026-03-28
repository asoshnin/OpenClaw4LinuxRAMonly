import json
import sqlite3
import logging
import os
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

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

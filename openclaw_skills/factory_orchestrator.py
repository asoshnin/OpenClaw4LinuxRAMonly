"""
MP-01: Factory Orchestrator (Kimi-Orch-01)
Ties together task queue claiming, subagent (Pi) delegation, and auditor verification.
"""
import os
import uuid
import json
import signal
import logging
import subprocess
import sys
from pathlib import Path

# Ensure imports work from skills dir
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from openclaw_skills.orchestrator.task_worker import TaskQueueManager
from openclaw_skills.orchestrator.pi_bridge import CodingAgentBridge
from openclaw_skills.orchestrator.artifact_gatherer import get_safe_diff
from openclaw_skills.architect.architect_tools import run_audit

log = logging.getLogger(__name__)


def _get_pid_file(project_root: str) -> Path:
    ws = Path(project_root) / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws / ".orchestrator.pid"


def _get_halt_file(project_root: str) -> Path:
    return Path(project_root) / "workspace" / ".watchdog_halt"

def _get_current_git_hash(repo_dir: str) -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return "HEAD"

def run_orchestrator(inbound_message: str = None) -> dict:
    manager = TaskQueueManager()
    bridge = CodingAgentBridge()
    
    project_root = os.environ.get("OPENCLAW_WORKSPACE", os.getcwd())
    if project_root.endswith("workspace"):
        project_root = os.path.dirname(project_root) # go up to project root
        
    project_root = os.path.abspath(project_root)

    # ── Safety Gate: Watchdog Halt Check ──────────────────────────────────────
    halt_file = _get_halt_file(project_root)
    if halt_file.exists():
        log.warning(
            "WATCHDOG HALT sentinel detected at %s. "
            "Refusing to claim new tasks. Remove the file to resume.",
            halt_file,
        )
        return {"status": "halted", "message": f"Watchdog halt is active. See {halt_file}"}

    # ── PID Registration ──────────────────────────────────────────────────────
    pid_file = _get_pid_file(project_root)
    pid_file.write_text(str(os.getpid()))
    log.debug("Orchestrator PID %d written to %s", os.getpid(), pid_file)

    def _cleanup_pid(signum=None, frame=None):
        pid_file.unlink(missing_ok=True)
        log.debug("Orchestrator PID file removed.")

    signal.signal(signal.SIGTERM, _cleanup_pid)
    signal.signal(signal.SIGINT, _cleanup_pid)
    
    try:
        if inbound_message:
            # Phase 1: Resume Active Subagent
            task = manager.get_active_subagent_task()
            if task:
                baseline_commit = task.get("baseline_commit") or "HEAD"
                diff = get_safe_diff(project_root, baseline_commit)
                
                # Using RT-01
                audit_report = run_audit(artifact_text=diff, task_context=task['payload'])
                
                status = audit_report.get("status", "")
                findings = "\n".join(audit_report.get("findings", []))
                
                if status == "🔴 NO GO":
                    manager.fail_task_with_retry(task['id'], findings)
                else:
                    manager.mark_task_completed(task['id'])
                    
                return audit_report
            else:
                return {"status": "idle", "message": "No active subagent task found to resume."}
                
        else:
            # Phase 2: Claim New Task
            task = manager.claim_next_task()
            if not task:
                return {"status": "idle", "message": "No queued tasks."}
                
            task_id = task['id']
            baseline_commit = _get_current_git_hash(project_root)
            
            spawn_payload = bridge.format_spawn_request(task_id, task['payload'], project_root)
            
            pending_session = f"pending-uuid-{uuid.uuid4().hex[:8]}"
            manager.mark_task_as_delegated(task_id, pending_session, baseline_commit)
            
            return spawn_payload
            
    except Exception as e:
        log.error(f"Orchestrator error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        manager.close()
        _cleanup_pid()

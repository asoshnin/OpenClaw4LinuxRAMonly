import argparse
import sys
import os
import subprocess
import time
import json

# Force workspace to prevent Airlock Breach
os.environ["OPENCLAW_WORKSPACE"] = "/home/alexey/openclaw-inbox/agentic_factory"

# Add project root to sys path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from openclaw_skills.orchestrator.intake import BacklogIntake
from openclaw_skills.factory_orchestrator import run_orchestrator

def main():
    parser = argparse.ArgumentParser(description="Factory Orchestrator CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    submit_parser = subparsers.add_parser("submit")
    submit_parser.add_argument("goal", type=str)
    
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("goal", type=str)
    
    trigger_parser = subparsers.add_parser("trigger")
    
    args = parser.parse_args()
    
    if args.command == "submit":
        intake = BacklogIntake()
        task_id = intake.submit_task(args.goal)
        print(f"Task submitted: {task_id}")
    elif args.command == "plan":
        intake = BacklogIntake()
        task_ids = intake.decompose_and_submit(args.goal)
        print(f"Plan created with tasks: {task_ids}")
    elif args.command == "trigger":
        watchdog_interval = float(os.environ.get("OPENCLAW_WATCHDOG_INTERVAL", "30.0"))
        print(f"Starting orchestration loop... (Watchdog interval: {watchdog_interval}s)")
        try:
            while True:
                # Phase 2: Claim Task
                res = run_orchestrator()
                
                if not res or res.get("status") in ["idle", "halted"]:
                    print(f"Queue idle/halted. Sleeping {watchdog_interval}s...")
                    time.sleep(watchdog_interval)
                else:
                    # Expecting a spawn_payload dict
                    if isinstance(res, dict) and res.get("runtime") == "acp":
                        print(f"Spawning subagent for task: {res.get('label')}")
                        agent_id = res.get("agentId", "main")
                        task_str = res.get("task", "")
                        
                        # Synchronously spawn OpenClaw agent
                        try:
                            subprocess.run([
                                "openclaw", "agent", 
                                "--agent", agent_id, 
                                "--message", task_str
                            ], check=False, timeout=300)
                        except subprocess.TimeoutExpired:
                            print(f"Warning: Subagent {agent_id} timed out after 300 seconds.")
                        
                        # Phase 1: Audit & Complete Task
                        print(f"Subagent finished. Triggering Audit Phase.")
                        audit_res = run_orchestrator(inbound_message="Subagent finished.")
                        print(f"Audit Result: {json.dumps(audit_res)}")
                        
                        print("Cooling down 5s before next task...")
                        time.sleep(5)
                    else:
                        print(f"Unknown payload processed: {json.dumps(res)}")
                        time.sleep(5)
                        
        except KeyboardInterrupt:
            print("\nOrchestrator loop stopped by user.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

"""
CLI Wrapper for Agentic Factory Orchestrator
"""
import argparse
import sys
import os

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
        import time
        import json
        watchdog_interval = float(os.environ.get("OPENCLAW_WATCHDOG_INTERVAL", "30.0"))
        print(f"Starting orchestration loop... (Watchdog interval: {watchdog_interval}s)")
        try:
            while True:
                res = run_orchestrator()
                # Check for idle or halted
                if not res or res.get("status") in ["idle", "halted"]:
                    print(f"Queue idle/halted. Sleeping {watchdog_interval}s...")
                    time.sleep(watchdog_interval)
                else:
                    print(f"Task processed: {json.dumps(res)}")
                    print("Cooling down 5s before next task...")
                    time.sleep(5)
        except KeyboardInterrupt:
            print("\nOrchestrator loop stopped by user.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

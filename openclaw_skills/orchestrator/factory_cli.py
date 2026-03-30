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
        res = run_orchestrator()
        print(f"Triggered workflow: {res}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

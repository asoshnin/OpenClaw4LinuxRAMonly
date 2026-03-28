#!/usr/bin/env python3
"""
Mermaid Correction Pipeline - Sprint 13
Implements the Local Scrubber -> Cloud Inference flow with HITL.
"""

import sys
import os
import json
import logging

# Ensure parent skills are reachable
sys.path.insert(0, os.path.dirname(__file__))
from architect.architect_tools import run_agent, request_ui_approval
# Resolve workspace config — never hardcode paths
try:
    from config import WORKSPACE_ROOT, OLLAMA_URL, LOCAL_MODEL
    DEFAULT_DB_PATH = os.path.join(str(WORKSPACE_ROOT), "database", "factory.db")
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import WORKSPACE_ROOT, OLLAMA_URL, LOCAL_MODEL
    DEFAULT_DB_PATH = os.path.join(str(WORKSPACE_ROOT), "database", "factory.db")

logger = logging.getLogger(__name__)

def run_mermaid_pipeline(script_content: str, db_path: str = DEFAULT_DB_PATH):
    """
    Orchestrates the Mermaid correction logic.
    """
    print("🚀 Initializing Mermaid Safety Scrubber (Local)...")
    
    # 1. Local Scrubbing Step
    scrub_task = f"Scan this Mermaid script for sensitive data:\n\n{script_content}"
    try:
        scrub_response = run_agent(db_path, "mermaid-safety-scrubber", scrub_task)
        # Parse the text response
        is_sensitive = "[SENSITIVE]" in scrub_response.upper()
        summary = scrub_response.replace("[SENSITIVE]", "").replace("[SAFE]", "").strip()
    except Exception as e:
        logger.error("Scrubbing failed: %s", e)
        print(f"❌ Error: Could not verify script safety locally. Aborting.")
        return

    # 2. Decision Logic
    should_proceed = True
    if is_sensitive:
        print("\n⚠️  [SENSITIVE DATA DETECTED]")
        print(f"Note from Scrubber: {summary}")
        
        prompt = (
            f"The Local Scrubber found potential sensitive data:\n\n"
            f"'{summary}'\n\n"
            f"Do you want to proceed and send this script to the Cloud (Gemini) for correction?"
        )
        should_proceed = request_ui_approval(prompt)
    
    if not should_proceed:
        print("\n🛑 Pipeline aborted by Navigator.")
        return

    # 3. Cloud Correction Step
    print("\n☁️  Sending to Cloud (Gemini-3.1-Pro) for correction...")
    
    # Note: We simulate the 'cloud' routing by overriding the run_agent's model call 
    # or by assuming the system router handles it.
    # For this test, we will instruct the agent to use its KB.
    correction_task = f"Correct this Mermaid script per your KB rules:\n\n{script_content}"
    
    # Normally, we'd have a 'tier' argument for run_agent. 
    # For now, we rely on the agent's persona being powerful enough in the cloud.
    try:
        # In a real setup, we would call the cloud router here.
        # For demonstration, we just call the agent.
        result = run_agent(db_path, "mermaid-syntax-engine", correction_task)
        print("\n✅ Correction Complete:")
        print(result)
    except Exception as e:
        print(f"❌ Correction failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 mermaid_pipeline.py \"<mermaid script>\"")
        sys.exit(1)
        
    run_mermaid_pipeline(sys.argv[1])

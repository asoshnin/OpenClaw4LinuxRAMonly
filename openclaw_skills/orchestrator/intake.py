"""
BL-01: Backlog Intake
Natural language backlog parsing into dependent sequences securely loaded into the tasks table.
"""
import sqlite3
import re
import json
import uuid
import logging
import sys
import os
from pathlib import Path

# Add project root to sys path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from openclaw_skills.config import GLOBAL_DB_PATH, LOCAL_MODEL, call_inference

log = logging.getLogger(__name__)

class BacklogIntake:
    def __init__(self, db_path: str | Path = None):
        self.db_path = db_path or GLOBAL_DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")

    def submit_task(self, goal: str, is_sensitive: bool = False, required_tier: str = 'cpu', depends_on: str = None) -> str:
        """Inject an atomic task directly into the queuing system."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        status = 'blocked' if depends_on else 'queued'
        
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (id, payload, is_sensitive, required_tier, status, depends_on)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (task_id, goal, is_sensitive, required_tier, status, depends_on))
        self.conn.commit()
        return task_id

    def decompose_and_submit(self, high_level_goal: str) -> list[str]:
        """Convert a high-level goal into sequentially dependent atomic tasks."""
        
        prompt = (
            "You are a Senior Technical Architect for the Agentic Factory. "
            "Decompose the following high-level goal into 1-3 atomic coding tasks. "
            "Every task MUST include specific filenames, functions, and exact logic. "
            "Output ONLY a raw JSON array of strings: `[\"Step 1: ...\", \"Step 2: ...\"]`.\n\n"
            f"Goal: {high_level_goal}\n"
        )
        
        try:
            # Inference tier cpu default for local models
            response = call_inference('cpu', LOCAL_MODEL, prompt)
            
            # Use regex to find the json array reliably (local models are chatty)
            match = re.search(r'\[.*\]', response, re.DOTALL)
            if not match:
                raise ValueError("Could not locate JSON array boundary in output.")
                
            json_str = match.group(0)
            task_list = json.loads(json_str)
            
            if not isinstance(task_list, list) or not all(isinstance(i, str) for i in task_list):
                raise ValueError("Output format invalid - must be a JSON array of strings.")
                
            if not task_list:
                raise ValueError("JSON array is empty.")
                
        except Exception as e:
            log.warning(f"Decomposition failed ({e}), falling back to monolithic task submission.")
            task_list = [high_level_goal]

        task_ids = []
        depends_on = None
        
        for task_def in task_list:
            t_id = self.submit_task(task_def, is_sensitive=False, required_tier='cpu', depends_on=depends_on)
            task_ids.append(t_id)
            depends_on = t_id # Chaining tasks sequentially
            
        return task_ids

    def close(self):
        self.conn.close()


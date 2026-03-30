import os
import json
import sqlite3
import pytest
import subprocess
import tempfile
from unittest.mock import patch
import sys

# Pre-setup sys.path so we can patch the underlying 'config' module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "openclaw_skills")))

from openclaw_skills.orchestrator.intake import BacklogIntake
from openclaw_skills.factory_orchestrator import run_orchestrator

# Ensure we pull schema from the valid path
SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql"))

@pytest.fixture
def e2e_env():
    # Environment Patching (CRITICAL ISOLATION)
    with tempfile.TemporaryDirectory() as temp_dir:
        # DB setup
        db_path = os.path.join(temp_dir, "factory.db")
        
        # Apply schema.sql
        with open(SCHEMA_PATH, "r") as f:
            schema_sql = f.read()
            
        conn = sqlite3.connect(db_path)
        conn.executescript(schema_sql)
        
        # We also need agents and audit_logs tables to support the Red Team Auditor properly without full migration logic
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                persona_hash TEXT,
                state_blob JSON,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                pipeline_id TEXT,
                action TEXT,
                rationale TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO agents (agent_id, name, description) 
            VALUES ('red-team-auditor-01', 'Red Team Auditor', 'Mock RT-01 Prompt');
        """)
        conn.commit()
        conn.close()
        
        # Git Repo init
        subprocess.run(["git", "init"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "--local", "user.name", "Test"], cwd=temp_dir, check=True)
        subprocess.run(["git", "config", "--local", "user.email", "test@example.com"], cwd=temp_dir, check=True)
        
        dummy_file = os.path.join(temp_dir, "README.md")
        with open(dummy_file, "w") as f:
            f.write("# Dummy file\n")
            
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True)
        
        import config
        # Patch configurations for complete isolation
        with patch.object(config, "GLOBAL_DB_PATH", db_path), \
             patch.object(config, "WORKSPACE_ROOT", temp_dir), \
             patch("openclaw_skills.config.GLOBAL_DB_PATH", db_path), \
             patch("openclaw_skills.config.WORKSPACE_ROOT", temp_dir), \
             patch("openclaw_skills.orchestrator.task_worker.GLOBAL_DB_PATH", db_path), \
             patch("openclaw_skills.orchestrator.intake.GLOBAL_DB_PATH", db_path), \
             patch("openclaw_skills.architect.architect_tools.WORKSPACE_ROOT", temp_dir), \
             patch.dict(os.environ, {"OPENCLAW_WORKSPACE": os.path.join(temp_dir, "workspace")}):
            yield temp_dir, db_path

@patch("openclaw_skills.orchestrator.intake.call_inference")
@patch("openclaw_skills.architect.architect_tools.call_inference")
@patch("openclaw_skills.architect.architect_tools.get_active_ollama_url", return_value="http://mock")
def test_e2e_happy_path_with_dependencies(mock_get_url, mock_audit_inference, mock_intake_inference, e2e_env):
    temp_dir, db_path = e2e_env
    
    # 1. Intake
    # Mock inference to return JSON array for decomposition
    mock_intake_inference.return_value = 'Here is the decomposition:\n["Step 1: DB", "Step 2: API"]'
    
    intake = BacklogIntake()
    task_ids = intake.decompose_and_submit("Build a web server")
    intake.close()
    
    assert len(task_ids) == 2
    task1_id, task2_id = task_ids
    
    # 2. Verify Queue
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task1_id,))
    t1 = cursor.fetchone()
    assert t1['status'] == 'queued'
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task2_id,))
    t2 = cursor.fetchone()
    assert t2['status'] == 'blocked'
    assert t2['depends_on'] == task1_id
    
    # 3. Phase 2 (Dispatch Task 1)
    spawn_payload = run_orchestrator(None)
    assert spawn_payload.get("agentId") == "pi"
    assert "Step 1: DB" in spawn_payload.get("task")
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task1_id,))
    t1_updated = cursor.fetchone()
    assert t1_updated['status'] == 'processing_subagent'
    assert t1_updated['baseline_commit'] is not None
    assert len(t1_updated['baseline_commit']) > 0
    
    # Simulate Pi making a code commit locally
    new_file_path = os.path.join(temp_dir, "new_code.py")
    with open(new_file_path, "w") as f:
        f.write("print('hello')\n")
    subprocess.run(["git", "add", "new_code.py"], cwd=temp_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Pi's code"], cwd=temp_dir, check=True)
    
    # Mock Red Team Auditor response via call_inference
    mock_audit_inference.return_value = """
<AUDIT_REPORT>
  <STATUS>🟢 SIGN OFF</STATUS>
  <FINDINGS>All good</FINDINGS>
  <EPISTEMIC_CHALLENGE>None</EPISTEMIC_CHALLENGE>
  <RECOMMENDATIONS>None</RECOMMENDATIONS>
</AUDIT_REPORT>"""
    
    audit_report = run_orchestrator(inbound_message="Pi finished")
    assert audit_report.get("status") == "🟢 SIGN OFF"
    
    # 5. Verify Unblock
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task1_id,))
    t1_final = cursor.fetchone()
    assert t1_final['status'] == 'completed'
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task2_id,))
    t2_unblocked = cursor.fetchone()
    assert t2_unblocked['status'] == 'queued'
    
    conn.close()

@patch("openclaw_skills.orchestrator.intake.call_inference")
@patch("openclaw_skills.architect.architect_tools.call_inference")
@patch("openclaw_skills.architect.architect_tools.get_active_ollama_url", return_value="http://mock")
def test_e2e_circuit_breaker_loop(mock_get_url, mock_audit_inference, mock_intake_inference, e2e_env):
    temp_dir, db_path = e2e_env
    
    # 1. Intake
    intake = BacklogIntake()
    task_id = intake.submit_task("Write bad code")
    intake.close()
    
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    t1 = cursor.fetchone()
    assert t1['status'] == 'queued'
    
    # Execute loop to trigger fail count up
    for attempt in range(1, 4):
        # Dispatch
        run_orchestrator(None)
        
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        t_proc = cursor.fetchone()
        assert t_proc['status'] == 'processing_subagent'
        
        # Simulate Pi making a code commit locally to avoid empty artifact errors
        new_file_path = os.path.join(temp_dir, f"new_code_attempt_{attempt}.py")
        with open(new_file_path, "w") as f:
            f.write(f"print('error {attempt}')\n")
        subprocess.run(["git", "add", f"new_code_attempt_{attempt}.py"], cwd=temp_dir, check=True)
        subprocess.run(["git", "commit", "-m", f"Pi attempt {attempt}"], cwd=temp_dir, check=True)

        # Audit Fail
        mock_audit_inference.return_value = f"""
<AUDIT_REPORT>
  <STATUS>🔴 NO GO</STATUS>
  <FINDINGS>Failed attempt {attempt}</FINDINGS>
  <EPISTEMIC_CHALLENGE>Error here</EPISTEMIC_CHALLENGE>
  <RECOMMENDATIONS>Fix</RECOMMENDATIONS>
</AUDIT_REPORT>"""
        run_orchestrator("Pi finished")
        
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        t_failed = cursor.fetchone()
        
        if attempt < 3:
            assert t_failed['status'] == 'queued'
            assert t_failed['attempt_count'] == attempt
        else:
            assert t_failed['status'] == 'pending_hitl'
            assert t_failed['attempt_count'] == 3
            assert f"Failed attempt 3" in t_failed['last_error']
            
    conn.close()

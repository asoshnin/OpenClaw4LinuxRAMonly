import os
import sqlite3
import pytest
import tempfile
import json
from unittest.mock import patch, MagicMock

from openclaw_skills.orchestrator.intake import BacklogIntake
from openclaw_skills.orchestrator.task_worker import TaskQueueManager

@pytest.fixture
def test_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            is_sensitive BOOLEAN NOT NULL DEFAULT 0,
            required_tier TEXT NOT NULL,
            status TEXT CHECK(status IN ('queued', 'processing', 'completed', 'failed', 'pending_hitl', 'processing_subagent', 'blocked')) NOT NULL DEFAULT 'queued',
            attempt_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            last_error TEXT,
            session_id TEXT,
            baseline_commit TEXT,
            depends_on TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    
    yield path
    os.unlink(path)

def test_submit_task(test_db):
    intake = BacklogIntake(db_path=test_db)
    
    # Task 1: No dependency
    t1 = intake.submit_task("Task 1")
    
    # Task 2: Dependent
    t2 = intake.submit_task("Task 2", depends_on=t1)
    
    conn = sqlite3.connect(test_db)
    r1 = conn.execute("SELECT status FROM tasks WHERE id=?", (t1,)).fetchone()[0]
    r2 = conn.execute("SELECT status FROM tasks WHERE id=?", (t2,)).fetchone()[0]
    
    assert r1 == 'queued'
    assert r2 == 'blocked'
    
    conn.close()
    intake.close()

@patch("openclaw_skills.orchestrator.intake.call_inference")
def test_decompose_and_submit(mock_call_inference, test_db):
    intake = BacklogIntake(db_path=test_db)
    
    # Mocking noisy LLM output
    mock_call_inference.return_value = '''Here is your plan:
    ```json
    ["Task A", "Task B"]
    ```
    Good luck!'''
    
    tasks = intake.decompose_and_submit("Do a complex thing")
    
    assert len(tasks) == 2
    
    conn = sqlite3.connect(test_db)
    r1 = conn.execute("SELECT status, depends_on FROM tasks WHERE id=?", (tasks[0],)).fetchone()
    r2 = conn.execute("SELECT status, depends_on FROM tasks WHERE id=?", (tasks[1],)).fetchone()
    
    assert r1[0] == 'queued'
    assert r1[1] is None
    
    assert r2[0] == 'blocked'
    assert r2[1] == tasks[0]
    
    conn.close()
    intake.close()

def test_unblocking_logic(test_db):
    intake = BacklogIntake(db_path=test_db)
    t1 = intake.submit_task("Task 1")
    t2 = intake.submit_task("Task 2", depends_on=t1)
    
    manager = TaskQueueManager(db_path=test_db)
    manager.mark_task_completed(t1)
    
    conn = sqlite3.connect(test_db)
    r_t2 = conn.execute("SELECT status FROM tasks WHERE id=?", (t2,)).fetchone()
    assert r_t2[0] == 'queued'
    
    conn.close()
    manager.close()
    intake.close()

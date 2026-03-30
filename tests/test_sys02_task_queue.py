import sqlite3
import pytest
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from openclaw_skills.orchestrator.task_worker import TaskQueueManager

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    # Initialize schema
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

def test_claim_next_task(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status) VALUES ('task-1', '{}', 'cpu', 'queued')")
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status) VALUES ('task-2', '{}', 'gpu', 'queued')")
    conn.commit()
    conn.close()
    
    manager = TaskQueueManager(temp_db)
    
    # Claim any tier
    task = manager.claim_next_task()
    assert task is not None
    assert task['id'] == 'task-1'
    assert task['status'] == 'processing'
    
    # Verify DB state
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT status FROM tasks WHERE id='task-1'").fetchone()
    assert row[0] == 'processing'
    conn.close()
    manager.close()

def test_fail_task_with_retry(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status, attempt_count, max_retries) VALUES ('task-1', '{}', 'cpu', 'processing', 0, 2)")
    conn.commit()
    conn.close()
    
    manager = TaskQueueManager(temp_db)
    
    # Try 1
    res = manager.fail_task_with_retry('task-1', 'Error 1')
    assert res == 'QUEUED_FOR_RETRY'
    
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT status, attempt_count, last_error FROM tasks WHERE id='task-1'").fetchone()
    assert row[0] == 'queued'
    assert row[1] == 1
    assert row[2] == 'Error 1'
    conn.close()
    
    # Try 2
    res = manager.fail_task_with_retry('task-1', 'Error 2')
    assert res == 'HITL_REQUIRED'
    
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT status, attempt_count, last_error FROM tasks WHERE id='task-1'").fetchone()
    assert row[0] == 'pending_hitl'
    assert row[1] == 2
    assert row[2] == 'Error 2'
    conn.close()
    
    manager.close()

def test_circuit_breaker(temp_db):
    # Already hitting max_retries directly
    conn = sqlite3.connect(temp_db)
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status, attempt_count, max_retries) VALUES ('task-1', '{}', 'cpu', 'processing', 2, 3)")
    conn.commit()
    conn.close()
    
    manager = TaskQueueManager(temp_db)
    res = manager.fail_task_with_retry('task-1', 'Error 3')
    assert res == 'HITL_REQUIRED'
    
    task = manager.claim_next_task()
    assert task is None # Should not claim HITL tasks
    manager.close()

def test_release_stalled_tasks(temp_db):
    conn = sqlite3.connect(temp_db)
    # Stalled task
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status, updated_at) VALUES ('task-old', '{}', 'cpu', 'processing', datetime('now', '-40 minutes'))")
    # Active task
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status, updated_at) VALUES ('task-new', '{}', 'cpu', 'processing', datetime('now', '-10 minutes'))")
    # Completed task
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status, updated_at) VALUES ('task-comp', '{}', 'cpu', 'completed', datetime('now', '-40 minutes'))")
    conn.commit()
    conn.close()
    
    manager = TaskQueueManager(temp_db)
    count = manager.release_stalled_tasks(timeout_minutes=30)
    assert count == 1
    
    conn = sqlite3.connect(temp_db)
    # the old processing task should be requeued
    assert conn.execute("SELECT status FROM tasks WHERE id='task-old'").fetchone()[0] == 'queued'
    # the active processing task should remain processing
    assert conn.execute("SELECT status FROM tasks WHERE id='task-new'").fetchone()[0] == 'processing'
    # the completed task should remain completed
    assert conn.execute("SELECT status FROM tasks WHERE id='task-comp'").fetchone()[0] == 'completed'

    conn.close()
    manager.close()

import sqlite3
import pytest
import os
import tempfile
from pathlib import Path

from openclaw_skills.orchestrator.task_worker import TaskQueueManager
from openclaw_skills.orchestrator.pi_bridge import CodingAgentBridge

@pytest.fixture
def temp_db():
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

def test_format_spawn_request():
    bridge = CodingAgentBridge()
    task_id = "123"
    task_payload = "Write tests"
    project_root = "/home/user/project"
    factory_context = "[Context is strictly injected]"
    
    payload = bridge.format_spawn_request(task_id, task_payload, project_root, factory_context)
    
    assert payload == {
        "runtime": "acp",
        "agentId": "pi",
        "mode": "run",
        "task": "[Context is strictly injected]\n\nWrite tests\n",
        "cwd": "/home/user/project",
        "label": "Factory-Task-123"
    }
    
    # Test without factory_context
    payload_no_ctx = bridge.format_spawn_request(task_id, task_payload, project_root)
    assert payload_no_ctx == {
        "runtime": "acp",
        "agentId": "pi",
        "mode": "run",
        "task": "Write tests\n",
        "cwd": "/home/user/project",
        "label": "Factory-Task-123"
    }

def test_mark_task_as_delegated(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("INSERT INTO tasks (id, payload, required_tier, status) VALUES ('task-1', '{}', 'cpu', 'processing')")
    conn.commit()
    conn.close()
    
    manager = TaskQueueManager(temp_db)
    manager.mark_task_as_delegated('task-1', 'sub-agent-session-abc')
    
    conn = sqlite3.connect(temp_db)
    row = conn.execute("SELECT status, session_id FROM tasks WHERE id='task-1'").fetchone()
    assert row[0] == 'processing_subagent'
    assert row[1] == 'sub-agent-session-abc'
    conn.close()
    
    manager.close()

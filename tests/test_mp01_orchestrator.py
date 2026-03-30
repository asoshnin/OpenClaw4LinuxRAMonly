import os
import sqlite3
import pytest
import tempfile
from unittest.mock import patch, MagicMock

from openclaw_skills.orchestrator.artifact_gatherer import get_safe_diff
from openclaw_skills.factory_orchestrator import run_orchestrator

@pytest.fixture
def mock_db():
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

@patch("openclaw_skills.orchestrator.artifact_gatherer.subprocess.run")
def test_get_safe_diff(mock_run):
    mock_result = MagicMock()
    mock_result.stdout = "a" * 15000
    mock_run.return_value = mock_result
    
    diff = get_safe_diff("/some/path", "abc1234")
    
    # Check truncation
    assert len(diff) == 12000 + len("\n\n[DIFF TRUNCATED: Exceeds 12k chars]")
    assert "[DIFF TRUNCATED: Exceeds 12k chars]" in diff
    
    # Check git diff call
    args = mock_run.call_args[0][0]
    cwd = mock_run.call_args[1]['cwd']
    assert args == ["git", "diff", "abc1234", "HEAD", "--", ".", ":(exclude)*.lock", ":(exclude)*.json.bak"]
    assert cwd == "/some/path"

@patch("openclaw_skills.factory_orchestrator.subprocess.run")
@patch("openclaw_skills.factory_orchestrator.TaskQueueManager")
def test_run_orchestrator_phase2(mock_manager_class, mock_subprocess):
    # Phase 2: Claim task and format to Pi
    mock_manager = MagicMock()
    mock_manager_class.return_value = mock_manager
    
    mock_task = {
        "id": "task-999",
        "payload": "Create hello state",
        "required_tier": "cpu"
    }
    
    mock_manager.claim_next_task.return_value = mock_task
    
    mock_sp_result = MagicMock()
    mock_sp_result.stdout = "def456\n"
    mock_subprocess.return_value = mock_sp_result
    
    # When inbound_message is None
    result = run_orchestrator(None)
    
    # Since we mocked TaskQueueManager, we don't have real DB interaction, but we verify standard output format
    assert result["agentId"] == "pi"
    assert "Create hello state" in result["task"]
    assert "Factory-Task-task-999" == result["label"]
    
    # verify delegate
    args = mock_manager.mark_task_as_delegated.call_args[0]
    assert args[0] == "task-999"
    assert args[1].startswith("pending-uuid-")
    assert args[2] == "def456"

@patch("openclaw_skills.factory_orchestrator.TaskQueueManager")
@patch("openclaw_skills.factory_orchestrator.get_safe_diff")
@patch("openclaw_skills.factory_orchestrator.run_audit")
def test_run_orchestrator_phase1(mock_run_audit, mock_gatherer, mock_manager_class):
    mock_manager = MagicMock()
    mock_manager_class.return_value = mock_manager
    
    mock_task = {
        "id": "task-888",
        "payload": "Write test cases",
        "baseline_commit": "abcdef1"
    }
    mock_manager.get_active_subagent_task.return_value = mock_task
    
    mock_gatherer.return_value = "diff text"
    
    mock_audit_res = {
        "status": "🟢 SIGN OFF",
        "findings": ["Looks great"]
    }
    mock_run_audit.return_value = mock_audit_res
    
    result = run_orchestrator("Done with subagent")
    
    assert result == mock_audit_res
    mock_run_audit.assert_called_once_with(artifact_text="diff text", task_context="Write test cases")
    mock_manager.mark_task_completed.assert_called_once_with("task-888")

@patch("openclaw_skills.factory_orchestrator.TaskQueueManager")
@patch("openclaw_skills.factory_orchestrator.get_safe_diff")
@patch("openclaw_skills.factory_orchestrator.run_audit")
def test_run_orchestrator_phase1_fail(mock_run_audit, mock_gatherer, mock_manager_class):
    mock_manager = MagicMock()
    mock_manager_class.return_value = mock_manager
    mock_manager.get_active_subagent_task.return_value = {"id": "task-111", "payload": "Do it", "baseline_commit": "xyz"}
    
    mock_run_audit.return_value = {
        "status": "🔴 NO GO",
        "findings": ["Terrible implementation"]
    }
    
    run_orchestrator("Failed test")
    
    mock_manager.fail_task_with_retry.assert_called_once_with("task-111", "Terrible implementation")

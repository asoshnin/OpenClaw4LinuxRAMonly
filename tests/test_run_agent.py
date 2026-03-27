"""
test_run_agent.py — Unit tests for the minimal agent runner.

All Ollama calls are mocked — no live service required.
"""
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock


def _make_ollama_mock(response_text: str):
    """Returns a context-manager mock that simulates a successful Ollama response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"response": response_text}).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


@patch("urllib.request.urlopen")
def test_run_agent_happy_path(mock_urlopen, tmp_db):
    """run_agent returns the LLM response and writes an AGENT_RUN audit log entry."""
    mock_urlopen.return_value = _make_ollama_mock("I am the Mega-Orchestrator.")

    import architect_tools as at
    result = at.run_agent(tmp_db, "kimi-orch-01", "What is your role?")

    assert result == "I am the Mega-Orchestrator."

    # Verify audit log was written
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT action, agent_id FROM audit_logs WHERE action='AGENT_RUN'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][1] == "kimi-orch-01"


@patch("urllib.request.urlopen")
def test_run_agent_audit_log_truncated(mock_urlopen, tmp_db):
    """Audit log rationale is truncated to 500 chars even for long responses."""
    long_response = "X" * 2000
    mock_urlopen.return_value = _make_ollama_mock(long_response)

    import architect_tools as at
    at.run_agent(tmp_db, "kimi-orch-01", "Verbose task")

    conn = sqlite3.connect(tmp_db)
    rationale = conn.execute(
        "SELECT rationale FROM audit_logs WHERE action='AGENT_RUN'"
    ).fetchone()[0]
    conn.close()
    assert len(rationale) <= 500


def test_run_agent_unknown_agent_raises(tmp_db):
    """run_agent raises ValueError for an agent_id not in the DB."""
    import architect_tools as at
    with pytest.raises(ValueError, match="not found"):
        at.run_agent(tmp_db, "nonexistent-agent-99", "Any task")


@patch("urllib.request.urlopen")
def test_run_agent_ollama_unreachable_raises(mock_urlopen, tmp_db):
    """run_agent raises RuntimeError when Ollama is unreachable."""
    import urllib.error
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

    import architect_tools as at
    with pytest.raises(RuntimeError, match="Ollama unreachable"):
        at.run_agent(tmp_db, "kimi-orch-01", "Any task")


@patch("urllib.request.urlopen")
def test_run_agent_empty_response_raises(mock_urlopen, tmp_db):
    """run_agent raises RuntimeError when Ollama returns an empty response string."""
    mock_urlopen.return_value = _make_ollama_mock("")  # empty response

    import architect_tools as at
    with pytest.raises(RuntimeError, match="empty response"):
        at.run_agent(tmp_db, "kimi-orch-01", "Any task")


@patch("urllib.request.urlopen")
def test_run_agent_no_hitl_interaction(mock_urlopen, tmp_db):
    """run_agent must not call deploy_pipeline_with_ui or generate_token."""
    mock_urlopen.return_value = _make_ollama_mock("response")

    import architect_tools as at
    with patch.object(at, "deploy_pipeline_with_ui") as mock_deploy, \
         patch.object(at, "generate_token") as mock_token:
        at.run_agent(tmp_db, "kimi-orch-01", "Task")
        mock_deploy.assert_not_called()
        mock_token.assert_not_called()

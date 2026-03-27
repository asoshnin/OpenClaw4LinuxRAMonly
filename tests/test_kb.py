"""
test_kb.py — Unit tests for the Knowledge Base module.

Covers: load/format, submit_kb_proposal, approve_kb_proposal (HITL gate),
agent cannot self-approve, invalid inputs.
"""
import json
import os
import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────

def _write_kb(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _minimal_kb() -> dict:
    return {
        "security_rules": ["Rule A", "Rule B"],
        "capability_boundaries": ["kimi-orch-01: tool_x"],
        "epistemic_invariants": ["Invariant 1"],
    }


# ── load_knowledge_base ────────────────────────────────────────────────────

def test_load_kb_success(isolated_workspace):
    kb_file = isolated_workspace / "knowledge_base.json"
    _write_kb(kb_file, _minimal_kb())

    import kb
    result = kb.load_knowledge_base(str(kb_file))
    assert "security_rules" in result
    assert result["security_rules"] == ["Rule A", "Rule B"]


def test_load_kb_file_not_found(isolated_workspace):
    import kb
    with pytest.raises(FileNotFoundError):
        kb.load_knowledge_base(str(isolated_workspace / "nonexistent.json"))


def test_load_kb_malformed_json(isolated_workspace):
    bad_file = isolated_workspace / "bad_kb.json"
    bad_file.write_text("{not valid json :::}")

    import kb
    with pytest.raises(json.JSONDecodeError):
        kb.load_knowledge_base(str(bad_file))


# ── format_kb_for_prompt ──────────────────────────────────────────────────

def test_format_kb_for_prompt_contains_rules(isolated_workspace):
    import kb
    data = _minimal_kb()
    output = kb.format_kb_for_prompt(data)

    assert "[SYSTEM RULES]" in output
    assert "Rule A" in output
    assert "[CAPABILITIES]" in output
    assert "kimi-orch-01" in output
    assert "[INVARIANTS]" in output
    assert "Invariant 1" in output


def test_format_kb_empty_sections(isolated_workspace):
    """Empty sections produce no output — no stray headers."""
    import kb
    output = kb.format_kb_for_prompt({"security_rules": [], "capability_boundaries": [], "epistemic_invariants": []})
    assert "[SYSTEM RULES]" not in output


# ── submit_kb_proposal ────────────────────────────────────────────────────

def test_submit_kb_proposal_success(tmp_db):
    import kb
    uid = kb.submit_kb_proposal(
        tmp_db, "kimi-orch-01", "rule_add",
        "security_rules", "New rule text", "Testing"
    )
    assert isinstance(uid, int)
    assert uid > 0

    conn = sqlite3.connect(tmp_db)
    row = conn.execute(
        "SELECT * FROM proposed_kb_updates WHERE update_id=?", (uid,)
    ).fetchone()
    conn.close()
    assert row is not None
    # status index = 6 (update_id, proposed_by, update_type, target_key, proposed_value, rationale, status, ...)
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM proposed_kb_updates WHERE update_id=?", (uid,)
    ).fetchone()
    conn.close()
    assert row["status"] == "pending"


def test_submit_kb_proposal_invalid_type(tmp_db):
    import kb
    with pytest.raises(ValueError, match="Invalid update_type"):
        kb.submit_kb_proposal(
            tmp_db, "kimi-orch-01", "rule_explode",
            "security_rules", "value", "bad type"
        )


# ── approve_kb_proposal ───────────────────────────────────────────────────

def test_approve_kb_proposal_valid_token(tmp_db, isolated_workspace):
    """Valid HITL token → updates status, writes to KB file, logs KB_APPROVED."""
    kb_file = isolated_workspace / "knowledge_base.json"
    _write_kb(kb_file, _minimal_kb())

    import kb as kb_mod

    uid = kb_mod.submit_kb_proposal(
        tmp_db, "kimi-orch-01", "rule_add",
        "security_rules", "New approved rule", "Test approval"
    )

    # Mock the HITL validate_token so we don't need a live token file
    with patch("kb.validate_token", return_value=True):
        kb_mod.approve_kb_proposal(tmp_db, uid, "mocked-valid-token", kb_path=str(kb_file))

    # Check status updated
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM proposed_kb_updates WHERE update_id=?", (uid,)
    ).fetchone()
    conn.close()
    assert row["status"] == "approved"

    # Check KB file updated
    updated_kb = json.loads(kb_file.read_text())
    assert "New approved rule" in updated_kb["security_rules"]

    # Check audit log
    conn = sqlite3.connect(tmp_db)
    actions = [r[0] for r in conn.execute("SELECT action FROM audit_logs").fetchall()]
    conn.close()
    assert "KB_APPROVED" in actions


def test_approve_kb_proposal_invalid_token(tmp_db, isolated_workspace):
    """Invalid HITL token → PermissionError, no file write."""
    kb_file = isolated_workspace / "knowledge_base.json"
    _write_kb(kb_file, _minimal_kb())
    original_content = kb_file.read_text()

    import kb as kb_mod

    uid = kb_mod.submit_kb_proposal(
        tmp_db, "kimi-orch-01", "rule_add",
        "security_rules", "Should not appear", "Test"
    )

    with pytest.raises(PermissionError):
        kb_mod.approve_kb_proposal(tmp_db, uid, "bad-token", kb_path=str(kb_file))

    # KB file must not be modified
    assert kb_file.read_text() == original_content


def test_agent_cannot_approve_own_proposal(tmp_db, isolated_workspace):
    """
    An agent calls submit_kb_proposal, then attempts approve_kb_proposal
    without a valid HITL token — must be blocked by PermissionError.
    """
    kb_file = isolated_workspace / "knowledge_base.json"
    _write_kb(kb_file, _minimal_kb())

    import kb as kb_mod

    uid = kb_mod.submit_kb_proposal(
        tmp_db, "kimi-orch-01", "rule_add",
        "security_rules", "Autonomous edit", "Self-modification attempt"
    )

    # Agent does NOT have access to a valid token — it tries a fake one
    with pytest.raises(PermissionError):
        kb_mod.approve_kb_proposal(tmp_db, uid, "fake-token", kb_path=str(kb_file))

    # Confirm proposal is still pending
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM proposed_kb_updates WHERE update_id=?", (uid,)
    ).fetchone()
    conn.close()
    assert row["status"] == "pending"

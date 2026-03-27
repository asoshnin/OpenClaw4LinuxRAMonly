"""
test_validate_token.py — Burn-on-Read HITL token tests.

Covers: correct token, wrong token, missing file, and the critical
double-call replay-attack prevention (burn-on-read).
"""
import os
import pytest


def _get_funcs(ws):
    import architect_tools as at
    return at.generate_token, at.validate_token, at.TOKEN_FILE


def test_correct_token_returns_true(isolated_workspace):
    """Writing a token then validating it with the correct value returns True."""
    generate_token, validate_token, token_file = _get_funcs(isolated_workspace)
    token = generate_token()
    result = validate_token(token)
    assert result is True


def test_correct_token_deletes_file(isolated_workspace):
    """After a successful validation the token file is deleted (burn-on-read)."""
    generate_token, validate_token, token_file = _get_funcs(isolated_workspace)
    token = generate_token()
    assert os.path.exists(str(token_file))
    validate_token(token)
    assert not os.path.exists(str(token_file))


def test_wrong_token_returns_false(isolated_workspace):
    """Providing the wrong token returns False and still burns the file."""
    generate_token, validate_token, token_file = _get_funcs(isolated_workspace)
    generate_token()
    result = validate_token("completely-wrong-token")
    assert result is False
    assert not os.path.exists(str(token_file)), "Token file must be burned even on wrong token"


def test_missing_token_file_returns_false(isolated_workspace):
    """Calling validate_token when no token file exists returns False (no exception)."""
    _, validate_token, token_file = _get_funcs(isolated_workspace)
    assert not os.path.exists(str(token_file))
    result = validate_token("any-token")
    assert result is False


def test_replay_attack_prevented(isolated_workspace):
    """
    Burn-on-read: calling validate_token twice with the same correct token
    must return True the first time and False the second (file already burned).
    """
    generate_token, validate_token, _ = _get_funcs(isolated_workspace)
    token = generate_token()
    first = validate_token(token)
    second = validate_token(token)   # file is gone — no replay
    assert first is True
    assert second is False


def test_token_file_permissions(isolated_workspace):
    """Token file is written with mode 0o600 (user-only read/write)."""
    generate_token, _, token_file = _get_funcs(isolated_workspace)
    generate_token()
    stat = os.stat(str(token_file))
    # Extract permission bits
    perms = oct(stat.st_mode)[-3:]
    assert perms == "600", f"Expected 600, got {perms}"

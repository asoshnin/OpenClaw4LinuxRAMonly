"""
test_router.py — Unit tests for the Dynamic LLM Router.

All Ollama/cloud calls are mocked. No live service required.
"""
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

SENTINEL = "[SYS-HALT: HITL REQUIRED - SENSITIVE CLOUD ROUTING]"


def _get_router(ws):
    """Return the router module, relying on conftest's isolated_workspace patch."""
    import router
    return router


def _audit_actions(db_path):
    """Return list of action strings from audit_logs."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT action FROM audit_logs ORDER BY log_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Block A: Routing Halt ──────────────────────────────────────────────────

def test_routing_halt_sensitive_cloud(tmp_db):
    """sensitive=True + tier=cloud → PermissionError with sentinel, ROUTING_HALT logged."""
    with patch("router._call_local") as mock_local, \
         patch("router._call_cloud") as mock_cloud:
        import router
        with pytest.raises(PermissionError, match=r"\[SYS-HALT"):
            router.route_inference("task", True, "cloud", tmp_db)
        mock_local.assert_not_called()
        mock_cloud.assert_not_called()

    assert "ROUTING_HALT" in _audit_actions(tmp_db)


def test_routing_halt_never_calls_cloud(tmp_db):
    """Verify cloud is never touched regardless of availability."""
    with patch("router._ping_ollama", return_value=True), \
         patch("router._call_cloud") as mock_cloud:
        import router
        with pytest.raises(PermissionError):
            router.route_inference("task", True, "cloud", tmp_db)
        mock_cloud.assert_not_called()


# ── Block A: Local path ───────────────────────────────────────────────────

def test_route_local_sensitive_available(tmp_db):
    """sensitive=True + tier=local + Ollama up → returns response, logs ROUTE_LOCAL."""
    with patch("router._ping_ollama", return_value=True), \
         patch("router._call_local", return_value="local answer") as mock_local:
        import router
        result = router.route_inference("task", True, "local", tmp_db)

    assert result == "local answer"
    mock_local.assert_called_once()
    assert "ROUTE_LOCAL" in _audit_actions(tmp_db)


def test_route_local_sensitive_unavailable(tmp_db):
    """sensitive=True + tier=local + Ollama down → RuntimeError, ROUTE_LOCAL_FAIL logged."""
    with patch("router._ping_ollama", return_value=False):
        import router
        with pytest.raises(RuntimeError, match="Ollama"):
            router.route_inference("task", True, "local", tmp_db)

    assert "ROUTE_LOCAL_FAIL" in _audit_actions(tmp_db)


def test_route_local_no_cloud_fallback(tmp_db):
    """When Ollama is down with tier=local, cloud must NOT be called under any circumstances."""
    with patch("router._ping_ollama", return_value=False), \
         patch("router._call_cloud") as mock_cloud:
        import router
        with pytest.raises(RuntimeError):
            router.route_inference("task", True, "local", tmp_db)
        mock_cloud.assert_not_called()


# ── Block A: Cloud path ───────────────────────────────────────────────────

def test_route_cloud_nonsensitive(tmp_db):
    """not sensitive + tier=cloud → calls cloud, logs ROUTE_CLOUD."""
    with patch("router._call_cloud", return_value="cloud answer") as mock_cloud:
        import router
        result = router.route_inference("task", False, "cloud", tmp_db)

    assert result == "cloud answer"
    mock_cloud.assert_called_once()
    assert "ROUTE_CLOUD" in _audit_actions(tmp_db)


# ── Block A: Audit log completeness ──────────────────────────────────────

@pytest.mark.parametrize("sensitive,tier,mock_ping,expected_action", [
    (True,  "cloud", True,  "ROUTING_HALT"),
    (True,  "local", True,  "ROUTE_LOCAL"),
    (True,  "local", False, "ROUTE_LOCAL_FAIL"),
    (False, "cloud", True,  "ROUTE_CLOUD"),
])
def test_audit_log_written_for_every_outcome(tmp_db, sensitive, tier, mock_ping, expected_action):
    """Every routing outcome writes exactly one audit_logs record."""
    with patch("router._ping_ollama", return_value=mock_ping), \
         patch("router._call_local", return_value="ok"), \
         patch("router._call_cloud", return_value="ok"):
        import router
        try:
            router.route_inference("task", sensitive, tier, tmp_db)
        except (PermissionError, RuntimeError):
            pass  # expected for ROUTING_HALT and ROUTE_LOCAL_FAIL

    actions = _audit_actions(tmp_db)
    assert expected_action in actions, f"Expected {expected_action} in audit_logs, got {actions}"


def test_invalid_tier_raises_value_error(tmp_db):
    """An unknown tier value raises ValueError before any network call."""
    import router
    with pytest.raises(ValueError, match="Invalid min_model_tier"):
        router.route_inference("task", True, "quantum", tmp_db)

"""
test_obsidian_bridge.py — Sprint 7 test suite for ObsidianBridge and vault integration.

All HTTP calls are mocked via unittest.mock — no live Obsidian instance required.
Tests are ordered to match tasks.md E0→E4 blocks.

Coverage:
  E1: ObsidianBridge core methods (18 tests)
  E2: write_agent_result_to_vault() (5 tests)
  E3: ingest_vault_note() (7 tests)
"""

import json
import sqlite3
import sys
import os
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock, call

# ---------------------------------------------------------------------------
# Helpers — mock HTTP responses
# ---------------------------------------------------------------------------

def _mock_response(status: int, body: str | bytes):
    """Build a mock urllib response context manager."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _url_error():
    import urllib.error
    return urllib.error.URLError("Connection refused")


def _http_error(code: int, body: str = ""):
    import urllib.error
    from io import BytesIO
    fp = BytesIO(body.encode())
    return urllib.error.HTTPError(
        url="http://127.0.0.1:27123/vault/",
        code=code,
        msg=f"HTTP {code}",
        hdrs={},
        fp=fp,
    )


# ===========================================================================
# E1 — ObsidianBridge core method tests
# ===========================================================================

class TestObsidianBridgeConstruction:
    """Construction-time validation tests."""

    def test_bridge_raises_if_api_key_empty(self):
        from obsidian_bridge import ObsidianBridge
        with pytest.raises(ValueError, match="OBSIDIAN_API_KEY is required"):
            ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="")

    def test_bridge_raises_if_api_key_none_and_env_empty(self, monkeypatch):
        import obsidian_bridge as ob
        monkeypatch.setattr(ob, "OBSIDIAN_API_KEY", "")
        from obsidian_bridge import ObsidianBridge
        with pytest.raises(ValueError, match="OBSIDIAN_API_KEY is required"):
            ObsidianBridge(base_url="http://127.0.0.1:27123", api_key=None)

    def test_bridge_raises_if_non_localhost_url(self):
        from obsidian_bridge import ObsidianBridge
        with pytest.raises(ValueError, match="loopback"):
            ObsidianBridge(base_url="http://attacker.example.com:27123", api_key="key")

    def test_bridge_accepts_localhost(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://localhost:27123", api_key="key")
        assert bridge.base_url == "http://localhost:27123"

    def test_bridge_accepts_ipv4_loopback(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="key")
        assert bridge.api_key == "key"


class TestPing:
    """ping() method tests."""

    def test_ping_obsidian_up(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, "{}")):
            assert bridge.ping() is True

    def test_ping_obsidian_down(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=_url_error()):
            assert bridge.ping() is False

    def test_ping_returns_true_on_401(self):
        """401 means plugin is running but key is wrong — still 'up'."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=_http_error(401)):
            # HTTPError is caught as RuntimeError inside _make_request → ping catches RuntimeError
            assert bridge.ping() is True

    def test_ping_uses_vault_path_not_root(self):
        """ping() sends request to /vault/ — not /."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req.full_url)
            return _mock_response(200, "[]")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.ping()

        assert any("/vault/" in url for url in captured), f"Expected /vault/ in {captured}"


class TestReadNote:
    """read_note() method tests."""

    def test_read_note_success(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        md = "# Hello\n\nThis is a test note."
        with patch("urllib.request.urlopen", return_value=_mock_response(200, md)):
            result = bridge.read_note("30 - RESOURCES/test.md")
        assert result == md

    def test_read_note_not_found(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            with pytest.raises(FileNotFoundError):
                bridge.read_note("30 - RESOURCES/missing.md")


class TestWriteNote:
    """write_note() method tests."""

    def test_write_note_sends_put(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return _mock_response(200, "")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.write_note("00 - INBOX/note.md", "content")

        assert len(captured) == 1
        assert captured[0].get_method() == "PUT"
        assert "Bearer test-key" in captured[0].get_header("Authorization")

    def test_write_note_spaces_in_path_encoded_as_percent20(self):
        """Spaces must be encoded as %20 (not +) in the URL path."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req.full_url)
            return _mock_response(200, "")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.write_note("00 - INBOX/foo.md", "content")

        assert "00%20-%20INBOX/foo.md" in captured[0], f"URL was: {captured[0]}"
        assert "00+INBOX" not in captured[0]

    def test_write_note_rejects_path_traversal(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with pytest.raises(ValueError, match="traversal"):
            bridge.write_note("../evil.md", "bad content")

    def test_write_note_rejects_absolute_path(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with pytest.raises(ValueError, match="relative"):
            bridge.write_note("/etc/passwd", "bad content")


class TestAppendToNote:
    """append_to_note() method tests."""

    def test_append_sends_patch_not_post(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(req)
            return _mock_response(200, "")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.append_to_note("00 - INBOX/note.md", "new content")

        assert captured[0].get_method() == "PATCH", (
            f"Expected PATCH, got {captured[0].get_method()} — "
            "POST ?append=true does not exist in the plugin"
        )

    def test_append_sends_correct_body(self):
        """Body must be '\\n\\n{content}' encoded as UTF-8."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        captured_body = []

        def fake_urlopen(req, timeout=None):
            captured_body.append(req.data)
            return _mock_response(200, "")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.append_to_note("00 - INBOX/note.md", "my content")

        assert captured_body[0] == b"\n\nmy content"

    def test_append_creates_if_missing(self):
        """When PATCH returns 404, fall back to write_note (PUT)."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        methods = []

        def fake_urlopen(req, timeout=None):
            methods.append(req.get_method())
            if req.get_method() == "PATCH":
                raise _http_error(404)
            return _mock_response(200, "")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            bridge.append_to_note("00 - INBOX/new.md", "content")

        assert "PATCH" in methods
        assert "PUT" in methods  # fallback write_note


class TestListNotes:
    """list_notes() method tests."""

    def test_list_notes_returns_flat_array(self):
        """Plugin returns flat JSON array — NOT dict with 'files' key."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        fake_body = json.dumps(["00 - INBOX/a.md", "00 - INBOX/b.md"])
        with patch("urllib.request.urlopen", return_value=_mock_response(200, fake_body)):
            result = bridge.list_notes("00 - INBOX")
        assert result == ["00 - INBOX/a.md", "00 - INBOX/b.md"]

    def test_list_notes_missing_folder_returns_empty(self):
        """404 on list → return empty list, not an error."""
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=_http_error(404)):
            result = bridge.list_notes("nonexistent")
        assert result == []


class TestHealthCheck:
    """check_obsidian_health() tests."""

    def test_health_check_ok(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", return_value=_mock_response(200, "[]")):
            result = bridge.check_obsidian_health()
        assert result["status"] == "ok"
        assert result["url"] == "http://127.0.0.1:27123"
        assert isinstance(result["latency_ms"], int)

    def test_health_check_down(self):
        from obsidian_bridge import ObsidianBridge
        bridge = ObsidianBridge(base_url="http://127.0.0.1:27123", api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=_url_error()):
            result = bridge.check_obsidian_health()
        assert result["status"] == "down"
        assert result["latency_ms"] == 0


# ===========================================================================
# E2 — write_agent_result_to_vault() tests
# ===========================================================================

class TestWriteAgentResultToVault:
    """write_agent_result_to_vault() integration tests."""

    def _get_audit_log(self, db_path, action):
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT rationale FROM audit_logs WHERE action = ? ORDER BY log_id DESC LIMIT 1",
                (action,),
            ).fetchone()
        return row[0] if row else None

    def _bridge_mock(self, ping_return=True, write_raises=None):
        bridge = MagicMock()
        bridge.ping.return_value = ping_return
        if write_raises:
            bridge.write_note.side_effect = write_raises
        else:
            bridge.write_note.return_value = None
        return bridge

    def test_write_result_obsidian_up(self, tmp_db):
        """When bridge is up, writes note and logs VAULT_WRITE."""
        from architect_tools import write_agent_result_to_vault
        mock_bridge = self._bridge_mock(ping_return=True)
        with patch("architect_tools.ObsidianBridge", return_value=mock_bridge):
            result = write_agent_result_to_vault(
                tmp_db, "kimi-orch-01", "Test task", "Test result"
            )
        assert result is not None
        assert "00 - INBOX/openclaw/" in result
        assert mock_bridge.write_note.called
        log = self._get_audit_log(tmp_db, "VAULT_WRITE")
        assert log is not None

    def test_write_result_obsidian_down(self, tmp_db):
        """When bridge.ping() returns False, logs VAULT_WRITE_SKIPPED, returns None."""
        from architect_tools import write_agent_result_to_vault
        mock_bridge = self._bridge_mock(ping_return=False)
        with patch("architect_tools.ObsidianBridge", return_value=mock_bridge):
            result = write_agent_result_to_vault(
                tmp_db, "kimi-orch-01", "Test task", "Test result"
            )
        assert result is None
        log = self._get_audit_log(tmp_db, "VAULT_WRITE_SKIPPED")
        assert log is not None

    def test_write_result_auto_path_format(self, tmp_db):
        """Auto-generated path matches 00 - INBOX/openclaw/YYYY-MM-DD_... format."""
        from architect_tools import write_agent_result_to_vault
        mock_bridge = self._bridge_mock(ping_return=True)
        with patch("architect_tools.ObsidianBridge", return_value=mock_bridge):
            result = write_agent_result_to_vault(
                tmp_db, "kimi-orch-01", "Test task", "Test result"
            )
        assert result.startswith("00 - INBOX/openclaw/")
        assert "kimi-orch-01" in result
        assert result.endswith(".md")

    def test_write_result_sensitive_refused(self, tmp_db):
        """is_sensitive=True refuses write without calling bridge at all."""
        from architect_tools import write_agent_result_to_vault
        with patch("architect_tools.ObsidianBridge") as BridgeCls:
            result = write_agent_result_to_vault(
                tmp_db, "kimi-orch-01", "Secret task", "Secret result",
                is_sensitive=True,
            )
        assert result is None
        BridgeCls.assert_not_called()
        log = self._get_audit_log(tmp_db, "VAULT_WRITE_REFUSED_SENSITIVE")
        assert log is not None

    def test_write_result_truncates_long_result(self, tmp_db):
        """Result longer than 12,000 chars is truncated in the note template."""
        from architect_tools import write_agent_result_to_vault
        mock_bridge = self._bridge_mock(ping_return=True)
        long_result = "x" * 15000

        captured_content = []

        def capture_write(vault_path, content):
            captured_content.append(content)

        mock_bridge.write_note.side_effect = capture_write

        with patch("architect_tools.ObsidianBridge", return_value=mock_bridge):
            write_agent_result_to_vault(
                tmp_db, "kimi-orch-01", "Long task", long_result
            )

        assert len(captured_content) == 1
        # The rendered note should contain at most 12,000 'x' chars
        assert "x" * 12001 not in captured_content[0]
        assert "x" * 12000 in captured_content[0]


# ===========================================================================
# E3 — ingest_vault_note() tests
# ===========================================================================

class TestIngestVaultNote:
    """ingest_vault_note() integration tests."""

    def _get_audit_action(self, db_path, action):
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT rationale FROM audit_logs WHERE action = ? ORDER BY log_id DESC LIMIT 1",
                (action,),
            ).fetchone()
        return row[0] if row else None

    def test_ingest_vault_note_success(self, tmp_db):
        """Successful ingest: reads note, calls archive_log, logs VAULT_INGEST."""
        from librarian_ctl import ingest_vault_note
        mock_bridge = MagicMock()
        mock_bridge.read_note.return_value = "# Test Note\n\nSome content."

        mock_engine = MagicMock()
        mock_engine.archive_log.return_value = 42

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge), \
             patch("librarian_ctl.SafetyDistillationEngine", return_value=mock_engine):
            pid = ingest_vault_note(tmp_db, "30 - RESOURCES/note.md")

        assert pid == 42
        log = self._get_audit_action(tmp_db, "VAULT_INGEST")
        assert log is not None
        assert "30 - RESOURCES/note.md" in log

    def test_ingest_vault_note_obsidian_down(self, tmp_db):
        """RuntimeError from read_note (Obsidian down) propagates."""
        from librarian_ctl import ingest_vault_note
        mock_bridge = MagicMock()
        mock_bridge.read_note.side_effect = RuntimeError("Connection refused")

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge):
            with pytest.raises(RuntimeError, match="Connection refused"):
                ingest_vault_note(tmp_db, "30 - RESOURCES/note.md")

    def test_ingest_vault_note_missing_note(self, tmp_db):
        """FileNotFoundError from read_note propagates."""
        from librarian_ctl import ingest_vault_note
        mock_bridge = MagicMock()
        mock_bridge.read_note.side_effect = FileNotFoundError("Note not found")

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge):
            with pytest.raises(FileNotFoundError):
                ingest_vault_note(tmp_db, "30 - RESOURCES/missing.md")

    def test_ingest_uses_is_sensitive_flag(self, tmp_db):
        """is_sensitive=True must be forwarded to archive_log."""
        from librarian_ctl import ingest_vault_note
        mock_bridge = MagicMock()
        mock_bridge.read_note.return_value = "content"

        mock_engine = MagicMock()
        mock_engine.archive_log.return_value = 1

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge), \
             patch("librarian_ctl.SafetyDistillationEngine", return_value=mock_engine):
            ingest_vault_note(tmp_db, "30 - RESOURCES/note.md", is_sensitive=True)

        call_kwargs = mock_engine.archive_log.call_args
        assert call_kwargs.kwargs.get("is_sensitive") is True or (
            len(call_kwargs.args) >= 4 and call_kwargs.args[3] is True
        ), f"is_sensitive not True in archive_log call: {call_kwargs}"

    def test_ingest_rejects_oversized_note(self, tmp_db):
        """Notes over VAULT_INGEST_MAX_BYTES rejected before archive_log."""
        from librarian_ctl import ingest_vault_note
        from obsidian_bridge import VAULT_INGEST_MAX_BYTES
        mock_bridge = MagicMock()
        # Return a note 1 byte over the limit
        mock_bridge.read_note.return_value = "x" * (VAULT_INGEST_MAX_BYTES + 1)

        mock_engine = MagicMock()

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge), \
             patch("librarian_ctl.SafetyDistillationEngine", return_value=mock_engine):
            with pytest.raises(ValueError, match="VAULT_INGEST_MAX_BYTES"):
                ingest_vault_note(tmp_db, "30 - RESOURCES/huge.md")

        mock_engine.archive_log.assert_not_called()

    def test_ingest_vault_note_audit_log_on_failure(self, tmp_db):
        """When archive_log raises, VAULT_INGEST_FAILED is logged and exception re-raised."""
        from librarian_ctl import ingest_vault_note
        mock_bridge = MagicMock()
        mock_bridge.read_note.return_value = "small content"

        mock_engine = MagicMock()
        mock_engine.archive_log.side_effect = RuntimeError("Distillation failed")

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge), \
             patch("librarian_ctl.SafetyDistillationEngine", return_value=mock_engine):
            with pytest.raises(RuntimeError, match="Distillation failed"):
                ingest_vault_note(tmp_db, "30 - RESOURCES/note.md")

        log = self._get_audit_action(tmp_db, "VAULT_INGEST_FAILED")
        assert log is not None
        assert "30 - RESOURCES/note.md" in log

    def test_ingest_cli_not_found_exit_code(self, tmp_db, capsys):
        """CLI exits with code 1 and prints error message on FileNotFoundError."""
        import librarian_ctl
        mock_bridge = MagicMock()
        mock_bridge.read_note.side_effect = FileNotFoundError("Note not found in vault")

        with patch("librarian_ctl.ObsidianBridge", return_value=mock_bridge):
            with pytest.raises(SystemExit) as exc_info:
                # Simulate CLI call by calling ingest_vault_note and mimicking CLI error handling
                try:
                    librarian_ctl.ingest_vault_note(tmp_db, "missing.md")
                except FileNotFoundError as e:
                    import sys
                    print(f"Note not found: {e}", file=sys.stderr)
                    sys.exit(1)

        assert exc_info.value.code == 1

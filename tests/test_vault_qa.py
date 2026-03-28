"""
tests/test_vault_qa.py — Sprint 11 tests for vault_qa() RAG function.

Coverage:
  - Full retrieval loop (search → read → assemble)
  - Unreadable note skipping (non-fatal)
  - Empty search results
  - Wikilink [[Note Name]] format from path stem
  - context_text '--- Source: [[X]] ---' header format
  - Context Guard truncation
  - Audit log contains query only (never note content)
  - RuntimeError when Obsidian is not running
  - Citation format ([[) present in context_text per source

All HTTP calls mocked — no live Obsidian required.
"""

import json
import os
import sys
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "openclaw_skills"))
sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _search_response(*filenames):
    return json.dumps([
        {"filename": fn, "score": float(len(filenames) - i)}
        for i, fn in enumerate(filenames)
    ])


SEARCH_API_PATH = "/search/simple/"


def _make_urlopen_side_effect(search_results_json, note_contents: dict):
    """
    Returns a side_effect callable that dispatches:
      - GET /search/simple/ → search_results_json
      - GET /vault/<path>   → note_contents[path]
    """
    import urllib.error

    def side_effect(req, timeout=None):
        url = req.full_url
        if SEARCH_API_PATH in url:
            return _mock_response(200, search_results_json)
        # extract vault path from URL
        vault_prefix = "/vault/"
        idx = url.find(vault_prefix)
        if idx != -1:
            import urllib.parse
            raw_path = url[idx + len(vault_prefix):]
            decoded_path = urllib.parse.unquote(raw_path)
            if decoded_path in note_contents:
                return _mock_response(200, note_contents[decoded_path])
            fp = MagicMock()
            fp.read.return_value = b"Not found"
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, fp)
        raise RuntimeError(f"Unexpected URL in test: {url}")

    return side_effect


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("OBSIDIAN_API_KEY", "test-key")
    monkeypatch.setenv("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")


@pytest.fixture()
def tmp_db(tmp_path):
    db = str(tmp_path / "factory.db")
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE audit_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT,
                action TEXT,
                rationale TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVaultQA:

    def test_vault_qa_returns_result_with_sources(self, env):
        """3 searchable, readable notes → VaultQAResult with 3 sources."""
        from obsidian_bridge import vault_qa
        search_json = _search_response(
            "20 - AREAS/23 - AI/LLM.md",
            "30 - RESOURCES/article.md",
            "10 - PROJECTS/proj.md",
        )
        note_contents = {
            "20 - AREAS/23 - AI/LLM.md": "# LLM Notes\nContent A",
            "30 - RESOURCES/article.md": "# Article\nContent B",
            "10 - PROJECTS/proj.md": "# Project\nContent C",
        }
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("agentic workflows", limit=3)

        assert result["query"] == "agentic workflows"
        assert len(result["sources"]) == 3
        assert result["total_chars"] == len(result["context_text"])

    def test_vault_qa_skips_unreadable_note(self, env):
        """1 of 3 notes is unreadable (404) → 2 sources, no exception raised."""
        from obsidian_bridge import vault_qa
        search_json = _search_response(
            "20 - AREAS/23 - AI/LLM.md",
            "MISSING/note.md",
            "30 - RESOURCES/article.md",
        )
        note_contents = {
            "20 - AREAS/23 - AI/LLM.md": "Content A",
            "30 - RESOURCES/article.md": "Content B",
            # MISSING/note.md is not in dict → 404
        }
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("test", limit=3)

        assert len(result["sources"]) == 2

    def test_vault_qa_empty_results_returns_empty_sources(self, env):
        """Search returns [] → sources=[], context_text=''."""
        from obsidian_bridge import vault_qa
        with patch("urllib.request.urlopen", return_value=_mock_response(200, "[]")):
            result = vault_qa("query with no matches")

        assert result["sources"] == []
        assert result["context_text"] == ""
        assert result["total_chars"] == 0

    def test_vault_qa_wikilink_format_strips_md_extension(self, env):
        """Path '20 - AI/Note One.md' → wikilink '[[Note One]]'."""
        from obsidian_bridge import vault_qa
        search_json = _search_response("20 - AI/Note One.md")
        note_contents = {"20 - AI/Note One.md": "Some content"}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("note one", limit=1)

        assert len(result["sources"]) == 1
        assert result["sources"][0]["wikilink"] == "[[Note One]]"

    def test_vault_qa_context_text_has_source_headers(self, env):
        """context_text contains '--- Source: [[X]] ---' for each source."""
        from obsidian_bridge import vault_qa
        search_json = _search_response("folder/My Note.md")
        note_contents = {"folder/My Note.md": "# Content\nSome text here"}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("my note", limit=1)

        assert "--- Source: [[My Note]] ---" in result["context_text"]

    def test_vault_qa_context_guard_truncation(self, env):
        """Aggregated content > _max_chars → context_text truncated."""
        from obsidian_bridge import vault_qa
        big_content = "X" * 5000
        search_json = _search_response("folder/big.md", "folder/big2.md")
        note_contents = {"folder/big.md": big_content, "folder/big2.md": big_content}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("big query", limit=2, _max_chars=3000)

        assert result["total_chars"] <= 3000
        assert len(result["context_text"]) <= 3000

    def test_vault_qa_audit_log_contains_query_only_not_content(self, env, tmp_db):
        """audit_logs.rationale contains query text, NOT note content."""
        from obsidian_bridge import vault_qa
        secret_content = "SUPER SECRET VAULT CONTENT XYZ"
        search_json = _search_response("folder/secret.md")
        note_contents = {"folder/secret.md": secret_content}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            vault_qa("my query", db_path=tmp_db, limit=1)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT action, rationale FROM audit_logs WHERE action='VAULT_QA'"
            ).fetchall()
        assert len(rows) == 1
        action, rationale = rows[0]
        assert action == "VAULT_QA"
        assert "my query" in rationale
        # Critically: note content must NOT appear in the audit trail
        assert secret_content not in rationale
        assert "SUPER SECRET" not in rationale

    def test_vault_qa_obsidian_not_running_raises_runtime_error(self, env):
        """ping() returns False → RuntimeError before any search."""
        from obsidian_bridge import vault_qa
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(RuntimeError, match="not running"):
                vault_qa("test query")

    def test_vault_qa_citation_format_in_context_per_source(self, env):
        """Each source's wikilink appears in context_text as [[ ]]."""
        from obsidian_bridge import vault_qa
        search_json = _search_response("A/Alpha.md", "B/Beta.md")
        note_contents = {"A/Alpha.md": "alpha content", "B/Beta.md": "beta content"}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("alpha beta", limit=2)

        assert "[[Alpha]]" in result["context_text"]
        assert "[[Beta]]" in result["context_text"]

    def test_vault_qa_note_truncated_to_per_note_max(self, env):
        """Each note excerpt is capped at VAULT_QA_NOTE_MAX_CHARS."""
        from obsidian_bridge import vault_qa, VAULT_QA_NOTE_MAX_CHARS
        long_note = "Y" * (VAULT_QA_NOTE_MAX_CHARS + 500)
        search_json = _search_response("folder/long.md")
        note_contents = {"folder/long.md": long_note}
        side_effect = _make_urlopen_side_effect(search_json, note_contents)
        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = vault_qa("long query", limit=1)

        assert len(result["sources"][0]["excerpt"]) == VAULT_QA_NOTE_MAX_CHARS

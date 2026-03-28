"""
tests/test_vault_qa_cli.py — Sprint 11 tests for the 'vault-qa' CLI subcommand.

Tests cmd_vault_qa() and the argument dispatch in architect_tools.py.
All HTTP calls mocked — no live Obsidian required.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARCHITECT = os.path.join(_REPO_ROOT, "openclaw_skills", "architect")
sys.path.insert(0, _ARCHITECT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "openclaw_skills"))
sys.path.insert(0, _REPO_ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vault_qa_result(query="test", n_sources=2, context_text=None):
    """Build a fake VaultQAResult for mocking vault_qa()."""
    sources = [
        {"path": f"folder/Note{i}.md", "wikilink": f"[[Note{i}]]", "excerpt": f"Content {i}"}
        for i in range(n_sources)
    ]
    if context_text is None:
        context_text = "\n\n".join(
            f"--- Source: [[Note{i}]] ---\nContent {i}" for i in range(n_sources)
        )
    return {
        "query": query,
        "sources": sources,
        "context_text": context_text,
        "total_chars": len(context_text),
    }


def _make_args(**kwargs):
    """Create a simple namespace that mimics parsed args."""
    defaults = {
        "query": "test query",
        "db_path": None,
        "limit": 5,
        "sensitive": False,
        "output_json": False,
        "command": "vault-qa",
    }
    defaults.update(kwargs)
    ns = MagicMock()
    for k, v in defaults.items():
        setattr(ns, k, v)
    return ns


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVaultQACLI:

    def test_vault_qa_cli_prints_markdown_header(self, capsys):
        """Valid query with results → stdout contains '## Vault QA:' header."""
        from architect_tools import cmd_vault_qa
        mock_result = _make_vault_qa_result(query="agentic workflows")
        args = _make_args(query="agentic workflows")

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", True), \
             patch("obsidian_bridge.vault_qa", return_value=mock_result):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "## Vault QA: agentic workflows" in captured.out
        assert "[[Note0]]" in captured.out
        assert "[[Note1]]" in captured.out

    def test_vault_qa_cli_json_flag_outputs_valid_json(self, capsys):
        """--json flag → stdout is valid JSON with expected keys."""
        from architect_tools import cmd_vault_qa
        mock_result = _make_vault_qa_result(query="json test")
        args = _make_args(query="json test", output_json=True)

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", True), \
             patch("obsidian_bridge.vault_qa", return_value=mock_result):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 0
        parsed = json.loads(captured.out)
        assert parsed["query"] == "json test"
        assert "sources" in parsed
        assert "context_text" in parsed

    def test_vault_qa_cli_no_results_exit_2(self, capsys):
        """Empty search results → exit code 2, error message to stderr."""
        from architect_tools import cmd_vault_qa
        empty_result = {
            "query": "obscure",
            "sources": [],
            "context_text": "",
            "total_chars": 0,
        }
        args = _make_args(query="obscure query with no matches")

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", True), \
             patch("obsidian_bridge.vault_qa", return_value=empty_result):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 2
        assert "No vault notes found" in captured.err

    def test_vault_qa_cli_obsidian_down_exit_1(self, capsys):
        """RuntimeError from vault_qa (Obsidian down) → exit code 1."""
        from architect_tools import cmd_vault_qa
        args = _make_args(query="any query")

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", True), \
             patch("obsidian_bridge.vault_qa",
                   side_effect=RuntimeError("Obsidian is not running")):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "Error" in captured.err

    def test_vault_qa_cli_vault_tools_unavailable_exit_1(self, capsys):
        """VAULT_TOOLS_AVAILABLE=False → exit code 1 with helpful message."""
        from architect_tools import cmd_vault_qa
        args = _make_args(query="any query")

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", False):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "obsidian_bridge" in captured.err

    def test_vault_qa_cli_sources_shown_in_markdown_with_footnotes(self, capsys):
        """Markdown output has ### [[Note]] [^N] headers and #### Sources footer."""
        from architect_tools import cmd_vault_qa
        mock_result = _make_vault_qa_result(n_sources=3)
        args = _make_args(output_json=False)

        with patch("architect_tools.VAULT_TOOLS_AVAILABLE", True), \
             patch("obsidian_bridge.vault_qa", return_value=mock_result):
            exit_code = cmd_vault_qa(args)

        captured = capsys.readouterr()
        assert exit_code == 0
        # Source headers with footnote markers
        assert "### [[Note0]] [^1]" in captured.out
        assert "### [[Note1]] [^2]" in captured.out
        assert "### [[Note2]] [^3]" in captured.out
        # Footer section
        assert "#### Sources" in captured.out
        assert "[^1]:" in captured.out
        assert "[^2]:" in captured.out
        assert "[^3]:" in captured.out

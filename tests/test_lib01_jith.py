"""
tests/test_lib01_jith.py
========================
Test suite for jith_discovery.py (LIB-01).

Coverage:
  1. Security: injection strings raise ValueError.
  2. Security: unknown verb raises ValueError with clear message.
  3. Recursive discovery: ['architect', 'vault-qa'] returns known flags.
  4. Recursive discovery: ['architect', 'run'] returns positional args.
  5. Idempotency: repeated calls with a warm cache return identical results.
  6. Atomic cache: concurrent reads from a populated cache don't corrupt it.
  7. Epistemic gap: validate_invocation raises RuntimeError with [EPISTEMIC_GAP]
     when a requested flag is missing.
  8. Cache TTL: an expired cache entry is re-fetched.
  9. Version invalidation: changing version fingerprint busts the cache.
 10. Parser: _parse_help_output correctly extracts subcommands and flags.
"""

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

import pytest

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import openclaw_skills.librarian.jith_discovery as jith
from openclaw_skills.librarian.jith_discovery import (
    _parse_help_output,
    _sanitize_args,
    get_cli_capabilities,
    validate_invocation,
    VERB_ALLOWLIST,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect JITH_CACHE_PATH to a tmp dir so tests don't pollute each other."""
    cache_file = tmp_path / "jith_cache.json"
    monkeypatch.setattr(jith, "JITH_CACHE_PATH", cache_file)
    yield cache_file


# ---------------------------------------------------------------------------
# 1 & 2. Security tests
# ---------------------------------------------------------------------------

def test_security_injection_characters_raise():
    """Injection characters must be rejected before any subprocess call."""
    with pytest.raises(ValueError, match="Injection character"):
        _sanitize_args(["architect", "; rm -rf /"])


def test_security_unknown_verb_raises():
    """Verbs not in VERB_ALLOWLIST must be rejected."""
    with pytest.raises(ValueError, match="not in the allowlist"):
        _sanitize_args(["rm", "-rf", "/"])


def test_security_path_traversal_raises():
    """Path traversal sequences must be rejected."""
    with pytest.raises(ValueError, match="Path traversal"):
        _sanitize_args(["architect", "../../etc/passwd"])


def test_security_shell_metachar_raises():
    """Shell metacharacters in subcommand slot must be rejected."""
    with pytest.raises(ValueError, match="Injection character"):
        _sanitize_args(["architect", "run|cat /etc/passwd"])


def test_allowlist_contents():
    """All expected root verbs are in the allowlist."""
    for verb in ("architect", "librarian"):
        assert verb in VERB_ALLOWLIST


# ---------------------------------------------------------------------------
# 3 & 4. Recursive discovery (real CLI probes against actual scripts)
# ---------------------------------------------------------------------------

def test_discover_architect_root_subcommands():
    """Top-level architect discovery returns known subcommands."""
    caps = get_cli_capabilities(["architect"])
    subs = caps["subcommands"]
    # These are stable across versions; if missing → real CLI changed
    for expected_sub in ("run", "deploy", "vault-qa"):
        assert expected_sub in subs, f"Missing subcommand: {expected_sub}"


def test_discover_architect_vault_qa_flags():
    """Recursive discovery: ['architect', 'vault-qa'] surfaces --query and --sensitive."""
    caps = get_cli_capabilities(["architect", "vault-qa"])
    flags = caps["options"]
    assert "--query" in flags, "--query flag not found in architect vault-qa"
    assert "--sensitive" in flags, "--sensitive flag not found in architect vault-qa"
    assert "--json" in flags, "--json flag not found in architect vault-qa"


def test_discover_architect_run_positionals():
    """Recursive discovery: ['architect', 'run'] surfaces positional args."""
    caps = get_cli_capabilities(["architect", "run"])
    # The run subcommand takes db_path, agent_id, task as positionals
    positionals = caps["positionals"]
    assert len(positionals) >= 1, f"Expected positionals in 'run', got: {positionals}"


def test_discover_librarian_subcommands():
    """Librarian discovery returns known subcommands."""
    caps = get_cli_capabilities(["librarian"])
    subs = caps["subcommands"]
    for expected in ("init", "bootstrap", "register-agent"):
        assert expected in subs, f"Missing librarian subcommand: {expected}"


# ---------------------------------------------------------------------------
# 5. Idempotency — repeated calls return identical results
# ---------------------------------------------------------------------------

def test_idempotency_same_result_on_repeated_calls():
    """Multiple calls with same args return identical CapabilityMaps."""
    caps1 = get_cli_capabilities(["architect", "vault-qa"])
    caps2 = get_cli_capabilities(["architect", "vault-qa"])
    caps3 = get_cli_capabilities(["architect", "vault-qa"])
    assert caps1 == caps2 == caps3


# ---------------------------------------------------------------------------
# 6. Concurrency — simultaneous reads don't corrupt the cache
# ---------------------------------------------------------------------------

def test_concurrent_cache_reads_dont_fail(tmp_path):
    """Concurrent reads from a warm cache must all succeed without exception."""
    # Warm the cache first
    get_cli_capabilities(["architect"])

    errors = []

    def reader():
        try:
            get_cli_capabilities(["architect"])
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Concurrent cache reads raised: {errors}"


# ---------------------------------------------------------------------------
# 7. Epistemic gap — validate_invocation raises on missing flag
# ---------------------------------------------------------------------------

def test_validate_invocation_raises_on_missing_flag():
    """validate_invocation must raise RuntimeError with [EPISTEMIC_GAP] tag."""
    with pytest.raises(RuntimeError, match=r"\[EPISTEMIC_GAP\]"):
        validate_invocation(["architect", "vault-qa"], ["--query", "--does-not-exist"])


def test_validate_invocation_passes_on_known_flags():
    """validate_invocation must NOT raise when flags are valid."""
    # Should not raise
    validate_invocation(["architect", "vault-qa"], ["--query", "--sensitive"])


# ---------------------------------------------------------------------------
# 8. Cache TTL expiry
# ---------------------------------------------------------------------------

def test_cache_ttl_expiry(monkeypatch):
    """An expired cache entry forces a fresh CLI probe."""
    # Warm the cache
    caps1 = get_cli_capabilities(["librarian"])

    # Manually expire the entry by backdating its timestamp
    data = json.loads(jith.JITH_CACHE_PATH.read_text())
    key = "librarian"
    data["entries"][key]["timestamp"] -= (jith.JITH_CACHE_TTL_SECONDS + 10)
    jith.JITH_CACHE_PATH.write_text(json.dumps(data))

    # Next call should trigger a fresh probe (not raise)
    caps2 = get_cli_capabilities(["librarian"])
    assert "subcommands" in caps2


# ---------------------------------------------------------------------------
# 9. Version-based cache invalidation
# ---------------------------------------------------------------------------

def test_version_fingerprint_busts_cache(monkeypatch):
    """Changing the version fingerprint must invalidate all cached entries."""
    # Warm cache with a fake version
    data = {
        "_version": "fake-v0.0.1",
        "entries": {
            "architect": {
                "timestamp": time.time(),
                "capabilities": {"subcommands": {}, "options": {}, "positionals": []},
            }
        },
    }
    jith.JITH_CACHE_PATH.write_text(json.dumps(data))

    # get_cli_capabilities should see version mismatch, re-probe, return real data
    caps = get_cli_capabilities(["architect"])
    # Real probe will have subcommands populated
    assert len(caps["subcommands"]) > 0


# ---------------------------------------------------------------------------
# 10. Parser unit tests (no subprocess)
# ---------------------------------------------------------------------------

_SAMPLE_HELP = """\
usage: architect_tools.py vault-qa [-h] --query QUERY [--db-path DB_PATH]
                                   [--limit LIMIT] [--sensitive] [--json]

options:
  -h, --help         show this help message and exit
  --query QUERY      Plain-text search query (required)
  --db-path DB_PATH  Optional factory.db path for audit logging
  --limit LIMIT      Max notes to retrieve (default 5, clamped to 1-10)
  --sensitive        Mark retrieval as sensitive
  --json             Output raw JSON instead of formatted Markdown
"""

def test_parser_extracts_flags():
    caps = _parse_help_output(_SAMPLE_HELP)
    assert "--query" in caps["options"]
    assert "--sensitive" in caps["options"]
    assert "--json" in caps["options"]


def test_parser_long_and_short_flags():
    caps = _parse_help_output(_SAMPLE_HELP)
    help_entry = caps["options"].get("--help")
    assert help_entry is not None
    assert help_entry["short"] == "-h"


def test_parser_takes_value_detection():
    caps = _parse_help_output(_SAMPLE_HELP)
    assert caps["options"]["--query"]["takes_value"] is True    # --query QUERY
    assert caps["options"]["--sensitive"]["takes_value"] is False  # no VALUE token


_SUBCOMMAND_HELP = """\
usage: architect_tools.py [-h] {gen-token,deploy,teardown,run,vault-qa} ...

Architect Tools CLI

positional arguments:
  {gen-token,deploy,teardown,run,vault-qa}
    gen-token           Generate a new HITL approval token
    deploy              Deploy a new pipeline (Requires HITL Token)
    run                 Run a task attributed to a registered agent
    vault-qa            RAG search with wikilink citations

options:
  -h, --help  show this help message and exit
"""

def test_parser_extracts_subcommands():
    caps = _parse_help_output(_SUBCOMMAND_HELP)
    assert "run" in caps["subcommands"]
    assert "vault-qa" in caps["subcommands"]
    assert "deploy" in caps["subcommands"]


if __name__ == "__main__":
    pytest.main(["-v", __file__])

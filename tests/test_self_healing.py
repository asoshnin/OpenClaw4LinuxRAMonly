"""
test_self_healing.py — Tests for the circuit-breaker JSON parser
and the scoped epistemic scrubber.

All LLM calls are mocked. No live Ollama required.
"""
import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock, call


# ── parse_json_with_retry ────────────────────────────────────────────────

def test_parse_json_success_first_attempt():
    """Valid JSON on first attempt — model_call_fn never invoked."""
    from self_healing import parse_json_with_retry
    mock_fn = MagicMock()
    result = parse_json_with_retry('{"facts": [], "scrubbed_log": "ok"}', mock_fn)
    assert result == {"facts": [], "scrubbed_log": "ok"}
    mock_fn.assert_not_called()


def test_parse_json_success_second_attempt():
    """First call returns bad JSON; repair returns valid JSON on second attempt."""
    from self_healing import parse_json_with_retry

    good_json = '{"facts": ["repaired"], "scrubbed_log": "fixed"}'
    mock_fn = MagicMock(return_value=good_json)

    result = parse_json_with_retry("not json at all", mock_fn, max_retries=3)
    assert result == {"facts": ["repaired"], "scrubbed_log": "fixed"}
    mock_fn.assert_called_once()


def test_parse_json_circuit_breaker_trips():
    """All repair attempts fail → RuntimeError raised."""
    from self_healing import parse_json_with_retry

    mock_fn = MagicMock(return_value="still not json {{{")

    with pytest.raises(RuntimeError, match="circuit breaker tripped"):
        parse_json_with_retry("bad", mock_fn, max_retries=3)


def test_circuit_breaker_exact_retry_count():
    """model_call_fn is called exactly max_retries times before trip."""
    from self_healing import parse_json_with_retry

    mock_fn = MagicMock(return_value="{{bad}}")
    max_r = 3

    with pytest.raises(RuntimeError):
        parse_json_with_retry("bad", mock_fn, max_retries=max_r)

    assert mock_fn.call_count == max_r


def test_parse_json_repair_prompt_content():
    """The repair prompt passed to model_call_fn mentions the broken text."""
    from self_healing import parse_json_with_retry

    captured = []

    def capture_fn(prompt):
        captured.append(prompt)
        return '{"facts": [], "scrubbed_log": "repaired"}'

    parse_json_with_retry("broken_input_token", capture_fn, max_retries=3)
    assert "broken_input_token" in captured[0]


# ── _distill_local circuit breaker integration ───────────────────────────

def test_distill_local_uses_circuit_breaker(isolated_workspace):
    """If Ollama always returns bad JSON, RuntimeError propagates from _distill_local."""
    from safety_engine import SafetyDistillationEngine

    engine = SafetyDistillationEngine()
    with patch.object(engine, "_call_ollama", return_value="{{not json}}"):
        with pytest.raises(RuntimeError, match="circuit breaker"):
            engine._distill_local("some raw log")


def test_distill_local_succeeds_on_second_ollama_call(isolated_workspace):
    """First _call_ollama returns bad JSON; second returns valid — no circuit trip."""
    from safety_engine import SafetyDistillationEngine

    engine = SafetyDistillationEngine()
    valid_json = '{"facts": ["f1"], "scrubbed_log": "clean"}'
    responses = iter(["not json", valid_json])

    with patch.object(engine, "_call_ollama", side_effect=lambda _: next(responses)):
        result = engine._distill_local("raw log")

    assert result == {"facts": ["f1"], "scrubbed_log": "clean"}


# ── Scoped Epistemic Scrubber (archive_log) ──────────────────────────────

def test_archive_invalid_source_type(tmp_db):
    """archive_log() raises ValueError for unknown source_type."""
    from safety_engine import SafetyDistillationEngine
    engine = SafetyDistillationEngine()
    with pytest.raises(ValueError, match="Invalid source_type"):
        engine.archive_log(tmp_db, "src-1", "log text", source_type="unknown")


@patch("safety_engine._SQLITE_VEC_AVAILABLE", False)
def test_archive_internal_skips_distillation(tmp_db, isolated_workspace):
    """source_type='internal' → distill_safety() must NOT be called."""
    from safety_engine import SafetyDistillationEngine
    engine = SafetyDistillationEngine()

    with patch.object(engine, "distill_safety") as mock_distill, \
         patch.object(engine, "_get_embedding", return_value=[0.1] * 768):
        # sqlite-vec not available — won't get past the availability check
        # but distill_safety call happens BEFORE that check
        try:
            engine.archive_log(tmp_db, "src-int", "audit log text", source_type="internal")
        except RuntimeError:
            pass  # RuntimeError from missing sqlite-vec is expected

        mock_distill.assert_not_called()


@patch("safety_engine._SQLITE_VEC_AVAILABLE", False)
def test_archive_external_calls_distillation(tmp_db, isolated_workspace):
    """source_type='external' → distill_safety() IS called."""
    from safety_engine import SafetyDistillationEngine
    engine = SafetyDistillationEngine()

    with patch.object(engine, "distill_safety", return_value={"facts": [], "scrubbed_log": "x"}) as mock_distill, \
         patch.object(engine, "_get_embedding", return_value=[0.1] * 768):
        try:
            engine.archive_log(tmp_db, "src-ext", "external data", source_type="external")
        except RuntimeError:
            pass  # sqlite-vec not available

        mock_distill.assert_called_once()


@patch("safety_engine._SQLITE_VEC_AVAILABLE", False)
def test_archive_internal_still_embeds(tmp_db, isolated_workspace):
    """Even for internal content, _get_embedding() must be called."""
    from safety_engine import SafetyDistillationEngine
    engine = SafetyDistillationEngine()

    with patch.object(engine, "distill_safety") as mock_distill, \
         patch.object(engine, "_get_embedding", return_value=[0.0] * 768) as mock_embed:
        try:
            engine.archive_log(tmp_db, "src-int", "audit", source_type="internal")
        except RuntimeError:
            pass  # sqlite-vec not available

        mock_embed.assert_called_once()
        mock_distill.assert_not_called()

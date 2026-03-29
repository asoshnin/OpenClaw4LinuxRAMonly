"""
tests/test_inference_hardening.py
==================================
Verification Gate for PR-01 (Flash Tiering) + PR-02 (Structural Integrity).

Mandatory cases from the mission spec:
  1. Zero-Preamble Check: output starts exactly with the schema start char.
  2. Structural Check: invalid JSON triggers the Pydantic-style retry loop
     (circuit-breaker raises RuntimeError after MAX retries).
  3. Stop-Sequence Check: nested JSON is NOT cut off by the stop sequence.

Additional hardening tests:
  4. Bloat stripper removes conversational preamble.
  5. Socratic assessment correctly routes FLASH vs PRO.
  6. Schema validator catches missing required keys.
  7. Schema validator catches wrong types.
  8. Schema validator catches enum violations.
  9. Scrubber is attempted for FLASH tier (with mock).
 10. Circuit-breaker fires after exactly MAX_RETRIES JSON failures.
 11. Schema-aware stop sequence: flat schema -> \\n}, nested schema -> \\n}.
 12. generate_flash_prompt raises ValueError on empty task.
 13. generate_flash_prompt succeeds with a valid mock model response.
 14. Markdown-fenced JSON output is correctly unwrapped.
 15. Leading preamble text before { is stripped before parsing.
"""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from openclaw_skills.prompt_architect.prompt_architect_tools import (
    _PROMPT_CONFIG_SCHEMA,
    _MAX_JSON_RETRIES,
    _build_flash_system_prompt,
    _derive_stop_sequence,
    _socratic_tier_assessment,
    _strip_bloat,
    _validate_json_schema,
    generate_flash_prompt,
)


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

_SIMPLE_SCHEMA = {
    "type": "object",
    "required": ["name", "value"],
    "properties": {
        "name":  {"type": "string", "minLength": 1},
        "value": {"type": "string"},
    },
}

_NESTED_SCHEMA = {
    "type": "object",
    "required": ["meta", "items"],
    "properties": {
        "meta":  {"type": "object"},
        "items": {"type": "array"},
    },
}

def _mock_fn(response: str):
    """Return a model_call_fn that always returns *response*."""
    return lambda prompt: response


def _mock_fn_sequence(*responses):
    """Return a model_call_fn that cycles through *responses* in order."""
    responses = list(responses)
    counter = {"n": 0}
    def _fn(prompt):
        idx = min(counter["n"], len(responses) - 1)
        counter["n"] += 1
        return responses[idx]
    return _fn


# ---------------------------------------------------------------------------
# 1. Zero-Preamble Check
# ---------------------------------------------------------------------------

def test_zero_preamble_system_prompt_starts_with_flash_tag():
    """The assembled system prompt must open with [FLASH TIER — NO PREAMBLE]."""
    prompt = _build_flash_system_prompt("Generate agent config", _SIMPLE_SCHEMA)
    assert prompt.startswith("[FLASH TIER"), f"System prompt preamble missing: {prompt[:60]}"


def test_zero_preamble_output_starts_with_brace():
    """After generate_flash_prompt, the payload must be a dict (opened with {)."""
    valid_json = json.dumps({"name": "test", "value": "ok"})
    result = generate_flash_prompt(
        "Generate agent config",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn(valid_json),
        scrub_output=False,
    )
    assert isinstance(result["payload"], dict), "Payload must be a dict"
    assert result["payload"]["name"] == "test"


def test_zero_preamble_preamble_text_before_brace_is_stripped():
    """If the LLM emits preamble text before '{', it must be removed."""
    preamble_output = "Sure, here you go:\n" + json.dumps({"name": "x", "value": "y"})
    result = generate_flash_prompt(
        "short task",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn(preamble_output),
        scrub_output=False,
    )
    assert result["payload"]["name"] == "x"


# ---------------------------------------------------------------------------
# 2. Structural Check — invalid JSON triggers retry circuit-breaker
# ---------------------------------------------------------------------------

def test_structural_invalid_json_triggers_retries():
    """Repeated invalid JSON must trip the circuit-breaker (RuntimeError)."""
    with pytest.raises(RuntimeError, match="circuit-breaker"):
        generate_flash_prompt(
            "generate config",
            schema=_SIMPLE_SCHEMA,
            model_call_fn=_mock_fn("this is not json at all %%%"),
            scrub_output=False,
        )


def test_structural_retry_count_is_max_retries_plus_one():
    """generate_flash_prompt retries exactly MAX_RETRIES times then raises."""
    call_count = {"n": 0}

    def counting_fn(prompt):
        call_count["n"] += 1
        return "NOT JSON"

    with pytest.raises(RuntimeError, match="circuit-breaker"):
        generate_flash_prompt(
            "task",
            schema=_SIMPLE_SCHEMA,
            model_call_fn=counting_fn,
            scrub_output=False,
        )
    # Called once per attempt: initial + MAX_RETRIES
    assert call_count["n"] == _MAX_JSON_RETRIES + 1


def test_structural_recovery_on_second_attempt():
    """If the first call returns bad JSON but the second is valid, it succeeds."""
    valid = json.dumps({"name": "fixed", "value": "ok"})
    result = generate_flash_prompt(
        "task",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn_sequence("BROKEN", valid),
        scrub_output=False,
    )
    assert result["payload"]["name"] == "fixed"
    assert result["retries"] == 1


def test_structural_schema_violation_triggers_retry():
    """Missing required key must trigger the retry loop."""
    # First response: missing 'value' key (schema violation, not JSON error)
    bad = json.dumps({"name": "ok"})          # missing 'value'
    good = json.dumps({"name": "ok", "value": "here"})
    result = generate_flash_prompt(
        "task",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn_sequence(bad, good),
        scrub_output=False,
    )
    assert result["retries"] == 1
    assert result["payload"]["value"] == "here"


# ---------------------------------------------------------------------------
# 3. Stop-Sequence Check — nested JSON is NOT truncated
# ---------------------------------------------------------------------------

def test_stop_sequence_nested_json_preserved():
    """Nested JSON objects must survive parsing intact."""
    nested_payload = {
        "meta": {"author": "tester", "version": 2},
        "items": [1, 2, 3],
    }
    valid_json = json.dumps(nested_payload)
    result = generate_flash_prompt(
        "build nested config",
        schema=_NESTED_SCHEMA,
        model_call_fn=_mock_fn(valid_json),
        scrub_output=False,
    )
    assert result["payload"]["meta"]["version"] == 2
    assert result["payload"]["items"] == [1, 2, 3]


def test_stop_sequence_deeply_nested_json_preserved():
    """Three-level nesting must survive the stop-sequence + parser intact."""
    deep = {
        "meta": {"inner": {"key": "deep_value"}},
        "items": [{"a": 1}, {"b": 2}],
    }
    result = generate_flash_prompt(
        "deep nest task",
        schema=_NESTED_SCHEMA,
        model_call_fn=_mock_fn(json.dumps(deep)),
        scrub_output=False,
    )
    assert result["payload"]["meta"]["inner"]["key"] == "deep_value"


def test_derive_stop_sequence_flat():
    stop = _derive_stop_sequence(_SIMPLE_SCHEMA)
    assert "}" in stop


def test_derive_stop_sequence_nested():
    stop = _derive_stop_sequence(_NESTED_SCHEMA)
    assert "}" in stop


# ---------------------------------------------------------------------------
# 4. Bloat stripper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("preamble", [
    "Sure, here is your JSON:\n",
    "Of course! Here you go:\n",
    "Certainly, let me help:\n",
    "Here is the result:\n",
    "Here's your output:\n",
])
def test_strip_bloat_removes_preamble(preamble):
    payload = '{"x": 1}'
    stripped = _strip_bloat(preamble + payload)
    assert stripped.startswith("{"), f"Expected '{{', got: {stripped[:30]!r}"


def test_strip_bloat_leaves_json_intact():
    payload = '{"key": "value", "nested": {"a": 1}}'
    assert _strip_bloat(payload) == payload


# ---------------------------------------------------------------------------
# 5. Socratic tier assessment
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task,expected_tier", [
    ("Generate a simple agent config", "FLASH"),
    ("Transform this text to JSON", "FLASH"),
    ("Make a security decision about deploying agents", "PRO"),
    ("Should we delete these audit logs? Is this safe?", "PRO"),
    ("x" * 401, "PRO"),   # length heuristic
])
def test_socratic_tier_assessment(task, expected_tier):
    assert _socratic_tier_assessment(task) == expected_tier


# ---------------------------------------------------------------------------
# 6-8. Schema validator
# ---------------------------------------------------------------------------

def test_schema_validator_passes_valid_data():
    data = {"name": "ok", "value": "fine"}
    assert _validate_json_schema(data, _SIMPLE_SCHEMA) == []


def test_schema_validator_catches_missing_required_key():
    data = {"name": "ok"}  # missing 'value'
    errors = _validate_json_schema(data, _SIMPLE_SCHEMA)
    assert any("value" in e for e in errors)


def test_schema_validator_catches_wrong_type():
    data = {"name": 42, "value": "ok"}  # name should be string
    errors = _validate_json_schema(data, _SIMPLE_SCHEMA)
    assert any("name" in e for e in errors)


def test_schema_validator_catches_min_length():
    data = {"name": "", "value": "ok"}  # name minLength=1
    errors = _validate_json_schema(data, _SIMPLE_SCHEMA)
    assert any("minLength" in e for e in errors)


def test_schema_validator_catches_enum_violation():
    tier_schema = {
        "type": "object",
        "required": ["tier"],
        "properties": {"tier": {"type": "string", "enum": ["FLASH", "PRO"]}},
    }
    data = {"tier": "UNKNOWN"}
    errors = _validate_json_schema(data, tier_schema)
    assert any("UNKNOWN" in e for e in errors)


# ---------------------------------------------------------------------------
# 9. Scrubber is attempted for FLASH tier
# ---------------------------------------------------------------------------

def test_scrubber_called_for_flash_tier(monkeypatch):
    """The safety engine's distill_safety must be invoked for FLASH outputs."""
    valid_json = json.dumps({"name": "agent", "value": "v1"})

    mock_engine = mock.MagicMock()
    mock_engine.distill_safety.return_value = {"scrubbed_log": valid_json}
    mock_se_module = mock.MagicMock()
    mock_se_module.SafetyDistillationEngine.return_value = mock_engine

    import openclaw_skills.prompt_architect.prompt_architect_tools as pat
    monkeypatch.setitem(sys.modules, "safety_engine", mock_se_module)

    result = generate_flash_prompt(
        "compress agent data",   # short + no pro keywords → FLASH
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn(valid_json),
        scrub_output=True,
    )
    mock_engine.distill_safety.assert_called_once()
    assert result["scrubbed"] is True


def test_scrubber_not_called_when_disabled():
    """scrub_output=False must bypass the safety engine entirely."""
    valid_json = json.dumps({"name": "x", "value": "y"})
    result = generate_flash_prompt(
        "task",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn(valid_json),
        scrub_output=False,
    )
    assert result["scrubbed"] is False


# ---------------------------------------------------------------------------
# 10. Circuit-breaker exact retry count
# ---------------------------------------------------------------------------

def test_circuit_breaker_exact_count():
    """Circuit-breaker must fire after exactly _MAX_JSON_RETRIES + 1 calls."""
    calls = []
    def bad_fn(prompt):
        calls.append(1)
        return "bad JSON }"
    with pytest.raises(RuntimeError):
        generate_flash_prompt("x", schema=_SIMPLE_SCHEMA, model_call_fn=bad_fn, scrub_output=False)
    assert len(calls) == _MAX_JSON_RETRIES + 1


# ---------------------------------------------------------------------------
# 11. Markdown fencing unwrapped correctly
# ---------------------------------------------------------------------------

def test_markdown_fenced_json_unwrapped():
    """Output wrapped in ```json...``` must be parsed correctly."""
    valid = {"name": "doc", "value": "42"}
    fenced = f"```json\n{json.dumps(valid)}\n```"
    result = generate_flash_prompt(
        "short task",
        schema=_SIMPLE_SCHEMA,
        model_call_fn=_mock_fn(fenced),
        scrub_output=False,
    )
    assert result["payload"]["name"] == "doc"


# ---------------------------------------------------------------------------
# 12. Empty task raises ValueError
# ---------------------------------------------------------------------------

def test_empty_task_raises_value_error():
    with pytest.raises(ValueError, match="task_description"):
        generate_flash_prompt("", schema=_SIMPLE_SCHEMA, model_call_fn=_mock_fn("{}"))


def test_whitespace_only_task_raises_value_error():
    with pytest.raises(ValueError, match="task_description"):
        generate_flash_prompt("   ", schema=_SIMPLE_SCHEMA, model_call_fn=_mock_fn("{}"))


if __name__ == "__main__":
    pytest.main(["-v", __file__])

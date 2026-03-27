"""
Self-Healing JSON Parser — Sprint 6
Circuit-breaker pattern for LLM JSON output validation.

Design invariants (from SKILL.md):
  - parse_json_with_retry() NEVER returns a degraded fallback dict.
  - After max_retries, it raises RuntimeError — always.
  - Each retry attempt is logged at WARNING level.
"""

import json
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def parse_json_with_retry(
    raw_text: str,
    model_call_fn: Callable[[str], str],
    max_retries: int = 3,
) -> dict:
    """
    Attempt to parse raw_text as JSON, using model_call_fn to repair on failure.

    Circuit breaker algorithm:
      1. Try json.loads(raw_text).
      2. On JSONDecodeError: call model_call_fn with a repair prompt,
         replace raw_text with the returned text, increment counter.
      3. After max_retries failures: raise RuntimeError (never degrade silently).

    Args:
        raw_text:      The string to parse as JSON.
        model_call_fn: Callable(broken_text: str) -> str — called to attempt repair.
                       Typically wraps a local LLM call.
        max_retries:   Maximum number of repair attempts before the circuit trips.

    Returns:
        dict: Successfully parsed JSON object.

    Raises:
        RuntimeError: After max_retries failed parse attempts.
    """
    attempt = 0
    current_text = raw_text

    while True:
        try:
            return json.loads(current_text)
        except json.JSONDecodeError as exc:
            if attempt >= max_retries:
                logger.warning(
                    "JSON parse circuit breaker tripped after %d retries. "
                    "Last error: %s. Last text preview: %.120r",
                    max_retries, exc, current_text,
                )
                raise RuntimeError(
                    f"JSON parse circuit breaker tripped after {max_retries} retries"
                ) from exc

            attempt += 1
            logger.warning(
                "JSON parse retry %d/%d. Error: %s. Attempting LLM repair.",
                attempt, max_retries, exc,
            )
            repair_prompt = (
                "Fix this malformed JSON. Return ONLY valid JSON with no explanation:\n\n"
                f"{current_text}"
            )
            current_text = model_call_fn(repair_prompt)

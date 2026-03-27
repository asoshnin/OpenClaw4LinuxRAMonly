"""
Dynamic LLM Router — Sprint 6
Enforces the HITL-guarded routing policy for all inference requests.

Non-negotiable rules (from SKILL.md):
  - is_sensitive=True + tier="cloud"  → ROUTING_HALT (PermissionError, never cloud)
  - Ollama unavailable + tier="local" → RuntimeError (never silent cloud fallback)
  - Every routing outcome is written to audit_logs unconditionally.
"""

import os
import sys
import json
import sqlite3
import logging
import argparse
import urllib.request
import urllib.error

try:
    from config import WORKSPACE_ROOT, OLLAMA_URL, LOCAL_MODEL
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import WORKSPACE_ROOT, OLLAMA_URL, LOCAL_MODEL

try:
    from librarian.librarian_ctl import validate_path as _validate_path_impl
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "librarian"))
    from librarian_ctl import validate_path as _validate_path_impl


def _get_validate_path():
    """Return the live validate_path, which reads WORKSPACE_ROOT at call time."""
    # Re-import every call so monkeypatch in tests is always reflected
    try:
        import librarian_ctl as _lctl
        return _lctl.validate_path
    except ImportError:
        return _validate_path_impl

logger = logging.getLogger(__name__)

# Routing halt sentinel — must match exactly across the system
ROUTING_HALT_SENTINEL = "[SYS-HALT: HITL REQUIRED - SENSITIVE CLOUD ROUTING]"

# Routing audit action constants
ACTION_ROUTE_LOCAL      = "ROUTE_LOCAL"
ACTION_ROUTE_CLOUD      = "ROUTE_CLOUD"
ACTION_ROUTE_LOCAL_FAIL = "ROUTE_LOCAL_FAIL"
ACTION_ROUTING_HALT     = "ROUTING_HALT"


def _log_routing_action(db_path: str, action: str, rationale: str) -> None:
    """Write one audit record for the routing decision. Non-fatal if DB unavailable."""
    try:
        validate_path = _get_validate_path()
        valid = validate_path(db_path)
        with sqlite3.connect(valid) as conn:
            conn.execute(
                "INSERT INTO audit_logs (action, rationale) VALUES (?, ?)",
                (action, rationale),
            )
            conn.commit()
        logger.debug("Router audit: action=%s", action)
    except Exception as e:
        logger.warning("Router audit write failed (non-fatal): %s", e)


def _ping_ollama() -> bool:
    """Return True if Ollama is reachable, False otherwise."""
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3.0)
        return True
    except (urllib.error.URLError, OSError):
        return False


def _call_local(task_text: str) -> str:
    """Call the local Ollama model directly (raw generation, no distillation)."""
    payload = json.dumps({
        "model":  LOCAL_MODEL,
        "prompt": task_text,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response = result.get("response", "").strip()
            if not response:
                raise RuntimeError(
                    f"Ollama returned an empty response for model '{LOCAL_MODEL}'."
                )
            return response
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {OLLAMA_URL}: {e}") from e


def _call_cloud(task_text: str) -> str:
    """Call Gemini cloud for non-sensitive distillation only."""
    # Import lazily — only needed for cloud path
    try:
        from librarian.safety_engine import SafetyDistillationEngine
    except ImportError:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "librarian"))
        from safety_engine import SafetyDistillationEngine
    engine = SafetyDistillationEngine()
    result = engine._distill_cloud(task_text)
    return json.dumps(result)


def route_inference(
    task_text: str,
    is_sensitive: bool,
    min_model_tier: str,
    db_path: str,
) -> str:
    """
    Route an inference request according to the HITL-guarded routing policy.

    Args:
        task_text:      The task or log content to process.
        is_sensitive:   True = must stay local; False = cloud permitted.
        min_model_tier: 'local' or 'cloud'.
        db_path:        Path to factory.db for audit logging.

    Returns:
        The model response string.

    Raises:
        ValueError:       Invalid min_model_tier value.
        PermissionError:  ROUTING_HALT — sensitive + cloud requested.
        RuntimeError:     Local Ollama unavailable when tier='local'.
    """
    if min_model_tier not in ("local", "cloud"):
        raise ValueError(
            f"Invalid min_model_tier '{min_model_tier}'. Must be 'local' or 'cloud'."
        )

    # ── Rule 1 (non-negotiable): sensitive + cloud → HALT ───────────────────
    if is_sensitive and min_model_tier == "cloud":
        _log_routing_action(
            db_path, ACTION_ROUTING_HALT,
            f"{ROUTING_HALT_SENTINEL} task_preview={task_text[:80]!r}",
        )
        logger.warning("ROUTING_HALT: sensitive data + cloud tier requested.")
        raise PermissionError(ROUTING_HALT_SENTINEL)

    # ── Local path ───────────────────────────────────────────────────────────
    if min_model_tier == "local":
        if not _ping_ollama():
            _log_routing_action(
                db_path, ACTION_ROUTE_LOCAL_FAIL,
                f"Ollama unreachable at {OLLAMA_URL}",
            )
            logger.error("ROUTE_LOCAL_FAIL: Ollama is down. No cloud fallback.")
            raise RuntimeError(
                f"Ollama is unreachable at {OLLAMA_URL}. "
                "Start it with: ollama serve"
            )
        response = _call_local(task_text)
        _log_routing_action(
            db_path, ACTION_ROUTE_LOCAL,
            f"Local inference completed. preview={response[:80]!r}",
        )
        logger.info("ROUTE_LOCAL: inference complete.")
        return response

    # ── Cloud path (is_sensitive=False only, enforced above) ─────────────────
    response = _call_cloud(task_text)
    _log_routing_action(
        db_path, ACTION_ROUTE_CLOUD,
        f"Cloud inference completed. preview={response[:80]!r}",
    )
    logger.info("ROUTE_CLOUD: inference complete.")
    return response


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="OpenClaw Dynamic LLM Router CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route_parser = subparsers.add_parser("route", help="Route an inference task")
    route_parser.add_argument("db_path",    help="Path to factory.db")
    route_parser.add_argument("task",       help="Task text to route")
    route_parser.add_argument(
        "--sensitive", dest="sensitive", action="store_true", default=True,
        help="Mark task as sensitive (default: True — safest default)",
    )
    route_parser.add_argument(
        "--no-sensitive", dest="sensitive", action="store_false",
        help="Mark task as non-sensitive",
    )
    route_parser.add_argument(
        "--tier", choices=["local", "cloud"], default="local",
        help="Minimum model tier (default: local — safest default)",
    )

    args = parser.parse_args()

    try:
        result = route_inference(
            task_text=args.task,
            is_sensitive=args.sensitive,
            min_model_tier=args.tier,
            db_path=args.db_path,
        )
        print(result)
    except PermissionError as e:
        print(f"[ROUTING_HALT] {e}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as e:
        print(f"[ROUTE_FAIL] {e}", file=sys.stderr)
        sys.exit(1)

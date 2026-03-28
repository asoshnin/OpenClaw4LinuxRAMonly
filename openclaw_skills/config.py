"""
OpenClaw Central Configuration — Sprint 5
Single source of truth for workspace paths and runtime constants.
Import WORKSPACE_ROOT from here; never hardcode paths elsewhere.
"""

import os
import logging
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Workspace root: controlled entirely by env var.
# Default: ~/.openclaw/workspace
# To override: export OPENCLAW_WORKSPACE=/your/path
# ---------------------------------------------------------------------------
_ws_env = os.environ.get("OPENCLAW_WORKSPACE", "")
if _ws_env:
    WORKSPACE_ROOT = Path(_ws_env).expanduser().resolve()
    logger.debug("OPENCLAW_WORKSPACE from env: %s", WORKSPACE_ROOT)
else:
    WORKSPACE_ROOT = Path.home() / ".openclaw" / "workspace"
    logger.debug("OPENCLAW_WORKSPACE defaulting to: %s", WORKSPACE_ROOT)

# Derived paths — all guaranteed to be children of WORKSPACE_ROOT
TOKEN_FILE      = WORKSPACE_ROOT / ".hitl_token"
DEFAULT_DB_PATH = WORKSPACE_ROOT / "factory.db"
DEFAULT_REGISTRY_PATH = WORKSPACE_ROOT / "REGISTRY.md"

# ---------------------------------------------------------------------------
# Inference constants — Tiered Local Priority
# ---------------------------------------------------------------------------
OLLAMA_REMOTE_URL = os.environ.get("OLLAMA_REMOTE_URL", "http://192.168.1.8:11434")   # GPU server
OLLAMA_LOCAL_URL  = os.environ.get("OLLAMA_LOCAL_URL",  "http://127.0.0.1:11434")     # Local fallback
LOCAL_MODEL       = "nn-tsuzu/lfm2.5-1.2b-instruct"
EMBED_MODEL       = "nomic-embed-text"

# Deprecated alias kept for backward compatibility — callers should migrate to get_active_ollama_url()
OLLAMA_URL = OLLAMA_LOCAL_URL

# ---------------------------------------------------------------------------
# Tiered inference URL resolver
# ---------------------------------------------------------------------------
_PROBE_TIMEOUT = 2.0  # seconds — fast fail; GPU server should respond quickly


def get_active_ollama_url() -> str | None:
    """Probe OLLAMA_REMOTE_URL then OLLAMA_LOCAL_URL; return first reachable, or None.

    Priority order:
      1. GPU server (OLLAMA_REMOTE_URL / default 192.168.1.8:11434)
      2. Local Linux Ollama (OLLAMA_LOCAL_URL / default 127.0.0.1:11434)
      3. None — both offline; caller MUST halt and ask Navigator for cloud approval.

    Fail-Safe Contract:
      If this returns None, NEVER automatically fall back to cloud (Gemini/etc.).
      Return 'INFERENCE_ALERT' message to the UI and wait for explicit 'Approve Cloud'
      from the Navigator.

    Returns:
        str: Base URL of the first reachable server.
        None: Both servers are offline.
    """
    for label, url in [("GPU-remote", OLLAMA_REMOTE_URL), ("local", OLLAMA_LOCAL_URL)]:
        try:
            urllib.request.urlopen(f"{url}/api/tags", timeout=_PROBE_TIMEOUT)
            logger.debug("get_active_ollama_url: %s reachable at %s", label, url)
            return url
        except Exception:
            logger.debug("get_active_ollama_url: %s unreachable at %s", label, url)
    logger.warning("get_active_ollama_url: both GPU-remote and local Ollama are offline.")
    return None


# Pre-built alert message — return this verbatim when get_active_ollama_url() → None
INFERENCE_ALERT = (
    "INFERENCE_ALERT: Both Local and GPU Ollama servers are offline. "
    "Permission required to use Cloud LLM (Gemini) for this task. "
    "Reply with 'Approve Cloud' to proceed."
)

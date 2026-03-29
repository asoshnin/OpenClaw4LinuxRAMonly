"""
OpenClaw Central Configuration — v2026.3.28
Single source of truth for workspace paths and runtime constants.

Multi-Project Context Switcher (PR-05):
  find_project_root() discovers the nearest project root by walking upward
  from the current directory until a `.factory_anchor` file is found.
  All project-scoped paths are derived from this discovered root.
  Import WORKSPACE_ROOT (Global Hub) or call find_project_root() for silos.
"""

import os
import logging
import urllib.request
import urllib.error
import json
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
# Backlog sync target — resolved absolutely at import time.
# This file lives in _Development/ (source tree), NOT in WORKSPACE_ROOT.
# Override via OPENCLAW_BACKLOG_PATH env var if needed.
# ---------------------------------------------------------------------------
_SOURCE_ROOT = Path(__file__).resolve().parent.parent  # openclaw_skills/ -> repo root
BACKLOG_UPDATE_PATH: Path = Path(
    os.environ.get("OPENCLAW_BACKLOG_PATH", "")
).resolve() if os.environ.get("OPENCLAW_BACKLOG_PATH") else (
    _SOURCE_ROOT / "_Development" / "2026-03-29_current_backlog_update.md"
)

# ---------------------------------------------------------------------------
# PR-05: Multi-Project Context Switcher
# ---------------------------------------------------------------------------

#: Sentinel filename that marks a directory as a project root (silo or hub).
FACTORY_ANCHOR = ".factory_anchor"

#: Maximum depth to walk upward when searching for the anchor.
_ANCHOR_SEARCH_DEPTH = 12


def find_project_root(start_path: str | Path | None = None) -> Path:
    """Locate the nearest project root by walking upward for `.factory_anchor`.

    Search order:
      1. Walk from *start_path* (default: ``Path.cwd()``) upward up to
         ``_ANCHOR_SEARCH_DEPTH`` levels, looking for a ``FACTORY_ANCHOR`` file.
      2. If not found: honour ``OPENCLAW_WORKSPACE`` env var (interpreted as the
         workspace *inside* a project root, so we return its parent).
      3. Final fallback: ``WORKSPACE_ROOT`` (the Global Hub workspace's parent —
         i.e., ``_SOURCE_ROOT``).

    Args:
        start_path: Directory to begin the upward search from.
                    Defaults to ``Path.cwd()``.

    Returns:
        Absolute ``Path`` of the nearest project root directory.
    """
    start = Path(start_path).resolve() if start_path else Path.cwd().resolve()

    current = start
    for _ in range(_ANCHOR_SEARCH_DEPTH):
        if (current / FACTORY_ANCHOR).exists():
            logger.debug("find_project_root: anchor found at %s", current)
            return current
        parent = current.parent
        if parent == current:
            # Reached filesystem root without finding the anchor
            break
        current = parent

    # Fallback 1: OPENCLAW_WORKSPACE env var → its parent is the project root
    ws_env = os.environ.get("OPENCLAW_WORKSPACE", "")
    if ws_env:
        ws_path = Path(ws_env).expanduser().resolve()
        fallback = ws_path.parent
        logger.debug(
            "find_project_root: no anchor found from %s; falling back to env-var parent %s",
            start, fallback,
        )
        return fallback

    # Fallback 2: _SOURCE_ROOT (Global Hub — the repo root itself)
    logger.debug(
        "find_project_root: no anchor and no env-var; using _SOURCE_ROOT %s", _SOURCE_ROOT
    )
    return _SOURCE_ROOT


def get_project_paths(project_root: Path | None = None) -> dict[str, Path]:
    """Return a dict of all standard project-scoped paths for *project_root*.

    Keys:
      ``root``       — the project root itself
      ``workspace``  — ``root/workspace/``
      ``project_db`` — ``root/workspace/project.db`` (project-scoped SQLite)
      ``docs_dir``   — ``root/docs/``
      ``memory_dir`` — ``root/memory/``

    Args:
        project_root: Explicit root. If ``None``, calls ``find_project_root()``.

    Returns:
        Dict mapping path-name strings to resolved ``Path`` objects.
    """
    root = project_root or find_project_root()
    return {
        "root":        root,
        "workspace":   root / "workspace",
        "project_db":  root / "workspace" / "project.db",
        "docs_dir":    root / "docs",
        "memory_dir":  root / "memory",
    }


# Convenience aliases — evaluated at import time from the Global Hub root
_GLOBAL_ROOT = _SOURCE_ROOT
GLOBAL_DB_PATH: Path = _GLOBAL_ROOT / "workspace" / "factory.db"   # Static Global Hub DB
DOCS_DIR:       Path = _GLOBAL_ROOT / "docs"
MEMORY_DIR:     Path = _GLOBAL_ROOT / "memory"

# ---------------------------------------------------------------------------
# Inference constants — Tiered Local Priority
# ---------------------------------------------------------------------------
OLLAMA_REMOTE_URL    = os.environ.get("OLLAMA_REMOTE_URL", "http://192.168.1.8:11434")   # GPU server
OLLAMA_LOCAL_URL     = os.environ.get("OLLAMA_LOCAL_URL",  "http://127.0.0.1:11434")     # Local fallback
REMOTE_LOCAL_MODEL   = os.environ.get("REMOTE_LOCAL_MODEL", "ministral-3:8b")               # GPU server model
# REMOTE_LOCAL_MODEL   = os.environ.get("REMOTE_LOCAL_MODEL", "qwen3.5:9b")               # GPU server model
LOCAL_MODEL          = "nn-tsuzu/lfm2.5-1.2b-instruct"                                  # Local Linux model
EMBED_MODEL          = "nomic-embed-text"
CLOUD_MODEL          = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")                 # Cloud model fallback

# Deprecated alias kept for backward compatibility — callers should migrate to get_active_ollama_url()
OLLAMA_URL = OLLAMA_LOCAL_URL

# ---------------------------------------------------------------------------
# Tiered inference URL resolver
# ---------------------------------------------------------------------------
_PROBE_TIMEOUT = 2.0  # seconds — fast fail; GPU server should respond quickly

def get_inference_tier_order(agent_id: str) -> list[tuple[str, str]]:
    """Determine the tiered fallback order for inference.
    
    prompt-architect gets Cloud-First priority. Everyone else gets Local-First.
    """
    if agent_id == 'prompt-architect':
        return [('cloud', CLOUD_MODEL), ('gpu', REMOTE_LOCAL_MODEL), ('cpu', LOCAL_MODEL)]
    return [('gpu', REMOTE_LOCAL_MODEL), ('cpu', LOCAL_MODEL), ('cloud', CLOUD_MODEL)]

def call_inference(tier: str, model: str, prompt: str, is_sensitive: bool = False, timeout: float = 600.0) -> str:
    """Unified inference caller that handles both cloud and tiered local Ollama calls.
    
    Args:
        tier: 'cloud', 'gpu', or 'cpu'
        model: Model string (e.g. 'gemini-1.5-pro' or 'qwen3.5:9b')
        prompt: Full prompt string
        is_sensitive: If True, cloud inference must be bypassed by the caller (fail-safe enforces this).
        timeout: Request timeout.
        
    Returns:
        Generated response string.
        
    Raises:
        ConnectionError: If probe fails for a local tier.
        RuntimeError: For inference failures.
        KeyError: If Gemini API key is missing.
        PermissionError: If is_sensitive=True and tier is cloud.
    """
    if tier == 'cloud':
        if is_sensitive:
            raise PermissionError("Airlock Breach: Attempted to send sensitive data to the cloud.")
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise KeyError("GEMINI_API_KEY environment variable not set.")
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                try:
                    return result["candidates"][0]["content"]["parts"][0]["text"].strip()
                except (KeyError, IndexError):
                    raise RuntimeError(f"Error parsing cloud model output for {model}.")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cloud Inference Error ({model}): {e}")

    # Local Ollama inference (Tier: gpu or cpu)
    active_url = OLLAMA_REMOTE_URL if tier == 'gpu' else OLLAMA_LOCAL_URL
    
    # 1. Fast fail probe
    try:
        urllib.request.urlopen(f"{active_url}/api/tags", timeout=_PROBE_TIMEOUT)
    except Exception as e:
        raise ConnectionError(f"{tier.upper()} server unreachable at {active_url}") from e

    # 2. Generation call
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(f"{active_url}/api/generate", data=payload, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response_text = result.get("response", "").strip()
            if not response_text:
                raise RuntimeError(f"Ollama returned an empty response for model '{model}'. Ensure model is pulled.")
            return response_text
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {active_url}: {e}. Ensure Ollama is running.") from e

def get_active_ollama_url() -> tuple[str, str] | None:
    """Probe OLLAMA_REMOTE_URL then OLLAMA_LOCAL_URL; return (url, model) or None.

    Priority order:
      1. GPU server  → (OLLAMA_REMOTE_URL, REMOTE_LOCAL_MODEL)
      2. Local Linux → (OLLAMA_LOCAL_URL,  LOCAL_MODEL)
      3. None        — both offline; caller MUST halt and ask Navigator for cloud approval.

    Fail-Safe Contract:
      If this returns None, NEVER automatically fall back to cloud (Gemini/etc.).
      Return INFERENCE_ALERT to the UI and wait for explicit 'Approve Cloud' from the Navigator.

    Returns:
        (url, model): Base URL and matching model name for the first reachable server.
        None: Both servers are offline.
    """
    for label, url, model in [
        ("GPU-remote", OLLAMA_REMOTE_URL, REMOTE_LOCAL_MODEL),
        ("local",      OLLAMA_LOCAL_URL,  LOCAL_MODEL),
    ]:
        try:
            urllib.request.urlopen(f"{url}/api/tags", timeout=_PROBE_TIMEOUT)
            logger.debug("get_active_ollama_url: %s reachable at %s (model=%s)", label, url, model)
            return url, model
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

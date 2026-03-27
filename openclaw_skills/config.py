"""
OpenClaw Central Configuration — Sprint 5
Single source of truth for workspace paths and runtime constants.
Import WORKSPACE_ROOT from here; never hardcode paths elsewhere.
"""

import os
import logging
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
# Inference constants
# ---------------------------------------------------------------------------
OLLAMA_URL   = "http://127.0.0.1:11434"
LOCAL_MODEL  = "nn-tsuzu/lfm2.5-1.2b-instruct"
EMBED_MODEL  = "nomic-embed-text"

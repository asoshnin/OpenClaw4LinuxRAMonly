#!/usr/bin/env bash
# =============================================================================
# setup.sh — OpenClaw Cold Start Initialisation
# Sprint 5: OSS Readiness | Sprint 7: Obsidian Integration | Sprint 9: Vault Tools
#
# Usage:
#   bash setup.sh
#   OPENCLAW_WORKSPACE=/custom/path bash setup.sh
#   OBSIDIAN_VAULT_PATH=~/obsidian-vault bash setup.sh
#
# Environment variables:
#   OPENCLAW_WORKSPACE  — OpenClaw workspace dir (default: ~/.openclaw/workspace)
#   OBSIDIAN_VAULT_PATH — Absolute path to Obsidian vault root.
#                         REQUIRED for Sprint 9 vault tools (vault-route, vault-health-check,
#                         discover_domains). Optional for Sprint 7 write/ingest operations.
#   OBSIDIAN_BASE_URL   — Local REST API URL (default: http://127.0.0.1:27123)
#   OBSIDIAN_API_KEY    — Required when using any Obsidian integration feature
#
# All steps are idempotent — safe to re-run on an already-initialised workspace.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Preflight: Python version check (requires 3.10+)
# ---------------------------------------------------------------------------
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown")
    echo "ERROR: Python 3.10+ is required (found: Python $PYVER)." >&2
    echo "       On Ubuntu 20.04: sudo apt install python3.10" >&2
    echo "       Or download from: https://www.python.org/downloads/" >&2
    exit 1
fi
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python $PYVER ✓"

# ---------------------------------------------------------------------------
# Resolve workspace
# ---------------------------------------------------------------------------
WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"

# Sanity guard: workspace must be inside HOME to prevent accidental writes elsewhere
if [[ "$WORKSPACE" != "$HOME"* ]]; then
    echo "ERROR: OPENCLAW_WORKSPACE ($WORKSPACE) must be inside your home directory ($HOME)." >&2
    echo "       Set OPENCLAW_WORKSPACE to a path under \$HOME and retry." >&2
    exit 1
fi

DB="$WORKSPACE/factory.db"
REGISTRY="$WORKSPACE/REGISTRY.md"

# Resolve script directory so we can locate openclaw_skills regardless of cwd
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBRARIAN="$SCRIPT_DIR/openclaw_skills/librarian"
ARCHITECT="$SCRIPT_DIR/openclaw_skills/architect"

echo "======================================================"
echo "  OpenClaw — Cold Start"
echo "======================================================"
echo "  Workspace : $WORKSPACE"
echo "  Database  : $DB"
echo "  Registry  : $REGISTRY"
echo "======================================================"
echo ""

# Export so that config.py picks it up for all subprocess calls
export OPENCLAW_WORKSPACE="$WORKSPACE"

# Create workspace directory if needed
mkdir -p "$WORKSPACE"
echo "[0/7] Workspace directory ready."

# ---------------------------------------------------------------------------
# Step 1: Initialise relational DB schema (WAL mode, core tables)
# ---------------------------------------------------------------------------
echo "[1/7] Initialising relational DB schema..."
python3 "$LIBRARIAN/librarian_ctl.py" init "$DB"

# ---------------------------------------------------------------------------
# Step 2: Bootstrap core agents and pipeline
# ---------------------------------------------------------------------------
echo "[2/7] Bootstrapping core agents and pipeline..."
python3 "$LIBRARIAN/librarian_ctl.py" bootstrap "$DB"

# ---------------------------------------------------------------------------
# Step 3: Initialise vector tables (sqlite-vec)
# ---------------------------------------------------------------------------
echo "[3/7] Initialising vector archive (sqlite-vec)..."
python3 - <<PYEOF
import sys, os
sys.path.insert(0, "$LIBRARIAN")
from vector_archive import init_vector_db
init_vector_db("$DB")
print("  Vector tables ready.")
PYEOF

# ---------------------------------------------------------------------------
# Step 4: Apply schema migrations (is_system, pipeline_agents, description, tool_names)
# ---------------------------------------------------------------------------
echo "[4/7] Applying schema migrations..."
python3 "$LIBRARIAN/migrate_db.py" "$DB"

# ---------------------------------------------------------------------------
# Step 5: Generate first REGISTRY.md
# ---------------------------------------------------------------------------
echo "[5/7] Generating REGISTRY.md..."
python3 "$LIBRARIAN/librarian_ctl.py" refresh-registry "$DB" "$REGISTRY"

# ---------------------------------------------------------------------------
# Step 6 (optional): Bootstrap Obsidian vault structure
# ---------------------------------------------------------------------------
if [[ -n "${OBSIDIAN_VAULT_PATH:-}" ]]; then
    echo ""
    echo "[6/7] Bootstrapping Obsidian vault structure at $OBSIDIAN_VAULT_PATH ..."
    python3 "$SCRIPT_DIR/openclaw_skills/obsidian_vault_bootstrap.py" "$OBSIDIAN_VAULT_PATH" || \
        echo "  [WARNING] Vault bootstrap failed — check OBSIDIAN_VAULT_PATH."
else
    echo ""
    echo "[6/7] OBSIDIAN_VAULT_PATH not set — skipping vault directory bootstrap."
    echo "       Set OBSIDIAN_VAULT_PATH and re-run to create Johnny.Decimal folders."
fi

# ---------------------------------------------------------------------------
# Step 7 (optional): Check Obsidian Local REST API health
# ---------------------------------------------------------------------------
echo ""
echo "[7/7] Checking Obsidian Local REST API..."
python3 - <<'PYEOF' || true
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath('.')), 'openclaw_skills'))
try:
    from obsidian_bridge import ObsidianBridge
    result = ObsidianBridge().check_obsidian_health()
    if result['status'] == 'ok':
        print(f"  [OBSIDIAN] ✓ Reachable at {result['url']} ({result['latency_ms']}ms)")
    else:
        print(f"  [OBSIDIAN] ✗ Not running. Start Obsidian before using vault sync features.")
        print(f"             Set OBSIDIAN_BASE_URL and OBSIDIAN_API_KEY if using custom config.")
except ValueError as e:
    print(f"  [OBSIDIAN] ✗ Configuration error: {e}")
    print(f"             Set OBSIDIAN_API_KEY env var before using vault features.")
except ImportError:
    print("  [OBSIDIAN] Module not found — Sprint 7 may not be installed.")
PYEOF

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "======================================================"
echo "  ✅  OpenClaw is ready."
echo "======================================================"
echo ""
echo "  Run an agent:"
echo "    python3 $ARCHITECT/architect_tools.py run \\"
echo "      \"$DB\" kimi-orch-01 \"Describe the current system state\""
echo ""
echo "  Ingest a vault note:"
echo "    python3 $LIBRARIAN/librarian_ctl.py ingest-vault-note \\"
echo "      \"$DB\" \"30 - RESOURCES/note.md\""
echo ""
echo "  Refresh registry after DB changes:"
echo "    python3 $LIBRARIAN/librarian_ctl.py refresh-registry \"$DB\" \"$REGISTRY\""
echo ""

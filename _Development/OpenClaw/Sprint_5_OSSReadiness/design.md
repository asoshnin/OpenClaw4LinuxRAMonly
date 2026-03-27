# Design: Sprint 5 (OSS Readiness & Minimal Agent Runner)

---

## [DES-S5-01] `openclaw_skills/config.py` — Central Configuration Module

This is the foundational change for the entire sprint. All other modules import from here.

```python
# openclaw_skills/config.py
import os
from pathlib import Path

# OPENCLAW_WORKSPACE env var takes priority; defaults to ~/.openclaw/workspace
WORKSPACE_ROOT = Path(
    os.environ.get("OPENCLAW_WORKSPACE", Path.home() / ".openclaw" / "workspace")
).expanduser().resolve()

TOKEN_FILE = WORKSPACE_ROOT / ".hitl_token"
DEFAULT_DB_PATH = WORKSPACE_ROOT / "factory.db"
DEFAULT_REGISTRY_PATH = WORKSPACE_ROOT / "REGISTRY.md"
```

**Airlock update:** `validate_path()` in both `librarian_ctl.py` and `architect_tools.py` changes from:
```python
base_dir = os.path.realpath("/home/alexey/openclaw-inbox/workspace/")
```
to:
```python
from config import WORKSPACE_ROOT
base_dir = str(WORKSPACE_ROOT)  # already resolved via Path.resolve()
```

The trailing-slash correctness is preserved because `Path.resolve()` never adds a trailing slash, so `startswith(base_dir)` is safe against prefix collisions (e.g., `~/.openclaw/workspace_evil` vs `~/.openclaw/workspace`). We add an explicit `os.sep` suffix check:
```python
if not (target_abs == base_dir or target_abs.startswith(base_dir + os.sep)):
    raise PermissionError(f"Airlock Breach: {target_abs} is outside {base_dir}")
```

---

## [DES-S5-02] `setup.sh` — Single-Command Cold Start

```bash
#!/usr/bin/env bash
# setup.sh — OpenClaw cold start initialisation
set -euo pipefail

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"
DB="$WORKSPACE/factory.db"
REGISTRY="$WORKSPACE/REGISTRY.md"
LIBRARIAN="openclaw_skills/librarian"
ARCHITECT="openclaw_skills/architect"

echo "[OpenClaw] Using workspace: $WORKSPACE"

# Sanity: workspace must be under HOME
if [[ "$WORKSPACE" != "$HOME"* ]]; then
  echo "ERROR: OPENCLAW_WORKSPACE ($WORKSPACE) must be inside your home directory."
  exit 1
fi

mkdir -p "$WORKSPACE"

# Step 1: Relational DB + schema
echo "[1/5] Initialising relational DB..."
python3 "$LIBRARIAN/librarian_ctl.py" init "$DB"

# Step 2: Bootstrap core agents + pipeline
echo "[2/5] Bootstrapping factory..."
python3 "$LIBRARIAN/librarian_ctl.py" bootstrap "$DB"

# Step 3: Vector tables (sqlite-vec)
echo "[3/5] Initialising vector archive..."
python3 -c "import sys; sys.path.insert(0,'$LIBRARIAN'); from vector_archive import init_vector_db; init_vector_db('$DB')"

# Step 4: Schema migrations (is_system, pipeline_agents, description, tool_names)
echo "[4/5] Applying schema migrations..."
python3 "$LIBRARIAN/migrate_db.py" "$DB"

# Step 5: Generate first registry
echo "[5/5] Generating REGISTRY.md..."
python3 "$LIBRARIAN/librarian_ctl.py" refresh-registry "$DB" "$REGISTRY"

echo ""
echo "✅ OpenClaw ready."
echo "   Workspace : $WORKSPACE"
echo "   Database  : $DB"
echo "   Registry  : $REGISTRY"
echo ""
echo "Run an agent:"
echo "  python3 $ARCHITECT/architect_tools.py run \"$DB\" kimi-orch-01 \"Describe the current system state\""
```

---

## [DES-S5-03] `run_agent()` — Minimal Agent Runner

**Location:** `openclaw_skills/architect/architect_tools.py` (new function + CLI subcommand)

**Sequence diagram:**
```
Navigator → run_agent(agent_id, task_text, db_path)
                │
                ├─ get_agent_persona(db_path, agent_id)       [librarian read]
                │     └─ ValueError if not found
                │
                ├─ find_faint_paths(db_path, task_text, limit=3)  [vector search]
                │     └─ Returns [] gracefully if archive empty
                │
                ├─ _build_prompt(agent_record, memory_context, task_text)
                │     └─ System: "You are {name}, {description}. Context: {memory}"
                │        Human:  "{task_text}"
                │
                ├─ _call_ollama(prompt)                        [local LLM]
                │     └─ RuntimeError if Ollama unreachable
                │
                └─ audit_log(db_path, agent_id, action='AGENT_RUN', rationale=response[:500])
                      └─ Returns response string
```

**Implementation sketch:**
```python
def run_agent(db_path: str, agent_id: str, task_text: str) -> str:
    """[DES-S5-03] Execute a task attributed to a registered agent."""
    # 1. Load agent
    agent = get_agent_persona(db_path, agent_id)
    if not agent:
        raise ValueError(f"Agent '{agent_id}' not found in {db_path}")

    # 2. Retrieve memory context (gracefully handles empty archive)
    try:
        from vector_archive import find_faint_paths
        memory = find_faint_paths(db_path, task_text, limit=3)
        memory_text = "\n".join(
            m.get("content_json", {}).get("scrubbed_log", "") for m in memory
        ) or "No prior memory available."
    except Exception:
        memory_text = "Memory archive unavailable."

    # 3. Build prompt
    description = agent.get("description") or agent.get("name", "AI agent")
    prompt = (
        f"You are {agent['name']} — {description}.\n"
        f"Relevant memory context:\n{memory_text}\n\n"
        f"Task: {task_text}"
    )

    # 4. Call local Ollama (no cloud — run_agent is always local)
    payload = {"model": LOCAL_MODEL, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60.0) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            response = result.get("response", "").strip()
            if not response:
                raise RuntimeError("Ollama returned empty response.")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {OLLAMA_URL}: {e}")

    # 5. Audit log (truncated to 500 chars to protect audit table size)
    valid_db = validate_path(db_path)
    with sqlite3.connect(valid_db) as conn:
        conn.execute(
            "INSERT INTO audit_logs (agent_id, action, rationale) VALUES (?, 'AGENT_RUN', ?)",
            (agent_id, response[:500])
        )
        conn.commit()

    return response
```

**New CLI constants (top of `architect_tools.py`):**
```python
OLLAMA_URL = "http://127.0.0.1:11434"
LOCAL_MODEL = "nn-tsuzu/lfm2.5-1.2b-instruct"
```

**CLI subcommand addition:**
```python
run_parser = subparsers.add_parser("run", help="Run a task attributed to a registered agent")
run_parser.add_argument("db_path", type=str)
run_parser.add_argument("agent_id", type=str)
run_parser.add_argument("task", type=str)
# ...
elif args.command == "run":
    result = run_agent(args.db_path, args.agent_id, args.task)
    print(result)
```

---

## [DES-S5-04] Schema Migration — `description` and `tool_names` Columns

**Location:** `openclaw_skills/librarian/migrate_db.py`

```python
# New migration block (idempotent)
for col, default in [("description", "''"), ("tool_names", "''")]:
    try:
        cursor.execute(f"ALTER TABLE agents ADD COLUMN {col} TEXT DEFAULT {default};")
        logging.info(f"Migration: added column '{col}' to agents table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logging.info(f"Migration: column '{col}' already exists — skipping.")
        else:
            raise
```

**Bootstrap update in `librarian_ctl.py`:**
```python
cursor.execute("""
    INSERT OR IGNORE INTO agents (agent_id, name, version, description, tool_names) VALUES
    ('kimi-orch-01', 'Mega-Orchestrator (Kimi)', '1.3',
     'Lead Systems Architect & Workflow Orchestrator',
     'search_factory,deploy_pipeline_with_ui,teardown_pipeline,run_agent'),
    ('lib-keeper-01', 'The Librarian', '1.0',
     'Knowledge Keeper, DB Manager, Registry Generator',
     'refresh_registry,archive_log,find_faint_paths');
""")
```

---

## [DES-S5-05] Test Architecture

**Framework:** `pytest` + `unittest.mock`. No live service required.

**Directory layout:**
```
tests/
├── conftest.py          ← shared fixtures (tmp_db, tmp_workspace)
├── test_validate_path.py
├── test_validate_token.py
├── test_init_db.py
└── test_run_agent.py
```

**`conftest.py` key fixtures:**
```python
@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    """Provides a temp workspace and patches WORKSPACE_ROOT."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("OPENCLAW_WORKSPACE", str(ws))
    # Re-import config so WORKSPACE_ROOT picks up env change
    import importlib, openclaw_skills.config as cfg
    cfg.WORKSPACE_ROOT = ws
    cfg.TOKEN_FILE = ws / ".hitl_token"
    return ws

@pytest.fixture
def tmp_db(tmp_workspace):
    """Initialised + bootstrapped + migrated factory.db in tmp workspace."""
    db_path = str(tmp_workspace / "factory.db")
    from openclaw_skills.librarian.librarian_ctl import init_db, bootstrap_factory
    from openclaw_skills.librarian.migrate_db import migrate_database
    init_db(db_path)
    bootstrap_factory(db_path)
    migrate_database(db_path)
    return db_path
```

**Critical test cases:**

| Test | Logic |
|---|---|
| `validate_path` — correct path | Path inside workspace → returns resolved string |
| `validate_path` — outside boundary | `/tmp/evil` → raises `PermissionError` |
| `validate_path` — symlink traversal | Symlink inside workspace pointing outside → raises `PermissionError` |
| `validate_path` — prefix collision | `workspace_evil/` sibling dir → raises `PermissionError` |
| `validate_token` — correct token | Write token file, call `validate_token(token)` → `True`, file deleted |
| `validate_token` — wrong token | Write token file, call `validate_token("wrong")` → `False`, file deleted |
| `validate_token` — missing file | No file → returns `False` (no exception) |
| `init_db` round-trip | init → bootstrap → refresh-registry → registry file exists with expected content |
| `run_agent` — happy path | Stub Ollama response, verify audit log INSERT called with `action='AGENT_RUN'` |
| `run_agent` — unknown agent | `ValueError` raised with agent_id in message |
| `run_agent` — Ollama down | `RuntimeError` raised referencing Ollama URL |

---

## [DES-S5-06] README Repositioning

**Structure (new `README.md`):**
```
# OpenClaw for Linux

Self-hosted AI agents that never act without your explicit approval —
local-first, CPU-bound, zero cloud dependency for sensitive operations.

## Why OpenClaw?          ← comparison table vs. LangChain/CrewAI/AutoGen
## Architecture           ← diagram + link to current_state.md
## Quick Start            ← setup.sh + run_agent demo in 5 commands
## Security Model         ← Airlock + HITL + Burn-on-Read summary
## Backlog                ← link to _Development/OpenClaw/backlog.md
```

**Comparison table dimensions:**
| Dimension | LangChain | CrewAI | AutoGen | **OpenClaw** |
|---|---|---|---|---|
| Local-first | Optional | Optional | Optional | ✅ Always |
| HITL enforcement | Plugin | Plugin | Optional | ✅ Architectural primitive |
| Cloud required | Yes (default) | Yes (default) | Yes (default) | ❌ Never for sensitive ops |
| Infrastructure | Python + deps | Python + deps | Python + deps | Python + SQLite only |
| Data privacy | External APIs | External APIs | External APIs | ✅ Air-gapped option |

---

## Files Changed / Created in Sprint 5

| Action | File |
|---|---|
| NEW | `openclaw_skills/config.py` |
| NEW | `setup.sh` |
| NEW | `requirements.txt` |
| NEW | `tests/conftest.py` |
| NEW | `tests/test_validate_path.py` |
| NEW | `tests/test_validate_token.py` |
| NEW | `tests/test_init_db.py` |
| NEW | `tests/test_run_agent.py` |
| MODIFY | `openclaw_skills/librarian/librarian_ctl.py` — import config, update bootstrap |
| MODIFY | `openclaw_skills/librarian/migrate_db.py` — add description/tool_names migration |
| MODIFY | `openclaw_skills/architect/architect_tools.py` — import config, add run_agent + CLI subcommand |
| MODIFY | `README.md` — full rewrite per DES-S5-06 |

# OpenClaw Tools Reference

All CLI tools follow the same invocation pattern:
```bash
python3 <tool_path> <subcommand> [args] [--flags]
```

Run any tool with `--help` for full argument documentation.

---

## `librarian_ctl.py` — The Librarian

**Path:** `openclaw_skills/librarian/librarian_ctl.py`  
**Role:** State management — database, registry, memory, and agent registration.

| Subcommand | Description | Key Args |
|---|---|---|
| `init` | Initialise `factory.db` (WAL mode, core tables) | `db_path` |
| `bootstrap` | Seed core system agents and pipeline | `db_path` |
| `refresh-registry` | Regenerate `REGISTRY.md` from `factory.db` | `db_path`, `output_md_path` |
| `register-agent` | Register a new custom agent | `db_path`, `agent_id`, `name`, `[--description]`, `[--tool-names]`, `[--profile-file]`, `[--force]` |
| `ingest-vault-note` | Fetch an Obsidian vault note → distil → embed → archive | `db_path`, `vault_path`, `[--sensitive]` |

**Example:**
```bash
python3 openclaw_skills/librarian/librarian_ctl.py register-agent \
  ~/.openclaw/workspace/factory.db \
  my-analyst-01 "Research Summariser" \
  --description "Distils research notes" \
  --tool-names "run_agent,find_faint_paths"
```

---

## `architect_tools.py` — The Architect

**Path:** `openclaw_skills/architect/architect_tools.py`  
**Role:** Agent execution, HITL deployment gate, and vault writing.

| Subcommand | Description | Key Args |
|---|---|---|
| `run` | Run a task against a named agent | `db_path`, `agent_id`, `task` |
| `write-to-vault` | Write agent output to an Obsidian vault note | `db_path`, `agent_id`, `title`, `content` |
| `deploy` | Deploy a pipeline (triggers HITL GUI popup) | `db_path`, `pipeline_id` |
| `teardown` | Tear down a pipeline (protects system agents) | `db_path`, `pipeline_id` |
| `search` | Search agents or pipelines in `factory.db` | `db_path`, `query_type`, `[filter]` |

**Example:**
```bash
python3 openclaw_skills/architect/architect_tools.py run \
  ~/.openclaw/workspace/factory.db \
  kimi-orch-01 \
  "Summarise the last 5 audit log entries."
```

> **Security:** `deploy` requires a native OS (tkinter) Yes/No dialog. Cannot be bypassed in code.

---

## `router.py` — LLM Router

**Path:** `openclaw_skills/router.py`  
**Role:** Routes inference to local Ollama or cloud Gemini based on sensitivity and availability.

| Subcommand | Description | Key Args |
|---|---|---|
| `route` | Route a task to local or cloud inference | `db_path`, `task`, `[--sensitive / --no-sensitive]`, `[--tier local\|cloud]` |

**Routing policy:**

| `is_sensitive` | `tier` | Outcome |
|---|---|---|
| `True` | `local` | `ROUTE_LOCAL` — Ollama |
| `True` | `cloud` | `ROUTING_HALT` — `PermissionError` raised; cloud never called |
| `False` | `local` | `ROUTE_LOCAL` — Ollama (if reachable) |
| `False` | `cloud` | `ROUTE_CLOUD` — Gemini |

---

## `kb.py` — Knowledge Base

**Path:** `openclaw_skills/kb.py`  
**Role:** Static KB injection into agent prompts, and HITL-supervised KB update lifecycle.

| Subcommand | Description | Key Args |
|---|---|---|
| `submit` | Propose a new KB rule (queued for Navigator approval) | `db_path`, `agent_id`, `change_type`, `section`, `new_value`, `rationale` |
| `list-proposals` | List pending KB update proposals | `db_path` |
| `approve` | Approve a proposal with a Burn-on-Read HITL token | `db_path`, `update_id`, `token` |

---

## `setup.sh` — Cold-Start Initialiser

**Path:** `setup.sh`  
**Role:** One-command workspace initialisation. Idempotent — safe to re-run.

**Steps executed:**
```
[0/7] Workspace directory ready.
[1/7] Initialise relational DB schema
[2/7] Bootstrap core agents and pipeline
[3/7] Initialise vector archive (sqlite-vec)
[4/7] Apply schema migrations
[5/7] Generate REGISTRY.md
[6/7] (Optional) Bootstrap Obsidian vault folder structure
[7/7] (Optional) Obsidian health check
```

**Prerequisites:**
- Python 3.10+ (checked at runtime — exits with helpful message if missing)
- Ollama installed and running (`ollama serve`)
- `OPENCLAW_WORKSPACE` env var set (default: `~/.openclaw/workspace`)

---

## `src/tools/` — Vault Tools (Phase 2 — Not Yet Integrated)

> [!WARNING]
> These tools are **prototypes** placed in the legacy `src/` directory. They are not yet connected to `openclaw_skills/` and have no test coverage. They are scheduled for migration to `openclaw_skills/vault_tools/` in a future sprint.

| File | Purpose |
|---|---|
| `vault_intelligent_router.py` | Maps note YAML metadata → correct Johnny.Decimal folder path |
| `vault_schema_validator.py` | Validates YAML frontmatter against Universal Note Template schema |
| `vault_taxonomy_guard.py` | Enforces `NN - ` prefix on all vault folder path components |

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
| `True` | `local` | `ROUTE_LOCAL` — Tiered Ollama (returns `INFERENCE_ALERT` if offline) |
| `True` | `cloud` | `ROUTING_HALT` — `PermissionError` raised; cloud never called |
| `False` | `local` | `ROUTE_LOCAL` — Tiered Ollama (returns `INFERENCE_ALERT` if offline) |
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


## `openclaw_skills/vault_tools/` — Vault Tools

**Path:** `openclaw_skills/vault_tools/`  
**Role:** Vault routing, YAML schema validation, and Johnny.Decimal taxonomy enforcement.  
All tools are invokable via `architect_tools.py` subcommands (Mode A) and drive
the `ObsidianVaultArchitect` agent in autonomous health-scan mode (Mode B).

| Module | Function | Description |
|---|---|---|
| `vault_intelligent_router.py` | `discover_domains(vault_root)` | Runtime-scans `20 - AREAS/` → domain slug map. No hardcoded map. |
| `vault_intelligent_router.py` | `suggest_vault_path(metadata, filename, vault_root)` | Routes note to correct JD folder (case-insensitive, fallback to INBOX) |
| `vault_schema_validator.py` | `validate_vault_metadata(content, expected_path)` | Validates YAML frontmatter; returns errors, warnings, and repair template |
| `vault_taxonomy_guard.py` | `validate_taxonomy_compliance(vault_path)` | Enforces `NN - ` prefix on all vault path components |
| `vault_health_check.py` | `run_vault_health_check(vault_root, db_path)` | Read-only vault health scan; duplicate JD prefixes classified as ERRORS |
| `vault_health_check.py` | `format_health_report(result, vault_root)` | Renders health result as Obsidian-ready Markdown with YAML frontmatter |

**Environment variables required:**

| Variable | Required | Description |
|---|---|---|
| `OBSIDIAN_VAULT_PATH` | Yes (for routing & health check) | Absolute path to vault root (e.g. `~/obsidian-vault`) |
| `OBSIDIAN_API_KEY` | Yes (for all bridge operations) | Local REST API plugin key |
| `OBSIDIAN_BASE_URL` | No (default: `http://127.0.0.1:27123`) | Obsidian plugin URL — must be loopback |

**`architect_tools.py` subcommands:**

| Subcommand | Description | Exit Codes |
|---|---|---|
| `vault-route` | Suggest JD vault path for a note | 0=routed, 1=INBOX fallback |
| `vault-validate` | Validate note YAML frontmatter | 0=valid, 1=runtime error, 2=invalid |
| `vault-check-taxonomy` | Check path for `NN - ` prefix compliance | 0=pass, 1=runtime error, 2=fail |
| `vault-health-check` | Full autonomous vault health scan | 0=success, 1=runtime error |

**Examples:**

```bash
# Route a note based on its metadata
python3 openclaw_skills/architect/architect_tools.py vault-route \
  --metadata '{"type": "note", "domain": "AI"}' \
  --filename "LLM_Paper.md"
# → 20 - AREAS/23 - AI/LLM_Paper.md

# Validate a specific note (via Obsidian bridge)
python3 openclaw_skills/architect/architect_tools.py vault-validate \
  --note-path "20 - AREAS/23 - AI/LLM_Paper.md"

# Check a path for taxonomy compliance  
python3 openclaw_skills/architect/architect_tools.py vault-check-taxonomy \
  --vault-path "20 - AREAS/23 - AI/LLM_Paper.md"

# Run full vault health scan and write report to vault
python3 openclaw_skills/architect/architect_tools.py vault-health-check \
  --vault-root ~/obsidian-vault \
  --output-path "99 - META/vault_health_2026-03-28.md"
```

> **Security:** `vault_root` is read from `OBSIDIAN_VAULT_PATH` env var and is NOT
> subject to Airlock (`validate_path()`). The vault lives outside `OPENCLAW_WORKSPACE`
> by design. Only `--db-path` (factory.db) is Airlock-protected.

---

## `prompt_architect_tools.py` — Prompt Architect & Backlog Manager

**Path:** `openclaw_skills/prompt_architect/prompt_architect_tools.py`  
**Role:** Generates personas via structured Intelligence Packages and synthesizes Socratic epistemic gaps for self-evolution.

| Function | Description | Key Args |
|---|---|---|
| `log_epistemic_gap` | Logs tool/knowledge/logic failures to `epistemic_backlog` | `agent_id`, `gap_type`, `description`, `context_json`, `[db_path]` |
| `register_from_package` | Registers an agent from an `AgentIntelligencePackage` JSON payload, saves locally, and syncs safely to Obsidian. | `package_json`, `[db_path]` |
| `synthesize_backlog_report` | Atomically generates the priority BACKLOG.md from raw `epistemic_backlog` gaps | `[db_path]`, `[output_path]` |

---

## Safety Monitoring Tools

### `safety_watchdog.py`
**Path:** `openclaw_skills/watchdog/safety_watchdog.py`  
**Role:** Background daemon that monitors cloud spend and agent loop cycling.

| Mode | Description | Key Environment Variables |
|---|---|---|
| `python3 -m ...` | Starts the polling daemon (default 30s) | `OPENCLAW_DAILY_COST_LIMIT_USD`, `OPENCLAW_LOOP_THRESHOLD` |

### `control_tower.py`
**Path:** `control_tower.py` (Repo Root)  
**Role:** Real-time Tkinter dashboard for monitoring architecture state and emergency stops.

| Action | Description |
|---|---|
| `python3 control_tower.py` | Launches GUI (requires `$DISPLAY`) |
| **🛑 STOP** | Triggers manual kill: freezes tasks, sets halt sentinel, kills orchestrator |
| **⏸ PAUSE** | Sets the `.watchdog_halt` sentinel to prevent new task claims |

**Sentinel File:** `workspace/.watchdog_halt` — Created by watchdog or UI to block orchestrator execution. Delete this file to resume operations.



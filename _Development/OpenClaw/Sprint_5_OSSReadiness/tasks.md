# Tasks: Sprint 5 (OSS Readiness & Minimal Agent Runner)

**Sprint Goal:** Make OpenClaw cloneable, runnable, and demonstrable by any Linux developer in under 10 minutes.  
**Status legend:** `[ ]` pending · `[/]` in progress · `[x]` complete · `[!]` blocked

---

## BLOCK 0 — Config Module (Foundation, do first)

### Task 0.1 — Create `openclaw_skills/config.py`
**Ref:** [DES-S5-01]
- [x] Create `openclaw_skills/config.py` with `WORKSPACE_ROOT`, `TOKEN_FILE`, `DEFAULT_DB_PATH`, `DEFAULT_REGISTRY_PATH`
- [x] `WORKSPACE_ROOT` reads from `OPENCLAW_WORKSPACE` env var, defaults to `~/.openclaw/workspace` via `Path.home()`
- [x] All values resolved with `Path.expanduser().resolve()`

### Task 0.2 — Update `librarian_ctl.py` to import config
**Ref:** [DES-S5-01]
- [x] Remove hardcoded `"/home/alexey/openclaw-inbox/workspace/"` string from `validate_path()`
- [x] Import `WORKSPACE_ROOT` from `config` and use `str(WORKSPACE_ROOT)` as `base_dir`
- [x] Update `startswith` check to use `os.sep` suffix guard: `target_abs == base_dir or target_abs.startswith(base_dir + os.sep)`
- [x] Remove unused `import yaml` (DELTA-01)

### Task 0.3 — Update `architect_tools.py` to import config
**Ref:** [DES-S5-01]
- [x] Remove hardcoded `WORKSPACE_DIR` and `TOKEN_FILE` string literals from top of file
- [x] Import `WORKSPACE_ROOT`, `TOKEN_FILE`, `OLLAMA_URL`, `LOCAL_MODEL` from `config`
- [x] Update `startswith` Airlock check with `os.sep` suffix guard (same as Task 0.2)

### Task 0.4 — Verify Airlock still holds after config change
- [x] `grep -r "/home/alexey" openclaw_skills/` → zero matches in source files (only stale .pyc, gitignored)
- [x] Verified via test suite: symlink traversal, prefix-collision, and outside-boundary all raise `PermissionError`

---

## BLOCK 1 — Cold Start & Dependencies

### Task 1.1 — Create `requirements.txt`
**Ref:** [REQ-S5-03]
- [x] Created `requirements.txt` with `sqlite-vec>=0.1.0`, `pyyaml>=6.0`, `google-generativeai>=0.8.0`

### Task 1.2 — Create `setup.sh`
**Ref:** [DES-S5-02]
- [x] Created `setup.sh` at project root (executable: `chmod +x setup.sh`)
- [x] Script uses `OPENCLAW_WORKSPACE` env var, defaults to `~/.openclaw/workspace`
- [x] Includes home-directory sanity check before `mkdir -p`
- [x] Runs 5 steps in order: init → bootstrap → vector init → migrate → refresh-registry
- [x] All steps are idempotent (re-running on an existing workspace is safe)
- [x] Final output prints workspace path, DB path, and example `run_agent` CLI command

---

## BLOCK 2 — Schema Migration (prerequisite for runner + tests)

### Task 2.1 — Add `description` and `tool_names` columns to migration
**Ref:** [DES-S5-04]
- [x] Added migration block to `migrate_db.py` for `description TEXT` and `tool_names TEXT`
- [x] Use `try/except sqlite3.OperationalError` with "duplicate column name" check — idempotent
- [x] Log migration outcome at `INFO` level

### Task 2.2 — Seed description/tool_names for core agents in migration
**Ref:** [DES-S5-04]
- [x] Added idempotent `UPDATE` for `kimi-orch-01` and `lib-keeper-01` in migration
- [x] Guard: `WHERE description IS NULL OR description = ''` — safe to re-run

### Task 2.3 — Update `generate_registry()` to include new fields
**Ref:** [DES-S5-04]
- [x] `SELECT agent_id, name, version, description, tool_names FROM agents`
- [x] Registry output includes description (italicised) and tool_names per agent

---

## BLOCK 3 — Minimal Agent Runner

### Task 3.1 — Implement `run_agent()` function
**Ref:** [DES-S5-03]
- [x] Added `run_agent(db_path, agent_id, task_text) -> str` to `architect_tools.py`
- [x] Raises `ValueError` if agent not found
- [x] Memory context via `find_faint_paths()` — graceful fallback if archive unavailable
- [x] Prompt guard: memory truncated at 4,000 chars
- [x] HTTP POST to Ollama `/api/generate`, `timeout=60.0`
- [x] Raises `RuntimeError` on `URLError` or empty response
- [x] `INSERT INTO audit_logs` with `action='AGENT_RUN'`, rationale truncated to 500 chars

### Task 3.2 — Add `run` CLI subcommand to `architect_tools.py`
**Ref:** [DES-S5-03]
- [x] Added `run` subparser with `db_path`, `agent_id`, `task` arguments
- [x] Wired to `run_agent()`

---

## BLOCK 4 — Test Suite

### Task 4.1 — Create `tests/conftest.py`
**Ref:** [DES-S5-05]
- [x] `isolated_workspace` fixture (autouse): temp dir, env var, patches config + librarian_ctl + architect_tools
- [x] `tmp_db` fixture: full init → bootstrap → migrate round-trip

### Task 4.2 — `tests/test_validate_path.py`
- [x] Valid path inside workspace → passes
- [x] Workspace root itself → passes (exact equality branch)
- [x] `/tmp/evil` → raises PermissionError
- [x] Home directory → raises PermissionError
- [x] Prefix-collision sibling (`workspace_evil/`) → raises PermissionError (os.sep guard verified)
- [x] Symlink inside workspace pointing to `/tmp` → raises PermissionError

### Task 4.3 — `tests/test_validate_token.py`
- [x] Correct token → True, file deleted
- [x] Correct token → file deleted (burn verified)
- [x] Wrong token → False, file still burned
- [x] Missing file → False (no exception)
- [x] Replay attack → second call returns False
- [x] Token file permissions → 0o600

### Task 4.4 — `tests/test_init_db.py`
- [x] `init_db` creates 3 tables, WAL mode set
- [x] `bootstrap_factory` seeds core agents, idempotent
- [x] `migrate_database` adds `is_system`, `pipeline_agents`, `description`, `tool_names`
- [x] Migration is idempotent
- [x] `generate_registry` creates file with YAML frontmatter, agent names, description, tool_names

### Task 4.5 — `tests/test_run_agent.py`
- [x] Happy path: response returned, audit log written
- [x] Audit log rationale truncated to ≤500 chars
- [x] Unknown agent_id → ValueError
- [x] Ollama URLError → RuntimeError
- [x] Empty Ollama response → RuntimeError
- [x] `deploy_pipeline_with_ui` and `generate_token` not called

### Task 4.6 — All tests pass
- [x] `pytest tests/ -v` → **28 passed, 0 failed, exit code 0**

---

## BLOCK 5 — README & Documentation

### Task 5.1 — Rewrite `README.md`
**Ref:** [DES-S5-06]
- [x] Lead paragraph: "Self-hosted AI agents that never act without your explicit approval..."
- [x] "Why OpenClaw?" comparison table (LangChain / CrewAI / AutoGen / OpenClaw)
- [x] Architecture diagram and link to `current_state.md`
- [x] "Quick Start" in 5 commands using `setup.sh` and `run_agent` CLI
- [x] "Security Model" section (Airlock + HITL + Burn-on-Read with code examples)
- [x] Test suite instructions
- [x] Backlog link
- [x] Zero hardcoded absolute paths anywhere in README

### Task 5.2 — Backlog updated
- [x] Sprint 5 marked active in `_Development/OpenClaw/2026-03-27_backlog.md`

---

## ✅ Sprint 5 Complete

**Acceptance Gate: all checks passed**

| Check | Result |
|---|---|
| `grep -r "/home/alexey" openclaw_skills/` | ✅ Zero source matches |
| `pytest tests/ -v` | ✅ 28 passed, 0 failed |
| `setup.sh` idempotent structure | ✅ All 5 steps guarded |
| `run_agent` CLI subcommand | ✅ Implemented and tested |
| README lead paragraph | ✅ Positioning statement visible without scrolling |
| No hardcoded paths in README | ✅ Uses `$HOME/.openclaw/workspace` |

> Next: create state snapshot at `docs/2026-03-27__HH-MM_post_sprint5.md` and push to `github.com/asoshnin/OpenClaw4LinuxRAMonly`.

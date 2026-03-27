# Sprint 5 Requirements: OSS Readiness & Minimal Agent Runner

**Sprint Goal:** Transform OpenClaw from a personal tool into an installable, demonstrable open-source framework. Any developer should be able to `git clone`, run `setup.sh`, and have a working agent execute a task within 10 minutes on a Linux x86_64 machine — without touching a config file.

---

## Priority 0 — OSS Cloneability Blockers

### [REQ-S5-01] Remove All Hardcoded Absolute Paths (GAP-02)
The Airlock workspace path `/home/alexey/openclaw-inbox/workspace/` is currently hardcoded as a string literal in both `librarian_ctl.py` and `architect_tools.py`. This makes the project non-cloneable by any other user.

**Acceptance Criteria:**
- A single `openclaw_skills/config.py` module defines `WORKSPACE_ROOT` using an environment variable `OPENCLAW_WORKSPACE`, defaulting to `~/.openclaw/workspace` (via `Path.home()`).
- Both `librarian_ctl.py` and `architect_tools.py` import `WORKSPACE_ROOT` from `config.py` — no hardcoded path string remains in either file.
- Running `grep -r "/home/alexey" openclaw_skills/` returns zero matches.
- The Airlock boundary (`validate_path`) continues to function correctly after the change.

### [REQ-S5-02] Single-Command Cold Start
The current cold start requires 5–6 manual commands run from specific directories with hardcoded absolute paths. This is a real barrier to adoption.

**Acceptance Criteria:**
- A `setup.sh` script at the project root runs all initialisation steps in sequence: workspace directory creation → relational DB init → bootstrap → vector table init → schema migration → first registry generation.
- The script respects the `OPENCLAW_WORKSPACE` environment variable and defaults to `~/.openclaw/workspace`.
- Running `bash setup.sh` on a fresh clone produces a ready `factory.db` with no errors, regardless of working directory.
- All steps are idempotent — re-running `setup.sh` on an already-initialised workspace is safe.

### [REQ-S5-03] `requirements.txt` with Pinned Versions
No `requirements.txt` currently exists. Users must manually discover dependencies from the README.

**Acceptance Criteria:**
- A `requirements.txt` at the project root lists all non-stdlib dependencies with minimum version pins: `sqlite-vec`, `pyyaml`, `google-generativeai`.
- A `pip install -r requirements.txt` on a clean virtualenv completes without errors.

---

## Priority 1 — Make the "Agent" Promise Honest

### [REQ-S5-04] Minimal Agent Runner
Currently, "agents" (`kimi-orch-01`, `lib-keeper-01`) are database records only — there is no code that can actually *run* one. The framework should be able to execute at least a local LLM call attributed to a registered agent, with the result logged to `audit_logs`.

**Acceptance Criteria:**
- A `run_agent(agent_id, task_text, db_path)` function exists in `openclaw_skills/architect/architect_tools.py` (or a new `runner.py` in the same directory).
- The function: (1) loads the agent record from `factory.db`, (2) calls `find_faint_paths()` to retrieve relevant memory context (top 3), (3) constructs a prompt from agent name/role + memory context + task, (4) calls the local Ollama model, (5) logs the result to `audit_logs` with `action='AGENT_RUN'`, (6) returns the LLM response string.
- If the `agent_id` does not exist in the DB, a `ValueError` is raised with a clear message.
- If Ollama is not reachable, a `RuntimeError` is raised — the function never silently returns empty output.
- The function is exposed as a CLI subcommand: `python3 architect_tools.py run <db_path> <agent_id> "<task>"`.

### [REQ-S5-05] README Repositioning and Demo Instructions
The current README leads with a three-tier architecture diagram. Potential users — especially those browsing GitHub — need to immediately understand what OpenClaw *does* and why it is different.

**Acceptance Criteria:**
- The README first paragraph reads: *"Self-hosted AI agents that never act without your explicit approval — local-first, CPU-bound, zero cloud dependency for sensitive operations."*
- A "Why OpenClaw?" section contains a comparison table vs. LangChain/CrewAI/AutoGen on dimensions: local-first, HITL enforcement, infrastructure requirements, and data privacy.
- A "Quick Start" section demonstrates the full flow using `setup.sh` and `run_agent` CLI in 5 commands or fewer.
- Instructions reference `OPENCLAW_WORKSPACE` not hardcoded paths.

---

## Priority 2 — OSS Table Stakes

### [REQ-S5-06] Automated Test Suite (GAP-05)
Zero automated test coverage currently exists. No external contributor can safely submit a patch.

**Acceptance Criteria:**
- A `tests/` directory at the project root contains at minimum:
  - `test_validate_path.py`: tests for correct paths, symlink-escaped paths, outside-boundary paths, and paths with the prefix-collision pattern (e.g., a sibling directory starting with the same name as `workspace`).
  - `test_validate_token.py`: tests for burn-on-read behaviour (token file deleted before comparison), correct token, wrong token, missing token file.
  - `test_init_db.py`: integration test for `init_db() → bootstrap_factory() → generate_registry()` round-trip against a temp in-memory or temp-file DB.
  - `test_run_agent.py`: mock-based test for `run_agent()` that stubs out Ollama and verifies the `audit_logs` INSERT is called with `action='AGENT_RUN'`.
- Running `pytest tests/` from the project root exits with code 0.
- No test requires a live Ollama instance — all LLM calls are mocked.

### [REQ-S5-07] Enhanced Agent Schema
The `agents` table currently stores only `(agent_id, name, version, persona_hash, state_blob, created_at, is_system)`. There is no structured way to record what an agent *does* or what tools it has access to.

**Acceptance Criteria:**
- A new migration in `migrate_db.py` adds `description TEXT` and `tool_names TEXT` (comma-separated list) columns to the `agents` table via idempotent `ALTER TABLE … IF NOT EXISTS`-equivalent pattern (try/except `OperationalError`).
- `bootstrap_factory()` is updated to seed `kimi-orch-01` with `description='Lead Systems Architect & Workflow Orchestrator'` and `tool_names='search_factory,deploy_pipeline_with_ui,teardown_pipeline,run_agent'`.
- `generate_registry()` is updated to include `description` and `tool_names` in the Markdown output.
- `search_factory('agents')` returns the new fields in its dict output.

---

## Out of Scope for Sprint 5
- Dynamic LLM Router (Phase 2)
- Obsidian Sync (Phase 3)
- Async Task Queue (Phase 3)
- Scoped Epistemic Scrubber refactor (Phase 2)
- Web UI or REST API of any kind

---

## Safety Constraints
- All new code in `openclaw_skills/` must pass through `validate_path()` for any file operation. No exceptions.
- `run_agent()` must NOT call `deploy_pipeline_with_ui()` or any HITL gate — it is a read+inference operation only, not a deployment action.
- Test fixtures must use temporary directories and must never write to the real `OPENCLAW_WORKSPACE`.
- `setup.sh` must check that `OPENCLAW_WORKSPACE` resolves to a path within the user's home directory before creating any subdirectories (basic sanity guard — not a full Airlock).

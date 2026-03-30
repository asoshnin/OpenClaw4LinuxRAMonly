# Changelog

All notable changes are listed by Sprint. This project follows a sprint-based delivery model documented in `_Development/OpenClaw/`.

---
## Wave 1 Foundation + Wave 1.5 Context Isolation (2026-03-29) — v2026.3.28

**277 tests passing** (+98 from Wave 0 baseline of 179).

### Wave 1: Foundation Hardening

- **BL-00 / BL-00c (Sprint Infrastructure):** Created `epistemic_backlog`, `sprints`, and `tasks` tables in `factory.db` via `migrate_bl00c.py`. Seeded 4 Strategic Waves (Foundation, Perception, Evolution, Governance) and 26 backlog tasks with `priority` and `source_doc` columns. Verified read/write integrity via `tests/test_bl00_functional.py`.

- **LIB-01 (JITH Protocol):** Implemented `openclaw_skills/librarian/jith_discovery.py` — a recursive CLI capability discovery engine. Security allowlist (`VERB_ALLOWLIST`) blocks all non-OpenClaw verbs. Injection characters and path traversal are always rejected (`shell=False` universally). Results cached atomically (`.tmp` → `os.replace()`) with 24-hour TTL and version-fingerprint invalidation. `validate_invocation()` emits `[EPISTEMIC_GAP]` reports for missing flags. 19 tests in `tests/test_lib01_jith.py`.

- **LIB-02 (Backlog Sync Utility):** Implemented `openclaw_skills/librarian/sync_backlog.py` — fail-safe HTML-marker injection model synchronizing `factory.db` task statuses to `_Development/2026-03-29_current_backlog_update.md`. Features: unique marker assertion (exit 1 on violation), 20% size-guard, dry-run mode, atomic writes, and `update_task_status()` enforcing the Verified-Completion Invariant (non-empty `test_summary` required). 12 tests in `tests/test_lib02_sync.py`.

- **PR-01 + PR-02 (Flash-Schema Unified Protocol):** Added `generate_flash_prompt()` to `openclaw_skills/prompt_architect/prompt_architect_tools.py`. Features: Socratic tier assessment (FLASH/PRO routing), No-Preamble instruction block, schema-aware stop sequence, bloat stripping, JSON circuit-breaker (retry loop with repair prompt), Pydantic-style schema validator (no external deps), and Sovereign Safety Guard (all Flash outputs unconditionally scrubbed by `safety_engine.py`). 33 tests in `tests/test_inference_hardening.py`.

- **V2 Glossary Synchronization:** Global semantic migration from Pipeline → Workflow across all documentation. Steering files (`.kiro/`), docs, README, and SKILL.md all aligned to the V2 semantic model.

### Wave 1.5: Multi-Project Context Isolation

- **PR-05 (Context Switcher):** Implemented `find_project_root()` and `get_project_paths()` in `openclaw_skills/config.py`. Anchor-based upward recursion discovers the nearest `.factory_anchor` file; falls back to `OPENCLAW_WORKSPACE` env var, then `_SOURCE_ROOT`. `GLOBAL_DB_PATH`, `DOCS_DIR`, `MEMORY_DIR` added as convenience aliases. `.factory_anchor` created at the Global Hub root. Steering files (`structure.md`, `sprint-workflow.md`) rewritten with Multi-Project Silo architecture and SQL-First authority invariants. 15 tests in `tests/test_pr05_context_switcher.py`.

- **PR-06 (Global Project Registry & `factory-init`):** Added `projects` table to `factory.db` via `migrate_db.py` step 9 (`ON DELETE SET NULL` for parent lineage). Extracted shared schema DDL into `openclaw_skills/librarian/db_utils.py` (`initialize_project_schema()`). Built `openclaw_skills/architect/project_init.py` — `factory-init` CLI with pre-flight guard (abort on existing `project.db`/anchor unless `--force`), `realpath` normalization, directory provisioning, and Global Hub registration with parent validation. 16 tests in `tests/test_pr06_project_registry.py`.

### Wave 2 Perception Phase: Red Team Auditor (2026-03-30)
- **RT-01 (Red Team Auditor):** Registered `red-team-auditor-01` into the DB. Implemented `run_audit` in `architect_tools.py` to enforce quality checks using a `<AUDIT_REPORT>` XML schema parsing logic, capturing epistemic challenges, findings, limits, status, and recommendations. Extended `run_agent()` to support `--audit` workflows, logging the structured review unconditionally to the `audit_logs` DB before release.

- **docs(OSS-01):** Created Chat-First `getting_started.md` operational manual for Vibe Coders.

- **feat(QA-01):** Comprehensive E2E factory pipeline testing suite with isolated Git/DB fixtures. Implemented `tests/test_e2e_factory.py` to test Happy Path, Dependency Unblocking and the HITL Circuit Breaker loop safely using local mocks of `call_inference`.

- **SYS-02 (Task Queue Worker):** Implemented `feat(SYS-02): Atomic Async Task Queue Worker with HITL circuit breaker and zombie recovery`. Created TaskQueueManager in openclaw_skills/orchestrator/task_worker.py.

- **EV-01 (Pi Coding Agent Bridge):** Implemented `feat(EV-01): ACP Coding Agent (Pi) Bridge and asynchronous session_id delegation tracking`. Created `CodingAgentBridge` in `openclaw_skills/orchestrator/pi_bridge.py` and modified `TaskQueueManager` to handle `processing_subagent` and `session_id`.

- **MP-01 (Factory Manager):** Implemented `feat(MP-01): Event-Driven Factory Manager (Kimi-Orch-01) state machine with Git baseline artifact gathering`. Created `openclaw_skills/factory_orchestrator.py` dynamically resuming subagents safely via baseline git diffs gathered from `artifact_gatherer.py`.

- **BL-01 (Backlog Manager Intake):** Implemented `feat(BL-01): Backlog Intake with LLM regex-decomposition, sequential task chaining (depends_on), and SKILL.md integration`. Created `BacklogIntake` logic in `intake.py` and wrapped in CLI utility `factory_cli.py`. Extended SQLite schema and upstream `TaskQueueManager.mark_task_completed()` logic to automatically unblock cascaded dependencies safely.

- **LIB-01.1 & LIB-01.2 (Semantic Artifact Graph):** Transformed Librarian's registry from a static log into a semantic capability knowledge graph. Implemented `semantic_parser.py` (Local zero-shot LLM fallback + JSON decoding) to extract structured `capabilities` and `dependencies`. Added `assert_artifact_writable()` to strictly enforce `is_readonly=1` airgap on OpenClaw native artifacts (`openclaw::*`). Updated `sync_openclaw_artifacts.py` to aggressively filter target components before upserting the semantic graph into `factory.db`. 22 tests passing in `tests/test_lib01_1_artifacts.py`.

---
## Wave 1 Foundation (2026-03-29) — Epistemic Backlog Migration

- BL-00 Migration Complete: Verified the functional constraints and read/write integrity of the `epistemic_backlog` table.

---

## Sprint 11 (2026-03-28) — The Semantic Bridge

- Added `ObsidianBridge.search_vault(query, limit=5)`: calls `GET /search/simple/` Obsidian Local REST API endpoint; returns top-N vault-relative paths ordered by score; query URL-encoded (`%20` not `+`); limit clamped to `[1, 10]`
- Added standalone `vault_qa(query, db_path, limit, is_sensitive)` RAG function in `obsidian_bridge.py`:
  - Full retrieval loop: search → per-note `read_note()` → truncate (3,000 chars/note) → assemble `context_text`
  - `[[WikiLink]]` citations: stem of each note filename wrapped in `[[...]]`
  - Context Guard: total context capped at 12,000 chars (standalone) or 6,000 chars (prompt injection)
  - Audit log: `action='VAULT_QA'`, `rationale=query[:200]` only — vault note content never logged
  - Obsidian unavailable → `RuntimeError`; unreadable notes → `WARNING` + skip (non-fatal)
- Added `[VAULT CONTEXT]` prompt block to `run_agent()`:
  - Injected after `[MEMORY CONTEXT]`, before `[TASK]` (Sprint 11 prompt order)
  - Includes wikilink citation instruction: *"When citing a source, use [[Note Name]] format"*
  - Only injected when `vault_qa_result` kwarg is provided — fully backward compatible
- Added `vault-qa` subcommand to `architect_tools.py`:
  - `--query` (required), `--db-path`, `--limit`, `--sensitive`, `--json`
  - Exit codes: 0=results, 1=error (Obsidian down), 2=no results
  - Markdown output: `## Vault QA: <query>` + `### [[Note]]` sections
- Updated `lib-keeper-01` to v2.0: description includes Vault QA mode; `tool_names` += `vault-qa`
- Updated `obsidian-vault-architect` to v3.0: description includes Mode C (Vault QA); `tool_names` += `vault-qa`
- `REGISTRY.md` refreshed via `refresh-registry` to reflect both persona updates
- `TypedDict`: `VaultQASource`, `VaultQAResult` added to `obsidian_bridge.py` for type clarity
- Added 23 new tests across 3 files — **total: 179 passing**

---

## Sprint 10 (2026-03-28) — OSS Community Readiness

- Updated `CHANGELOG.md`, `README.md`, `CONTRIBUTING.md` with accurate test counts (156)
- Added Sprint 9 vault tools references and `OBSIDIAN_VAULT_PATH` documentation to `README.md` Quick Start
- Extended `CONTRIBUTING.md` Design Constraints table with `No hardcoded DOMAIN_MAP` and `OBSIDIAN_VAULT_PATH via env var only` rules
- Fixed `.github/workflows/test.yml`: added `OBSIDIAN_VAULT_PATH` environment variable for CI cloud runners
- Hardened `register_agent()` in `librarian_ctl.py`:
  - Added absolute `is_system=1` protection (PermissionError — `--force` cannot bypass)
  - Distinct audit actions: `AGENT_REGISTERED` (new) vs `AGENT_UPDATED` (force overwrite)
  - Migrated CLI from positional args to `--flag` arguments
  - Exit codes: 0 = success, 1 = runtime/permission error, 2 = exists without `--force`
- Added 10 new tests in `tests/test_register_agent.py` — **total: 156 passing**
- Confirmed `_Development/` excluded from git tracking (`.gitignore` verified, `git ls-files` empty)

---

## Sprint 9 (2026-03-28) — Vault Tools Migration & ObsidianVaultArchitect

- Migrated vault tools from legacy `src/tools/` to production `openclaw_skills/vault_tools/` package
- Refactored `vault_intelligent_router.py`: replaced hardcoded `DOMAIN_MAP` with runtime `discover_domains()` that scans the live `20 - AREAS/` folder — no more out-of-sync domain maps
  - Case-insensitive domain lookup (`"AI"`, `"ai"`, `"Ai"` all resolve identically)
  - Duplicate Johnny.Decimal numerical prefix detection (logs warning, first-match wins)
- Hardened `vault_schema_validator.py`: `tags` added as mandatory field; `suggested_frontmatter` repair block included in every validation response
- Hardened `vault_taxonomy_guard.py`: `ALLOWED_SYSTEM_COMPONENTS` extended with `templates`, `dashboards`, `ai logs`
- Added `vault_health_check.py`: autonomous read-only vault scanner
  - Duplicate JD prefixes in `20 - AREAS/` classified as structural **errors** (not warnings)
  - Notes in `40 - ARCHIVE/` skipped; notes over `VAULT_INGEST_MAX_BYTES` flagged as warnings
  - `format_health_report()` renders results as Obsidian-ready Markdown with valid YAML frontmatter
- Added 4 new `architect_tools.py` subcommands: `vault-route`, `vault-validate`, `vault-check-taxonomy`, `vault-health-check`
- Updated `ObsidianVaultArchitect` agent to v2.0 with dual-mode description (Mode A: CLI tools, Mode B: autonomous health scan)
- Updated `TOOLS.md` with full `vault_tools` package reference table and CLI examples
- Updated `.env.example` and `setup.sh` to document `OBSIDIAN_VAULT_PATH` as required for vault routing and health check
- Deleted legacy `src/tools/` directory (decommissioned)
- Added 52 new tests — **total: 156 passing**

---

## Sprint 8 (2026-03-27) — OSS Community Readiness

- Rewrote `CHANGELOG.md` (removed legacy Letta.ai/macOS content)
- Added Glossary, CI badge, Getting Started and Obsidian callouts to `README.md`
- Added Python 3.10+ preflight check and consistent `[0/7]`–`[7/7]` step counter to `setup.sh`
- Wrapped Ollama `URLError` with human-readable `RuntimeError` in `safety_engine.py` and `router.py`
- Added `pytest>=7.0` to `requirements.txt`
- Created `.env.example` with all environment variables documented
- Created `CONTRIBUTING.md` with design constraints and contribution guidelines
- Fixed `knowledge_base.json` hardcoded "Alexey" → "the human operator"
- Added `register_agent()` function + `register-agent` CLI subcommand to `librarian_ctl.py`
- New documentation: `docs/glossary.md`, `docs/getting_started.md`, `docs/how_to_create_agent.md`, `docs/README.md`
- Added GitHub Actions CI workflow (`.github/workflows/test.yml`) — Python 3.10/3.11/3.12 matrix
- Removed `_Development/` internal planning docs from public git tracking

---

## Sprint 7 (2026-03-27) — Obsidian Bidirectional Sync

- Added `openclaw_skills/obsidian_bridge.py`: stdlib-only HTTP client for the Obsidian Local REST API
  - Loopback enforcement (`127.0.0.1` / `localhost` only — no remote exfiltration)
  - `OBSIDIAN_API_KEY` mandatory at construction; empty string raises `ValueError`
  - Dual path validation: blocks `../` traversal and absolute paths
  - Methods: `ping()`, `read_note()`, `write_note()`, `append_to_note()`, `list_notes()`, `check_obsidian_health()`
- Added `openclaw_skills/obsidian_vault_bootstrap.py`: idempotent Johnny.Decimal folder creator
- Added `write_agent_result_to_vault()` to `architect_tools.py`
  - Sensitivity Gate: `is_sensitive=True` blocks vault writes completely
  - Context Guard: output truncated to 12,000 chars before vault insertion
  - New CLI: `architect_tools.py write-to-vault`
- Added `ingest_vault_note()` + `ingest-vault-note` CLI to `librarian_ctl.py`
  - IPI Size Gate: notes >50,000 bytes rejected before hitting LLMs
  - Always `source_type='external'` (vault content always scrubbed)
- Updated `setup.sh`: vault bootstrap step and Obsidian health check (non-blocking)
- Added `docs/linux_obsidian_setup.md`: full Linux AppImage + Local REST API setup runbook
- Added 34 new tests (`tests/test_obsidian_bridge.py`): 94/94 total passing

---

## Sprint 6 (2026-03-27) — Core Intelligence & Resilience

- Added `openclaw_skills/router.py`: Dynamic LLM Router with HITL halt policy
  - 6-row routing decision matrix (sensitive/non-sensitive × local/cloud/unavailable)
  - `ROUTING_HALT` sentinel: `is_sensitive=True + tier=cloud` raises `PermissionError` — cloud never called
  - All 4 routing outcomes (`ROUTE_LOCAL`, `ROUTE_CLOUD`, `ROUTE_LOCAL_FAIL`, `ROUTING_HALT`) logged to `audit_logs`
- Added `openclaw_skills/kb.py` + `openclaw_skills/knowledge_base.json`: Static Knowledge Base
  - Security rules, capability boundaries, and epistemic invariants injected as first prompt block
  - `submit_kb_proposal()` + `approve_kb_proposal()` with HITL Burn-on-Read token
  - Migration: `proposed_kb_updates` table
- Added `openclaw_skills/librarian/self_healing.py`: circuit-breaking JSON parser
  - `parse_json_with_retry()` — max 3 retries then `RuntimeError`; never silent fallback
- Scoped Epistemic Scrubber: `archive_log()` gains `source_type` parameter
  - `source_type='internal'` skips distillation (trusted system output)
  - `source_type='external'` (default) always runs through scrubber
- 32 new tests (Sprint 6); total 60/60 passing

---

## Sprint 5 (2026-03-27) — OSS Readiness & Agent Runner

- Added `openclaw_skills/config.py`: central `OPENCLAW_WORKSPACE` path abstraction
- Added `setup.sh`: single-command cold-start sequence (idempotent, 5 steps)
- Added `requirements.txt` with pinned runtime dependencies
- Added `run_agent()` + `run` CLI subcommand to `architect_tools.py`
- Added `description TEXT` and `tool_names TEXT` columns to `agents` table (via `migrate_db.py`)
- Repositioned `README.md` with comparison table vs. LangChain/CrewAI/AutoGen
- 28 tests; all passing

---

## Sprint 3.5 / Sprint 4 (2026-03-16 to 2026-03-26) — Lifecycle & Repository Cleansing

- Implemented pipeline deployment, teardown, and HITL Burn-on-Read token lifecycle in `architect_tools.py`
- `deploy_pipeline_with_ui()`: tkinter GUI popup (Yes/No) required before any pipeline deployment
- `teardown_pipeline()`: protected system agents (`is_system=1`) are never torn down
- `validate_token()`: token file deleted before comparison (true Burn-on-Read)
- Full repository migration from legacy Letta.ai/macOS codebase to OpenClaw for Linux
- `AGENTS.md` added with persistent AI coding assistant directives

---

## Sprints 1–3 (2026-03-16) — Core Librarian, Airlock & Vector Archive

- `librarian_ctl.py`: Airlock (`validate_path()` with `os.sep` prefix-collision guard), DB init (WAL mode), bootstrap, registry generation
- `safety_engine.py`: Hybrid Safety Distillation Engine (local Ollama + cloud Gemini routing)
- `vector_archive.py`: `sqlite-vec` 768-dim vector init + Faint Path semantic search (`find_faint_paths()`)
- `migrate_db.py`: incremental schema migration runner
- Three-layer memory: The Map (`REGISTRY.md`), The State (`factory.db`), The Archive (`sqlite-vec`)

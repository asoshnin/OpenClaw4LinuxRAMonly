# Changelog

All notable changes are listed by Sprint. This project follows a sprint-based delivery model documented in `_Development/OpenClaw/`.

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

---
name: OpenClaw Core Architecture & Security
description: Foundational constraints, technology stack, directory structure, and non-negotiable security policies (HITL, Airlock) for OpenClaw. Must be read when modifying architecture, writing file operations, or provisioning components.
---

# Product Overview

OpenClaw is a hardened, self-evolving agentic operating system built for Linux x86_64.
- **Goal:** Epistemic Sovereignty. The human Navigator (Alexey) retains cryptographically enforced control over deployment decisions via HITL gates.
- **Hardware:** ThinkPad W540 (x86_64, Linux, CPU-bound).
- **RAM-Only Architecture:** Runtime state lives in SQLite WAL + sqlite-vec.
- **Privacy:** Sensitive inference is locally handled via Ollama. Cloud (Gemini) strictly for scrubbed log distillation.

# Configuration (Sprint 5+)

- **Never hardcode workspace paths.** The Source of Truth is `/home/alexey/openclaw-inbox/agentic_factory/`. The `~/.openclaw/workspace` directory is a **Symlinked Buffer**. Memory and Docs folders are linked bidirectionally between the two.
- **Single source of truth:** `openclaw_skills/config.py` defines `WORKSPACE_ROOT`, `TOKEN_FILE`, `DEFAULT_DB_PATH`, and `DEFAULT_REGISTRY_PATH`. All other modules import from here.
- Both `librarian_ctl.py` and `architect_tools.py` import `WORKSPACE_ROOT` from `config`. No path string literals in those files.

# Security & HITL Policy (Non-Negotiable)

1. **The HITL Gate**: Every pipeline deployment MUST use `deploy_pipeline_with_ui(db_path, pipeline_id, pipeline_name, topology_json)` from `architect_tools.py`. Never generate tokens manually or suppress the `PermissionError`.
2. **Airlock Workspace Boundary**:
   - All file ops use `os.path.realpath()`.
   - `validate_path()` imports `WORKSPACE_ROOT` from `config.py`. The `startswith()` check MUST include an `os.sep` suffix guard to prevent prefix-collision attacks:
     ```python
     if not (target_abs == base_dir or target_abs.startswith(base_dir + os.sep)):
         raise PermissionError(f"Airlock Breach: {target_abs} is outside {base_dir}")
     ```
   - Never use a bare `startswith(base_dir)` without the `os.sep` guard.
   - **Constraint:** Ensure `openclaw_skills/` remains "Invisible" to the execution workspace logic.
3. **Burn-on-Read Token**: Handled by the UI wrapper; token is deleted before comparison.
4. **Context Guard**: Logs passed to any LLM call must be truncated to 12,000 characters maximum before the call.
5. **Epistemic Scrubber**: All *externally-ingested* data entering the Vector Archive must pass through `safety_engine.py`. Internal audit logs may be embedded directly.
6. **System Agent Protection**: Agents with `is_system=1` in `factory.db` are immutable. The `register_agent()` function enforces this absolutely — `--force` does not override `is_system=1`.
7. **Secrets**: Use env vars (e.g., `GEMINI_API_KEY`, `OPENCLAW_WORKSPACE`, `OBSIDIAN_API_KEY`, `OBSIDIAN_BASE_URL`, `OBSIDIAN_VAULT_PATH`). Never hardcode paths or keys.

# Agent Runner Constraints (Sprint 5+)

- `run_agent(db_path, agent_id, task_text)` is a **read + local inference + audit** operation only.
- It MUST NOT call `deploy_pipeline_with_ui()` or any HITL gate.
- It MUST call local Ollama only — never cloud APIs.
- It MUST log the result to `audit_logs` with `action='AGENT_RUN'`.
- It MUST raise `ValueError` if `agent_id` is not found, and `RuntimeError` if Ollama is unreachable. Never return silently on failure.
- **Prompt construction order (Sprint 6+):** The prompt MUST be assembled in this exact order:
  1. `[SYSTEM RULES]` — content from `load_knowledge_base()` in `kb.py` (security_rules block)
  2. `[AGENT IDENTITY]` — agent name and description from DB
  3. `[MEMORY CONTEXT]` — top-3 Faint Paths from `find_faint_paths()` (max 4000 chars)
  4. `[TASK]` — the `task_text` argument
- If `knowledge_base.json` is missing, log at `WARNING` and continue with empty KB prefix — do not raise.

# Dynamic LLM Router Policy (Sprint 6+)

`openclaw_skills/router.py` implements `route_inference(task_text, is_sensitive, min_model_tier, db_path) -> str`.

**Non-negotiable routing rules:**
1. `is_sensitive=True` + `min_model_tier="cloud"` → **ALWAYS** raise `PermissionError("[SYS-HALT: HITL REQUIRED - SENSITIVE CLOUD ROUTING]")`. Log `ROUTING_HALT` to `audit_logs`. **Never call any cloud API.** No exceptions.
2. Local Ollama unavailable + `min_model_tier="local"` → raise `RuntimeError`. Log `ROUTE_LOCAL_FAIL`. **No silent fallback to cloud.**
3. Every routing outcome (all 4 action types: `ROUTE_LOCAL`, `ROUTE_CLOUD`, `ROUTE_LOCAL_FAIL`, `ROUTING_HALT`) must be written to `audit_logs` unconditionally.
4. Availability check: ping `{OLLAMA_URL}/api/tags` with `timeout=3.0` before every local call.
5. Defaults for all CLI callers: `--sensitive`, `--tier local` (safest possible defaults).

# Knowledge Base Policy (Sprint 6+)

- `openclaw_skills/knowledge_base.json` is a **static committed file** — not runtime-generated, not vectorized.
- `openclaw_skills/kb.py` provides `load_knowledge_base()`, `format_kb_for_prompt()`, `submit_kb_proposal()`, `approve_kb_proposal()`.
- **Agents may only PROPOSE updates** via `submit_kb_proposal()` — they never call `approve_kb_proposal()`.
- `approve_kb_proposal()` requires a valid HITL burn-on-read token. Any code path that calls it without a token MUST raise `PermissionError`.
- KB content is never passed to `archive_log()` or embedded in `vec_passages` — static injection only.
- Atomic KB file updates: always write to a `.tmp` file and use `os.replace()` — same pattern as `generate_registry()`.

# Self-Healing JSON Parser (Sprint 6+)

- `openclaw_skills/librarian/self_healing.py` provides `parse_json_with_retry(raw_text, model_call_fn, max_retries=3) -> dict`.
- On `JSONDecodeError`: call `model_call_fn` with a repair prompt. Increment counter.
- After `max_retries` failures: raise `RuntimeError("JSON parse circuit breaker tripped after N retries")`. **Never return a degraded fallback dict.**
- `_distill_local()` in `safety_engine.py` MUST use `parse_json_with_retry()`. The bare `except json.JSONDecodeError` silent fallback is forbidden.
- Log each retry attempt at `WARNING` level.

# Scoped Epistemic Scrubber (Sprint 6+)

`archive_log()` signature is extended: `archive_log(db_path, raw_source_id, raw_log, is_sensitive=True, source_type="external")`.
- `source_type="external"` (default): calls `distill_safety()` before embedding — existing behaviour.
- `source_type="internal"`: **skips `distill_safety()` entirely.** Uses `{"scrubbed_log": raw_log, "facts": []}` directly. Embedding step still runs.
- `distilled_memory` table gains a `source_type TEXT DEFAULT 'external'` column (new migration).
- Internal audit callers must explicitly pass `source_type="internal"` — the default remains `external` so external data is always scrubbed if callers forget the argument.

# Obsidian Bridge Policy (Sprint 7+)

`openclaw_skills/obsidian_bridge.py` provides `ObsidianBridge` — an HTTP client for the Obsidian Local REST API plugin (`http://127.0.0.1:27123`).

**Non-negotiable rules:**
1. **Localhost enforcement.** `ObsidianBridge.__init__` MUST validate that `base_url` resolves to a loopback address (`localhost`, `127.0.0.1`, `::1`). Any other hostname raises `ValueError`. This is an enforced invariant — the security review justification ("local-only, no routing needed") is only valid because this check exists.
2. **API key is required.** `OBSIDIAN_API_KEY` env var is mandatory. An empty string MUST raise `ValueError("OBSIDIAN_API_KEY is required")` at construction time. Empty key causes `401 Unauthorized`, which silently manifests as `VAULT_WRITE_SKIPPED` forever — never acceptable.
3. **`append_to_note` uses `PATCH`, NOT `POST ?append=true`.** The `POST /vault/{path}?append=true` endpoint does not exist in the plugin. `PATCH /vault/{path}` is the correct append method. This is a hard correctness constraint.
4. **`list_notes` response is a flat JSON array.** The plugin returns `["path/a.md", "path/b.md"]` — NOT `{"files": [...], "folders": [...]}`. Parse accordingly.
5. **`ping()` uses `GET /vault/`, NOT `GET /`.** The root endpoint (`/`) is unreliable across plugin versions. `GET /vault/` returns a consistent HTTP response (including `401`) when the plugin is running.
6. **Sensitivity gate on vault writes.** `write_agent_result_to_vault(..., is_sensitive=True)` MUST return `None` immediately without rendering or writing any content. The vault may sync to cloud via Obsidian sync plugins (e.g., Remotely Save + OneDrive).
7. **Context Guard on vault writes.** `result` passed to `write_agent_result_to_vault()` MUST be truncated at 12,000 characters before being embedded in the note template.
8. **IPI size gate on vault ingest.** `ingest_vault_note()` MUST reject notes larger than 50,000 bytes (`VAULT_INGEST_MAX_BYTES`) before calling `archive_log()`. Raise `ValueError` — do not ingest oversized notes silently.
9. **`is_sensitive` flag MUST be propagated.** `ingest_vault_note(is_sensitive=True)` MUST call `archive_log(..., is_sensitive=True)`. Never hardcode False. This controls local (Ollama) vs cloud (Gemini) distillation.
10. **Vault ingest always uses `source_type="external"`.** Vault notes carry the same IPI risk as web-clipped content. Never allow `source_type="internal"` for vault-originated content.
11. **Vault write failures are non-fatal; ingest failures are explicit.** `write_agent_result_to_vault` MUST never raise on Obsidian unavailability (log + return `None`). `ingest_vault_note` MUST raise `RuntimeError` if Obsidian is down (explicit Navigator action).
12. **Audit trail for ingest failures.** If `archive_log()` raises during `ingest_vault_note`, log `action='VAULT_INGEST_FAILED'` to `audit_logs` before re-raising.
13. **Path validation in `write_note`.** Both checks are required: `os.path.normpath(vault_path).startswith("..")` AND `os.path.isabs(os.path.normpath(vault_path))`. Neither alone is sufficient.

# Vault Tools Policy (Sprint 9+)

`openclaw_skills/vault_tools/` is the production vault tools package. **Never use the deleted `src/tools/` path.**

**Key modules:**
- `vault_intelligent_router.py` — `discover_domains(vault_root)` scans `20 - AREAS/` at runtime. **No hardcoded `DOMAIN_MAP`.** `suggest_vault_path(metadata, filename, vault_root)` does case-insensitive slug matching with INBOX fallback.
- `vault_schema_validator.py` — `validate_vault_metadata(content, expected_path)` validates YAML frontmatter. Mandatory fields: `id`, `type`, `summary`, `tags`, `domain`. Always returns `suggested_frontmatter` repair block.
- `vault_taxonomy_guard.py` — `validate_taxonomy_compliance(vault_path)` enforces `NN - ` prefix on all path components. System folders (`.obsidian`, `templates`, `dashboards`, `ai logs`, `.git`, `openclaw`) are exempt via ancestor-path short-circuit.
- `vault_health_check.py` — `run_vault_health_check(vault_root, db_path)` is **read-only**. Duplicate JD numerical prefixes in `20 - AREAS/` = **ERROR** (not warning). Notes in `40 - ARCHIVE/` are skipped. `format_health_report()` produces Obsidian-ready Markdown.

**Airlock exception:** `vault_root` (the Obsidian vault) is NOT subject to `validate_path()`. It lives outside `OPENCLAW_WORKSPACE` by design. It is sourced from `OBSIDIAN_VAULT_PATH` env var only — never passed through Airlock.

**`architect_tools.py` subcommands (Sprint 9):** `vault-route`, `vault-validate`, `vault-check-taxonomy`, `vault-health-check`. All follow exit codes 0=success, 1=error, 2=validation failure.

**`VAULT_TOOLS_AVAILABLE` guard:** vault_tools is imported with a graceful try/except in `architect_tools.py`. All four command handlers check `VAULT_TOOLS_AVAILABLE` before executing.

# Managed Browser Policy (v2026.3.28)

- Legacy "Extension Relays" are removed. We use CDP attachment.
- **Protocol:** `OPEN URL` -> `SNAPSHOT --INTERACTIVE` -> `ACT (using e1, e2 refs)`.
- No CSS selectors allowed. 
- Agents MUST use `openclaw browser snapshot --interactive` to get element references (`e1`, `e2`) before clicking or typing.

# Strategic Vision & Self-Evolution

- **Recursive Self-Evolution:** The system operates on an atomic synthesis loop for constant capability upgrades.
- **Invariant:** Agents MUST identify system deficiencies using the `[EPISTEMIC_GAP]` tag.
- **Invariant:** All high-stakes artifacts MUST pass through the **Red Team Auditor** (Status: Assessment -> Findings -> Recommendations).

# Database Backlog Migration (BL-00)

- The `factory.db` database contains an `epistemic_backlog` table for automated tracking and reporting of identified gaps.

# Technology Stack

- **Runtime**: Python 3.10+ (Synchronous execution only), SQLite (WAL), `sqlite-vec` (768-dim embeddings).
- **AI/Inference**: Ollama (`nomic-embed-text`, `nn-tsuzu/lfm2.5-1.2b-instruct`), `google-generativeai` (distillation only).
- **Libraries**: `pyyaml`, `tkinter`, `argparse`, `logging`, `hashlib`, `secrets`, `urllib.request` (HTTP — no `requests`/`httpx`), `pytest` (test suite).
- **FORBIDDEN**: No ORMs (SQLAlchemy), No async frameworks, No Docker/K8s, No external vector DBs, No `requests`/`httpx` (use `urllib.request` only).

# Project Structure & Patterns

- `.agents/` — AI agent steering and workflow configs (this file, workflows/).
- `openclaw_skills/config.py` — **Central config module. Import here, never hardcode.**
- `openclaw_skills/router.py` — Dynamic LLM Router with HITL-guarded routing policy. *(Sprint 6)*
- `openclaw_skills/kb.py` — Static KB loader, prompt formatter, and HITL-supervised reflection queue. *(Sprint 6)*
- `openclaw_skills/knowledge_base.json` — Committed static rules file. Never vectorize, never auto-modify. *(Sprint 6)*
- `openclaw_skills/obsidian_bridge.py` — Obsidian Local REST API client. localhost-only. See Obsidian Bridge Policy. *(Sprint 7)*
- `openclaw_skills/obsidian_vault_bootstrap.py` — Idempotent Johnny.Decimal folder creation for new vault setup. *(Sprint 7)*
- `openclaw_skills/vault_tools/` — Production vault tools package: router, schema validator, taxonomy guard, health check. See Vault Tools Policy. *(Sprint 9)*
- `openclaw_skills/librarian/` — DB management, registry, vector archive, safety engine, self-healing parser.
- `openclaw_skills/librarian/self_healing.py` — Circuit-breaking JSON parser. Max 3 retries then raise. *(Sprint 6)*
- `openclaw_skills/architect/` — Discovery, HITL, deploy, teardown, agent runner, vault tool subcommands.
- `tests/` — pytest suite. 156 tests. Fixtures use temp dirs. No test touches real `WORKSPACE_ROOT`.
- `docs/` — User-facing documentation (getting_started, architecture, glossary, how_to_create_agent, linux_obsidian_setup, telegram_interface).
- `_Development/OpenClaw/` — Sprint tracking and backlog. **Not tracked in git** (`.gitignore` exclusion verified).
- **CLI Patterns**: `argparse` subcommands. DB path is a positional argument for legacy commands (`init`, `bootstrap`, `refresh-registry`, `ingest-vault-note`). Sprint 9+ vault tool subcommands and `register-agent` use `--flag` arguments. Exit codes: 0=success, 1=runtime error, 2=validation/existence failure.
- **Setup**: `setup.sh` at project root. Respects `OPENCLAW_WORKSPACE` and `OBSIDIAN_VAULT_PATH`. Idempotent.
- **Git**: `origin` remote = `https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git` (the Linux OpenClaw public repo). `mac-factory` remote = separate Mac prototype repo — not the canonical codebase.
- **CI**: `.github/workflows/test.yml` runs pytest on Python 3.10/3.11/3.12. Required env vars: `OPENCLAW_WORKSPACE`, `OBSIDIAN_API_KEY`, `OBSIDIAN_VAULT_PATH`.

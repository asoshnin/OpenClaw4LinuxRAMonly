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

- **Never hardcode workspace paths.** The workspace root is resolved from the `OPENCLAW_WORKSPACE` environment variable, defaulting to `~/.openclaw/workspace`.
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
3. **Burn-on-Read Token**: Handled by the UI wrapper; token is deleted before comparison.
4. **Context Guard**: Logs passed to any LLM call must be truncated to 12,000 characters maximum before the call.
5. **Epistemic Scrubber**: All *externally-ingested* data entering the Vector Archive must pass through `safety_engine.py`. Internal audit logs may be embedded directly.
6. **System Agent Protection**: Agents with `is_system=1` in `factory.db` are immutable.
7. **Secrets**: Use env vars (e.g., `GEMINI_API_KEY`, `OPENCLAW_WORKSPACE`, `OBSIDIAN_API_KEY`, `OBSIDIAN_BASE_URL`). Never hardcode paths or keys.

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

# Technology Stack

- **Runtime**: Python 3.10+ (Synchronous execution only), SQLite (WAL), `sqlite-vec` (768-dim embeddings).
- **AI/Inference**: Ollama (`nomic-embed-text`, `nn-tsuzu/lfm2.5-1.2b-instruct`), `google-generativeai` (distillation only).
- **Libraries**: `pyyaml`, `tkinter`, `argparse`, `logging`, `hashlib`, `secrets`, `urllib.request` (HTTP — no `requests`/`httpx`), `pytest` (test suite).
- **FORBIDDEN**: No ORMs (SQLAlchemy), No async frameworks, No Docker/K8s, No external vector DBs, No `requests`/`httpx` (use `urllib.request` only).

# Project Structure & Patterns

- `.agents/` — AI agent steering and workflow configs.
- `openclaw_skills/config.py` — **Central config module. Import here, never hardcode.**
- `openclaw_skills/router.py` — Dynamic LLM Router with HITL-guarded routing policy. *(Sprint 6)*
- `openclaw_skills/kb.py` — Static KB loader, prompt formatter, and HITL-supervised reflection queue. *(Sprint 6)*
- `openclaw_skills/knowledge_base.json` — Committed static rules file. Never vectorize, never auto-modify. *(Sprint 6)*
- `openclaw_skills/obsidian_bridge.py` — Obsidian Local REST API client. localhost-only. See Obsidian Bridge Policy. *(Sprint 7)*
- `openclaw_skills/obsidian_vault_bootstrap.py` — Idempotent Johnny.Decimal folder creation for new vault setup. *(Sprint 7)*
- `openclaw_skills/librarian/` — DB management, registry, vector archive, safety engine, self-healing parser.
- `openclaw_skills/librarian/self_healing.py` — Circuit-breaking JSON parser. Max 3 retries then raise. *(Sprint 6)*
- `openclaw_skills/architect/` — Discovery, HITL, deploy, teardown, agent runner.
- `tests/` — pytest suite. Fixtures use temp dirs. No test touches real `WORKSPACE_ROOT`.
- `docs/YYYY-MM-DD__HH-MM_*.md` — timestamped snapshots.
- `_Development/OpenClaw/` — Sprint tracking and backlog.
- **CLI Patterns**: `argparse` subcommands. DB path is always a positional argument, never hardcoded.
- **Setup**: `setup.sh` at project root. Respects `OPENCLAW_WORKSPACE` and `OBSIDIAN_VAULT_PATH`. Idempotent.

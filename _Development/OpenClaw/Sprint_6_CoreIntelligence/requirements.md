# Sprint 6 Requirements: Core Intelligence & Resilience

**Sprint Goal:** Elevate OpenClaw from a minimal agent runner into a resilient, self-repairing intelligence layer — one that routes inference safely between local and cloud models, maintains a human-supervised knowledge base, recovers autonomously from JSON parse failures, and archives only the data that genuinely requires scrubbing.

**Pre-requisite:** Sprint 5 (OSS Readiness) is complete and all tests pass. The `config.py`, `setup.sh`, `run_agent()`, and `tests/` suite must be present and green before this sprint begins.

---

## Block A — Dynamic LLM Router (HITL-Guarded)

### [REQ-S6-01] Sensitive Cloud Routing Must Never Silently Fall Back
The current `distill_safety()` routing is binary: `is_sensitive=True` → local, `is_sensitive=False` → cloud. There is no guard for the case where the *calling agent* requests cloud inference on sensitive data, nor for cases where the local model is unavailable and a cloud fallback is considered.

**User Story:** As the Navigator, I need the system to stop and wait for my explicit approval before sending any data classified as sensitive to a cloud API — even if the local model is temporarily unavailable.

**Acceptance Criteria:**
- A new module `openclaw_skills/router.py` implements `route_inference(task_text, is_sensitive, min_model_tier, db_path) -> str`.
- `min_model_tier` accepts values `"local"` or `"cloud"`.
- If `is_sensitive=True` AND `min_model_tier="cloud"`: the router **must NOT call any cloud API**. Instead, it sets a `pending_hitl` record in `audit_logs` (action=`'ROUTING_HALT'`, rationale=`'[SYS-HALT: HITL REQUIRED - SENSITIVE CLOUD ROUTING]'`) and raises a `PermissionError` with that sentinel string.
- If `is_sensitive=False` AND `min_model_tier="cloud"`: the router calls `_distill_cloud()` normally.
- If `is_sensitive=True` AND `min_model_tier="local"`: the router calls `_distill_local()` normally — the existing behaviour.
- If the local Ollama endpoint is unavailable (URLError) AND `min_model_tier="local"`: raises `RuntimeError` — **no silent fallback to cloud**.
- A CLI subcommand `python3 router.py route <db_path> <task> --sensitive --tier local` exposes the function for testing and manual use.
- All routing decisions are logged to `audit_logs` unconditionally (action=`'ROUTE_LOCAL'` or `'ROUTE_CLOUD'` or `'ROUTING_HALT'`).

---

## Block B — Static Knowledge Base & HITL-Supervised Reflection Queue

### [REQ-S6-02] Static Knowledge Base Injection
Agent prompts currently contain no persistent, curated knowledge — only semantic memory retrieved from `vec_passages`. Curated rules and invariants (security policies, capability boundaries) must be injected verbatim into every agent's system prompt, not vectorized.

**User Story:** As the Navigator, I need core agent rules (e.g., "Never deploy without HITL") to be hard-wired into every prompt as a static string, not retrievable by vector search or modifiable by an LLM.

**Acceptance Criteria:**
- A new file `openclaw_skills/knowledge_base.json` contains a JSON object with at minimum these keys: `"security_rules"`, `"capability_boundaries"`, `"epistemic_invariants"`.
- A function `load_knowledge_base() -> dict` in `openclaw_skills/kb.py` reads this file and returns the parsed object. It raises `FileNotFoundError` on missing file and `json.JSONDecodeError` on malformed content — never returns silently.
- `run_agent()` in `architect_tools.py` is updated to call `load_knowledge_base()` and inject the `security_rules` block as a `[SYSTEM RULES]\n{rules}` prefix in the prompt — before the memory context and before the task text.
- The knowledge base content is **never embedded into `vec_passages`** — it is static string injection only.
- The knowledge base file is committed to the repository and treated as a configuration artifact, not runtime state.

### [REQ-S6-03] HITL-Supervised Reflection Queue
Agents may generate candidate updates to their own rules or knowledge base during operation. These must never be applied autonomously — they must queue for human review.

**User Story:** As the Navigator, I need a way to review and approve (or reject) rule updates that an agent proposes, without any autonomous self-modification.

**Acceptance Criteria:**
- A new SQLite table `proposed_kb_updates` is added via a new migration in `migrate_db.py`:
  ```sql
  CREATE TABLE IF NOT EXISTS proposed_kb_updates (
      update_id INTEGER PRIMARY KEY AUTOINCREMENT,
      proposed_by TEXT,       -- agent_id
      update_type TEXT,       -- 'rule_add' | 'rule_modify' | 'rule_delete'
      target_key TEXT,        -- key in knowledge_base.json
      proposed_value TEXT,    -- new value (JSON string)
      rationale TEXT,
      status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
      submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      reviewed_at TIMESTAMP
  );
  ```
- A function `submit_kb_proposal(db_path, agent_id, update_type, target_key, proposed_value, rationale) -> int` in `kb.py` inserts a `pending` record and returns `update_id`. It validates `update_type` against the allowed set and raises `ValueError` otherwise.
- A function `approve_kb_proposal(db_path, update_id, navigator_token) -> None` in `kb.py` validates the HITL burn-on-read token, updates `status='approved'` and `reviewed_at`, then writes the new value into `knowledge_base.json`. Raises `PermissionError` on invalid token.
- A CLI subcommand `python3 kb.py list-proposals <db_path>` prints all `pending` proposals in a human-readable table.
- An agent calling `submit_kb_proposal()` MUST NOT trigger `approve_kb_proposal()` in the same execution — enforcement is by design (separate function + HITL token requirement).

---

## Block C — Self-Healing JSON Parsers

### [REQ-S6-04] Circuit Breaker with Auto-Retry for JSON Parse Failures
The current `_distill_local()` has a single silent fallback on `json.JSONDecodeError`: it returns `{"facts": [], "scrubbed_log": raw_text}`. This hides failures and degrades the archive silently.

**User Story:** As the Navigator, I need the system to attempt to recover from malformed LLM JSON output automatically (up to 3 retries), and escalate to a HITL halt state if all retries are exhausted — so I always know when the system is degraded.

**Acceptance Criteria:**
- A new function `parse_json_with_retry(raw_text, model_call_fn, max_retries=3) -> dict` in `openclaw_skills/librarian/self_healing.py` implements the circuit breaker:
  1. Attempt `json.loads(raw_text)`.
  2. On `JSONDecodeError`: call `model_call_fn()` with a repair prompt (e.g., `"Fix this malformed JSON and return only valid JSON: {raw_text}"`), increment retry counter.
  3. After `max_retries` failures: raise `RuntimeError("JSON parse circuit breaker tripped after N retries")` — never silently degrade.
- `_distill_local()` in `safety_engine.py` is updated to call `parse_json_with_retry()` instead of the bare `try/except json.JSONDecodeError`.
- The circuit breaker retry count and trip events are logged at `WARNING` level via the `logging` module.
- Tests in `tests/test_self_healing.py` cover: successful first-parse, successful second-attempt recovery, and circuit-breaker trip after max retries — all with mocked LLM calls.

---

## Block D — Scoped Epistemic Scrubber

### [REQ-S6-05] Restrict Epistemic Scrubber to External Content Only
Currently, `archive_log()` always calls `distill_safety()` (which calls the scrubber) regardless of whether the content is an internal audit trail or externally-ingested data. Internal OpenClaw audit logs have already been sanitized through the system's own controlled output — scrubbing them adds one full Ollama roundtrip per archive on the CPU-limited W540 with no security benefit.

**User Story:** As the Navigator operating on a CPU-bound ThinkPad W540, I need the scrubber to run only when it is actually required (external data), not on internal audit logs — reducing per-archive inference calls from 2 to 1 for internal content.

**Acceptance Criteria:**
- `archive_log()` in `safety_engine.py` gains a parameter `source_type: str` with allowed values `"external"` (default) or `"internal"`.
- If `source_type="internal"`: `archive_log()` skips the `distill_safety()` call entirely and uses the `raw_log` directly as `content_json` (formatted as `{"scrubbed_log": raw_log, "facts": []}`). The embedding step still runs (local Ollama is used for embeddings regardless).
- If `source_type="external"`: existing behaviour is preserved exactly — `distill_safety()` is called before embedding.
- A migration in `migrate_db.py` adds a `source_type TEXT DEFAULT 'external'` column to `distilled_memory`.
- All callers of `archive_log()` that archive internal audit logs (e.g., internal system diagnostics) are updated to pass `source_type="internal"`.
- Tests verify that `distill_safety()` is NOT called when `source_type="internal"`, and IS called for `source_type="external"`.

---

## Out of Scope for Sprint 6
- Obsidian Bidirectional Sync (Phase 3)
- Health-Check Supervisor (Phase 3)
- SQLite-backed Async Task Queue (Phase 3)
- Web UI, REST API, or any network listener
- Moving files from `openclaw_skills/` into `src/` (GAP-03 — deferred pending Navigator decision)

---

## Safety Constraints (All Blocks)
- Every new file operation in any new module must call `validate_path()` before use. No exceptions.
- `route_inference()` must never call cloud APIs when `is_sensitive=True`, even if the local model is unavailable. The system must halt, not degrade silently.
- `approve_kb_proposal()` requires a valid HITL burn-on-read token. It must not be callable without one.
- `parse_json_with_retry()` must raise, not return a degraded result, after `max_retries` exhausted.
- All tests must use isolated temp workspaces (via `conftest.py` `isolated_workspace` fixture). No test touches the real `OPENCLAW_WORKSPACE`.
- No new external dependencies beyond those in `requirements.txt`. Retry and circuit-breaker logic uses stdlib only.

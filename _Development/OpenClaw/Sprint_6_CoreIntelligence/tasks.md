# Tasks: Sprint 6 — Core Intelligence & Resilience

**Sprint Goal:** Dynamic LLM routing with HITL-guarded cloud access, static knowledge base with supervised reflection queue, self-healing JSON circuit breaker, and scoped epistemic scrubber.

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` complete · `[!]` blocked

---

## BLOCK A — Dynamic LLM Router

### Task A.1 — Create `openclaw_skills/router.py`
**Ref:** [REQ-S6-01], [DES-Block-A]
- [x] Create `openclaw_skills/router.py` with `route_inference(task_text, is_sensitive, min_model_tier, db_path) -> str`
- [x] Implement the 6-row routing decision matrix from `design.md §2.3`
- [x] Add Ollama availability ping via `urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3.0)`
- [x] Implement `ROUTING_HALT` path: log to `audit_logs` with `action='ROUTING_HALT'`, raise `PermissionError("[SYS-HALT: HITL REQUIRED - SENSITIVE CLOUD ROUTING]")`
- [x] Log every routing outcome to `audit_logs` (actions: `ROUTE_LOCAL`, `ROUTE_CLOUD`, `ROUTE_LOCAL_FAIL`, `ROUTING_HALT`)
- [x] Import `WORKSPACE_ROOT`, `OLLAMA_URL`, `LOCAL_MODEL` from `config.py` — no hardcoded values
- [x] All DB writes pass through `validate_path()`

### Task A.2 — Add `router.py` CLI subcommand
**Ref:** [REQ-S6-01]
- [x] Add `if __name__ == "__main__":` block with `argparse`
- [x] Subcommand `route <db_path> <task> [--sensitive] [--tier local|cloud]`
- [x] Defaults: `--sensitive`, `--tier local` (safest defaults)
- [x] Print result to stdout; print errors to stderr with `sys.exit(1)`

### Task A.3 — Tests: `tests/test_router.py`
**Ref:** [DES §8]
- [x] `test_route_local_sensitive_available` — local + sensitive + Ollama up → returns response, logs `ROUTE_LOCAL`
- [x] `test_route_local_sensitive_unavailable` — local + sensitive + Ollama down → raises `RuntimeError`, logs `ROUTE_LOCAL_FAIL`
- [x] `test_routing_halt_sensitive_cloud` — sensitive + tier=cloud → raises `PermissionError` with sentinel, logs `ROUTING_HALT`, **cloud never called**
- [x] `test_route_cloud_nonsensitive` — not sensitive + tier=cloud → calls cloud distillation, logs `ROUTE_CLOUD`
- [x] `test_routing_halt_never_calls_cloud` — verify mock: cloud API mock asserted NOT called when `ROUTING_HALT` fires
- [x] `test_audit_log_written_for_every_call` — parameterize all 4 outcomes, assert 1 `audit_logs` row each
- [x] All Ollama/cloud calls mocked with `unittest.mock.patch`

---

## BLOCK B — Static Knowledge Base & Reflection Queue

### Task B.1 — Create `openclaw_skills/knowledge_base.json`
**Ref:** [REQ-S6-02]
- [x] Create `openclaw_skills/knowledge_base.json` with keys: `security_rules`, `capability_boundaries`, `epistemic_invariants`
- [x] Populate with the canonical content from `design.md §3.1`
- [x] Validate JSON is well-formed before committing

### Task B.2 — Create `openclaw_skills/kb.py`
**Ref:** [REQ-S6-02], [REQ-S6-03]
- [x] Implement `load_knowledge_base(kb_path=None) -> dict` — raises `FileNotFoundError` or `json.JSONDecodeError` on failure
- [x] Implement `format_kb_for_prompt(kb: dict) -> str` — structured prefix as per `design.md §3.3`
- [x] Implement `submit_kb_proposal(db_path, agent_id, update_type, target_key, proposed_value, rationale) -> int`
  - [ ] Validate `update_type` ∈ `{'rule_add', 'rule_modify', 'rule_delete'}` — raise `ValueError` otherwise
  - [ ] `INSERT INTO proposed_kb_updates` with `status='pending'`
  - [ ] Return `update_id`
- [x] Implement `approve_kb_proposal(db_path, update_id, navigator_token) -> None`
  - [ ] Call `validate_token(navigator_token)` — raise `PermissionError` on failure
  - [ ] `UPDATE proposed_kb_updates SET status='approved', reviewed_at=...`
  - [ ] Atomic write to `knowledge_base.json` via `tmpfile + os.replace()`
  - [ ] `INSERT INTO audit_logs (action='KB_APPROVED', rationale=...)`
- [x] Add `list-proposals <db_path>` argparse subcommand
- [x] Import `WORKSPACE_ROOT` from `config`; all file ops via `validate_path()`

### Task B.3 — Add `proposed_kb_updates` migration to `migrate_db.py`
**Ref:** [REQ-S6-03]
- [x] Add migration step 6 to `migrate_database()` in `migrate_db.py`
- [x] `CREATE TABLE IF NOT EXISTS proposed_kb_updates (...)` — schema from `design.md §3.4`
- [x] Log outcome at INFO level

### Task B.4 — Inject knowledge base into `run_agent()`
**Ref:** [REQ-S6-02]
- [x] Import `load_knowledge_base`, `format_kb_for_prompt` from `kb.py` in `architect_tools.py`
- [x] Call `load_knowledge_base()` at the start of `run_agent()`
- [x] Build prompt with KB prefix first, then agent identity, then memory context, then task — per `design.md §3.3`
- [x] If `load_knowledge_base()` raises `FileNotFoundError`, log `WARNING` and continue with empty KB string (graceful degradation for first-run before KB file exists)

### Task B.5 — Tests: `tests/test_kb.py`
**Ref:** [DES §8]
- [x] `test_load_kb_success` — loads a valid temp `knowledge_base.json`, returns dict with expected keys
- [x] `test_load_kb_file_not_found` — raises `FileNotFoundError`
- [x] `test_load_kb_malformed_json` — raises `json.JSONDecodeError`
- [x] `test_format_kb_for_prompt_contains_rules` — output string includes security_rules content
- [x] `test_submit_kb_proposal_success` — inserts row, returns `update_id`, status is `pending`
- [x] `test_submit_kb_proposal_invalid_type` — raises `ValueError`
- [x] `test_approve_kb_proposal_valid_token` — updates status, writes to `knowledge_base.json`, logs `KB_APPROVED`
- [x] `test_approve_kb_proposal_invalid_token` — raises `PermissionError`, no file write
- [x] `test_agent_cannot_approve_own_proposal` — `submit_kb_proposal` + `approve_kb_proposal` in same call without valid token → blocked by HITL gate

---

## BLOCK C — Self-Healing JSON Parser

### Task C.1 — Create `openclaw_skills/librarian/self_healing.py`
**Ref:** [REQ-S6-04]
- [x] Implement `parse_json_with_retry(raw_text, model_call_fn, max_retries=3) -> dict`
- [x] Attempt `json.loads(raw_text)` on each iteration
- [x] On `JSONDecodeError`: call `model_call_fn(repair_prompt)` and increment counter
- [x] After `max_retries` failures: log `WARNING` and raise `RuntimeError("JSON parse circuit breaker tripped after N retries")`
- [x] Use Python `logging` module — no `print()` statements
- [x] `Callable[[str], str]` type annotation for `model_call_fn`

### Task C.2 — Refactor `_distill_local()` in `safety_engine.py`
**Ref:** [REQ-S6-04]
- [x] Extract `_call_ollama(self, prompt: str) -> str` as a private helper (removes duplication between distil and repair paths)
- [x] Import `parse_json_with_retry` from `self_healing`
- [x] Replace bare `try/except json.JSONDecodeError` fallback with `parse_json_with_retry(response_text, repair_fn, max_retries=3)`
- [x] The repair `model_call_fn` lambda: `lambda broken: self._call_ollama(f"Fix this malformed JSON. Return ONLY valid JSON:\n\n{broken}")`

### Task C.3 — Tests: `tests/test_self_healing.py`
**Ref:** [DES §8]
- [x] `test_parse_json_success_first_attempt` — valid JSON on first call, `model_call_fn` never called
- [x] `test_parse_json_success_second_attempt` — first invalid, second valid; `model_call_fn` called once
- [x] `test_parse_json_circuit_breaker_trips` — all 3 repair attempts fail → `RuntimeError` raised
- [x] `test_circuit_breaker_exact_retry_count` — assert `model_call_fn` called exactly `max_retries` times before trip
- [x] `test_distill_local_uses_circuit_breaker` — mock Ollama to return invalid JSON 3 times, assert `RuntimeError` propagates from `_distill_local()`

---

## BLOCK D — Scoped Epistemic Scrubber

### Task D.1 — Add `source_type` column migration to `migrate_db.py`
**Ref:** [REQ-S6-05]
- [x] Add migration step 7 to `migrate_database()`:
  ```sql
  ALTER TABLE distilled_memory ADD COLUMN source_type TEXT DEFAULT 'external';
  ```
- [x] Wrap in `try/except sqlite3.OperationalError` for idempotency
- [x] Log outcome at INFO level

### Task D.2 — Update `archive_log()` in `safety_engine.py`
**Ref:** [REQ-S6-05]
- [x] Add `source_type: str = "external"` parameter
- [x] Validate `source_type` ∈ `{"internal", "external"}` — raise `ValueError` otherwise
- [x] `if source_type == "internal"`: skip `distill_safety()`, use `{"scrubbed_log": raw_log, "facts": []}` directly
- [x] `if source_type == "external"`: call `distill_safety()` as before
- [x] Both paths compute embedding and write to `distilled_memory` and `vec_passages`
- [x] Include `source_type` in `INSERT INTO distilled_memory` statement
- [x] Log mode at `DEBUG` level: `"Archiving %s content for source_id=%s"`

### Task D.3 — Tests for scoped scrubber (add to `tests/test_self_healing.py`)
**Ref:** [REQ-S6-05]
- [x] `test_archive_internal_skips_distillation` — `source_type="internal"` → `distill_safety()` mock NOT called
- [x] `test_archive_external_calls_distillation` — `source_type="external"` → `distill_safety()` mock IS called
- [x] `test_archive_invalid_source_type` — raises `ValueError`
- [x] `test_archive_internal_still_embeds` — even for internal, `_get_embedding()` IS called (embedding always runs)
- [x] `test_source_type_stored_in_db` — verify `distilled_memory.source_type` column is written correctly

---

## BLOCK E — Acceptance Gate

### Task E.1 — Full test suite passes
- [x] `pytest tests/ -v` exits 0 with all existing 28 tests + new Sprint 6 tests passing
- [x] Count target: ≥ 58 tests total (28 existing + ~30 new)

### Task E.2 — Security audit
- [x] `grep -r "/home/alexey" openclaw_skills/` → zero source matches
- [x] `grep -rn "cloud" openclaw_skills/router.py` — confirm cloud is only called in the `not is_sensitive` branch
- [x] Verify `approve_kb_proposal()` cannot be reached without HITL token (code review by Navigator)
- [x] Confirm `parse_json_with_retry()` has no silent fallback path (no bare `except` returning degraded dict)

### Task E.3 — Update documentation
- [x] Update `docs/2026-03-27__12-50_current_state.md` §3 with Sprint 6 summary
- [x] Update §7 (Known Issues): GAP-03 still open, no new gaps introduced
- [x] Update §9 Roadmap: mark Phase 2 items ✅ Complete
- [x] Update `_Development/OpenClaw/2026-03-27_backlog.md` to mark Sprint 6 complete, Sprint 7 next

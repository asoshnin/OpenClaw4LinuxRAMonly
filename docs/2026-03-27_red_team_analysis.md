# Red Team Code Analysis — OpenClaw Agentic Factory
**Date:** 2026-03-27  
**Scope:** `openclaw_skills/` canonical layer only  
**Method:** Line-by-line cross-reference of actual source vs current_state.md documentation  
**Verdict:** See §6

---

## FINDINGS KEY
- ✅ **CONFIRMED** — Documented and matches code
- ⚠️ **DELTA** — Underdocumented, divergent, or surprising behavior found in code
- 🔴 **VULN** — Security risk identified
- 📎 **NOTE** — Non-critical observation

---

## File 1: `librarian_ctl.py`

### Imports
```
os, sys, argparse, sqlite3, json, yaml, datetime
```
⚠️ **DELTA-01 — `yaml` and `json` imported but never used**  
`import yaml` and `import json` appear at the top of `librarian_ctl.py`. Neither module is called anywhere in the file (the registry output is built via f-strings, not `yaml.dump()`). These are dead imports — harmless, but undocumented and potentially confusing for maintainers.

### `validate_path()`
✅ Confirmed — matches documented spec exactly. `os.path.realpath()` used, `PermissionError` raised on breach.

### `init_db()`
✅ Confirmed — schema matches `[DES-03]`, WAL mode + synchronous=NORMAL both present.

📎 **NOTE-01 — `PRAGMA synchronous=NORMAL` not in any spec doc**  
`PRAGMA synchronous=NORMAL;` is set alongside WAL mode. This is a correct and beneficial pairing (WAL works best with NORMAL sync), but it is **not mentioned in any sprint design doc or the current_state.md**. Not a security risk, but should be documented.

### `bootstrap_factory()`
✅ Confirmed — seeds `kimi-orch-01`, `lib-keeper-01`, `factory-core` with `INSERT OR IGNORE`.

### `generate_registry()`
✅ Confirmed — atomic write via `.tmp` + `os.replace()`.

⚠️ **DELTA-02 — Both `db_path` AND `output_md_path` pass through `validate_path()`**  
The documentation notes the Airlock is enforced on the DB path. Correctly, the `output_md_path` is also validated. This is good security hygiene but was not explicitly documented in current_state.md (§3.1.4 only mentions db_path validation).

### CLI
✅ Three commands: `init`, `bootstrap`, `refresh-registry`. All documented.

---

## File 2: `migrate_db.py`

### `migrate_database()`
✅ Confirmed — three operations: `ALTER TABLE`, `CREATE TABLE IF NOT EXISTS pipeline_agents`, `UPDATE agents SET is_system`.

⚠️ **DELTA-03 — `migrate_db.py` has NO `validate_path()` call on `db_path` when the OperationalError path is taken**  
On line 26, if `ALTER TABLE` raises an error that is NOT "duplicate column name", the code prints an error message and **continues execution** to the next `cursor.execute()` rather than aborting. This means a partial migration can silently proceed in an unexpected error condition. Low exploitability, but undocumented behavior.

📎 **NOTE-02 — `migrate_database()` has no return value**  
The function returns `None` implicitly. The current_state.md doesn't acknowledge this — callers have no programmatic way to check migration success other than checking for absence of exceptions. Consider returning a migration report dict in a future sprint.

---

## File 3: `vector_archive.py`

### `init_vector_db()`
✅ Confirmed — `sqlite_vec.load(conn)` pattern, `vec_passages` FLOAT[768], `distilled_memory` schema.

📎 **NOTE-03 — `enable_load_extension(True)` is a persistent connection setting**  
`conn.enable_load_extension(True)` must be called before `sqlite_vec.load(conn)`. This is correct. However, it is a **security-sensitive SQLite flag** that allows loading arbitrary shared libraries. It is set to `True` but never reset to `False` afterward. In the current sandboxed usage this is fine, but worth noting in documentation.

### `find_faint_paths()`
✅ Confirmed — KNN query with `AND k = ?`, JOIN with `distilled_memory`, `content_json` parsed to dict.

⚠️ **DELTA-04 — `json` is imported inside the function body (lazy import)**  
`import json` appears at line 53 inside `find_faint_paths()`, not at the module level. This is unusual. It works correctly but diverges from Python convention and was not documented. Compare: `safety_engine.py` imports `json` at module level. Inconsistency.

⚠️ **DELTA-05 — `SafetyDistillationEngine` is imported INSIDE `find_faint_paths()` on every call**  
The engine is instantiated fresh on every search call. For single calls this is fine. For batch operations (e.g., 100 semantic searches), this creates 100 new engine objects and makes 100 fresh Ollama connections. Not a correctness bug, but a performance smell that was not documented (no caching/singleton pattern).

📎 **NOTE-04 — `except Exception: pass` on `json.loads()` silently swallows parse errors**  
Lines 87-90: if `content_json` cannot be parsed as JSON, the raw string is passed through unchanged. This is a documented fallback, but "pass" is silent — callers would receive a string instead of a dict for that field without any indication. A log warning would be safer.

---

## File 4: `safety_engine.py`

### Module-level `import sqlite_vec`
🔴 **VULN-01 — Hard import at module level with no error handling**  
`import sqlite_vec` (line 11) will raise an `ImportError` and crash the entire module if `sqlite-vec` is not installed.  
**Impact:** Importing `SafetyDistillationEngine` from `safety_engine.py` — even for a simple local distillation that never touches the vector DB — will fail entirely if `sqlite-vec` is not installed.  
**Documented?** No. current_state.md §7 (GAP-06) mentions this risk but the fix was not applied.  
**Recommended fix:**
```python
try:
    import sqlite_vec
    SQLITE_VEC_AVAILABLE = True
except ImportError:
    SQLITE_VEC_AVAILABLE = False
```
Then guard `archive_log()` with a check.

### `truncate_for_distillation()`
✅ Confirmed — middle-truncate at 12,000 chars, head 6,000 + tail 6,000, inserts marker.

### `_get_embedding()`
✅ Confirmed — POST to `/api/embeddings`, `timeout=30.0`, returns `result.get("embedding", [])`.

⚠️ **DELTA-06 — Empty list `[]` returned silently on missing "embedding" key**  
If the Ollama response JSON does not contain an `"embedding"` key (e.g., model error, wrong model name), `result.get("embedding", [])` returns an empty list `[]`. This empty vector would then be serialized and passed to `archive_log()`, which would attempt to insert `[]` into `vec_passages`. The `sqlite-vec` extension may silently store a 0-dim vector or raise a dimension mismatch error. This error path is not documented.

### `_distill_local()`
✅ Confirmed — truncation applied first, `"format": "json"` enforced, double-parse with fallback.

📎 **NOTE-05 — `_distill_local` can return `None` implicitly on Ollama success**  
If `urllib.request.urlopen()` succeeds but the response body is malformed such that neither the `try` nor `except json.JSONDecodeError` branch executes (theoretically impossible with current control flow, but worth noting), the function returns `None` implicitly. The annotated return type is `dict`.

### `_distill_cloud()`
✅ Confirmed — truncation applied, `GEMINI_API_KEY` env var required, `response_mime_type: application/json` set.

⚠️ **DELTA-07 — Cloud distillation failure returns a dict, not an exception**  
On line 129-130, if the Gemini response cannot be parsed (key error, JSONDecodeError), the function **returns** `{"facts": [], "scrubbed_log": "Error parsing cloud model output."}` rather than raising an exception. This means `archive_log()` will silently archive an empty/error record into `distilled_memory` and the vector DB — with no indication that the distillation failed. This behavior is undocumented.

### `distill_safety()`
✅ Confirmed — routes `is_sensitive=True` to local, `False` to cloud.

### `archive_log()`
✅ Confirmed — distill → embed → insert `distilled_memory` → insert `vec_passages`, returns `new_id`.

⚠️ **DELTA-08 — `archive_log` does NOT call `init_vector_db()` first**  
`archive_log()` connects to the DB and inserts directly into `distilled_memory` and `vec_passages`. If `init_vector_db()` has never been called (e.g., on a fresh DB that has only had `init_db()` run), these tables do not exist and the insert will raise `sqlite3.OperationalError: no such table`. The initialization sequence is correct in the runbook, but this implicit dependency is undocumented as a hard requirement.

---

## File 5: `architect_tools.py`

### `TK_AVAILABLE` guard
✅ Confirmed — graceful `ImportError` fallback to terminal prompt. This is an improvement over earlier versions and is documented.

### `WORKSPACE_DIR` / `TOKEN_FILE`
✅ Confirmed — hardcoded strings, validated before use.

### `validate_path()`
✅ Confirmed — identical logic to `librarian_ctl.py`.

🔴 **VULN-02 — Airlock boundary is checked with `startswith()`, vulnerable to path prefix collision**  
Both `librarian_ctl.py` and `architect_tools.py` use:
```python
if not target_abs.startswith(base_dir):
```
where `base_dir = os.path.realpath("/home/alexey/openclaw-inbox/workspace/")`.  
The trailing slash in `workspace/` **prevents** the classic collision attack (e.g., `/home/alexey/openclaw-inbox/workspace_evil/` would _not_ pass because `startswith` requires the full `workspace/` prefix). This is correctly implemented.  
✅ **No actual vulnerability** — the trailing slash is deliberate protection. Documenting as confirmed-safe for future auditors.

### `search_factory()`
✅ Confirmed — parameterized queries only, no SQL injection vector. `filter_val` is passed as a bound parameter `?`, never string-formatted into the query.

⚠️ **DELTA-09 — `search_factory('audit_logs', ...)` filters by BOTH `agent_id` and `pipeline_id` with OR**  
Line 62: `WHERE agent_id = ? OR pipeline_id = ?` passes `filter_val` for BOTH columns. This means `filter_val='kimi-orch-01'` would return all audit_logs records where either `agent_id='kimi-orch-01'` OR `pipeline_id='kimi-orch-01'`. This double-use of a single filter_val is undocumented — callers may not expect this broad match behavior.

### `generate_token()`
✅ Confirmed — UUID4, `O_WRONLY | O_CREAT | O_TRUNC`, mode `0o600`.

📎 **NOTE-06 — `generate_token()` does not check if a token file already exists**  
If a token was generated but never consumed (e.g., Navigator ran `gen-token` twice), the second call will silently overwrite the first token (`O_TRUNC` flag). The old token is then permanently invalidated. This is actually correct security behavior (no stale token accumulation), but is undocumented.

### `validate_token()`
✅ Confirmed — reads, **deletes file** (`os.remove`) before comparison, returns boolean.

⚠️ **DELTA-10 — `validate_token()` returns `False` (not raises) if TOKEN_FILE doesn't exist**  
Line 98: `if not os.path.exists(TOKEN_FILE): return False`. This means calling `deploy_pipeline` with any token when no token file exists prints no special error — the caller just gets `PermissionError("Invalid or expired HITL token. Deployment aborted.")` which is correct, but the root cause (no token file) is not surfaced to the operator. A more informative error would help debugging.

### `deploy_pipeline()`
✅ Confirmed — validates token first, then path, inserts pipeline + audit log.

📎 **NOTE-07 — `deploy_pipeline` does NOT check for pipeline_id collision**  
An `INSERT INTO pipelines` without `OR IGNORE` will raise `sqlite3.IntegrityError: UNIQUE constraint failed: pipelines.pipeline_id` if the `pipeline_id` already exists. This exception propagates to the CLI handler and is printed. This is acceptable behavior (fail-loud on duplicate), but it means the HITL token is **burned** even on a duplicate-ID error — the deployment fails but the token has already been consumed. This is documented in neither the spec nor the current_state.md.

### `request_ui_approval()`
✅ Confirmed — GUI or terminal fallback.

⚠️ **DELTA-11 — Terminal fallback accepts "yes" and "y" but not "YES" or "Y"**  
Line 146: `response = input(...).lower().strip()` — `.lower()` is applied, so "YES" → "yes" → accepted. ✅ Actually correct. No divergence.

### `deploy_pipeline_with_ui()`
✅ Confirmed — generates token internally, agent never exposed to token value.

### `teardown_pipeline()`
✅ Confirmed — Check-Before-Kill algorithm, `is_system` guard, shared-reference guard, physical file deletion inside `validate_path()`.

⚠️ **DELTA-12 — `teardown_pipeline` swallows ALL exceptions during file deletion**  
Lines 207-215: `except Exception: deleted_agents.append(f"{agent_id} (db only, file err)")` — any exception during `validate_path()` or `os.remove()` is silently caught and reported only via the summary string. This includes `PermissionError` on the file itself (e.g., file is read-only). The DB record is still deleted. The function returns success. This silent swallow is undocumented.

📎 **NOTE-08 — `teardown_pipeline` inserts into `audit_logs` EVEN if the pipeline did not exist**  
If `DELETE FROM pipelines WHERE pipeline_id = ?` matches zero rows (pipeline doesn't exist), the code still writes a `TEARDOWN` audit log entry. This could create orphan audit records for non-existent pipelines. Undocumented.

### CLI
✅ Three commands: `gen-token`, `deploy`, `teardown`. All documented.

---

## §6 Summary Table

| ID | File | Type | Severity | Issue |
|---|---|---|---|---|
| DELTA-01 | `librarian_ctl.py` | Dead import | 🟢 Low | `import yaml` and `import json` unused |
| NOTE-01 | `librarian_ctl.py` | Undocumented | 🟢 Low | `PRAGMA synchronous=NORMAL` not in any spec |
| DELTA-02 | `librarian_ctl.py` | Underdocumented | 🟢 Low | `output_md_path` also Airlock-validated (good, but unmentioned) |
| DELTA-03 | `migrate_db.py` | Logic | 🟡 Medium | Partial migration continues silently on unexpected OperationalError |
| NOTE-02 | `migrate_db.py` | Design | 🟢 Low | No return value — callers cannot check migration success programmatically |
| NOTE-03 | `vector_archive.py` | Security hygiene | 🟢 Low | `enable_load_extension(True)` never reset to False |
| DELTA-04 | `vector_archive.py` | Style | 🟢 Low | `import json` inside function body (lazy, inconsistent) |
| DELTA-05 | `vector_archive.py` | Performance | 🟢 Low | `SafetyDistillationEngine` instantiated fresh on every search call |
| NOTE-04 | `vector_archive.py` | Silent failure | 🟡 Medium | `json.loads()` error silently passes raw string through |
| **VULN-01** | `safety_engine.py` | **Import crash** | 🔴 **High** | `import sqlite_vec` at module level — crashes whole module if not installed |
| DELTA-06 | `safety_engine.py` | Data integrity | 🟡 Medium | Empty `[]` embedding silently written to DB on Ollama key-miss |
| NOTE-05 | `safety_engine.py` | Type annotation | 🟢 Low | `_distill_local` implicitly returns `None` on impossible control-flow path |
| DELTA-07 | `safety_engine.py` | Silent failure | 🟡 Medium | Cloud parse failure returns error-dict silently instead of raising |
| DELTA-08 | `safety_engine.py` | Implicit dependency | 🟡 Medium | `archive_log()` silently fails if `init_vector_db()` was never called |
| VULN-02 | `architect_tools.py` | Security (confirmed safe) | ✅ N/A | `startswith()` with trailing slash — correctly prevents prefix collision |
| DELTA-09 | `architect_tools.py` | Underdocumented | 🟢 Low | `search_factory('audit')` OR-matches both agent_id and pipeline_id |
| NOTE-06 | `architect_tools.py` | Behavior | 🟢 Low | Duplicate `gen-token` silently overwrites previous token (correct behavior) |
| DELTA-10 | `architect_tools.py` | UX | 🟢 Low | No-token-file condition returns opaque error to operator |
| NOTE-07 | `architect_tools.py` | Token consumption | 🟡 Medium | HITL token burned even when deployment fails due to duplicate pipeline_id |
| DELTA-12 | `architect_tools.py` | Silent failure | 🟡 Medium | File deletion exceptions silently caught in `teardown_pipeline` |
| NOTE-08 | `architect_tools.py` | Data integrity | 🟢 Low | TEARDOWN audit log written even for non-existent pipeline |

---

## §7 Verdict

**No critical security vulnerabilities were found that can be exploited externally.**

The Airlock (`validate_path`), Burn-on-Read token, and GUI HITL gate all behave precisely as designed. The `startswith()` check is correctly implemented with a trailing slash.

**One high-severity operational risk (VULN-01) was confirmed:**  
`import sqlite_vec` at module level in `safety_engine.py` will crash the module on import if the package is not installed — making **all** distillation and archival functionality unavailable even when not using vector operations.

**Five medium-severity silent failures were identified** (DELTA-03, DELTA-06, DELTA-07, DELTA-08, NOTE-07) where errors are swallowed or masked, making debugging difficult without DB-level inspection.

**Recommended immediate fix (VULN-01):**
```python
# safety_engine.py — replace line 11
try:
    import sqlite_vec
    _SQLITE_VEC_AVAILABLE = True
except ImportError:
    _SQLITE_VEC_AVAILABLE = False

# In archive_log():
if not _SQLITE_VEC_AVAILABLE:
    raise RuntimeError("sqlite-vec not installed. Run: pip install sqlite-vec")
conn.enable_load_extension(True)
sqlite_vec.load(conn)
```

# Feature Review V2 — OpenClaw Agentic Factory
**Date:** 2026-03-27 | **Author:** Epistemic Audit System  
**Status:** Read-Only Cross-Reference Audit

---

## Preamble: Architectural Duality

> [!IMPORTANT]
> The repository contains **two distinct codebases** that must be clearly distinguished in this audit:
> - **`src/`** — Legacy Letta.ai implementation (macOS-era). **STRICTLY ISOLATED — do not import or extend.**
> - **`openclaw_skills/`** — The canonical OpenClaw implementation for Linux (x86_64). This is the live, authoritative source of truth.

This audit cross-references both layers against the Phase 1 & 2 feature baseline and flags gaps accordingly.

---

## Part 1: Feature Mapping

### Feature 1 — Dynamic LLM Router (`HITLRequiredException` + Airlock Logic)

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `HITLRequiredException` | ✅ **IMPLEMENTED (src/)** | `src/routing/dynamic_router.py:3` | Custom exception class raised on sensitive-cloud routing conflict |
| `DynamicLLMRouter.route_task()` | ✅ **IMPLEMENTED (src/)** | `src/routing/dynamic_router.py:12` | Routes based on `is_sensitive` + `min_model_tier`; enforces HALT on `is_sensitive=True` + `min_model_tier='cloud'` |
| **Airlock path validation** | ✅ **IMPLEMENTED (openclaw_skills/)** | `openclaw_skills/librarian/librarian_ctl.py:14` | `validate_path()` using `os.path.realpath` to enforce `/home/alexey/openclaw-inbox/workspace/` boundary |
| **Hybrid sensitivity router** | ✅ **IMPLEMENTED (openclaw_skills/)** | `openclaw_skills/librarian/safety_engine.py:134` | `SafetyDistillationEngine.distill_safety()` routes `is_sensitive=True` → local Ollama; `False` → Gemini cloud |

> [!NOTE]
> The `HITLRequiredException` in `src/routing/dynamic_router.py` is the **legacy Letta implementation** of the concept. The OpenClaw equivalent is the GUI popup gate in the now-deleted `architect_tools.py` (Sprint 2) and the sensitivity routing in `safety_engine.py`.

---

### Feature 2 — Configuration Engine (`config.py` Dynamic Path Resolution)

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `config.py` dynamic `BASE_DIR` | ✅ **IMPLEMENTED (src/)** | `src/config.py:5` | Uses `Path(__file__).resolve().parent.parent` for repo-relative resolution |
| `WORKSPACE_DIR` path constant | ✅ Partial | `src/config.py:7` | Defined but **not consumed** by OpenClaw skills (they hardcode the path directly) |
| `FACTORY_DB_PATH` constant | ✅ Partial | `src/config.py:10` | Defined but **not consumed** by OpenClaw skills |
| OpenClaw hardcoded path | ⚠️ **GAP** | `openclaw_skills/librarian/librarian_ctl.py:16` | `WORKSPACE_DIR` is hardcoded as string literal `"/home/alexey/openclaw-inbox/workspace/"`. Not importing from `config.py`. |

> [!WARNING]
> **Architecture Gap:** `openclaw_skills/` does not import from `src/config.py` (correctly, due to isolation boundary). However, this means the OpenClaw layer has no centralized config engine of its own. The absolute path is duplicated across `librarian_ctl.py` and `architect_tools.py` (now deleted). A dedicated `openclaw_skills/config.py` is missing.

---

### Feature 3 — Librarian / Database Setup

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `init_db()` — SQLite initialization | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/librarian_ctl.py:22` | Full schema creation: `agents`, `pipelines`, `audit_logs` |
| `PRAGMA journal_mode=WAL;` | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/librarian_ctl.py:30` | WAL mode + `PRAGMA synchronous=NORMAL;` both enforced |
| `sqlite-vec` integration | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/vector_archive.py:8, 24-25` | `import sqlite_vec` + `sqlite_vec.load(conn)` pattern on every connection |
| `vec_passages` virtual table | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/vector_archive.py:30-35` | `FLOAT[768]` via `vec0` — aligned with `nomic-embed-text` output dimensions |
| `distilled_memory` table | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/vector_archive.py:38-46` | Full schema with `raw_source_id`, `content_json JSON`, `is_sensitive`, `timestamp` |
| `bootstrap_factory()` seeding | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/librarian_ctl.py:71` | Seeds `kimi-orch-01`, `lib-keeper-01`, and `factory-core` with `INSERT OR IGNORE` |
| `generate_registry()` atomic write | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/librarian_ctl.py:97` | Write to `.tmp` then `os.replace()` for crash-safe atomic swap |
| `pipeline_agents` relation table | ✅ **IMPLEMENTED (migration)** | `openclaw_skills/librarian/migrate_db.py:34-44` | Many-to-many mapping with `ON DELETE CASCADE` FK constraints |
| `is_system` column on `agents` | ✅ **IMPLEMENTED (migration)** | `openclaw_skills/librarian/migrate_db.py:24-32` | `ALTER TABLE` with duplicate-column guard via `try/except sqlite3.OperationalError` |
| CLI interface | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/librarian_ctl.py:136-164` | `init`, `bootstrap`, `refresh-registry` subcommands via `argparse` |

---

### Feature 4 — AgenticPromptArchitect (Architect Tools)

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `validate_path()` (Architect copy) | ❌ **MISSING — FILE DELETED** | `openclaw_skills/architect/architect_tools.py` | **File was deleted**. All Architect tool functionality including path validation, `search_factory`, `get_agent_persona`, `generate_token`, `validate_token`, `deploy_pipeline`, `request_ui_approval`, `deploy_pipeline_with_ui` is **lost**. |
| `search_factory()` discovery tool | ❌ **MISSING — FILE DELETED** | (was `architect_tools.py`) | — |
| `get_agent_persona()` | ❌ **MISSING — FILE DELETED** | (was `architect_tools.py`) | — |
| `deploy_pipeline_with_ui()` (UI HITL) | ❌ **MISSING — FILE DELETED** | (was `architect_tools.py`) | — |
| `SKILL.md` agent definition | ✅ **INTACT** | `openclaw_skills/architect/SKILL.md` | Instructs the agent to use `deploy_pipeline_with_ui` — but the tool no longer exists. |
| Legacy `deploy_new_agent()` (Letta) | ⚠️ **ISOLATED/LEGACY** | `src/tools/deploy_agent_tool.py:15` | Letta-based deployment via REST API to `localhost:8283`. Not part of OpenClaw canonical layer. |

> [!CAUTION]
> **Critical Gap: `architect_tools.py` was deleted.** This is the most severe gap in Phase 2. The SKILL.md references `deploy_pipeline_with_ui` which no longer exists on disk. The Architect agent persona (`kimi-orch-01.md`) and SKILL.md are orphaned. **Immediate reconstruction is required before any deployment operations can proceed.**

---

### Feature 5 — Secure Teardown Tool

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `teardown_pipeline()` | ❌ **MISSING — FILE DELETED** | (was `openclaw_skills/architect/architect_tools.py`) | The entire Garbage Collection tool with Check-Before-Kill logic, `is_system` guard, shared-reference check, physical `.md` file deletion, and audit logging is **lost with the deleted file**. |
| `pipeline_agents` table (dependency) | ✅ INTACT | `openclaw_skills/librarian/migrate_db.py:34-44` | The schema backing teardown is intact; only the teardown logic is missing. |
| CLI hook (`teardown` subcommand) | ❌ **MISSING — FILE DELETED** | (was `architect_tools.py __main__`) | — |

---

### Feature 6 — Ollama Integration (Execution Bridge)

| Component | Status | Location | Implementation Detail |
|---|---|---|---|
| `_get_embedding()` via Ollama | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/safety_engine.py:40` | HTTP POST to `http://127.0.0.1:11434/api/embeddings` with `nomic-embed-text` model, `timeout=30.0` |
| `_distill_local()` via Ollama | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/safety_engine.py:57` | HTTP POST to `/api/generate` with `nn-tsuzu/lfm2.5-1.2b-instruct`; `"format": "json"` enforced; `timeout=30.0` |
| `_distill_cloud()` via Gemini | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/safety_engine.py:95` | HTTP POST to Gemini `generateContent` REST endpoint; `response_mime_type: application/json`; `timeout=30.0` |
| `truncate_for_distillation()` (guardrail) | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/safety_engine.py:20` | Middle-truncate strategy: head 6000 + tail 6000 chars, injected marker; called at entry of both `_distill_local` and `_distill_cloud` |
| `archive_log()` end-to-end pipeline | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/safety_engine.py:140` | Full distill → embed → write to `distilled_memory` + `vec_passages` pipeline |
| `find_faint_paths()` KNN search | ✅ **IMPLEMENTED** | `openclaw_skills/librarian/vector_archive.py:51` | SQLite-vec KNN query with `WHERE embedding MATCH ? AND k = ?` compliant syntax |

---

## Part 2: V2 Automated Test Plan

### Test Group 1: Dynamic LLM Router
**Module:** `src/routing/dynamic_router.py` (legacy reference only)

```
test_router_blocks_sensitive_cloud_routing
  - Arrange: DynamicLLMRouter(), task_id=uuid4(), is_sensitive=True, min_model_tier='cloud'
  - Assert: raises HITLRequiredException
  - Assert: exception message contains "[SYS-HALT: HITL REQUIRED"

test_router_allows_sensitive_local_routing
  - Assert: returns local_model string, does NOT raise

test_router_allows_non_sensitive_cloud_routing
  - Assert: returns cloud_model string, does NOT raise

test_router_default_fallback_is_local
  - Arrange: min_model_tier='local'
  - Assert: returns self.local_model
```

---

### Test Group 2: Configuration Engine
**Module:** `src/config.py`

```
test_config_paths_are_absolute
  - Assert: all exported Path objects are absolute (path.is_absolute() == True)

test_config_resolves_relative_to_repo_root
  - Assert: FACTORY_DB_PATH is inside BASE_DIR / "database"
  - Assert: WORKSPACE_DIR is inside BASE_DIR / "workspace"

test_config_no_hardcoded_usernames
  - Assert: str(FACTORY_DB_PATH) does not contain "/home/" (portability check)
```

> [!NOTE]
> For OpenClaw layer: A test must be written once a dedicated `openclaw_skills/config.py` is created. Until then, test the hardcoded path constant in `librarian_ctl.py` with a monkeypatch fixture.

---

### Test Group 3: Librarian / Database Engine
**Module:** `openclaw_skills/librarian/librarian_ctl.py`, `vector_archive.py`, `migrate_db.py`

```
test_validate_path_blocks_traversal_attack
  - Arrange: target_path = "/home/alexey/openclaw-inbox/workspace/../../../etc/passwd"
  - Assert: raises PermissionError with "Airlock Breach"

test_validate_path_accepts_valid_workspace_path
  - Arrange: target_path within WORKSPACE_DIR
  - Assert: returns os.path.realpath of path (no exception)

test_init_db_creates_all_tables (tmp_path fixture)
  - Call init_db(str(tmp_db))
  - Query sqlite_master for tables: agents, pipelines, audit_logs
  - Assert: all three tables exist

test_init_db_enforces_wal_mode
  - Call init_db(); SELECT pragma_journal_mode FROM pragma_journal_mode()
  - Assert: result == "wal"

test_bootstrap_seeds_core_agents
  - Call init_db() then bootstrap_factory()
  - SELECT agent_id FROM agents
  - Assert: 'kimi-orch-01' and 'lib-keeper-01' in results

test_generate_registry_is_atomic (tmp_path fixture)
  - Call generate_registry(); assert .tmp file does NOT exist after completion
  - Assert: output file exists and contains YAML frontmatter block

test_init_vector_db_creates_vec_passages (requires sqlite-vec installed)
  - Call init_vector_db()
  - Query: SELECT name FROM sqlite_master WHERE type='table' AND name='vec_passages'
  - Assert: row returned

test_migrate_db_adds_is_system_column
  - Call init_db() then migrate_database()
  - PRAGMA table_info(agents)
  - Assert: 'is_system' column present

test_migrate_db_is_idempotent
  - Call migrate_database() twice
  - Assert: no exception raised on second call (duplicate column guard works)

test_migrate_db_creates_pipeline_agents_table
  - Assert: pipeline_agents table exists after migration

test_migrate_db_marks_core_agents_system
  - Call bootstrap + migrate
  - SELECT is_system FROM agents WHERE agent_id='kimi-orch-01'
  - Assert: is_system == 1
```

---

### Test Group 4: Architect Tools
**Module:** `openclaw_skills/architect/architect_tools.py` (**MUST BE RECONSTRUCTED FIRST**)

> [!CAUTION]
> All tests in this group are **blocked** until `architect_tools.py` is restored. The below is the target test contract for the reconstructed file.

```
test_search_factory_returns_agents
  - Arrange: bootstrapped factory.db
  - Call: search_factory(db_path, 'agents')
  - Assert: list contains dicts with 'agent_id' key

test_search_factory_with_filter
  - Call: search_factory(db_path, 'agents', filter_val='kimi-orch-01')
  - Assert: exactly one result

test_search_factory_rejects_invalid_query_type
  - Assert: raises ValueError for query_type='invalid'

test_search_factory_blocks_path_traversal
  - Call with db_path outside workspace
  - Assert: raises PermissionError

test_deploy_pipeline_with_fake_token
  - Arrange: generate_token() stores a real token
  - Call: deploy_pipeline(db_path, ..., approval_token="wrong-token")
  - Assert: raises PermissionError with "Invalid or expired HITL token"

test_deploy_pipeline_burns_token_on_read
  - Arrange: generate_token()
  - Call: deploy_pipeline(db_path, ..., approval_token=token)
  - Assert: TOKEN_FILE no longer exists on disk

test_generate_token_file_has_600_permissions
  - Call: generate_token()
  - Assert: os.stat(TOKEN_FILE).st_mode & 0o777 == 0o600
```

---

### Test Group 5: Secure Teardown Tool
**Module:** `openclaw_skills/architect/architect_tools.py` (**MUST BE RECONSTRUCTED FIRST**)

> [!CAUTION]
> All tests blocked until `architect_tools.py` is restored.

```
test_teardown_skips_system_agents
  - Arrange: migrate DB, set is_system=1 for kimi-orch-01
  - Create pipeline_agents record linking kimi-orch-01 to a test pipeline
  - Call: teardown_pipeline(db_path, test_pipeline_id)
  - Assert: kimi-orch-01 still present in agents table

test_teardown_skips_shared_agents
  - Arrange: agent referenced by TWO pipelines
  - Teardown pipeline #1
  - Assert: agent still in agents (shared reference preserved)

test_teardown_deletes_unprotected_agent
  - Arrange: non-system agent referenced by only one pipeline
  - Call: teardown_pipeline()
  - Assert: agent removed from agents table

test_teardown_removes_physical_file
  - Arrange: create {agent_id}.md in workspace
  - Call: teardown_pipeline()
  - Assert: file no longer exists

test_teardown_logs_audit_record
  - Call: teardown_pipeline()
  - SELECT * FROM audit_logs WHERE action='TEARDOWN'
  - Assert: row exists with correct pipeline_id

test_teardown_blocks_workspace_escape
  - Arrange: agent_id containing path traversal chars (e.g. "../../../etc/test")
  - Assert: validate_path raises PermissionError before os.remove
```

---

### Test Group 6: Ollama Integration (Safety Engine)
**Module:** `openclaw_skills/librarian/safety_engine.py`

```
test_truncate_short_text_passthrough
  - Input: text of length 100
  - Assert: output == input (no truncation)

test_truncate_long_text_preserves_head_and_tail
  - Input: "A" * 6000 + "B" * 3000 + "C" * 6000 (total 15000)
  - Assert: output starts with "A" * 6000
  - Assert: output ends with "C" * 6000
  - Assert: "[TRUNCATED FOR RESILIENCE]" in output

test_truncate_exact_limit_not_truncated
  - Input: "X" * 12000
  - Assert: output == input

test_get_embedding_raises_on_ollama_unreachable
  - Monkeypatch Ollama URL to non-responsive port
  - Assert: raises RuntimeError containing "Ollama API Error"

test_get_embedding_timeout_enforced
  - Monkeypatch urlopen to sleep > 30s
  - Assert: urllib.error.URLError raised within ~30s (use threading timeout)

test_distill_local_applies_truncation
  - Monkeypatch urlopen to capture payload
  - Call _distill_local with 15000-char string
  - Assert: captured prompt length <= 12000 + len(prompt_template) + len(TRUNCATED_MARKER)

test_distill_cloud_requires_api_key
  - Unset GEMINI_API_KEY environment variable
  - Assert: raises ValueError("GEMINI_API_KEY environment variable not set")

test_distill_safety_routes_sensitive_to_local
  - Monkeypatch both _distill_local and _distill_cloud
  - Call distill_safety(is_sensitive=True)
  - Assert: _distill_local called, _distill_cloud NOT called

test_distill_safety_routes_non_sensitive_to_cloud
  - Call distill_safety(is_sensitive=False)
  - Assert: _distill_cloud called, _distill_local NOT called

test_find_faint_paths_knn_syntax
  - Assert: the SQL query contains "AND k = ?" and NOT a trailing "LIMIT ?"
  - (Static code inspection via ast.parse or grep on source)
```

---

## Part 3: Summary & Priority Remediation Matrix

| Priority | Issue | Action Required |
|---|---|---|
| 🔴 **P0 - CRITICAL** | `architect_tools.py` deleted | Reconstruct immediately. All HITL, deployment, discovery, and teardown capabilities are offline. |
| 🔴 **P0 - CRITICAL** | `SKILL.md` references non-existent `deploy_pipeline_with_ui` | Will cause agent runtime failures. Resolved automatically when file is restored. |
| 🟠 **P1 - HIGH** | No centralized `openclaw_skills/config.py` | Hardcoded paths duplicated across multiple files. Risk of path drift. |
| 🟡 **P2 - MEDIUM** | `src/config.py` not consumed by OpenClaw layer | Config values redeclared as literals. Acceptable given isolation constraint, but should be documented. |
| 🟢 **P3 - LOW** | No `pytest` test files exist under `openclaw_skills/` | All test coverage is in `src/tests/` (legacy). OpenClaw layer has zero automated test coverage. |

---

*Audit conducted under Strict Isolation Boundary: `src/` legacy code read for reference only. No modifications made to any source files.*

# Sprint 7 — Obsidian Bidirectional Sync
## Requirements

**Sprint:** 7  
**Name:** Ecosystem & Integration — Obsidian Bidirectional Sync  
**Status:** Spec  
**Date:** 2026-03-27  

---

## Background

Phase 3 of the OpenClaw roadmap introduces Ecosystem & Integration. The first item is **Obsidian Bidirectional Sync**: the ability for OpenClaw agents to read notes from and write structured notes back into an Obsidian vault on the Navigator's Linux desktop (ThinkPad W540).

The Navigator is using the **Obsidian vault architecture** documented in gist `asoshnin/bc201f0a1fbb009e37004cdb913f09bb` — a RAG-native vault with Johnny.Decimal folder taxonomy:

```
00 - INBOX       → Raw captures, mobile dumps
10 - PROJECTS    → Active work with defined deadlines
20 - AREAS       → Ongoing domains (Health, Finance, Research)
30 - RESOURCES   → Evergreen reference material
40 - ARCHIVE     → Completed / deprecated (excluded from AI index)
90-99            → Meta, Templates, Dashboards, AI Logs
```

**Important constraint:** Obsidian has not yet been installed on the W540. This sprint includes a Linux installation block as a prerequisite.

---

## Integration Strategy

The integration channel is the **Obsidian Local REST API community plugin** (by coddingtonbear), served at `http://127.0.0.1:27123`. This approach:

- Guarantees atomic, plugin-managed writes (no race conditions from direct filesystem writes)
- Provides a clean `GET /vault/{path}` / `PUT /vault/{path}` / `POST /vault/` interface
- Supports reading note content, listing vault paths, and appending to notes
- Requires Obsidian to be running on the desktop — acceptable for the W540 always-on setup
- Zero new Python dependencies: uses `urllib.request` only (existing pattern)

**Direct filesystem writes are explicitly forbidden** in OpenClaw. All Obsidian writes must go through the Local REST API.

---

## User Stories

### US-7-01: Obsidian Linux Installation & Vault Bootstrap (Prerequisites)
> **As** the Navigator,  
> **I want** Obsidian installed on my W540 Linux desktop with the Local REST API plugin active and a minimal Johnny.Decimal vault structure initialized,  
> **So that** I can use it as a connected external knowledge layer for OpenClaw.

**Acceptance criteria:**
- [ ] Obsidian AppImage downloaded, made executable, and runnable on Linux x86_64
- [ ] A vault directory exists at `~/obsidian-vault/` (or `OBSIDIAN_VAULT_PATH` env var)
- [ ] The Johnny.Decimal folder structure (`00 - INBOX`, `10 - PROJECTS`, `20 - AREAS`, `30 - RESOURCES`, `40 - ARCHIVE`, `90 - TEMPLATES`, `99 - META`) is created
- [ ] The **Obsidian Local REST API** community plugin is installed and enabled
- [ ] The plugin serves on `http://127.0.0.1:27123` with a Navigator-set API key stored in `OBSIDIAN_API_KEY` env var
- [ ] A `setup.sh` step is added: verify Obsidian is running and plugin is reachable, warn if not (non-blocking)
- [ ] All steps are documented in a runbook section in `docs/`

### US-7-02: ObsidianBridge Python Module
> **As** an OpenClaw developer,  
> **I want** a `openclaw_skills/obsidian_bridge.py` module that wraps the Local REST API,  
> **So that** agents can read and write notes without knowing the HTTP details.

**Acceptance criteria:**
- [ ] `ObsidianBridge` class with configurable `base_url` and `api_key` (from env vars, never hardcoded)
- [ ] `base_url` MUST resolve to a loopback address (`localhost`, `127.0.0.1`, `::1`); any other host raises `ValueError` at construction time
- [ ] `api_key` is **required**: empty string raises `ValueError("OBSIDIAN_API_KEY is required")` at construction time
- [ ] `ping()` → returns `True` if Obsidian is reachable, `False` otherwise (no exceptions)
- [ ] `read_note(vault_path: str) -> str` → returns raw markdown content; raises `FileNotFoundError` if note does not exist
- [ ] `write_note(vault_path: str, content: str) -> None` → creates or overwrites note atomically via `PUT /vault/{path}`; raises `ValueError` on path traversal (`../`) or absolute paths
- [ ] `append_to_note(vault_path: str, content: str) -> None` → appends content via `PATCH /vault/{path}`; creates note via `PUT` if it does not exist (404 on PATCH)
- [ ] `list_notes(folder: str = "") -> list[str]` → returns list of note paths under the given folder prefix
- [ ] All calls go through `urllib.request` only — no `requests`, no `httpx`
- [ ] All calls time out at 10 seconds — no blocking Obsidian operations
- [ ] `OBSIDIAN_BASE_URL` env var (default: `http://127.0.0.1:27123`), `OBSIDIAN_API_KEY` env var (**required — no default**)
- [ ] `ObsidianBridge` is importable without Obsidian running (fails only on actual call)

### US-7-03: Agent Output → Obsidian INBOX
> **As** the Navigator,  
> **I want** agent task results to be optionally written to the Obsidian INBOX as structured notes,  
> **So that** I can review agent work in my primary tool (Obsidian) rather than database queries.

**Acceptance criteria:**
- [ ] `write_agent_result_to_vault(db_path, agent_id, task_text, result, vault_path=None, is_sensitive=False)` in `architect_tools.py`
- [ ] If `is_sensitive=True`: log `VAULT_WRITE_REFUSED_SENSITIVE` to audit_logs, return `None` — **never write sensitive content to the vault** (vault may sync to cloud via Obsidian sync plugins)
- [ ] `result` is truncated at 12,000 characters before being embedded in the note template (consistent with Context Guard)
- [ ] Default `vault_path`: `00 - INBOX/openclaw/{YYYY-MM-DD}_{agent_id}_{task_slug}.md`
- [ ] Note content follows a standard template (see Design for schema)
- [ ] If Obsidian is not running: log `WARNING`, write to `audit_logs` with `action='VAULT_WRITE_SKIPPED'`, return gracefully — **never raise on Obsidian unavailability**
- [ ] If Obsidian is running and write succeeds: log to `audit_logs` with `action='VAULT_WRITE'`
- [ ] `run_agent()` does NOT automatically write to vault — caller must opt-in via the new function

### US-7-04: Vault Note → OpenClaw Memory Archive
> **As** the Navigator,  
> **I want** to be able to ingest a specific Obsidian note into the OpenClaw vector archive (Faint Paths),  
> **So that** agents can retrieve knowledge I've curated in my vault during task execution.

**Acceptance criteria:**
- [ ] `ingest_vault_note(db_path, vault_path, is_sensitive=False)` in `librarian_ctl.py`
- [ ] Reads note content via `ObsidianBridge.read_note()`
- [ ] Passes content to `SafetyDistillationEngine.archive_log()` with `source_type="external"` (always scrubbed — vault notes are externally authored content carrying IPI risk equivalent to web-clipped content)
- [ ] The `is_sensitive` flag is **always propagated** to `archive_log()` — controls whether Ollama (local) or Gemini (cloud) performs distillation
- [ ] Rejects notes larger than 50,000 bytes before ingestion: raises `ValueError("Vault note exceeds VAULT_INGEST_MAX_BYTES")`
- [ ] On `archive_log()` exception: logs `action='VAULT_INGEST_FAILED'`, `rationale=f"Failed: {e}"`, then re-raises
- [ ] Returns `passage_id` on success; logs `action='VAULT_INGEST'` to audit_logs
- [ ] If Obsidian is not running: raises `RuntimeError` (ingestion must be explicit — no silent skip)
- [ ] CLI subcommand: `librarian_ctl.py ingest-vault-note <db_path> <vault_path> [--sensitive]`

### US-7-05: Vault Health-Check in Pre-flight
> **As** the Navigator,  
> **I want** `setup.sh` and the system startup to check whether Obsidian is reachable,  
> **So that** I am notified early if the Local REST API is down, without blocking any other operation.

**Acceptance criteria:**
- [ ] `check_obsidian_health()` function in `obsidian_bridge.py`; returns `{"status": "ok"|"down", "url": str}`
- [ ] `setup.sh` calls a Python health-check snippet: prints `[OBSIDIAN] ✓ reachable` or `[OBSIDIAN] ✗ not running — start Obsidian before ingesting vault notes`
- [ ] Health check uses a 3-second timeout; never blocks > 3s
- [ ] Result is non-fatal: all other setup steps proceed regardless

### US-7-06: Test Suite — Obsidian Integration
> **As** a developer,  
> **I want** all Obsidian integration code covered by mocked tests,  
> **So that** the suite passes without a live Obsidian instance (consistent with the existing 60-test pattern).

**Acceptance criteria:**
- [ ] `tests/test_obsidian_bridge.py` — covers `ping`, `read_note`, `write_note`, `append_to_note`, `list_notes`, health check
- [ ] `tests/conftest.py` updated: `obsidian_bridge` added to `sys.path`; `OBSIDIAN_BASE_URL` and `OBSIDIAN_API_KEY` patched in `isolated_workspace` fixture
- [ ] All HTTP calls mocked via `unittest.mock.patch("urllib.request.urlopen")`
- [ ] Test: `ObsidianBridge(api_key="")` → raises `ValueError` at construction
- [ ] Test: `ObsidianBridge(base_url="http://attacker.com:27123")` → raises `ValueError` (non-localhost)
- [ ] Test: Obsidian down → `ping()` returns `False`, no exception
- [ ] Test: `read_note` on missing path → `FileNotFoundError`
- [ ] Test: `write_note` sends correct `PUT` with bearer token header
- [ ] Test: `write_note("../evil.md", ...)` → raises `ValueError` (path traversal)
- [ ] Test: `write_note("/etc/passwd", ...)` → raises `ValueError` (absolute path)
- [ ] Test: `append_to_note` sends `PATCH` (not POST) with correct `\n\n{content}` body
- [ ] Test: `write_agent_result_to_vault` with `is_sensitive=True` → logs `VAULT_WRITE_REFUSED_SENSITIVE`, returns `None`
- [ ] Test: `write_agent_result_to_vault` when Obsidian is down → logs `VAULT_WRITE_SKIPPED`, returns `None`
- [ ] Test: `ingest_vault_note` when Obsidian is down → raises `RuntimeError`
- [ ] Test: `ingest_vault_note(..., is_sensitive=True)` → `archive_log` called with `is_sensitive=True`
- [ ] Test: `ingest_vault_note` when `archive_log` raises → logs `VAULT_INGEST_FAILED`, re-raises
- [ ] Test count target: ≥ 80 total tests passing

---

## Out of Scope for Sprint 7

- Mobile iOS sync (Remotely Save / Working Copy) — no mobile device on W540
- Obsidian Git plugin setup — vault backup via git is a separate concern
- Obsidian Copilot / Smart Connections plugin setup — those are Obsidian-internal AI tools
- Automatic background watching of vault for new notes — polling/inotify is Phase 4
- Writing directly to vault filesystem (bypassing the Local REST API) — **permanently forbidden**

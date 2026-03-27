# Sprint 7 — Obsidian Bidirectional Sync
## Tasks

**Sprint:** 7  
**Status:** Not Started  
**Date:** 2026-03-27  

Status legend: `- [ ]` todo · `- [/]` in progress · `- [x]` done · `- [!]` blocked

---

## Block A — Linux Installation & Vault Bootstrap (Manual + setup.sh)

### A1: Obsidian AppImage Installation Runbook
- [ ] Create `docs/linux_obsidian_setup.md` with step-by-step Linux installation guide
  - [ ] AppImage download using GitHub API + `curl` (NOT bare wget glob — glob does not expand in quoted strings):
    ```bash
    APPIMAGE_URL=$(curl -s https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest \
      | python3 -c "import sys,json; assets=json.load(sys.stdin)['assets']; print([a['browser_download_url'] for a in assets if a['name'].endswith('.AppImage') and 'arm' not in a['name']][0])")
    wget "$APPIMAGE_URL" -O ~/obsidian.AppImage && chmod +x ~/obsidian.AppImage
    ```
  - [ ] First-run vault creation at `~/obsidian-vault/` (or `OBSIDIAN_VAULT_PATH`)
  - [ ] Setting `OBSIDIAN_VAULT_PATH` in `~/.bashrc`
  - [ ] Local REST API plugin installation steps (Community Plugins → Browse → coddingtonbear)
  - [ ] API key generation and `OBSIDIAN_API_KEY` env var setup (**required** — plugin mandates it by default)
  - [ ] Port verification: `curl -s http://127.0.0.1:27123/vault/ -H "Authorization: Bearer $OBSIDIAN_API_KEY"`
  - [ ] Optional hardening: HTTPS on port 27124 (self-signed cert + ssl context in urllib) noted as alternative

### A2: Vault Structure Bootstrap Script
- [ ] Create `openclaw_skills/obsidian_vault_bootstrap.py`
  - [ ] `JOHNNY_DECIMAL_FOLDERS` constant list (all 8 folders per design)
  - [ ] `setup_vault_structure(vault_path: str) -> None` — `os.makedirs(..., exist_ok=True)` for each folder
  - [ ] CLI: `python3 obsidian_vault_bootstrap.py <vault_path>`
  - [ ] If `vault_path` doesn't exist: raise `FileNotFoundError` with clear message
  - [ ] Log each folder created at INFO, existing folders at DEBUG

### A3: `setup.sh` Updates
- [ ] Add `OBSIDIAN_VAULT_PATH` env var check at top of setup.sh
- [ ] Add vault directory bootstrap step (calls `obsidian_vault_bootstrap.py` if env var set)
- [ ] Add Obsidian health check step at end (non-blocking, calls inline Python via `|| true`)
- [ ] Document new env vars in setup.sh header comment

---

## Block B — `ObsidianBridge` Core Module

### B1: Module Setup
- [ ] Create `openclaw_skills/obsidian_bridge.py`
  - [ ] Module-level constants: `OBSIDIAN_BASE_URL`, `OBSIDIAN_API_KEY`, `OBSIDIAN_TIMEOUT = 10.0`
  - [ ] All values from env vars (never hardcoded)
  - [ ] `logger = logging.getLogger(__name__)`

### B2: `ObsidianBridge.__init__` and `_make_request`
- [ ] `__init__(self, base_url=None, api_key=None)`: defaults to module constants
  - [ ] **Localhost enforcement**: parse `base_url` with `urllib.parse.urlparse`; raise `ValueError` if `hostname not in ("localhost", "127.0.0.1", "::1")`
  - [ ] **API key enforcement**: raise `ValueError("OBSIDIAN_API_KEY is required")` if `api_key` is empty string or `None`
- [ ] `_make_request(self, method, path, body=None, content_type="text/markdown") -> tuple[int, str]`
  - [ ] Constructs `urllib.request.Request` with `Authorization: Bearer {api_key}` header
  - [ ] URL-encodes path segments via `urllib.parse.quote(vault_path, safe="/")` — uses `%20` for spaces, NOT `+` (deliberate RFC 3986 path encoding; comment required)
  - [ ] `urlopen(timeout=OBSIDIAN_TIMEOUT)` — raises on exception, returns `(status, body)`
  - [ ] On HTTP 4xx/5xx: raises `RuntimeError(f"Obsidian API {status}: {body[:200]}")`

### B3: `ping()`
- [ ] `GET /vault/` to Obsidian (NOT `GET /` — root endpoint reliability varies by plugin version)
- [ ] Returns `True` on any HTTP response, including 401 (plugin is running even if key is wrong)
- [ ] Returns `False` on any connection-level exception (URLError, timeout) — never propagates

### B4: `read_note(vault_path)`
- [ ] `GET /vault/{encoded_path}`
- [ ] Returns response body as `str`
- [ ] On 404: raises `FileNotFoundError(f"Note not found: {vault_path}")`
- [ ] On other errors: raises `RuntimeError`

### B5: `write_note(vault_path, content)`
- [ ] `PUT /vault/{encoded_path}`
- [ ] `Content-Type: text/markdown`
- [ ] Body: `content.encode("utf-8")`
- [ ] Vault path validation (both checks required):
  - [ ] `os.path.normpath(vault_path).startswith("..")` → raise `ValueError("vault_path traversal detected")`
  - [ ] `os.path.isabs(os.path.normpath(vault_path))` → raise `ValueError("vault_path must be relative")`
- [ ] Returns `None` on success

### B6: `append_to_note(vault_path, content)`
- [ ] `PATCH /vault/{encoded_path}` with `Content-Type: text/markdown` (**NOT** `POST ?append=true` — that endpoint does not exist)
- [ ] Body: `f"\n\n{content}".encode("utf-8")` (plugin appends body to end of file)
- [ ] If PATCH returns 404 (note doesn't exist): fall back to `write_note(vault_path, content)`
- [ ] On success: returns `None`

### B7: `list_notes(folder)`
- [ ] `GET /vault/{encoded_folder}/` (trailing slash = directory listing)
- [ ] Parse JSON response: **flat array of path strings** e.g. `["00 - INBOX/note.md", ...]` — NOT `{"files": [...], "folders": [...]}` (that schema is incorrect for the actual plugin)
- [ ] Returns flat list of file path strings
- [ ] Empty folder `""`: returns all vault notes
- [ ] On 404: returns empty list (missing folder is not an error)
- [ ] On other HTTP errors: raises `RuntimeError`

### B8: `check_obsidian_health()`
- [ ] Times `ping()` with `time.time()` before/after
- [ ] Returns `{"status": "ok", "url": self.base_url, "latency_ms": int}` or `{"status": "down", ...}`
- [ ] `latency_ms` = 0 when down

---

## Block C — Agent Output → Vault Note

### C1: `write_agent_result_to_vault()` in `architect_tools.py`
- [ ] Add function signature per design spec (including `is_sensitive=False` parameter)
- [ ] **Sensitivity gate (check first):** if `is_sensitive=True` → log `VAULT_WRITE_REFUSED_SENSITIVE` to audit_logs, return `None` immediately — do not instantiate bridge, do not render template
- [ ] Auto-generate `vault_path` when `None`: `f"00 - INBOX/openclaw/{date}_{agent_id}_{slug}.md"`
  - [ ] `slug`: `re.sub(r'[^a-z0-9_]', '', task_text[:40].lower().replace(' ', '_'))`
  - [ ] `date`: `datetime.now().strftime("%Y-%m-%d")`
- [ ] Build Markdown note from template (YAML frontmatter + body) per design §4.1
  - [ ] Truncate `result` at 12,000 characters before embedding (Context Guard)
- [ ] Try `ObsidianBridge().ping()`:
  - [ ] If `True`: call `write_note(vault_path, rendered_md)`; log `VAULT_WRITE` to audit_logs
  - [ ] If `False`: log `VAULT_WRITE_SKIPPED` to audit_logs; return `None`
- [ ] Add `write-to-vault` CLI subcommand:
  ```
  architect_tools.py write-to-vault <db_path> <agent_id> "<task>" "<result>" [--vault-path PATH] [--sensitive]
  ```

---

## Block D — Vault Note → OpenClaw Archive

### D1: `ingest_vault_note()` in `librarian_ctl.py`
- [ ] Add function signature per design spec
- [ ] Import `ObsidianBridge` lazily (avoid import error if `obsidian_bridge.py` not on path)
- [ ] `bridge = ObsidianBridge(); content = bridge.read_note(vault_path)` — propagate `RuntimeError` if down
- [ ] Size check: `if len(content.encode()) > VAULT_INGEST_MAX_BYTES: raise ValueError("Vault note exceeds VAULT_INGEST_MAX_BYTES")`
- [ ] Call `SafetyDistillationEngine().archive_log(db_path, raw_source_id=vault_path, raw_log=content, is_sensitive=is_sensitive, source_type="external")`
  - [ ] On any exception from `archive_log`: log `action='VAULT_INGEST_FAILED'`, `rationale=f"Failed to ingest {vault_path}: {e}"` to audit_logs; re-raise
- [ ] Log `VAULT_INGEST` to `audit_logs` on success
- [ ] Print `Archived as passage_id={id}` to stdout

### D2: `ingest-vault-note` CLI in `librarian_ctl.py`
- [ ] Add `ingest-vault-note` subcommand to the argparse CLI
  - [ ] Positional: `db_path`, `vault_path`
  - [ ] Optional: `--sensitive` flag (default: False)
- [ ] Error handling: `FileNotFoundError` → clear "Note not found" message + exit 1
- [ ] Error handling: `RuntimeError` → "Obsidian is not running" message + exit 1

---

## Block E — Tests

### E0: `conftest.py` Update (MUST be done before any other E tasks)
- [ ] Add `openclaw_skills/` to `sys.path` in `conftest.py` (where `obsidian_bridge.py` will live), following the Sprint 5/6 pattern
- [ ] In `isolated_workspace` fixture: patch `obsidian_bridge.OBSIDIAN_BASE_URL` to `"http://127.0.0.1:27123"` and `obsidian_bridge.OBSIDIAN_API_KEY` to `"test-key"` via `monkeypatch.setattr`

### E1: `tests/test_obsidian_bridge.py`
- [ ] `test_ping_obsidian_up` — mock `GET /vault/` returns 200; assert `ping()` is `True`
- [ ] `test_ping_obsidian_down` — mock raises `URLError`; assert `ping()` is `False`, no exception
- [ ] `test_ping_returns_true_on_401` — mock returns 401; assert `ping()` still `True` (plugin is running)
- [ ] `test_bridge_raises_if_api_key_empty` — `ObsidianBridge(api_key="")` raises `ValueError`
- [ ] `test_bridge_raises_if_non_localhost_url` — `ObsidianBridge(base_url="http://attacker.com:27123")` raises `ValueError`
- [ ] `test_read_note_success` — mock returns 200 with markdown body; assert content returned
- [ ] `test_read_note_not_found` — mock returns 404; assert `FileNotFoundError`
- [ ] `test_write_note_sends_put` — assert method is `PUT`, path URL-encoded, bearer header present
- [ ] `test_write_note_spaces_in_path` — `"00 - INBOX/foo.md"` → URL contains `00%20-%20INBOX/foo.md` (NOT `00+INBOX`)
- [ ] `test_write_note_rejects_path_traversal` — `write_note("../evil.md", "x")` raises `ValueError`
- [ ] `test_write_note_rejects_absolute_path` — `write_note("/etc/passwd", "x")` raises `ValueError`
- [ ] `test_append_sends_patch_not_post` — mock PATCH 200; assert HTTP method is `PATCH`
- [ ] `test_append_sends_correct_body` — capture request body; assert equals `"\n\nmy content".encode("utf-8")`
- [ ] `test_append_creates_if_missing` — mock PATCH returns 404; assert `write_note` called as fallback
- [ ] `test_list_notes_returns_flat_array` — mock returns JSON array `["a/b.md", "c/d.md"]`; assert list of 2 strings returned
- [ ] `test_list_notes_missing_folder_returns_empty` — mock 404; assert returns `[]`
- [ ] `test_health_check_ok` — ping True; assert `{"status": "ok", ...}`
- [ ] `test_health_check_down` — ping False; assert `{"status": "down", ...}`

### E2: `write_agent_result_to_vault` tests
- [ ] `test_write_result_obsidian_up` — mock `ping=True`, `write_note`; assert `VAULT_WRITE` in audit_logs, returns `vault_path`
- [ ] `test_write_result_obsidian_down` — mock `ping=False`; assert `VAULT_WRITE_SKIPPED` in audit_logs, returns `None`
- [ ] `test_write_result_auto_path_format` — assert returned path matches `00 - INBOX/openclaw/YYYY-MM-DD_...`
- [ ] `test_write_result_sensitive_refused` — `is_sensitive=True`; assert `VAULT_WRITE_REFUSED_SENSITIVE` in audit_logs, returns `None`, no bridge call made
- [ ] `test_write_result_truncates_long_result` — pass `result` of 15,000 chars; assert note content contains at most 12,000 chars

### E3: `ingest_vault_note` tests
- [ ] `test_ingest_vault_note_success` — mock `read_note` returns content, mock `archive_log` returns 1; assert `VAULT_INGEST` logged, returns 1
- [ ] `test_ingest_vault_note_obsidian_down` — mock `read_note` raises `RuntimeError`; assert propagated
- [ ] `test_ingest_vault_note_missing_note` — mock `read_note` raises `FileNotFoundError`; assert propagated
- [ ] `test_ingest_uses_is_sensitive_flag` — mock `archive_log`; assert called with `is_sensitive=True` when `ingest_vault_note(..., is_sensitive=True)`
- [ ] `test_ingest_rejects_oversized_note` — mock `read_note` returns 50,001-byte string; assert `ValueError` raised before `archive_log` called
- [ ] `test_ingest_vault_note_audit_log_on_failure` — mock `archive_log` raises; assert `VAULT_INGEST_FAILED` logged, exception re-raised
- [ ] `test_ingest_cli_not_found_exit_code` — mock `read_note` raises `FileNotFoundError`; assert exit code 1 and "Note not found" in stderr

### E4: Target test count
- [ ] Run `pytest tests/ -v` — confirm ≥ 80 tests passing (60 existing + 20 new Sprint 7 tests)

---

## Block F — Documentation

### F1: Linux Obsidian Setup Runbook
- [ ] Create `docs/linux_obsidian_setup.md` with all steps (see design §2)
  - [ ] AppImage download (GitHub API method; explain why bare wget glob fails)
  - [ ] Vault creation, plugin install, API key setup, env var configuration
  - [ ] Quick verification command: `curl -s http://127.0.0.1:27123/vault/ -H "Authorization: Bearer $OBSIDIAN_API_KEY"`
  - [ ] Troubleshooting section: port in use, plugin not enabled, 401 Unauthorized, CORS
  - [ ] Optional: HTTPS on port 27124 for cleartext-free local API key transport

### F2: Update `docs/2026-03-27__12-50_current_state.md`
- [ ] Add Sprint 7 section under §3 Completed Sprints (post-implementation)
- [ ] Update §2 Repository Structure with new files
- [ ] Update Phase 3 roadmap table: Obsidian Sync → ✅ Complete

### F3: Update `README.md`
- [ ] Update test count (≥ 75)
- [ ] Add `OBSIDIAN_BASE_URL` and `OBSIDIAN_API_KEY` to environment variable list

---

## Acceptance Gate

- [ ] `pytest tests/ -v` — ≥ 80 tests passing (60 existing + 20 new), 0 failures
- [ ] Security audit:
  - [ ] No `OBSIDIAN_API_KEY` hardcoded anywhere
  - [ ] `ObsidianBridge` raises `ValueError` on empty API key
  - [ ] `ObsidianBridge` raises `ValueError` on non-localhost `base_url`
  - [ ] No direct vault filesystem writes for note content
  - [ ] `write_note` rejects `../` and absolute path arguments
  - [ ] `write_agent_result_to_vault(is_sensitive=True)` returns `None`, does not write
  - [ ] `write_agent_result_to_vault` result truncated at 12,000 chars
  - [ ] `ingest_vault_note` rejects notes over 50,000 bytes
  - [ ] `ingest_vault_note` always uses `source_type="external"`
  - [ ] `ingest_vault_note` logs `VAULT_INGEST_FAILED` on `archive_log` exception
  - [ ] `ingest_vault_note` never raises on Obsidian unavailability (it DOES raise — explicit failure by design)
  - [ ] `write_agent_result_to_vault` never raises on Obsidian unavailability
- [ ] `docs/linux_obsidian_setup.md` exists, complete, uses GitHub API download method
- [ ] `setup.sh` updated and idempotent

# Sprint 7 — Obsidian Bidirectional Sync
## Design

**Sprint:** 7  
**Date:** 2026-03-27  

---

## 1. Architecture Overview

```
Navigator (Alexey)
    │
    ├── Obsidian Desktop App (W540 Linux)
    │       └── Local REST API plugin → http://127.0.0.1:27123
    │
    └── OpenClaw Runtime
            ├── openclaw_skills/obsidian_bridge.py   ← NEW: HTTP client wrapper
            ├── openclaw_skills/architect/architect_tools.py  ← MODIFY: write_agent_result_to_vault()
            └── openclaw_skills/librarian/librarian_ctl.py   ← MODIFY: ingest-vault-note CLI
```

**Data flows:**

```
Agent result → write_agent_result_to_vault() → ObsidianBridge.write_note() → Local REST API → vault/00 - INBOX/
Vault note   → ingest_vault_note()           → ObsidianBridge.read_note()  → archive_log(source_type='external') → vec_passages
```

---

## 2. Linux Installation Runbook (Block A)

> This block has no code output — it produces a documented manual procedure and a `setup.sh` health-check hook.

### 2.1 Obsidian AppImage on Linux (x86_64)

```bash
# Download latest AppImage via GitHub API (no glob expansion in wget)
APPIMAGE_URL=$(curl -s https://api.github.com/repos/obsidianmd/obsidian-releases/releases/latest \
  | python3 -c "
import sys, json
assets = json.load(sys.stdin)['assets']
print([a['browser_download_url'] for a in assets if a['name'].endswith('.AppImage') and 'arm' not in a['name']][0])
")
wget "$APPIMAGE_URL" -O ~/obsidian.AppImage
chmod +x ~/obsidian.AppImage

# First run (creates vault)
~/obsidian.AppImage
# → Navigator creates vault at: ~/obsidian-vault/   (or OBSIDIAN_VAULT_PATH env var)
# → Navigator sets OBSIDIAN_VAULT_PATH in ~/.bashrc or ~/.profile
```

### 2.2 Local REST API Plugin Installation

1. In Obsidian: Settings → Community Plugins → Browse → search "Local REST API" (by coddingtonbear)
2. Install → Enable
3. Navigate to plugin settings → copy the generated API key
4. Set env var: `export OBSIDIAN_API_KEY="<paste key>"`
5. Plugin default port: `27123`, default host: `127.0.0.1` → no changes needed

### 2.3 Vault Folder Bootstrap Script

`setup.sh` will call a Python snippet that creates the Johnny.Decimal folders if they do not exist (direct filesystem — vault not necessarily running at setup time):

```python
# setup_vault_structure.py (called by setup.sh)
FOLDERS = [
    "00 - INBOX", "00 - INBOX/openclaw",
    "10 - PROJECTS", "20 - AREAS", "30 - RESOURCES",
    "40 - ARCHIVE", "90 - TEMPLATES", "99 - META",
]
```

This is the **only** direct filesystem operation in the Obsidian integration — bootstrapping empty directories before the API is available. Once Obsidian is running, all further operations go through the Local REST API.

---

## 3. `obsidian_bridge.py` Design (Block B)

### 3.1 Configuration

```python
OBSIDIAN_BASE_URL = os.environ.get("OBSIDIAN_BASE_URL", "http://127.0.0.1:27123")
OBSIDIAN_API_KEY  = os.environ.get("OBSIDIAN_API_KEY", "")  # Empty string → ValueError at construction
OBSIDIAN_TIMEOUT  = 10.0  # seconds — all calls
VAULT_INGEST_MAX_BYTES = 50_000  # ~50KB; reject oversized notes before ingestion
```

> **No external APIs.** The Local REST API runs on `127.0.0.1` — not the internet. `base_url` is validated at construction time to enforce this invariant.

> **API key enforcement.** The Obsidian Local REST API plugin requires the Bearer token by default. An empty key results in `401 Unauthorized` on every call. `ObsidianBridge` raises `ValueError` at construction if `api_key` is empty, making misconfiguration immediately visible rather than silently masking as "Obsidian down".

### 3.2 `ObsidianBridge` Class

```python
class ObsidianBridge:
    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url or OBSIDIAN_BASE_URL
        self.api_key  = api_key  or OBSIDIAN_API_KEY
        # Enforce localhost — prevents OBSIDIAN_BASE_URL override from bypassing router.py
        from urllib.parse import urlparse
        parsed = urlparse(self.base_url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError(
                f"ObsidianBridge: base_url must resolve to loopback. Got: {parsed.hostname}"
            )
        # Enforce API key — empty key causes 401 on all calls, masking as 'Obsidian down'
        if not self.api_key:
            raise ValueError(
                "OBSIDIAN_API_KEY is required. Set the env var or pass api_key= to ObsidianBridge()."
            )

    def _make_request(self, method, path, body=None, content_type="application/json") -> tuple[int, str]: ...
    # Wraps urllib.request.Request + urlopen(timeout=OBSIDIAN_TIMEOUT)
    # Authorization: Bearer {api_key} header on all requests
    # NOTE: spaces in path encoded as %20 (urllib.parse.quote, safe="/") — NOT as +; — deliberately RFC 3986 path encoding
    # Returns (status_code, response_body_str)
    # Raises RuntimeError on HTTP errors (non-2xx)

    def ping(self) -> bool: ...
    # GET /vault/ → True on any HTTP response (including 401 — plugin running but key wrong)
    # False only on connection-level exception (URLError, timeout)
    # NOTE: Uses /vault/ not / — root endpoint reliability varies by plugin version

    def read_note(self, vault_path: str) -> str: ...
    # GET /vault/{url_encoded_path}
    # Returns response body (raw markdown)
    # Raises FileNotFoundError on 404
    # Raises RuntimeError on other HTTP errors

    def write_note(self, vault_path: str, content: str) -> None: ...
    # Validates vault_path: raises ValueError if path starts with '..' OR is absolute
    # PUT /vault/{url_encoded_path}
    # Content-Type: text/markdown
    # Creates or overwrites atomically (plugin handles this)

    def append_to_note(self, vault_path: str, content: str) -> None: ...
    # PATCH /vault/{url_encoded_path}   ← NOT POST, NOT ?append=true
    # Content-Type: text/markdown
    # Sends "\n\n{content}" as body (plugin appends to end of file)
    # If note does not exist (PATCH returns 404): falls back to write_note()

    def list_notes(self, folder: str = "") -> list[str]: ...
    # GET /vault/{encoded_folder}/ (trailing slash = directory listing)
    # Returns flat JSON array of path strings: ["00 - INBOX/note.md", ...]
    # NOTE: API returns a flat array, NOT {"files": [...], "folders": [...]}
    # On 404: returns [] (missing folder is not an error)
    # On other errors: raises RuntimeError

    def check_obsidian_health(self) -> dict: ...
    # {"status": "ok"|"down", "url": str, "latency_ms": int}
    # Uses ping() internally with timing
```

### 3.3 URL Encoding

Vault paths may contain spaces (e.g., `"00 - INBOX/..."`). All `vault_path` arguments must be URL-encoded:

```python
import urllib.parse
encoded = urllib.parse.quote(vault_path, safe="/")
url = f"{self.base_url}/vault/{encoded}"
```

---

## 4. Agent Output → Vault Note Schema (Block C)

### 4.1 `write_agent_result_to_vault()` in `architect_tools.py`

**Signature:**
```python
def write_agent_result_to_vault(
    db_path: str,
    agent_id: str,
    task_text: str,
    result: str,
    vault_path: str = None,   # None → auto-generate in 00 - INBOX/openclaw/
    is_sensitive: bool = False,
) -> str | None:
    """
    Returns vault_path on success.
    Returns None if: Obsidian unavailable, OR is_sensitive=True.
    Never raises.
    """
```

**Auto-generated path format:**
```
00 - INBOX/openclaw/YYYY-MM-DD_{agent_id}_{slug}.md
```
Where `slug = task_text[:40].lower().replace(" ", "_")` with non-alphanumeric chars stripped.

**Note Markdown Template:**
```markdown
---
title: "{task_text[:80]}"
agent: {agent_id}
date: {YYYY-MM-DD}
tags: [openclaw, agent-output]
status: unprocessed
is_sensitive: false
---

## Task

{task_text}

## Result

{result[:12000]}  <!--  Context Guard: truncated at 12,000 chars -->

---
*Generated by OpenClaw agent `{agent_id}` on {ISO datetime}*
```

**Sensitivity gate:**
- `is_sensitive=True` → log `VAULT_WRITE_REFUSED_SENSITIVE` to audit_logs, return `None` immediately. **Do not render or write the template.** The vault may sync to cloud via Obsidian sync plugins (e.g., Remotely Save + OneDrive).

**Audit log behaviour:**
- Success → `audit_logs`: `action='VAULT_WRITE'`, `rationale=f"Wrote {vault_path}"`
- Bridge down → `audit_logs`: `action='VAULT_WRITE_SKIPPED'`, returns `None` (never raises)

### 4.2 Prompt Order (no change to run_agent)

`write_agent_result_to_vault()` is a **separate, opt-in step** called by the Navigator or a pipeline after `run_agent()`. It does not modify `run_agent()` behaviour.

---

## 5. Vault Note → OpenClaw Archive (Block D)

### 5.1 `ingest_vault_note()` in `librarian_ctl.py`

```python
def ingest_vault_note(db_path: str, vault_path: str, is_sensitive: bool = False) -> int:
    """
    Reads a note from the Obsidian vault and archives it into vec_passages.

    vault_path:   Relative path within vault (e.g., '30 - RESOURCES/some_note.md')
    is_sensitive: If True, uses local Ollama distillation; if False, uses Gemini.
                  This flag is ALWAYS propagated — controls cloud vs local routing.
    Returns:      passage_id (int)
    Raises:       RuntimeError if Obsidian is not reachable.
                  ValueError if note exceeds VAULT_INGEST_MAX_BYTES (50,000 bytes).
    """
```

**Flow:**
1. `bridge.read_note(vault_path)` → raw markdown (raises `RuntimeError` if Obsidian is down)
2. Size check: `if len(content.encode()) > VAULT_INGEST_MAX_BYTES: raise ValueError(...)`
3. `engine.archive_log(db_path, raw_source_id=vault_path, raw_log=content, is_sensitive=is_sensitive, source_type="external")`
   - On exception: log `action='VAULT_INGEST_FAILED'`, `rationale=f"Failed to ingest {vault_path}: {e}"` to audit_logs; re-raise
4. Log to `audit_logs`: `action='VAULT_INGEST'`, `rationale=f"Ingested {vault_path}"`
5. Return `passage_id`

**CLI:**
```bash
python3 openclaw_skills/librarian/librarian_ctl.py ingest-vault-note \
    $HOME/.openclaw/workspace/factory.db \
    "30 - RESOURCES/AI Research Notes.md" \
    --sensitive
```

---

## 6. Pre-flight Health Check (Block E)

### 6.1 `setup.sh` Integration

```bash
# At end of setup.sh (non-blocking):
echo "[OBSIDIAN] Checking Local REST API..."
python3 -c "
from openclaw_skills.obsidian_bridge import ObsidianBridge
result = ObsidianBridge().check_obsidian_health()
if result['status'] == 'ok':
    print('[OBSIDIAN] ✓ Reachable at ' + result['url'] + ' (' + str(result['latency_ms']) + 'ms)')
else:
    print('[OBSIDIAN] ✗ Not running. Start Obsidian before using vault sync features.')
    print('[OBSIDIAN]   Set OBSIDIAN_BASE_URL and OBSIDIAN_API_KEY if using custom config.')
" || true  # never fail setup if Obsidian check errors
```

### 6.2 Vault Directory Bootstrap (idempotent)

```bash
# vault_bootstrap.py (called by setup.sh if OBSIDIAN_VAULT_PATH is set)
vault_path = os.environ.get("OBSIDIAN_VAULT_PATH", "")
if vault_path:
    for folder in FOLDERS:
        os.makedirs(os.path.join(vault_path, folder), exist_ok=True)
else:
    print("[VAULT] OBSIDIAN_VAULT_PATH not set — skipping vault directory bootstrap.")
```

---

## 7. Security Review

| Concern | Decision |
|---|---|
| **Local REST API on localhost** | Not routed through `router.py` — `ObsidianBridge.__init__` enforces at construction time that `base_url` resolves to a loopback address (`localhost`, `127.0.0.1`, `::1`). Any other host raises `ValueError`, making the "local-only" claim an enforced invariant rather than an assumption. |
| **API key enforcement** | `OBSIDIAN_API_KEY` is required. Empty string raises `ValueError` at construction. This prevents silent `VAULT_WRITE_SKIPPED` masking a 401 misconfiguration. |
| **Sensitive output gate** | `write_agent_result_to_vault(is_sensitive=True)` returns `None` immediately without writing. Vault may sync to cloud via Obsidian sync plugins (Remotely Save + OneDrive). |
| **Result size / Context Guard** | `result` truncated at 12,000 characters in note template — consistent with existing Context Guard. |
| **Vault path validation** | `write_note` validates: `os.path.normpath(vault_path)` must not start with `..` AND must not be absolute (`os.path.isabs`). Both checks required — `../` and `/etc/` attacks both blocked. |
| **IPI in vault ingest** | Vault notes carry IPI risk identical to web-clipped content. `source_type="external"` is hardcoded — always triggers the Epistemic Scrubber. Notes over 50,000 bytes are rejected before ingestion. |
| **Direct filesystem writes** | Forbidden for note content. Only `os.makedirs()` for directory bootstrap (before API is available). |
| **Obsidian unavailability** | Write path: non-fatal (log + return None). Ingest path: explicit RuntimeError (caller is informed). |
| **Cleartext API key on HTTP** | API key sent as Bearer over `http://127.0.0.1` (loopback). Risk: local process sniffing. Mitigation: Obsidian also supports HTTPS on port 27124 (document in runbook as optional hardening). |

---

## 8. New File Map

| File | Status | Description |
|---|---|---|
| `openclaw_skills/obsidian_bridge.py` | **NEW** | `ObsidianBridge` class, health check |
| `openclaw_skills/obsidian_vault_bootstrap.py` | **NEW** | `setup_vault_structure()` — creates JD folders |
| `openclaw_skills/architect/architect_tools.py` | **MODIFY** | Add `write_agent_result_to_vault()` |
| `openclaw_skills/librarian/librarian_ctl.py` | **MODIFY** | Add `ingest_vault_note()`, `ingest-vault-note` CLI |
| `setup.sh` | **MODIFY** | Add vault bootstrap + health check steps |
| `tests/test_obsidian_bridge.py` | **NEW** | Full mocked test coverage |
| `docs/linux_obsidian_setup.md` | **NEW** | Step-by-step Linux installation runbook |

---

## 9. Sequence Diagrams

### Write Flow (Agent → Vault)

```
Navigator / Pipeline
    → run_agent(db_path, agent_id, task)  → result: str
    → write_agent_result_to_vault(db_path, agent_id, task, result)
            → ObsidianBridge.ping()
                ├── REACHABLE → write_note(auto_path, rendered_md)
                │       → PUT /vault/00%20-%20INBOX/openclaw/...
                │       → audit_logs: VAULT_WRITE
                │       → return auto_path
                └── DOWN → audit_logs: VAULT_WRITE_SKIPPED → return None
```

### Ingest Flow (Vault → Archive)

```
Navigator (CLI)
    → librarian_ctl.py ingest-vault-note <db_path> "30 - RESOURCES/note.md"
            → ObsidianBridge.read_note("30 - RESOURCES/note.md")
                    → GET /vault/30%20-%20RESOURCES/note.md
                    → returns raw_markdown: str
            → SafetyDistillationEngine.archive_log(
                  db_path, raw_source_id="30 - RESOURCES/note.md",
                  raw_log=raw_markdown, source_type="external"
              )
                    → distill_safety() → embedding → vec_passages
            → audit_logs: VAULT_INGEST
            → print(f"Archived as passage_id={passage_id}")
```

---

## 10. Environment Variables Summary

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `OBSIDIAN_BASE_URL` | `http://127.0.0.1:27123` | No | Local REST API endpoint — **must resolve to loopback; enforced at construction** |
| `OBSIDIAN_API_KEY` | — | **Yes** | Bearer token for REST API — **empty string raises ValueError at construction** |
| `OBSIDIAN_VAULT_PATH` | `""` | No (for bootstrap only) | Filesystem path to vault root |
| `VAULT_INGEST_MAX_BYTES` | `50000` | No | Max note size for vault ingest (defense against oversized IPI payloads) |
| `OPENCLAW_WORKSPACE` | `~/.openclaw/workspace` | Yes (existing) | OpenClaw workspace |

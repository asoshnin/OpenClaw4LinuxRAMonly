# Sprint 4 Requirements: Repository Cleansing & Remote Migration

**Sprint Goal:** Detach the OpenClaw codebase from its legacy Letta.ai repository history, purge all macOS/Letta-specific files, and establish the canonical clean repository at `https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git`.

---

## [REQ-S4-01] Disconnect from Legacy Remote
The local repository must be detached from `https://github.com/asoshnin/agentic_factory.git`. No code from the old remote must ever be pushed to the new one.

## [REQ-S4-02] Fresh Git History
The new repository must begin with a clean, single initial commit. The full legacy Letta commit history (10+ commits) must NOT be carried over to the new remote, as it contains macOS-specific configuration, old credentials references, and irrelevant architecture decisions.

**Method:** `git checkout --orphan` creates a new branch with no commit history, then the contents are committed fresh.

## [REQ-S4-03] Delete All Legacy Letta/macOS Files
The following files are confirmed legacy and must be removed before the initial commit:

| File/Directory | Reason for Deletion |
|---|---|
| `src/` (entire directory) | Letta.ai Python implementation — macOS, PostgreSQL, REST API dependent |
| `openapi_letta.json` | Letta OpenAPI spec (1.6 MB) — obsolete |
| `ecosystem.config.js` | PM2 process manager config — macOS-only |
| `scripts/diagnostic.sh` | Mac M1 environment diagnostic — wrong platform |
| `clean_reset_librarian.py` | Patches a hardcoded Letta agent ID via REST — obsolete |
| `fix_librarian.py` | Likely Letta agent fix script — to be confirmed before deletion |
| `wire_factory.py` | Likely Letta agent wiring — to be confirmed before deletion |
| `EXAMPLE_Letta Proactive Agentic Architect Deployment Guide.md` | Letta-specific example — obsolete |
| `KIRO_HANDOFF_GUIDE.md` | Contains Letta agent IDs and macOS URLs — obsolete |

## [REQ-S4-04] Verify Remaining Files Before Commit
Before committing, the operator must run `grep -r "agentic_factory.git\|letta\|localhost:8283\|/home/alexey"` over the kept files to catch any remaining hardcoded legacy references.

## [REQ-S4-05] Update `.gitignore`
The new `.gitignore` must explicitly protect:
- `*.db` and `*.db-wal` and `*.db-shm` — SQLite state files
- `.env` — API keys
- `__pycache__/` and `*.pyc`
- `venv/` and `.venv/`
- `workspace/` — runtime state (should NOT be committed to GitHub)
- `.hitl_token` — Burn-on-Read security token

## [REQ-S4-06] Update README.md
The README must be rewritten to describe OpenClaw for Linux, not Letta for macOS.

## [REQ-S4-07] Push to New Remote with Verified Contents
The new remote is: `https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git`  
Push only to `main` branch. Confirm the push was successful and the GitHub UI shows clean contents.

## [REQ-S4-08] Safety Precondition
The Navigator has confirmed a full backup of `agentic_factory/` exists. **No operation in this sprint destroys local files permanently** — the orphan branch approach keeps the old history accessible locally until confirmed safe. Only remote pushes are irreversible.

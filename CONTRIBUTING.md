# Contributing to OpenClaw for Linux

Thank you for your interest in OpenClaw! This document explains how to contribute effectively while respecting the architectural constraints that make the project safe and minimal.

---

## Quick Start: Running the Test Suite

```bash
git clone https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git
cd OpenClaw4LinuxRAMonly
pip install -r requirements.txt
pytest tests/ -v
```

All 156+ tests run without a live Ollama or Obsidian instance — all HTTP calls are mocked. A clean run with only Python and pip is required.

---

## Design Constraints (Non-Negotiable)

These constraints are architectural decisions, not style preferences. Please do not submit PRs that violate them.

| Constraint | Rationale |
|---|---|
| **No `async`/`await`** | Synchronous execution is a safety design choice — it makes the HITL gate predictable and auditable. |
| **No ORM (no SQLAlchemy etc.)** | Raw `sqlite3` is intentional. Minimal dependency surface, maximum transparency. |
| **No Docker / Kubernetes** | OpenClaw is intentionally local-first and air-gapped. Cloud orchestration defeats the purpose. |
| **No new external dependencies** | Allowed deps: `sqlite-vec`, `pyyaml`, `google-generativeai`, `tkinter` (stdlib), `pytest`. Any new dep requires explicit discussion first. |
| **No hardcoded paths** | All file operations must use `validate_path()` via the Airlock. Never use `open()` without a prior path validation. |
| **No silent exception swallowing** | Use explicit `try/except` with logged errors. `except Exception: pass` is never acceptable. |
| **No hardcoded `DOMAIN_MAP`** | Vault domain routing uses `discover_domains()` to scan the live filesystem. Static maps go stale. |
| **`OBSIDIAN_VAULT_PATH` via env var only** | The vault lives outside `OPENCLAW_WORKSPACE`. Supply via environment variable — never hardcode. |

---

## Code Conventions

### CLI Pattern
All tools expose a CLI via `argparse` subcommands. See `librarian_ctl.py` and `architect_tools.py` as canonical examples:
```bash
python3 openclaw_skills/librarian/librarian_ctl.py <subcommand> [args]
```

### Database Access
- Always use parameterized queries — never string interpolation in SQL.
- WAL mode is already set in `init_db()` — do not change `PRAGMA journal_mode`.
- Only modify `factory.db` via `librarian_ctl.py` or `architect_tools.py` — never direct SQLite calls from new code.

### Logging
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Normal operation")
logger.warning("HITL gate triggered")
logger.error("Something failed: %s", e)
```

### File Operations
```python
from librarian_ctl import validate_path
safe_path = validate_path(user_provided_path)  # raises PermissionError on Airlock breach
with open(safe_path, "r") as f:
    ...
```

---

## How to Report a Bug

Open a [GitHub Issue](https://github.com/asoshnin/OpenClaw4LinuxRAMonly/issues/new) and include:

1. **OS and Python version**: `python3 --version`
2. **Exact command you ran**
3. **Full error output / traceback**
4. **Contents of `~/.openclaw/workspace/REGISTRY.md`** (if relevant — contains no sensitive data)

---

## How to Propose a Feature

1. Open a GitHub Issue describing the feature and your use case.
2. Wait for discussion and agreement before writing code.
3. Do not submit unsolicited pull requests — they will be closed without review.

Features that change the security model (HITL gate, Airlock, audit logging) require particularly careful discussion.

---

## Security Policy

- **Never** submit PRs containing API keys, tokens, or credentials of any kind.
- **Never** hardcode paths outside `OPENCLAW_WORKSPACE`.
- If you discover a security vulnerability, please open a **private** GitHub Security Advisory rather than a public issue.

# Refactoring Folder Structure & Consolidation Plan (2026-03-27_11-50)

## 1. Executive Summary
Following a Red Team QA Audit, the initial consolidation plan was **REJECTED** due to environmental fragility (hardcoded user paths) and a broken Python package hierarchy (missing `__init__.py` files). This document outlines the refined, production-ready strategy for consolidating OpenClaw assets into the canonical root: `/home/alexey/openclaw-inbox/agentic_factory/`.

## 2. Refined Directory Map (Canonical)
The target structure enforces strict "Separation of Concerns" and adheres to Python packaging standards.

| Component | Canonical Path | Rationale |
| :--- | :--- | :--- |
| **Core Logic** | `agentic_factory/src/` | Standard source root. |
| **Routing** | `agentic_factory/src/routing/` | Specialized logic for LLM orchestration. |
| **Database** | `agentic_factory/database/` | Isolated state storage (requires strict `.gitignore`). |
| **Workspace** | `agentic_factory/workspace/` | Agent declarations and "Epistemic Audit" outputs. |
| **Skills** | `agentic_factory/src/skills/` | Refactored from `openclaw_skills/`. |
| **Docs** | `agentic_factory/docs/` | Project documentation and handoff guides. |
| **Tests** | `agentic_factory/tests/` | Consolidated test suite. |

## 3. Red Team Fixes & Implementation Steps

### Step 1: Initialize Python Packages (The `__init__.py` Fix)
To resolve the **BROKEN PACKAGE HIERARCHY** blocker, the following command must be executed before moving code:
```bash
find /home/alexey/openclaw-inbox/agentic_factory/src -type d -exec touch {}/__init__.py \;
```

### Step 2: Abstract Path Resolution (The "No Home" Fix)
All Python scripts must replace hardcoded absolute strings (`/home/alexey/...`) with relative path resolution.
**Mandatory Code Snippet for `src/config.py`:**
```python
import os
from pathlib import Path

# Root: /home/alexey/openclaw-inbox/agentic_factory/
BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "database"
WORKSPACE_DIR = BASE_DIR / "workspace"

# Safe DB Path Resolution
FACTORY_DB_PATH = DB_DIR / "factory.db"
```

### Step 3: Security & Git Hygiene
To prevent **SENSITIVE DATA CO-LOCATION** leakage:
1. Create `agentic_factory/.gitignore`:
   ```text
   *.db
   *.log
   .env
   __pycache__/
   venv/
   .venv/
   ```
2. Set permissions for the database directory: `chmod 700 /home/alexey/openclaw-inbox/agentic_factory/database/`.

## 4. Atomic Consolidation Workflow
1. **Prepare**: Create all target directories and `__init__.py` markers.
2. **Move**: Execute `mv` for source, database, and workspace files.
3. **Refactor**: Update imports to use relative paths or a centralized `config.py`.
4. **Verify**: Run `grep -r "/home/alexey/"` to ensure no hardcoded environment-specific strings remain.

## 5. Audit Status
- **Red Team Score**: 5.3 -> **Target 9.0+**
- **Verdict**: Pending Implementation of Action Plan.

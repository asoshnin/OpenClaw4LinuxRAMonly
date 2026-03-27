# Design: Sprint 4 (Repository Cleansing & Remote Migration)

## Strategy: Orphan Branch Approach (Safe & Reversible)

We do NOT use `git filter-branch` or `git push --force` on the old repo. Instead we create a fresh orphan branch locally, commit the clean state, and push it to the new remote as a completely new project. The old history remains intact locally until we are confident the new repo is correct.

```
OLD:  origin → github.com/asoshnin/agentic_factory.git  (Letta history)
NEW:  openclaw → github.com/asoshnin/OpenClaw4LinuxRAMonly.git  (clean slate)
```

---

## [DES-S4-01] Files to DELETE (Confirmed Letta/macOS Legacy)

```
src/                                    ← Entire directory (Letta Python + tests)
openapi_letta.json                      ← 1.6 MB Letta OpenAPI spec
ecosystem.config.js                     ← PM2 config (macOS)
scripts/diagnostic.sh                   ← Mac M1 environment checker
clean_reset_librarian.py                ← Patches hardcoded Letta agent via REST API
fix_librarian.py                        ← Same pattern: requests + hardcoded Letta agent ID
EXAMPLE_Letta Proactive Agentic Architect Deployment Guide.md  ← Letta example
KIRO_HANDOFF_GUIDE.md                   ← Contains Letta agent IDs + macOS URLs
```

> Note: `wire_factory.py` was already absent from the filesystem at audit time — no action needed.

## [DES-S4-02] Files to KEEP

```
openclaw_skills/                        ← CANONICAL implementation (all sprints 1-3.5)
  librarian/
    librarian_ctl.py
    migrate_db.py
    vector_archive.py
    safety_engine.py
  architect/
    architect_tools.py
    SKILL.md

_Development/OpenClaw/                  ← All sprint specs, backlog, design docs
  AgenticFactoryOnClaw.md
  Sprint_1_Librarian/
  Sprint_2_Architect/
  Sprint_3_Vector/
  Sprint_3.5_Resilience/
  Sprint_4_RepoCleansing/              ← This sprint
  2026-03-27_backlog.md
  2026-03-27_11-50_refactoring_folders_structure.md
  Backup/                              ← Local backup (will be gitignored)

docs/                                   ← All documentation generated this session
  2026-03-27__12-50_current_state.md
  2026-03-27_12-45_feature_review_v2.md
  2026-03-27_red_team_analysis.md
  2026-03-27_12-30_feature_review_and_test_plan.md

database/                               ← Directory kept (factory.db gitignored)
workspace/                              ← Directory kept (all contents gitignored)

CHANGELOG.md                            ← Keep, update header
README.md                               ← Rewrite from scratch
.gitignore                              ← Rewrite from scratch
```

## [DES-S4-03] New `.gitignore` Content

```gitignore
# === Runtime State (NEVER COMMIT) ===
workspace/
database/*.db
database/*.db-wal
database/*.db-shm

# === Security ===
.env
.hitl_token
*.token

# === Python ===
__pycache__/
*.pyc
*.pyo
venv/
.venv/
*.egg-info/

# === Backup ===
_Development/OpenClaw/Backup/

# === Editor ===
.DS_Store
*.swp
```

## [DES-S4-04] New README.md Structure

```markdown
# OpenClaw for Linux (RAM-Only Architecture)
Brief 3-line description of the project.

## Architecture
Link to current_state.md or inline diagram.

## Quick Start
Cold start runbook (from §8 of current_state.md)

## Security Model
Airlock + HITL summary.

## Backlog
Link to backlog.md
```

## [DES-S4-05] Git Operations Sequence

```bash
# Step 1: Create orphan branch (no history)
git checkout --orphan openclaw-clean

# Step 2: Unstage everything (orphan starts staged)
git rm -rf --cached .

# Step 3: Delete legacy files from disk
rm -rf src/
rm -f openapi_letta.json ecosystem.config.js
rm -f scripts/diagnostic.sh
rm -f clean_reset_librarian.py fix_librarian.py
rm -f "EXAMPLE_Letta Proactive Agentic Architect Deployment Guide.md"
rm -f KIRO_HANDOFF_GUIDE.md

# Step 4: Write new .gitignore and README.md

# Step 5: Stage all kept files
git add .

# Step 6: Verify staged contents (CRITICAL CHECK BEFORE COMMIT)
git status
git diff --cached --name-only | head -60

# Step 7: Confirm no legacy references remain
grep -r "letta\|agentic_factory.git\|localhost:8283\|/home/alexey" \
  openclaw_skills/ _Development/ docs/ --include="*.py" --include="*.md" -l

# Step 8: Initial commit
git commit -m "feat(init): OpenClaw for Linux — clean foundation post Sprint 3.5

Canonical implementation only. Legacy Letta/macOS code removed.
Includes: Librarian, Architect Tools, Safety Engine, Vector Archive,
HITL Gates, Burn-on-Read tokens, sqlite-vec integration.
Documentation: Sprint 1-4 specs, current state, red team analysis."

# Step 9: Add new remote (keep old one for safety)
git remote add openclaw https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git

# Step 10: Push ONLY to new remote
git push openclaw openclaw-clean:main

# Step 11: Verify on GitHub before removing old remote
# Open: https://github.com/asoshnin/OpenClaw4LinuxRAMonly
# Check: openclaw_skills/ is visible, src/ is absent
```

## [DES-S4-06] Hardcoded Path Audit

The grep check (Step 7 above) will catch any Python files containing `/home/alexey`. Currently known hardcoded paths:
- `librarian_ctl.py:16` — `WORKSPACE_DIR = "/home/alexey/openclaw-inbox/workspace/"`
- `architect_tools.py:19` — `WORKSPACE_DIR = "/home/alexey/openclaw-inbox/workspace/"`

**Decision:** These are documented as GAP-02 in `current_state.md`. They are **not blocking** for this sprint — the system works on the current machine. Fixing them is Phase 1 backlog (Enhanced Discovery / Config Engine). We proceed with documentation of the known hardcoded paths and defer the `config.py` refactor to a later sprint.

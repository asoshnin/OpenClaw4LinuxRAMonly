# Tasks: Sprint 4 (Repository Cleansing & Remote Migration)

**Precondition:** Navigator has confirmed a local backup of `agentic_factory/` exists.  
**Status legend:** `[ ]` pending · `[/]` in progress · `[x]` complete

---

## Step 1 — Create Orphan Branch
**Ref:** [DES-S4-05]  
Creates a new branch with zero commit history, leaving the old Letta history intact.
```bash
cd /home/alexey/openclaw-inbox/agentic_factory
git checkout --orphan openclaw-clean
git rm -rf --cached .
```
✅ Safe: does not delete any files. Does not touch old `main` branch. Fully reversible with `git checkout main`.

---

## Step 2 — Delete Legacy Files
**Ref:** [DES-S4-01]  
Remove all Letta/macOS-specific files from disk.
```bash
rm -rf src/
rm -f openapi_letta.json
rm -f ecosystem.config.js
rm -f "EXAMPLE_Letta Proactive Agentic Architect Deployment Guide.md"
rm -f KIRO_HANDOFF_GUIDE.md
rm -f clean_reset_librarian.py
rm -f fix_librarian.py
rm -f scripts/diagnostic.sh
```
Verify the `scripts/` directory is now empty and can be removed if no other files exist:
```bash
ls -la scripts/
```

---

## Step 3 — Write New `.gitignore`
**Ref:** [DES-S4-03]  
Replace the existing `.gitignore` with the OpenClaw-specific rules.  
*(Execute via Antigravity file write tool — do not use echo redirection)*

Key entries verified:
- `workspace/` — runtime DB and agent profiles excluded
- `database/*.db` — SQLite state excluded
- `.hitl_token` — security token excluded
- `_Development/OpenClaw/Backup/` — local backup excluded

---

## Step 4 — Write New `README.md`
**Ref:** [DES-S4-04]  
Replace `README.md` with an OpenClaw-for-Linux description.  
*(Execute via Antigravity file write tool)*

Structure:
1. Project title + 3-sentence abstract
2. Architecture overview (link to `docs/2026-03-27__12-50_current_state.md`)
3. Quick Start (cold start runbook from §8)
4. Security Model (Airlock + HITL summary)
5. Backlog link

---

## Step 5 — Stage and Audit
**Ref:** [DES-S4-05], [DES-S4-06]  
Stage all files and run verification checks before committing.

```bash
git add .
git status
```

**MANDATORY CHECK — Legacy reference scan:**
```bash
grep -rn "letta\|localhost:8283\|agentic_factory.git" \
  openclaw_skills/ _Development/ docs/ \
  --include="*.py" --include="*.md"
```
Expected: matches only in `_Development/OpenClaw/Backup/` (excluded by .gitignore) and documentation files that legitimately *reference* Letta for historical context.

**MANDATORY CHECK — No secrets committed:**
```bash
grep -rn "GEMINI_API_KEY\s*=\s*['\"]" openclaw_skills/ docs/ --include="*.py"
```
Expected: zero matches (API key is read from environment, never hardcoded).

**KNOWN acceptable finding:** `/home/alexey` will appear in `librarian_ctl.py:16` and `architect_tools.py:19`. This is documented as GAP-02 and deferred to a future sprint. Not blocking.

---

## Step 6 — Initial Commit
```bash
git commit -m "feat(init): OpenClaw for Linux — clean foundation post Sprint 3.5

Canonical implementation only. Legacy Letta/macOS code removed.
Includes: Librarian, Architect Tools, Safety Engine, Vector Archive,
HITL Gates, Burn-on-Read tokens, sqlite-vec integration.
Documentation: Sprint 1-4 specs, current state, red team analysis."
```

---

## Step 7 — Add New Remote
```bash
git remote add openclaw https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git
git remote -v
```
Expected output shows both remotes:
```
openclaw   https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git (fetch)
openclaw   https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git (push)
origin     https://github.com/asoshnin/agentic_factory.git (fetch)
origin     https://github.com/asoshnin/agentic_factory.git (push)
```

---

## Step 8 — Push to New Remote
```bash
git push openclaw openclaw-clean:main
```
> [!IMPORTANT]
> Push ONLY to `openclaw` remote. Do NOT run `git push origin` at any point during this sprint.

---

## Step 9 — Verify on GitHub (MANUAL STEP — Navigator)
Open `https://github.com/asoshnin/OpenClaw4LinuxRAMonly` in a browser and confirm:

| Check | Expected |
|---|---|
| `openclaw_skills/` folder visible | ✅ |
| `src/` folder absent | ✅ |
| `openapi_letta.json` absent | ✅ |
| `workspace/` folder absent | ✅ (gitignored) |
| `docs/` folder visible with 4 markdown files | ✅ |
| `_Development/OpenClaw/` visible | ✅ |
| `_Development/OpenClaw/Backup/` absent | ✅ (gitignored) |
| Single commit in history | ✅ |
| README.md displays OpenClaw description | ✅ |

---

## Step 10 — Switch Local `main` to New History (After GitHub Confirmed)
Once the GitHub UI confirms everything is correct:
```bash
# Make openclaw-clean the new main
git checkout main
git reset --hard openclaw-clean

# Set new remote as default for main
git branch --set-upstream-to=openclaw/main main

# Optional: remove old remote (only after full confirmation)
# git remote remove origin
```

> [!CAUTION]
> Only remove `origin` remote after you are 100% satisfied with the new repo. The old `agentic_factory` repo on GitHub is not affected regardless.

---

## Step 11 — Update Sprint 4 Status in Backlog
Mark "Repository Cleansing" as ✅ Done in `_Development/OpenClaw/2026-03-27_backlog.md`.

---

## Rollback Plan
If anything goes wrong before Step 8 (push), rollback is trivial:
```bash
git checkout main          # Return to original branch with full Letta history
git branch -D openclaw-clean  # Delete the orphan branch
```
Everything on disk is restored to exactly the state before Sprint 4 began.

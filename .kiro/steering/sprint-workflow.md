---
inclusion: manual
---

# Sprint Workflow & Development Process

## Sprint Structure

Each sprint lives in `_Development/OpenClaw/Sprint_N_Name/` and contains three files following the Kiro spec pattern:

| File | Purpose |
|---|---|
| `requirements.md` | User stories + acceptance criteria for the Navigator |
| `design.md` | Technical architecture, sequence diagrams, component design |
| `tasks.md` | Discrete, trackable implementation tasks with status |

## Completed Sprints

| Sprint | Name | Status |
|---|---|---|
| Sprint 1 | Librarian | ✅ Complete |
| Sprint 2 | Architect | ✅ Complete |
| Sprint 3 | Vector Archive | ✅ Complete |
| Sprint 3.5 | Resilience | ✅ Complete |
| Sprint 4 | Repo Cleansing | ✅ Complete |

## Active Backlog

See `#[[file:_Development/OpenClaw/2026-03-27_backlog.md]]` for the live roadmap.

**Next planned sprints:**
- **Sprint 5**: Dynamic LLM Router (HITL-Guarded)
- **Sprint 6**: Static KB Injection
- **Sprint 7**: Self-Healing Parsers

## Task Status Conventions (tasks.md)

```
- [ ] Task not started
- [~] Task in progress  
- [x] Task complete
- [!] Task blocked — describe blocker inline
```

## Creating a New Sprint

1. Create directory: `_Development/OpenClaw/Sprint_N_Name/`
2. Create `requirements.md` — define user stories with acceptance criteria
3. Create `design.md` — architecture decisions, sequence diagrams, data flow
4. Create `tasks.md` — discrete tasks derived from design
5. Update `_Development/OpenClaw/YYYY-MM-DD_backlog.md` to mark sprint as active
6. After completion, create a state snapshot in `docs/YYYY-MM-DD__HH-MM_current_state.md`

## Commit Message Convention

```
<type>(<scope>): <description>

Types: feat, fix, refactor, docs, chore, security
Scopes: librarian, architect, vector, safety, hitl, db, registry

Examples:
feat(architect): add dynamic LLM router with HITL guard
fix(librarian): handle WAL checkpoint timeout on cold start
security(hitl): enforce burn-on-read token for all deploy paths
```

## REGISTRY.md Refresh

After any changes to agents or pipelines in `factory.db`, regenerate the registry:

```bash
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry \
    /path/to/workspace/factory.db \
    ./REGISTRY.md
```

Commit the updated `REGISTRY.md` as part of the same changeset.

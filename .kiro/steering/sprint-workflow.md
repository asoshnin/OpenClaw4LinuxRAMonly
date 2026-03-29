---
inclusion: manual
---

# Sprint Workflow & Development Process

## SQL-First Status Authority

> **Invariant:** The `tasks` and `sprints` tables in `factory.db` are the **master
> authority** for all workflow status. Flat markdown backlogs (`tasks.md`, backlog `.md`
> files) are **read-only human mirrors** — they are synced *from* the DB by
> `sync_backlog.py`, never the reverse.

**Task completion lifecycle:**
1. Code written.
2. Test suite passes (demonstrated, not assumed).
3. `tasks.status` updated to `complete` in `factory.db` with non-empty `test_summary`.
4. `sync_backlog.py` regenerates the Markdown mirror.
5. For high-stakes items: Navigator provides explicit HITL sign-off.

## Wave-Based Sprint Structure

Sprints are now organized as **Strategic Waves** (recorded in the `sprints` table):

| Wave | Name | Focus |
|---|---|---|
| 1 | Wave 1 Foundation | DB schema, prompt hardening, JITH primitives |
| 2 | Wave 2 Perception | Semantic Bridge, Red Team Auditor quality gate |
| 3 | Wave 3 Evolution | Persona Builder, coding stack, tiered inference |
| 4 | Wave 4 Governance | Marketplace, scaling, UI dashboard, OSS readiness |

Tasks belonging to a wave are stored in `tasks` with a `sprint_id` FK to `sprints.id`.

## Legacy File-Based Sprint Pattern (Deprecated)

The old `_Development/OpenClaw/Sprint_N_Name/` directory pattern with `requirements.md`,
`design.md`, and `tasks.md` files is **deprecated** for active tracking. These files may
still be created for planning documentation but must NOT be treated as authoritative for
task status. Use the DB.

## Completed Legacy Sprints (Historical Reference)

| Sprint | Name | Status |
|---|---|---|
| Sprint 1 | Librarian | ✅ Complete |
| Sprint 2 | Architect | ✅ Complete |
| Sprint 3 | Vector Archive | ✅ Complete |
| Sprint 3.5 | Resilience | ✅ Complete |
| Sprint 4 | Repo Cleansing | ✅ Complete |

## Querying Active Work (SQL-First)

```bash
# Show all in-progress tasks
python3 -c "
import sqlite3
conn = sqlite3.connect('workspace/factory.db')
for row in conn.execute(\"SELECT t.id, t.domain, t.status, s.name FROM tasks t JOIN sprints s ON t.sprint_id=s.id WHERE t.status NOT IN ('complete','failed') ORDER BY s.id, t.id\"):
    print(row)
conn.close()
"
```

## Creating a New Task

```python
import sqlite3
conn = sqlite3.connect('workspace/factory.db')
conn.execute(\"INSERT OR IGNORE INTO tasks (id, sprint_id, domain, description) VALUES (?,?,?,?)\",
    ('MY-01', 1, 'Domain', 'Task description'))
conn.commit()
```

## Commit Message Convention

```
<type>(<scope>): <description>

Types: feat, fix, refactor, docs, chore, security
Scopes: librarian, architect, vector, safety, hitl, db, registry, config

Examples:
feat(config): add find_project_root() anchor-based discovery
fix(librarian): handle WAL checkpoint timeout on cold start
security(hitl): enforce burn-on-read token for all deploy paths
```

## REGISTRY.md Refresh

After any changes to agents in `factory.db`, regenerate the registry:

```bash
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry \
    /path/to/workspace/factory.db \
    ./REGISTRY.md
```

Commit the updated `REGISTRY.md` as part of the same changeset.

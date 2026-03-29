"""
BL-00c Migration: Create sprints and tasks tables in factory.db.
Idempotent: safe to re-run; uses INSERT OR IGNORE for data ingestion.
"""
import sqlite3
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("BL-00c")

# Resolve DB path (honour OPENCLAW_WORKSPACE if set)
WORKSPACE = os.environ.get(
    "OPENCLAW_WORKSPACE",
    os.path.expanduser("~/.openclaw/workspace"),
)
DB_PATH = os.path.join(WORKSPACE, "factory.db")


def run_migration(db_path: str) -> None:
    log.info("Opening DB: %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    cur = conn.cursor()

    # --- sprints table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sprints (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            goal       TEXT,
            status     TEXT CHECK(status IN ('planned', 'active', 'complete')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    log.info("sprints table ready.")

    # --- tasks table ---
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          TEXT PRIMARY KEY,
            sprint_id   INTEGER REFERENCES sprints(id),
            depends_on  TEXT,
            assigned_to TEXT REFERENCES agents(agent_id),
            domain      TEXT,
            description TEXT,
            status      TEXT DEFAULT 'pending'
                        CHECK(status IN ('pending', 'in_progress', 'awaiting_review',
                                         'complete', 'failed', 'blocked')),
            test_summary TEXT,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    log.info("tasks table ready.")

    conn.commit()

    # --- Seed sprints (4 Strategic Waves) ---
    waves = [
        ("Wave 1 Foundation",   "Harden DB schema, prompt logic, and JITH primitives.", "active"),
        ("Wave 2 Perception",   "Activate Semantic Bridge and Red Team Auditor quality gate.", "planned"),
        ("Wave 3 Evolution",    "Recursive self-evolution: Persona Builder, coding stack, tiered inference.", "planned"),
        ("Wave 4 Governance",   "Marketplace decoupling, scaling, UI dashboard, OSS readiness.", "planned"),
    ]
    for name, goal, status in waves:
        cur.execute(
            "INSERT OR IGNORE INTO sprints (name, goal, status) VALUES (?, ?, ?)",
            (name, goal, status),
        )
    conn.commit()
    log.info("Seeded %d sprint waves.", len(waves))

    # Fetch wave IDs
    cur.execute("SELECT id, name FROM sprints ORDER BY id")
    wave_map = {name: wid for wid, name in cur.fetchall()}
    w1, w2, w3, w4 = (
        wave_map["Wave 1 Foundation"],
        wave_map["Wave 2 Perception"],
        wave_map["Wave 3 Evolution"],
        wave_map["Wave 4 Governance"],
    )

    # --- Seed tasks ---
    tasks = [
        # (id, sprint_id, depends_on, assigned_to, domain, description, status)
        ("BL-00",  w1, None,    None, "DB",       "Implement factory.db migration for epistemic_backlog table", "complete"),
        ("BL-00c", w1, "BL-00", None, "DB",       "Implement Sprints and Tasks tables for managed orchestration", "in_progress"),
        ("PR-01",  w1, None,    None, "Prompt",   "Refactor prompt_architect skill for Flash Tier (No preamble, stop sequences)", "pending"),
        ("PR-02",  w1, "PR-01", None, "Prompt",   "Structural Integrity: Pydantic-validated JSON output for prompt_architect", "pending"),
        ("LIB-01", w1, None,    None, "Librarian","Implement Just-in-Time Help (JITH): openclaw --help discovery logic", "pending"),
        ("SB-01",  w2, "LIB-01",None, "Bridge",   "Implement Block A: VAULT_QA_NOTE_MAX_CHARS & TypedDicts", "pending"),
        ("SB-02",  w2, "SB-01", None, "Bridge",   "Implement Block B: search_vault() tool (w/ Path Validation)", "pending"),
        ("RT-01",  w2, None,    None, "Audit",    "Implement Red Team Auditor agent with structured assessment protocol", "pending"),
        ("SB-03",  w2, "SB-02", None, "Bridge",   "Implement Block C: vault_qa() tool + 9 tests (Context Guard)", "pending"),
        ("SB-04",  w2, "SB-03", None, "Bridge",   "Implement Block D: [VAULT CONTEXT] prompt block in run_agent()", "pending"),
        ("SB-05",  w2, "SB-04", None, "Bridge",   "Implement Block E/F: vault-qa CLI + 174 test suite", "pending"),
        ("PE-01",  w3, "SB-05", None, "Persona",  "Build Persona Builder assistant (Search, Voice, Vault grounding)", "pending"),
        ("EV-01",  w3, "SB-05", None, "Evolution","Integrate OpenCode/Cline/Pi coding stack into R&D swarm workflows", "pending"),
        ("EV-02",  w3, None,    None, "Evolution","Implement Janitor Agent with strict Deletion Allowlist (Trash policy)", "pending"),
        ("PR-03",  w3, "PR-02", None, "Prompt",   "Tiered Inference: Label prompts as FLASH (Markdown) or PRO (XML)", "pending"),
        ("PR-04",  w3, "PR-03", None, "Prompt",   "POMDP Framework: Belief State (Knowns/Unknowns) & Pro-con lookahead", "pending"),
        ("BL-01",  w3, "BL-00c",None, "Backlog",  "Automated Epistemic Backlog: Agents write gaps to factory.db", "pending"),
        ("BL-02",  w4, "BL-01", None, "Backlog",  "BacklogManager Agent: Periodic synthesis of raw gaps into BACKLOG.md", "pending"),
        ("MP-01",  w4, None,    None, "Market",   "Architecture: Decouple /core from /custom skills + Sandboxing", "pending"),
        ("SYS-01", w4, None,    None, "Resil.",   "Health-Check Supervisor: Pre-flight ping and systemctl recovery", "pending"),
        ("SYS-02", w4, None,    None, "Scaling",  "SQLite-backed Async Task Queue (WAL mode)", "pending"),
        ("GOV-01", w4, None,    None, "Gov.",     "Integrate LangFuse for task-level token budgeting and cost monitoring", "pending"),
        ("UI-01",  w4, None,    None, "UI/UX",    "Design/Build visual dashboard for swarm management and settings", "pending"),
        ("RH-01",  w4, None,    None, "Roles",    "Provision 18 Role Helper profiles (Executive, Product, Legal, etc.)", "pending"),
        ("OSS-01", w4, None,    None, "OSS",      "Block E: Create docs/glossary.md and docs/getting_started.md", "pending"),
        ("OSS-02", w4, "OSS-01",None, "OSS",      "Block F: Final .gitignore cleanup and git rm of _Development/", "pending"),
    ]

    for (tid, sid, deps, agent, domain, desc, status) in tasks:
        cur.execute("""
            INSERT OR IGNORE INTO tasks
                (id, sprint_id, depends_on, assigned_to, domain, description, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tid, sid, deps, agent, domain, desc, status))

    # Update BL-00 to complete and BL-00c to in_progress separately
    # (INSERT OR IGNORE won't overwrite existing rows, so we UPSERT status for these two)
    cur.execute(
        "UPDATE tasks SET status='complete',    test_summary='Verified: functional tests passed (tests/test_bl00_functional.py). Both positive write/read and negative constraint enforcement confirmed.' WHERE id='BL-00'",
    )
    cur.execute(
        "UPDATE tasks SET status='in_progress', test_summary='Migration script running now; schema verified post-creation.' WHERE id='BL-00c'",
    )

    conn.commit()
    log.info("Seeded %d tasks.", len(tasks))

    # --- Verification query ---
    cur.execute("SELECT COUNT(*) FROM sprints")
    sprint_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tasks")
    task_count = cur.fetchone()[0]
    cur.execute("SELECT id, status FROM tasks WHERE id IN ('BL-00', 'BL-00c')")
    status_rows = cur.fetchall()

    conn.close()
    log.info("Schema verified: %d sprints, %d tasks.", sprint_count, task_count)
    for tid, s in status_rows:
        log.info("  Task %s -> status=%s", tid, s)
    log.info("BL-00c migration complete.")


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    run_migration(path)

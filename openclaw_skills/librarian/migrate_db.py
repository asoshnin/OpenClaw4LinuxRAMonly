"""
Database Migration Script - Sprint 3.5 + Sprint 5 + Sprint 6 + Sprint 13
Lifecycle, resilience, schema enrichment, intelligence layer, and epistemic
self-evolution updates.
"""
import sqlite3
import logging
import argparse
import sys
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

try:
    from librarian_ctl import validate_path
except ImportError:
    sys.path.append(os.path.dirname(__file__))
    from librarian_ctl import validate_path


def migrate_database(db_path: str):
    valid_db_path = validate_path(db_path)
    print(f"Executing migration on {valid_db_path}...")
    
    with sqlite3.connect(valid_db_path) as conn:
        cursor = conn.cursor()
        
        # 1. Add is_system to agents
        try:
            cursor.execute("ALTER TABLE agents ADD COLUMN is_system BOOLEAN DEFAULT 0;")
            print("Added 'is_system' column to agents.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("'is_system' column already exists in agents.")
            else:
                print(f"Operational error altering agents table (is_system): {e}")
                
        # 2. Create pipeline_agents tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_agents (
                pipeline_id TEXT,
                agent_id TEXT,
                PRIMARY KEY (pipeline_id, agent_id),
                FOREIGN KEY(pipeline_id) REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
                FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
            );
        """)
        print("Ensured pipeline_agents table exists.")
        
        # 3. Mark core agents as system
        cursor.execute("""
            UPDATE agents
            SET is_system = 1
            WHERE agent_id IN ('kimi-orch-01', 'lib-keeper-01');
        """)
        logger.info("Updated core agents is_system flag. Rows affected: %d", cursor.rowcount)

        # 4. Add description and tool_names columns (Sprint 5)
        for col in ("description", "tool_names"):
            try:
                cursor.execute(f"ALTER TABLE agents ADD COLUMN {col} TEXT DEFAULT '';")
                logger.info("Added column '%s' to agents table.", col)
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info("Column '%s' already exists — skipping.", col)
                else:
                    raise

        # 5. Seed description/tool_names for core agents (idempotent UPDATE)
        cursor.execute("""
            UPDATE agents SET
                description = 'Lead Systems Architect & Workflow Orchestrator',
                tool_names  = 'search_factory,deploy_pipeline_with_ui,teardown_pipeline,run_agent'
            WHERE agent_id = 'kimi-orch-01' AND (description IS NULL OR description = '');
        """)
        cursor.execute("""
            UPDATE agents SET
                description = 'Knowledge Keeper, DB Manager, Registry Generator',
                tool_names  = 'refresh_registry,archive_log,find_faint_paths'
            WHERE agent_id = 'lib-keeper-01' AND (description IS NULL OR description = '');
        """)
        logger.info("Seeded description/tool_names for core agents.")

        # 6. Create proposed_kb_updates table (Sprint 6 — Reflection Queue)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proposed_kb_updates (
                update_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                proposed_by   TEXT,
                update_type   TEXT CHECK(update_type IN ('rule_add', 'rule_modify', 'rule_delete')),
                target_key    TEXT,
                proposed_value TEXT,
                rationale     TEXT,
                status        TEXT DEFAULT 'pending'
                              CHECK(status IN ('pending', 'approved', 'rejected')),
                submitted_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at   TIMESTAMP
            );
        """)
        logger.info("Ensured proposed_kb_updates table exists.")

        # 7. Add source_type column to distilled_memory (Sprint 6 — Scoped Scrubber)
        # distilled_memory is created by vector_archive.init_vector_db(); it may not
        # exist on fresh DBs that have not yet been vector-initialised — skip gracefully.
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='distilled_memory'"
        ).fetchone()
        if table_exists:
            try:
                cursor.execute(
                    "ALTER TABLE distilled_memory ADD COLUMN source_type TEXT DEFAULT 'external';"
                )
                logger.info("Added 'source_type' column to distilled_memory.")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.info("'source_type' column already exists in distilled_memory — skipping.")
                else:
                    raise
        else:
            logger.info("distilled_memory table not found — step 7 will run after init_vector_db().")

        # 8. Create epistemic_backlog table (Sprint 13 — Self-Evolution Loop)
        # Written by all agents to record tool gaps, knowledge holes, and logic failures.
        # Periodically synthesised by the backlog-manager into BACKLOG.md.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS epistemic_backlog (
                entry_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id     TEXT NOT NULL,
                gap_type     TEXT CHECK(gap_type IN (
                                 'tool_missing',
                                 'knowledge_insufficient',
                                 'logic_failure'
                             )),
                description  TEXT NOT NULL,
                context_json JSON,
                status       TEXT DEFAULT 'raw'
                             CHECK(status IN ('raw', 'analyzed', 'prioritized', 'resolved')),
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        logger.info("Ensured epistemic_backlog table exists.")

        conn.commit()
    logger.info("Migration completed successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migration Script for Agentic Factory Schema")
    parser.add_argument("db_path", type=str, help="Path to factory.db")
    args = parser.parse_args()
    
    migrate_database(args.db_path)

"""
Database Migration Script - Sprint 3.5
Lifecycle and Resilience tracking schema updates.
"""
import sqlite3
import argparse
import sys
import os

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
        print(f"Updated core agents. Rows affected: {cursor.rowcount}")
        
        conn.commit()
    print("Migration completed successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migration Script for Agentic Factory Schema")
    parser.add_argument("db_path", type=str, help="Path to factory.db")
    args = parser.parse_args()
    
    migrate_database(args.db_path)

"""
Migration script for EV-01: Integrate Pi Coding Agent Bridge.
Adds session_id to the tasks table.
Note: SQLite does not support ALTER TABLE for modifying CHECK constraints directly. 
We rely on the application tracking to enforce correct states.
"""
import sqlite3
import logging
from pathlib import Path
from openclaw_skills.config import GLOBAL_DB_PATH

log = logging.getLogger(__name__)

def run_migration(db_path: Path | str = GLOBAL_DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()
    
    # Check if columns exist
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "session_id" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN session_id TEXT;")
        log.info("Added session_id column to tasks table.")
        
    conn.commit()
    conn.close()
    log.info("Migration EV-01 completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()

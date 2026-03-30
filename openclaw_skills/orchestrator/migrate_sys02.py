"""
Migration script for SYS-02: Async Task Queue Worker.
Adds attempt_count, max_retries, and last_error to the tasks table.
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
    
    if "attempt_count" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN attempt_count INTEGER DEFAULT 0;")
        log.info("Added attempt_count column to tasks table.")
        
    if "max_retries" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN max_retries INTEGER DEFAULT 3;")
        log.info("Added max_retries column to tasks table.")
        
    if "last_error" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN last_error TEXT;")
        log.info("Added last_error column to tasks table.")
        
    conn.commit()
    conn.close()
    log.info("Migration SYS-02 completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()

"""
Migration script for BL-01: Backlog Intake mechanism.
Adds depends_on to the tasks table.
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
    
    if "depends_on" not in columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT;")
        log.info("Added depends_on column to tasks table.")
        
    conn.commit()
    conn.close()
    log.info("Migration BL-01 completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()

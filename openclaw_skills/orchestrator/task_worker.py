"""
SYS-02: Async Task Queue Worker
"""
import sqlite3
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional

from openclaw_skills.config import GLOBAL_DB_PATH

log = logging.getLogger(__name__)

class TaskQueueManager:
    def __init__(self, db_path: str | Path = None):
        self.db_path = db_path or GLOBAL_DB_PATH
        self.conn = sqlite3.connect(self.db_path)
        # Enforce WAL mode for concurrency safety
        self.conn.execute("PRAGMA journal_mode=WAL;")
        # Need row factory to return dicts easily
        self.conn.row_factory = sqlite3.Row

    def claim_next_task(self, required_tier: str = None) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        
        # Build tier filter if provided
        tier_clause = ""
        params = []
        if required_tier:
            tier_clause = "AND required_tier = ?"
            params.append(required_tier)
            
        # SQLite 3.35+ supports UPDATE ... RETURNING
        update_sql = f"""
            UPDATE tasks 
            SET status='processing', updated_at=CURRENT_TIMESTAMP 
            WHERE id = (
                SELECT id FROM tasks 
                WHERE status='queued' {tier_clause}
                ORDER BY created_at ASC 
                LIMIT 1
            )
            RETURNING *;
        """
        try:
            cursor.execute(update_sql, tuple(params))
            row = cursor.fetchone()
            if row:
                self.conn.commit()
                return dict(row)
        except sqlite3.OperationalError as e:
            # Fallback for SQLite < 3.35.0 (Strict BEGIN IMMEDIATE)
            if "syntax error" in str(e).lower() or "returning" in str(e).lower():
                self.conn.rollback()
                try:
                    self.conn.execute("BEGIN IMMEDIATE;")
                    select_sql = f"""
                        SELECT * FROM tasks 
                        WHERE status='queued' {tier_clause}
                        ORDER BY created_at ASC 
                        LIMIT 1
                    """
                    cursor.execute(select_sql, tuple(params))
                    row = cursor.fetchone()
                    if row:
                        task_id = row['id']
                        cursor.execute("UPDATE tasks SET status='processing', updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
                        self.conn.commit()
                        
                        # Re-fetch updated row to match RETURNING behavior
                        cursor.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
                        updated_row = cursor.fetchone()
                        return dict(updated_row)
                    else:
                        self.conn.rollback()
                        return None
                except Exception as inner_e:
                    self.conn.rollback()
                    raise inner_e
            else:
                self.conn.rollback()
                raise e
                
        self.conn.commit()
        return None

    def mark_task_completed(self, task_id: str) -> None:
        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            self.conn.execute(
                "UPDATE tasks SET status='completed', updated_at=CURRENT_TIMESTAMP WHERE id=?", 
                (task_id,)
            )
            self.conn.execute(
                "UPDATE tasks SET status='queued', updated_at=CURRENT_TIMESTAMP WHERE depends_on=?", 
                (task_id,)
            )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise e

    def mark_task_as_delegated(self, task_id: str, session_id: str, baseline_commit: str = None) -> None:
        self.conn.execute(
            "UPDATE tasks SET status='processing_subagent', session_id=?, baseline_commit=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", 
            (session_id, baseline_commit, task_id)
        )
        self.conn.commit()

    def get_active_subagent_task(self) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status='processing_subagent' ORDER BY updated_at DESC LIMIT 1")
        row = cursor.fetchone()
        return dict(row) if row else None
        
    def fail_task_with_retry(self, task_id: str, error_log: str) -> str:
        cursor = self.conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        try:
            cursor.execute("SELECT attempt_count, max_retries FROM tasks WHERE id=?", (task_id,))
            row = cursor.fetchone()
            if not row:
                self.conn.rollback()
                raise ValueError(f"Task {task_id} not found")
                
            attempt_count = row['attempt_count'] + 1
            max_retries = row['max_retries']
            
            if attempt_count >= max_retries:
                status = 'pending_hitl'
                result = "HITL_REQUIRED"
            else:
                status = 'queued'
                result = "QUEUED_FOR_RETRY"
                
            cursor.execute("""
                UPDATE tasks 
                SET status=?, last_error=?, attempt_count=?, updated_at=CURRENT_TIMESTAMP 
                WHERE id=?
            """, (status, error_log, attempt_count, task_id))
            
            self.conn.commit()
            return result
            
        except Exception as e:
            self.conn.rollback()
            raise e

    def release_stalled_tasks(self, timeout_minutes: int = 30) -> int:
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE tasks 
            SET status='queued', updated_at=CURRENT_TIMESTAMP 
            WHERE status='processing' 
            AND updated_at < datetime('now', '-' || ? || ' minutes')
        """, (timeout_minutes,))
        count = cursor.rowcount
        self.conn.commit()
        return count

    def close(self):
        self.conn.close()

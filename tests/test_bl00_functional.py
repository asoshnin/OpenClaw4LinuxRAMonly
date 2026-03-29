import sqlite3
import pytest
from pathlib import Path
import os

DB_PATH = Path('workspace/factory.db').resolve()

def test_epistemic_backlog_insert():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Positive Test: Data Write/Read
    valid_data = ('tester-01', 'task-123', 'tool', 'Missing browser control skill validation', 'Fix browser proxy', 'pending')
    cursor.execute('''
        INSERT INTO epistemic_backlog (agent_id, task_id, gap_type, description, proposed_fix, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', valid_data)
    
    conn.commit()
    last_id = cursor.lastrowid
    
    cursor.execute('SELECT agent_id, gap_type, description, status FROM epistemic_backlog WHERE id = ?', (last_id,))
    row = cursor.fetchone()
    
    assert row is not None
    assert row[0] == 'tester-01'
    assert row[1] == 'tool'
    assert row[2] == 'Missing browser control skill validation'
    assert row[3] == 'pending'
    
    # Cleanup positive test record so we leave db clean
    cursor.execute('DELETE FROM epistemic_backlog WHERE id = ?', (last_id,))
    conn.commit()
    conn.close()

def test_epistemic_backlog_constraint():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Negative Test: Constraint Enforcement
    invalid_data = ('tester-01', 'task-123', 'hallucination', 'Invalid gap type', 'x', 'pending')
    
    with pytest.raises(sqlite3.IntegrityError) as exc_info:
        cursor.execute('''
            INSERT INTO epistemic_backlog (agent_id, task_id, gap_type, description, proposed_fix, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', invalid_data)
        
    assert "CHECK constraint failed" in str(exc_info.value)
    
    conn.close()

if __name__ == '__main__':
    pytest.main(['-v', __file__])

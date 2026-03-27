"""
Vector Archive Initialization - Sprint 3
Handles the setup of the SQLite-Vec database tables and extensions.
"""

import os
import sqlite3
import sqlite_vec

# Import Airlock validation from Sprint 1
try:
    from librarian_ctl import validate_path
except ImportError:
    # Fallback if run from a different working directory
    import sys
    sys.path.append(os.path.dirname(__file__))
    from librarian_ctl import validate_path

def init_vector_db(db_path: str) -> None:
    """[DES-13] Initializes sqlite-vec virtual table and memory table."""
    valid_db_path = validate_path(db_path)
    
    with sqlite3.connect(valid_db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)

        cursor = conn.cursor()
        
        # Virtual table (768-dim) array for vectors matching nomic-embed-text
        cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS vec_passages USING vec0(
            passage_id INTEGER PRIMARY KEY,
            embedding FLOAT[768]
        );
        """)
        
        # Metadata & Content
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS distilled_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_source_id TEXT,
            content_json JSON,
            is_sensitive BOOLEAN,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        conn.commit()


def find_faint_paths(db_path: str, query_text: str, limit: int = 5) -> list[dict]:
    """[REQ-13] Retrieve Faint Paths via semantic search using sqlite-vec."""
    import json
    try:
        from safety_engine import SafetyDistillationEngine
    except ImportError:
        import sys
        sys.path.append(os.path.dirname(__file__))
        from safety_engine import SafetyDistillationEngine
        
    engine = SafetyDistillationEngine()
    query_vector = engine._get_embedding(query_text)
    query_vector_json = json.dumps(query_vector)
    
    valid_db_path = validate_path(db_path)
    with sqlite3.connect(valid_db_path) as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
            
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # User defined MATCH query
        cursor.execute("""
            SELECT v.passage_id, v.distance, m.raw_source_id, m.content_json, m.is_sensitive, m.timestamp
            FROM vec_passages v
            JOIN distilled_memory m ON m.id = v.passage_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
        """, (query_vector_json, limit))
        
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            res = dict(row)
            try:
                res['content_json'] = json.loads(res['content_json'])
            except Exception:
                pass
            results.append(res)
            
        return results

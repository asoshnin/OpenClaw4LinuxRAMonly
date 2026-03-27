# Design: Sprint 1 (The Librarian)

## [DES-01] File Architecture
- Root: `/home/alexey/openclaw-inbox/workspace/`
- Database: `factory.db` (SQLite)
- Control Script: `librarian_ctl.py` (Python 3.10+)
- Outputs: `REGISTRY.md` (Obsidian-ready)
- Covers: [REQ-01]

## [DES-02] Hardened Path Validator
```python
def validate_path(target_path):
    """[DES-02] Realpath validation for Airlock protection."""
    base_dir = os.path.realpath("/home/alexey/openclaw-inbox/workspace/")
    target_abs = os.path.realpath(target_path)
    if not target_abs.startswith(base_dir):
        raise PermissionError(f"Airlock Breach: {target_abs} is outside {base_dir}")
    return target_abs
```
- Covers: [REQ-02]

## [DES-03] Database Schema & Initialization
The `init_db()` function will execute the following SQL:
```sql
-- Agents Table
CREATE TABLE IF NOT EXISTS agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    persona_hash TEXT,
    state_blob JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Pipelines Table
CREATE TABLE IF NOT EXISTS pipelines (
    pipeline_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    topology_json JSON,
    status TEXT CHECK(status IN ('active', 'archived', 'deprecated'))
);

-- Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    pipeline_id TEXT,
    action TEXT,
    rationale TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(pipeline_id)
);
```
- Covers: [REQ-01], [REQ-03]

## [DES-04] Bootstrap Seed Script
```sql
-- Initial system registration
INSERT OR IGNORE INTO agents (agent_id, name, version) VALUES 
('kimi-orch-01', 'Mega-Orchestrator (Kimi)', '1.3'),
('lib-keeper-01', 'The Librarian', '1.0');

INSERT OR IGNORE INTO pipelines (pipeline_id, name, status) VALUES 
('factory-core', 'System Core Operations', 'active');

INSERT OR IGNORE INTO audit_logs (agent_id, pipeline_id, action, rationale) VALUES 
('lib-keeper-01', 'factory-core', 'BOOTSTRAP', 'Initial system seeding in Sprint 1');
```
- Covers: [REQ-05]

## [DES-05] Atomic Write Pattern
The `generate_registry()` function must fetch data from SQLite and write the Markdown file atomically.
- Format: YAML Frontmatter + Markdown Body.
- Covers: [REQ-04]

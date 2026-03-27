# Design: Sprint 2 (The Architect & HITL Gates)

## [DES-06] Architect Skill Architecture
- **Location**: `/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/architect/`
- **Main Tool**: `architect_tools.py`
- **Definition**: `SKILL.md` (OpenClaw Skill Format)
- Covers: [REQ-06]

## [DES-07] Discovery Tool: `search_factory`
The Architect will use a read-only SQLite connector to query the Librarian.
```python
def search_factory(query_type, filter_val=None):
    """[DES-07] Discovery logic for Architect.
    query_type: 'agents' | 'pipelines' | 'audit'
    """
    # Deterministic SELECT query execution on factory.db
    # Returns JSON result to the Architect
```
- Covers: [REQ-06]

## [DES-08] HITL Token Manager (CLI & Storage)
- **Generation Command**: `python3 architect_tools.py gen-token` (Executed by User).
- **Mechanism**: Generates a random UUID4.
- **Storage**: Written to `/home/alexey/openclaw-inbox/workspace/.hitl_token`.
- **Permissions**: File mode `600` (User-only access).
- Covers: [REQ-09]

## [DES-09] Token Validator: `validate_token`
A internal helper function used by all high-risk tools.
```python
def validate_token(provided_token):
    """[DES-09] One-time token validation (Burn-on-Read)."""
    token_file = "/home/alexey/openclaw-inbox/workspace/.hitl_token"
    # 1. Read stored token
    # 2. Compare with provided_token
    # 3. DELETE token_file IMMEDIATELY (os.remove)
    # 4. Return True if match, else False
```
- Covers: [REQ-07], [REQ-08]

## [DES-10] Deploy Tool: `deploy_pipeline`
The core factory tool for expanding the ecosystem.
```python
def deploy_pipeline(pipeline_name, topology_json, approval_token):
    """[DES-10] Secure pipeline deployment.
    1. validate_path(workspace) [cite: [DES-02]]
    2. validate_token(approval_token) [cite: [DES-09]]
    3. If valid: write to SQLite 'pipelines' table + write agent files to workspace.
    """
```
- Covers: [REQ-07]

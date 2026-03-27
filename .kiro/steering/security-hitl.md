---
inclusion: auto
name: security-hitl
description: Security policies, HITL gate, Burn-on-Read token, Airlock, and agent protection rules. Use when creating or modifying deployment code, agent provisioning, file operations, or anything touching factory.db.
---

# Security & HITL Policy

## The HITL Gate (Non-Negotiable)

Every pipeline deployment MUST use `deploy_pipeline_with_ui(db_path, pipeline_id, pipeline_name, topology_json)` from `architect_tools.py`.

**Workflow:**
1. Design pipeline logic internally
2. Call `deploy_pipeline_with_ui()` directly — do NOT pre-generate tokens
3. A `tkinter` GUI popup appears on Navigator's screen
4. If Navigator clicks **Yes**: token generated internally, gate passed, deployment proceeds
5. If Navigator clicks **No**: `PermissionError("Deployment rejected by human Navigator via UI.")` is raised immediately

**Never:**
- Generate or validate HITL tokens via CLI manually
- Attempt to call the underlying deploy function directly without the UI wrapper
- Suppress or catch the `PermissionError` from a rejected deployment

## Burn-on-Read Token

- Token file is deleted **before** comparison — this prevents replay attacks
- The agent never sees the token value; `deploy_pipeline_with_ui()` handles it transparently
- Token lifetime: single use, expires on read

## Airlock (Workspace Boundary)

- All file operations use `os.path.realpath()` to resolve paths
- Any path resolving outside the workspace root must raise an `AirlockBreachError`
- When suggesting file I/O code, always include the airlock check pattern:

```python
def _safe_path(workspace_root: str, relative_path: str) -> str:
    resolved = os.path.realpath(os.path.join(workspace_root, relative_path))
    if not resolved.startswith(os.path.realpath(workspace_root)):
        raise PermissionError(f"Airlock breach: {resolved} is outside workspace")
    return resolved
```

## System Agent Protection

- Agents with `is_system=1` in `factory.db` are immutable
- Never generate teardown, update, or delete SQL targeting system agents
- The bootstrap set (e.g., `kimi-orch-01`, `lib-keeper-01`) is always `is_system=1`

## Context Guard

- Logs passed to any LLM call must be truncated to **12,000 characters maximum**
- This prevents OOM crashes on the ThinkPad W540's limited RAM
- Pattern: `log_text = log_text[:12000]` before any LLM call

## Epistemic Scrubber

- All data entering the Vector Archive passes through `safety_engine.py`
- The scrubber strips IPI (Individually Personally Identifiable) information via a dedicated prompt
- Never suggest vectorizing raw audit logs without scrubbing first

## Secrets Management

- `GEMINI_API_KEY` via environment variable only
- Never hardcode API keys, tokens, or credentials in source files
- `.gitignore` covers `workspace/` and `database/` — runtime state never enters git

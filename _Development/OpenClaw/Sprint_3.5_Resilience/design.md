# Design: Sprint 3.5 (Lifecycle & Resilience)

Following the **Navigator's Readiness Review**, this sprint focuses on the "cleanup" and "safety" of the factory operations to prevent resource leaks (zombie agents) and hardware-level failures (OOM/Context Overflows).

---

## 1. Lifecycle Management: Dependency Mapping

### [DES-15] Schema Update: System Protection & Relations
To support safe teardowns, we must distinguish between "System Core" agents and "Disposable" task-specific agents. We also need a many-to-many relationship table to track agent participation in pipelines.

```sql
-- [DES-15.1] Add system protection flag to agents
ALTER TABLE agents ADD COLUMN is_system BOOLEAN DEFAULT 0;

-- [DES-15.2] Explicit mapping of agents to pipelines
CREATE TABLE IF NOT EXISTS pipeline_agents (
    pipeline_id TEXT,
    agent_id TEXT,
    PRIMARY KEY (pipeline_id, agent_id),
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id) ON DELETE CASCADE
);

-- [DES-15.3] Mark core agents as system (Bootstrap update)
UPDATE agents SET is_system = 1 WHERE agent_id IN ('kimi-orch-01', 'lib-keeper-01');
```

### [DES-16] Garbage Collection: `teardown_pipeline`
The `teardown_pipeline` tool in `architect_tools.py` will implement a "Check-Before-Kill" logic to ensure shared resources are preserved.

**Logic Flow**:
1.  **Identify Participants**: Select all `agent_id` from `pipeline_agents` where `pipeline_id = ?`.
2.  **Filter Protected**: For each agent, check if `is_system == 1`. Skip these.
3.  **Check References**: For each unprotected agent, check if they are mapped to *any other* active pipeline in `pipeline_agents`.
4.  **Execute Deletion**:
    *   Remove entry from `pipeline_agents`.
    *   If no other references exist and `is_system == 0`:
        *   Delete agent from `agents` table.
        *   Delete physical `.md` profile from the Airlock (`workspace/`).
5.  **Audit**: Log the teardown event in `audit_logs` with the rationale "Pipeline Decommissioned".

---

## 2. Resilience Guardrails: Safety Engine Hardening

### [DES-17] Network Resiliency: urllib Timeouts
To prevent zombie Python processes on the **ThinkPad W540**, all network calls (Ollama and Gemini) must have hard timeouts.

**Implementation**:
```python
# safety_engine.py update
import urllib.request

# Use timeout=30.0 in all urlopen calls
# response = urllib.request.urlopen(req, timeout=30.0)
```
*   **Target**: `_distill_local`, `_distill_cloud`, and `_get_embedding`.

### [DES-18] Context Window Protection: Text Truncation
The `lfm2.5-1.2b` model is highly efficient but sensitive to large inputs. We implement a **"Middle-Truncate"** strategy for logs exceeding **12,000 characters**.

**Logic**:
```python
def truncate_for_distillation(text: str, limit: int = 12000) -> str:
    """[DES-18] Prevent Context Window Overflow."""
    if len(text) <= limit:
        return text
    
    # Keep 6,000 chars from start, 6,000 from end
    half = limit // 2
    head = text[:half]
    tail = text[-half:]
    
    return f"{head}\n\n...[TRUNCATED FOR RESILIENCE]...\n\n{tail}"
```
*   **Rationale**: The "Head" usually contains initial setup/context, and the "Tail" contains the most recent results/errors. This preservation strategy is optimal for "Faint Path" extraction.

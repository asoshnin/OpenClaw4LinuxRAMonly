---
name: prompt-architect
description: "Inference Optimizer & Epistemic Intelligence Designer skill module."
---

# Prompt Architect Skill

The **Prompt Architect** skill provides the logical tooling mapping to both create new synthesized agent configurations (The Architect phase) and process raw epistemic gaps into digestible workflow constraints (The Backlog Manager phase). 

## Core Capabilities

### 1. `log_epistemic_gap(agent_id, gap_type, description, context_json, db_path=None)`
Records gaps discovered by the swarm during workflow execution.
*   **Categories:** `tool_missing`, `knowledge_insufficient`, `logic_failure`
*   **Dual-Write:** Inserts raw status into `epistemic_backlog`, and records the action into `audit_logs` simultaneously.

### 2. `synthesize_backlog_report(db_path=None, output_path=None)`
Called by the `backlog-manager` PRO-tier agent.
*   Queries `epistemic_backlog` where `status = 'raw'`.
*   Groups the data into an organized Markdown table summarizing gaps, maintaining atomic Row ID tracking.
*   Writes out to the Project Root's `BACKLOG.md`.
*   Atomically updates target gaps to `status = 'analyzed'`.

### 3. `register_from_package(package_json, db_path=None)`
Ingests a structured JSON package and dynamically registers the persona into `factory.db`.

**Agent Intelligence Package strict structure requirement:**
```json
{
  "agent_id": "test-agent-01",
  "tier": "FLASH",
  "intelligence_triad": {
    "system_prompt": "You are a test agent.",
    "kb_schema": {"type": "minimal"},
    "tool_definitions": []
  },
  "epistemic_backlog_directive": "Report on errors",
  "safety_and_security": [],
  "test_cases": []
}
```

**Security constraints:**
*   Requires strict deep validation parsing.
*   If `ObsidianBridge` is accessible, it dynamically duplicates the registered `.json` artifact into `99 - META/OpenClaw/Agents/` for secure Vault tracking. Fallback continues local operation safely without the Vault.

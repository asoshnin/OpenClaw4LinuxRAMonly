
---
type: specification
tags: [architecture, agentic-factory, openclaw, epistemic-navigation, security-hardened]
version: 1.3
status: production-ready
last_updated: 2026-03-26
---

# Agentic Factory on OpenClaw: System Specification (Hardened)

## 1. Vision & Epistemic Framework
The **Agentic Factory** is a self-evolving AI operating system designed to navigate the **Universal Document Classification (UDC)** without being swept away by the "superhighways" of statistical AI consensus.

* **Epistemic Navigation**: Shifting from composing answers to directing inquiry.
* **Faint Paths**: Prioritizing nuanced, non-obvious, and contrarian insights that high-level human judgment requires.
* **The Responsibility Premium**: Ensuring the Architect’s advice is structured so the human Navigator (Alexey) can take informed accountability.

## 2. System Architecture
We implement a three-tier agentic hierarchy:

1.  **Mega-Orchestrator (Kimi)**: The Bridge. Manages the high-level conversation, user intent, and final synthesis.
2.  **AgenticPromptArchitect**: The Factory. A specialized sub-agent that designs, builds, and deploys new pipelines. It generates "The Map" for every new inquiry.
3.  **The Librarian**: The Keeper. A system service/skill that manages the underlying SQLite and Vector databases. It provides the "Memory of the Factory."

## 3. Memory Layer Topology
To solve the scalability problem while maintaining human-readability, we use a hybrid approach:

| Layer | Technology | Content |
|---|---|---|
| **Tier 1: The Map** | Markdown + YAML | `REGISTRY.md`, `DASHBOARD.md`, and Agent Profiles. High-level, curated views for the Obsidian Vault. |
| **Tier 2: The State** | SQLite (`factory.db`) | **WAL Mode Enabled.** Structured data: Agent IDs, Pipeline graphs, Tool versions, and Audit transaction logs. |
| **Tier 3: The Archive** | Vector DB (`sqlite-vec`) | **Memory-capped.** Semantic search for "Faint Paths," past decisions, and distilled summaries. |

## 4. Security & Hardened HITL Enforcement
* **The Hardened Airlock**: All factory operations are strictly isolated within `/home/alexey/openclaw-inbox/workspace/`.
    * **Enforcement (Symlink Protection)**: Librarian/Architect tools must use strict cryptographic path resolution (e.g., Python's `os.path.realpath()`). Before any file operation, the tool must assert that the final resolved absolute path strictly begins with `/home/alexey/openclaw-inbox/workspace/`.
* **Technical HITL Gates**: High-risk tools (e.g., `deploy_agent`, `delete_resource`, `write_config`) require a **verified approval token**.
    * **Mechanism**: A token is generated only by a separate, user-only manual shell command and passed as a required parameter to the tool. If omitted, the tool must instantly fail and instruct the AI to ask the user.
* **Safety Distillation**: All archival memory entries must pass through an "Epistemic Filter" during the sublimation process to strip potential Indirect Prompt Injections (IPIs) and active instructions from the research data.
* **Path Isolation**: Sensitive credentials and host-level configurations are abstracted away from the Architect.

## 5. Technical Requirements

### 5.1 SQLite Schema (Librarian core)
```sql
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT DEFAULT '1.0',
    persona_hash TEXT,
    state_blob JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipelines (
    pipeline_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    topology_json JSON, -- Describes supervisor/worker relationships
    status TEXT CHECK(status IN ('active', 'archived', 'deprecated'))
);

CREATE TABLE audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT,
    pipeline_id TEXT, -- Linked for full state reconstructability
    action TEXT,
    rationale TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(pipeline_id)
);
```

### 5.2 Environmental & Operational
* **Runtime**: OpenClaw Environment (Linux x86_64).
* **Language**: Python 3.10+ (for Librarian skills and Architect tools).
* **Database**: SQLite3 with `PRAGMA journal_mode=WAL;`.
* **Vector Engine**: `sqlite-vec` (preferred for low memory footprint on Linux environments).
* **Formatting**: Obsidian-ready Markdown with mandatory YAML frontmatter.
* **Atomic Writes**: All Markdown generation must use atomic writes (write to `.tmp` then rename) to prevent race conditions with the KIRO IDE file watcher.

## 6. Implementation Plan (Sprint-Based)

### Sprint 1: The Librarian & SQLite Schema
* Initialize `factory.db` with the defined schema and WAL mode.
* **Bootstrap Phase**: Execute an initial SQL seed script to manually inject the Librarian and Kimi Orchestrator profiles into the empty `agents` table.
* Create the Librarian skill set for deterministic CRUD operations with strict path validation.
* Generate the first `REGISTRY.md` from the DB state using atomic writes.

### Sprint 2: The Architect & Initial Pipeline
* Equip the Architect with "Discovery" tools to query the Librarian.
* Implement the 5-Phase Deployment Workflow with **Hardened HITL Gates**.
* Bootstrap the first research pipeline (e.g., "Ravisant-Deconstruction").

### Sprint 3: Vector Archive & Search Integration
* Implement the **Safety Distillation** process: nightly distillation of logs into Vector Memory.
* Add semantic search capabilities to the Architect's Discovery phase.
* Enable cross-session "Faint Path" retrieval.

## 7. Maintenance & Evolution
* **Daily Sublimation**: Log-to-Summary pipeline runs during heartbeats to minimize data noise.
* **Resource Management**: Cap vector cache and monitor system RAM usage via `systemd`/`cgroups` limits to ensure W540 stability.
* **Epistemic Auditing**: Periodic review of "Design Patterns" by the Navigator.

---
*Created by Al (Lead Systems Architect) for Alexey (The Navigator). Hardened via Red Team Audit v4. Fully compliant with KIRO IDE specifications.*
```


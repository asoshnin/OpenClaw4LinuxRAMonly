# OpenClaw Glossary (V2 Standard)

A plain-English reference for all OpenClaw-specific terminology. No prior AI/ML knowledge required.

---

## The Entity Hierarchy

- **Assistant:** The primary user-facing interface. An orchestration of Agents and Workflows to solve specific domains (e.g., DeepResearch Assistant).
- **Agent:** A digital persona/role with a designated capability set (e.g., Librarian, Architect).
- **Skill:** A capability package (e.g., `browser-automation`).
- **Tool:** An atomic function call *within* a Skill (e.g., `browser_open`, `click`).
- **Workflow:** A versioned, reproducible sequence of steps followed by an Assistant.

---

## System Primitives & Roles

- **Navigator (You):** The human operator who owns the system and is the sole authority for approving any consequential action. The Navigator is never replaced by an agent — all deployment decisions gate on explicit Navigator approval.
- **The Librarian:** The designated system agent (`lib-keeper-01`) responsible for managing persistent state, including the database, Vector Archive, Registry, and semantic memory.
- **Red Team Auditor:** A ruthless critic persona focused on quality assessments. All high-stakes artifacts must pass through the Auditor pipeline (Status: Assessment -> Findings -> Recommendations).

---

## Evolution & Resilience Protocols

- **Epistemic Backlog:** A database-backed registry of system gaps (in `factory.db`) for recursive self-evolution. Agents flag functional deficiencies to be addressed later.
- **Just-in-Time Help (JITH):** A resilience protocol where agents dynamically discover CLI syntax via `--help` discovery at runtime. No hardcoded flags are permitted for external scripts.
- **Socratic Improvement:** Continuous refinement and critical questioning applied recursively to early solutions before finalizing artifacts.
- **Epistemic Sovereignty:** The design principle that the human operator stays in full control of what the AI knows and does.

---

## Security & Architecture Concepts

- **Airlock:** A security check that prevents any file operation from writing outside the designated workspace folder (`~/.openclaw/workspace` or equivalent symlinked buffer).
- **HITL Gate (Human-in-the-Loop):** A hard stop blocking execution to wait for explicit native OS dialog approval before a workflow or sensitive action is deployed.
- **Burn-on-Read Token:** A one-time cryptographic token used to prove Navigator approval. The token file is destroyed immediately upon reading, structurally preventing replay attacks.
- **Faint Path:** A semantically similar memory retrieved from past sessions to inject relevant historical context into an agent's reasoning.
- **Knowledge Base:** The static configuration file (`knowledge_base.json`) enforcing core boundaries. Agents may propose changes, but only the Navigator approves them.

---

## Terminology Migration Map (Legacy -> V2 Standard)

- **Pipeline** -> **Workflow**
- **Agentic Pipeline** -> **Assistant Workflow**
- **Tool (generic)** -> **Skill (package) / Tool (atomic)**

---

## Why These Names?

OpenClaw is designed to be a *hardened agentic operating system*. The naming reflects this:
- **Navigator** (not "user") — you steer; the agents execute.
- **Airlock** (from spacecraft design) — a controlled barrier between inside and outside.
- **Faint Path** (from navigation) — a barely visible trail that leads somewhere meaningful.
- **Epistemic Sovereignty** — from philosophy: the right to control what you know and believe.
- **Burn-on-Read** — from intelligence tradecraft: a document that self-destructs after reading.

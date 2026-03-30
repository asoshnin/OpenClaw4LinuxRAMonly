# Agentic Factory Current Backlog Update (2026-03-29)

This document synthesizes all identified backlog tasks from textual sources and strategic brainstorming as of March 29th, 2026. It categorizes them by functional domain and prioritizes them based on technical dependencies (Waves) and strategic alignment.

## 📊 Consolidated Backlog Table

<!-- START_STATUS_TABLE -->
| ID | Wave | Domain | Task Description | Source Doc | Priority | Status |
|---|---|---|---|---|---|---|
| **BL-00** | 1 | DB | Implement factory.db migration for epistemic_backlog table |  |  | Complete |
| **BL-00c** | 1 | DB | Implement Sprints and Tasks tables for managed orchestration |  |  | Complete |
| **LIB-01** | 1 | Librarian | Implement Just-in-Time Help (JITH): openclaw --help discovery logic |  |  | Complete |
| **LIB-01.1** | 1 | Librarian | Extend Librarian Discovery with native artifact index/readonly guard |  |  | Complete |
| **LIB-01.2** | 1 | Librarian | Implement Semantic Extractor Tool for SKILL.md parsing |  |  | Complete |
| **LIB-02** | 1 | Librarian | Implement sync_backlog.py utility (Injection Model) |  |  | Complete |
| **PR-01** | 1 | Prompt | Refactor prompt_architect skill for Flash Tier (No preamble, stop sequences) |  |  | Complete |
| **PR-02** | 1 | Prompt | Structural Integrity: Pydantic-validated JSON output for prompt_architect |  |  | Complete |
| **PR-05** | 1 | Config | Multi-Project Context Switcher: find_project_root() + silo path resolution |  |  | Complete |
| **PR-06** | 1 | DB | Global Project Registry: Cross-project relations and lineage tracking |  |  | Complete |
| **RT-01** | 2 | Audit | Implement Red Team Auditor agent with structured assessment protocol |  |  | Complete |
| **SB-01** | 2 | Bridge | Implement Block A: VAULT_QA_NOTE_MAX_CHARS & TypedDicts |  |  | Pending |
| **SB-02** | 2 | Bridge | Implement Block B: search_vault() tool (w/ Path Validation) |  |  | Pending |
| **SB-03** | 2 | Bridge | Implement Block C: vault_qa() tool + 9 tests (Context Guard) |  |  | Pending |
| **SB-04** | 2 | Bridge | Implement Block D: [VAULT CONTEXT] prompt block in run_agent() |  |  | Pending |
| **SB-05** | 2 | Bridge | Implement Block E/F: vault-qa CLI + 174 test suite |  |  | Pending |
| **BL-01** | 3 | Backlog | Automated Epistemic Backlog: Agents write gaps to factory.db |  |  | Pending |
| **EV-01** | 3 | Evolution | Integrate OpenCode/Cline/Pi coding stack into R&D swarm workflows |  |  | Pending |
| **EV-02** | 3 | Evolution | Implement Janitor Agent with strict Deletion Allowlist (Trash policy) |  |  | Pending |
| **PE-01** | 3 | Persona | Build Persona Builder assistant (Search, Voice, Vault grounding) |  |  | Pending |
| **PR-03** | 3 | Prompt | Tiered Inference: Label prompts as FLASH (Markdown) or PRO (XML) |  |  | Pending |
| **PR-04** | 3 | Prompt | POMDP Framework: Belief State (Knowns/Unknowns) & Pro-con lookahead |  |  | Pending |
| **BL-02** | 4 | Backlog | BacklogManager Agent: Periodic synthesis of raw gaps into BACKLOG.md |  |  | Pending |
| **GOV-01** | 4 | Gov. | Integrate LangFuse for task-level token budgeting and cost monitoring |  |  | Pending |
| **MP-01** | 4 | Market | Architecture: Decouple /core from /custom skills + Sandboxing |  |  | Pending |
| **OSS-01** | 4 | OSS | Block E: Create docs/glossary.md and docs/getting_started.md |  |  | Pending |
| **OSS-02** | 4 | OSS | Block F: Final .gitignore cleanup and git rm of _Development/ |  |  | Pending |
| **RH-01** | 4 | Roles | Provision 18 Role Helper profiles (Executive, Product, Legal, etc.) |  |  | Pending |
| **SYS-01** | 4 | Resil. | Health-Check Supervisor: Pre-flight ping and systemctl recovery |  |  | Pending |
| **SYS-02** | 4 | Scaling | SQLite-backed Async Task Queue (WAL mode) |  |  | Pending |
| **UI-01** | 4 | UI/UX | Design/Build visual dashboard for swarm management and settings |  |  | Pending |
<!-- END_STATUS_TABLE -->

## 🎯 Strategic Priorities (March 29th)

1.  **Wave 1.5 (Multi-Project Support):** Critical priority to enable context-isolated development across parallel projects without semantic pollution.
2.  **Wave 2 (Perception):** Activation of the Semantic Bridge and the Red Team Auditor remains the gateway to high-stakes decision making.

---

## 📑 Appendix: Comprehensive Task Specifications

<!-- START_APPENDIX_SPECS -->
| ID | Requirements and Specifications |
|---|---|
| **BL-00** | **Database Migration (Backlog Table)**<br>• **Requirement:** Create the `epistemic_backlog` table in `factory.db`.<br>• **Status:** Complete. |
| **BL-00c**| **Sprint & Task Management Infrastructure**<br>• **Requirement:** Create relational tables for Wave-based orchestration.<br>• **Specification:** (1) `sprints` table with `name` (UNIQUE), `goal`, and `status`. (2) `tasks` table with `id` (PK), `depends_on` (Prerequisites), `assigned_to` (Agent FK), `status` (extended enum with `awaiting_review` and `failed`), and `test_summary`. |
| **PR-05** | **Multi-Project Switcher (Wave 1.5)**<br>• **Requirement:** Enable instant context-switching between project silos.<br>• **Specification:** (1) Implement `find_project_root()` in `config.py` using upward-recursive discovery for `.factory_anchor`. (2) Resolve `DOCS_DIR`, `MEMORY_DIR`, and `PROJECT_DB` dynamically based on the discovered root. |
| **PR-06** | **Global Project Registry (Wave 1.5)**<br>• **Requirement:** Track lineage and relationships between projects.<br>• **Specification:** Implement `projects` table in global `factory.db` storing `project_id`, `root_path`, and `parent_project_id`. Build `project-init` CLI to spawn standardized folder structures. |
| **LIB-01** | **Just-in-Time Help (JITH Librarian)**<br>• **Requirement:** Ensure version-safe execution without manual command re-training.<br>• **Specification:** Implement a protocol where the Librarian executes `openclaw <cmd> --help` to discover latest flags/subcommands dynamically before translating natural language intent into CLI calls. |
| **PR-01** | **Flash Tier Optimization (Refactor)**<br>• **Requirement:** Refactor `prompt_architect` for high-speed "Flash" inference.<br>• **Specification:** Inject "No Preamble" invariants. Implement `stop_sequences` (e.g., `["}"]`) in model calls to prevent token drift. |
| **PR-02** | **Structural Integrity (Pydantic/JSON)**<br>• **Requirement:** Force the `prompt_architect` to output architecture as Pydantic-validated JSON.<br>• **Specification:** Define a `PromptConfig` Pydantic model (fields: `system_prompt`, `kb_schema`, `tool_definitions`). Inject the JSON schema into the LLM prompt. |
| **SB-02** | **Vault Search Tool (Hardened)**<br>• **Requirement:** Implement a search primitive with mandatory path validation to prevent traversal attacks.<br>• **Specification:** Implement `search_vault(query, limit)` in `obsidian_bridge.py` using the Obsidian `GET /search/simple/` endpoint. **Security Guard:** Every result path must be validated against `OBSIDIAN_VAULT_PATH` using `os.path.commonpath`. |
| **RT-01** | **Red Team Auditor (Surgical Critique)**<br>• **Requirement:** Formalize the quality gate for all `PRO` tier outputs.<br>• **Specification:** Implement a detached critic persona. Protocol: Identifies Security, Logic, and Ambiguity flaws. Report Status: 🔴 NO GO, 🟡 CONDITIONAL PASS, 🟢 SIGN OFF. |
| **PE-01** | **Persona Builder (Voice, Knowledge, UDC Grounding)**<br>• **Requirement:** Create high-fidelity digital replicas.<br>• **Specification:** Pipeline: (1) Web Search for bio-data, (2) VoiceSimulator (ElevenLabs) integration, (3) **UDC Grounding:** Utilize the Semantic Bridge to index user-specific history from the Obsidian Vault. |
| **EV-02** | **The Janitor Agent (Trash Policy Guardrail)**<br>• **Requirement:** Automate cleanup of ephemeral pipelines without risking core logic.<br>• **Specification:** Monitor `active_pipelines`. Cleanup must use a "Trash" protocol (move to `.trash/` or database `archived` status) rather than `rm`, governed by a Core Deletion Allowlist. |
| **RH-01** | **18 Role-Helper Provisioning**<br>• **Requirement:** Deploy the tactical tier of specialized corporate assistants.<br>• **Specification:** Create 18 profile files (`.md`) based on the v3.0 Architecture list (Executive, Backend, Legal, etc.). |
| **OSS-02** | **Repository Sanitation (Git Cleanup)**<br>• **Requirement:** Remove all internal development artifacts before public release.<br>• **Specification:** Clean `.gitignore` to ensure no local logs or databases are tracked. Execute `git rm -r --cached _Development/`. Update `knowledge_base.json` to replace all personal PII (e.g., "Alexey") with generic role identifiers (e.g., "the human Navigator"). |
<!-- END_APPENDIX_SPECS -->

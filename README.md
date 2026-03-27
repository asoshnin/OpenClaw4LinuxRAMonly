# OpenClaw for Linux (RAM-Only Architecture)

A hardened, self-evolving agentic operating system built for Linux x86_64. Designed for **Epistemic Sovereignty**: the human Navigator retains full control over every deployment decision through cryptographically enforced Human-in-the-Loop (HITL) gates. All AI inference runs locally — no cloud dependency for sensitive operations.

---

## Architecture

Three-tier agentic hierarchy operating over a single SQLite state database (`factory.db`):

```
Navigator (Alexey)
    │
    ▼
Mega-Orchestrator [kimi-orch-01]        ← Architect Tools
    │   Designs pipelines, triggers HITL GUI popup
    ▼
The Librarian [lib-keeper-01]           ← Librarian CTL
    │   Manages DB state, generates REGISTRY.md
    ▼
Vector Archive + Safety Engine          ← sqlite-vec + Ollama
        Semantic memory, distillation, Faint Path retrieval
```

**Memory Layers:**

| Layer | Technology | Contents |
|---|---|---|
| The Map | Markdown + YAML | `REGISTRY.md`, Agent Profiles |
| The State | SQLite WAL mode | Agents, Pipelines, Audit Logs |
| The Archive | `sqlite-vec` (768-dim) | Distilled memory, semantic search |

Full technical documentation: [`docs/2026-03-27__12-50_current_state.md`](docs/2026-03-27__12-50_current_state.md)

---

## Quick Start

### Prerequisites
```bash
# Python 3.10+, sqlite-vec, ollama
pip install sqlite-vec pyyaml
ollama serve &
ollama pull nomic-embed-text
ollama pull nn-tsuzu/lfm2.5-1.2b-instruct

# For cloud distillation (non-sensitive logs)
export GEMINI_API_KEY="your-key-here"
```

### Cold Start
```bash
cd openclaw_skills/librarian

# 1. Initialize relational schema (WAL mode)
python3 librarian_ctl.py init /path/to/workspace/factory.db

# 2. Seed core agents and system pipeline
python3 librarian_ctl.py bootstrap /path/to/workspace/factory.db

# 3. Initialize vector tables
python3 -c "from vector_archive import init_vector_db; init_vector_db('/path/to/workspace/factory.db')"

# 4. Apply lifecycle migration (is_system flag, pipeline_agents table)
python3 migrate_db.py /path/to/workspace/factory.db

# 5. Generate first registry
python3 librarian_ctl.py refresh-registry \
    /path/to/workspace/factory.db \
    /path/to/workspace/REGISTRY.md
```

---

## Security Model

| Mechanism | Implementation |
|---|---|
| **Airlock** | `os.path.realpath()` enforces workspace boundary on every file op |
| **Burn-on-Read Token** | HITL token file deleted before comparison — replay-proof |
| **GUI HITL Gate** | `tkinter` popup blocks agent execution; headless fallback to terminal prompt |
| **Agent never sees token** | `deploy_pipeline_with_ui()` generates and consumes token transparently |
| **System Agent Protection** | `is_system=1` flag prevents teardown of core agents |
| **Context Guard** | Logs truncated at 12,000 chars before LLM calls — prevents OOM on W540 |
| **Epistemic Scrubber** | All archived logs pass through an IPI-stripping prompt before vectorization |

---

## Project Structure

```
openclaw_skills/
├── librarian/
│   ├── librarian_ctl.py      Library core: DB init, bootstrap, registry
│   ├── migrate_db.py         Schema migration (Sprint 3.5)
│   ├── vector_archive.py     sqlite-vec: init + Faint Path search
│   └── safety_engine.py      Hybrid distillation: local (Ollama) + cloud (Gemini)
└── architect/
    ├── architect_tools.py    Discovery, HITL, deploy, teardown
    └── SKILL.md              Agent skill definition

docs/                         Technical documentation
_Development/OpenClaw/        Sprint specs and backlog
workspace/                    Runtime state (gitignored)
database/                     factory.db location (gitignored)
```

---

## Backlog

See [`_Development/OpenClaw/2026-03-27_backlog.md`](_Development/OpenClaw/2026-03-27_backlog.md) for the full roadmap.

**Next up:** Dynamic LLM Router (HITL-Guarded), Static KB Injection, Self-Healing Parsers.

---

*Hardware target: ThinkPad W540 (x86_64, Linux). All sensitive inference is CPU-bound and air-gapped.*

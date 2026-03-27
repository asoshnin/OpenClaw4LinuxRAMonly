# OpenClaw for Linux

> **Self-hosted AI agents that never act without your explicit approval —  
> local-first, CPU-bound, zero cloud dependency for sensitive operations.**

OpenClaw is a hardened agentic runtime for Linux x86_64. It solves the central problem of AI agent frameworks: **how do you keep a human in control of every consequential action?** The answer is a cryptographically enforced Human-in-the-Loop (HITL) gate baked into the architecture, not bolted on as an afterthought.

---

## Why OpenClaw?

| Dimension | LangChain | CrewAI | AutoGen | **OpenClaw** |
|---|---|---|---|---|
| Local-first inference | Optional | Optional | Optional | ✅ Always |
| HITL enforcement | Plugin/manual | Plugin/manual | Optional | ✅ Architectural primitive |
| Cloud required | Yes (default) | Yes (default) | Yes (default) | ❌ Never for sensitive ops |
| Infrastructure | Python + many deps | Python + many deps | Python + many deps | Python + SQLite only |
| Air-gapped option | ❌ | ❌ | ❌ | ✅ Full air-gap supported |
| Burn-on-Read token security | ❌ | ❌ | ❌ | ✅ Built-in |
| Audit trail | External | External | External | ✅ WAL-mode SQLite |

---

## Architecture

```
Navigator (Human)
    └── Mega-Orchestrator [kimi-orch-01]    ← architect_tools.py
            └── The Librarian [lib-keeper-01]   ← librarian_ctl.py
                    └── Vector Archive + Safety Engine  ← sqlite-vec + Ollama
```

**Three memory layers:**
- **The Map:** `REGISTRY.md` — human-readable agent/pipeline registry (auto-generated)
- **The State:** `factory.db` — SQLite WAL-mode relational store (agents, pipelines, audit logs)
- **The Archive:** `sqlite-vec` 768-dim vectors — semantic memory for Faint Path retrieval

**Security primitives:**
- **Airlock:** All file ops are scoped to `OPENCLAW_WORKSPACE` via `os.path.realpath()` + `os.sep` prefix-collision guard
- **HITL Gate:** Every pipeline deployment requires a native GUI popup (or terminal prompt) confirmation from the Navigator
- **Burn-on-Read token:** The HITL token is deleted *before* the comparison — preventing replay attacks
- **HITL-Guarded Router:** Sensitive + cloud routing is unconditionally blocked with `[SYS-HALT]` — cloud never called, every decision audited
- **Static KB:** Security rules are committed JSON injected as the first prompt block — agents cannot override them through task text
- **Context Guard:** All LLM calls are middle-truncated at 12,000 characters

For the full technical reference, see [`docs/2026-03-27__12-50_current_state.md`](docs/2026-03-27__12-50_current_state.md).

---

## Quick Start

**Prerequisites:** Python 3.10+, [Ollama](https://ollama.ai) installed and running.

```bash
# 1. Clone
git clone https://github.com/asoshnin/OpenClaw4LinuxRAMonly.git
cd OpenClaw4LinuxRAMonly

# 2. Install dependencies
pip install -r requirements.txt

# 3. Pull required Ollama models
ollama pull nomic-embed-text
ollama pull nn-tsuzu/lfm2.5-1.2b-instruct

# 4. Cold start (idempotent — safe to re-run)
bash setup.sh

# 5. Run an agent task
python3 openclaw_skills/architect/architect_tools.py run \
  "$HOME/.openclaw/workspace/factory.db" \
  kimi-orch-01 \
  "What agents are currently registered in the factory?"

# 6. (Optional) Sync with Obsidian Vault
export OBSIDIAN_API_KEY="your-local-rest-api-key"
python3 openclaw_skills/architect/architect_tools.py write-to-vault \
  "$HOME/.openclaw/workspace/factory.db" \
  kimi-orch-01 \
  "Log entry" "Task completed successfully"
```

> **Custom workspace:** Set `OPENCLAW_WORKSPACE=/your/path` before running `setup.sh` or any CLI command.

---

## Security Model

### Airlock
Every file operation in OpenClaw is validated against the workspace boundary before execution:
```python
base_dir = str(WORKSPACE_ROOT)
target_abs = os.path.realpath(target_path)  # resolves symlinks
if not (target_abs == base_dir or target_abs.startswith(base_dir + os.sep)):
    raise PermissionError(f"Airlock Breach: {target_abs}")
```

### HITL Gate
No pipeline is deployed without an explicit human approval popup:
```python
# The agent calls this — it blocks until the Navigator clicks Yes/No
deploy_pipeline_with_ui(db_path, pipeline_id, pipeline_name, topology_json)
```
On "Yes": a Burn-on-Read UUID token is generated internally and consumed immediately — the agent never sees it.  
On "No": `PermissionError` is raised, nothing is written.

### Burn-on-Read
The HITL token file is **deleted before the comparison result is evaluated** — even a failed comparison burns the token, preventing replay attacks.

### System Agent Protection
`kimi-orch-01` and `lib-keeper-01` carry `is_system=1` in `factory.db`. The teardown engine skips these agents unconditionally.

### HITL-Guarded LLM Router
Every inference call passes through `router.py`:
```python
route_inference(task_text, is_sensitive=True, min_model_tier="local", db_path=...)
```
- `is_sensitive=True` + `min_model_tier="cloud"` → raises `PermissionError("[SYS-HALT: HITL REQUIRED]")` — cloud API never called.
- Ollama unavailable + `min_model_tier="local"` → `RuntimeError` — no silent fallback to cloud.
- Every routing decision (ROUTE_LOCAL, ROUTE_CLOUD, ROUTE_LOCAL_FAIL, ROUTING_HALT) is written to `audit_logs`.

### Static Knowledge Base & Reflection Queue
`knowledge_base.json` is a committed static file containing security rules, capability boundaries, and epistemic invariants. It is injected as the **first prompt block** before any memory or task content — agents cannot override it.

Agents may **propose** rule changes via `submit_kb_proposal()`. The Navigator **applies** them via `approve_kb_proposal()` with a HITL burn-on-read token.

---

## Running the Test Suite

```bash
pytest tests/ -v
```

All 94 tests run without a live Ollama or Obsidian instance (all HTTP calls are mocked). Coverage: Airlock path validation, symlink traversal attacks, sibling-prefix collision, Burn-on-Read token lifecycle, DB init round-trip, agent runner, dynamic LLM router (all 4 routing outcomes), knowledge base HITL gate, self-healing JSON circuit breaker, scoped epistemic scrubber, and Obsidian API safety invariants (Context Guard, Sensitivity Gate).

---

## Backlog & Roadmap

Active sprint and future phases tracked in:
- [`_Development/OpenClaw/2026-03-27_backlog.md`](_Development/OpenClaw/2026-03-27_backlog.md)
- [`_Development/OpenClaw/Sprint_7_ObsidianSync/`](_Development/OpenClaw/Sprint_7_ObsidianSync/) *(latest completed)*

---

## Hardware Target

ThinkPad W540 (x86_64, Linux). All inference runs locally via Ollama — no GPU required. Cloud (Gemini API) is used **only** for non-sensitive log distillation and is always opt-in via the `is_sensitive` flag. The `router.py` enforces this at the code level — sensitive data cannot reach the cloud even if a caller requests it.

---

## License

MIT

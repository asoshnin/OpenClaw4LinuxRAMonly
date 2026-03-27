# Getting Started with OpenClaw

Welcome. This guide walks you through OpenClaw from zero — no prior AI framework experience needed.

---

## 1. What is OpenClaw?

OpenClaw is a local-first AI agent runtime for Linux. It lets you create named AI agents, give them tasks, and keep a complete audit trail of what they did — all without sending sensitive data to the cloud. The key difference from tools like LangChain or AutoGen: **nothing consequential happens without your explicit approval**. A native OS dialog appears and waits for you to click Yes or No before any pipeline is deployed.

See the [Glossary](glossary.md) if any terms below are unfamiliar.

---

## 2. What is an "agent"?

An agent is a named AI persona stored in the database. Think of it like a job role: `kimi-orch-01` is the Mega-Orchestrator (plans and delegates tasks), and `lib-keeper-01` is The Librarian (manages memory and files). Agents don't run continuously — they activate when you send a task, produce a response, and stop. You can create your own agents for specific roles: research summariser, document classifier, code reviewer, etc.

---

## 3. What is the Navigator role?

**You.** The Navigator is the human operator who:
- Approves or rejects pipeline deployments (via GUI popup)
- Reviews and approves proposed changes to the knowledge base
- Decides what data stays local vs. what can go to the cloud

The system is explicitly designed so that an AI agent can never take a consequential action without your click.

---

## 4. Running your first task

After completing `bash setup.sh`, run:

```bash
python3 openclaw_skills/architect/architect_tools.py run \
  "$HOME/.openclaw/workspace/factory.db" \
  kimi-orch-01 \
  "What agents are currently registered in the factory?"
```

Here is what each part of the output means:

```
[KB] Loaded 3 security rules, 2 capability boundaries, 3 epistemic invariants.
```
→ The Knowledge Base was injected as the first prompt block. The agent cannot override these rules.

```
[MEMORY] Retrieved 0 faint paths from vector archive.
```
→ No similar past sessions were found (empty archive on first run — this is normal).

```
[AGENT kimi-orch-01] Task received: "What agents are currently registered..."
```
→ The agent is processing your task using the local Ollama model.

```
[RESPONSE] Currently registered agents are:
  - Mega-Orchestrator (kimi-orch-01) v1.3 [SYSTEM]
  - The Librarian (lib-keeper-01) v1.0 [SYSTEM]
```
→ The agent's response. The task result is also written to `audit_logs` in `factory.db`.

---

## 5. Reading the audit log

Every action taken by an agent is recorded in `factory.db`. To see recent entries:

```bash
sqlite3 "$HOME/.openclaw/workspace/factory.db" \
  "SELECT timestamp, agent_id, action, rationale FROM audit_logs ORDER BY timestamp DESC LIMIT 10;"
```

What to look for:
- `RUN_AGENT` — a task was executed
- `ROUTE_LOCAL` — inference was routed to local Ollama
- `ROUTE_CLOUD` — inference was routed to Gemini (non-sensitive only)
- `ROUTING_HALT` — a sensitive+cloud routing attempt was blocked
- `VAULT_WRITE_SKIPPED` — Obsidian is not running (non-fatal)
- `VAULT_INGEST` — a vault note was successfully archived to memory

---

## 6. Understanding the HITL popup

When a pipeline deployment is triggered, a native OS dialog appears:

```
┌─────────────────────────────────────┐
│  HITL Approval Required             │
│                                     │
│  Pipeline: system_bootstrap_pipeline│
│  Action: DEPLOY                     │
│                                     │
│  [Yes — Deploy]    [No — Abort]     │
└─────────────────────────────────────┘
```

- **Click Yes**: A Burn-on-Read token is generated and immediately consumed internally. The pipeline is deployed and the action is logged.
- **Click No**: A `PermissionError` is raised. Nothing is written. The attempt is logged.

The dialog is non-dismissable — you cannot close it without clicking Yes or No. This ensures every deployment is an explicit decision.

---

## 7. Reading REGISTRY.md

`~/.openclaw/workspace/REGISTRY.md` is a human-readable snapshot of all agents and pipelines in the system. Regenerate it any time:

```bash
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry \
  "$HOME/.openclaw/workspace/factory.db" \
  "$HOME/.openclaw/workspace/REGISTRY.md"
```

---

## 8. Optional: Connect Your Obsidian Vault

If you use [Obsidian](https://obsidian.md) as your personal knowledge base, you can feed your own notes directly to your agents as trusted context. This is one of the most powerful features of the system — instead of the agent only having access to system audit logs, it can draw on your own curated notes, research, and reference material.

**Security guarantee:** The Obsidian integration is loopback-only (`127.0.0.1` enforced at the code level — no remote connections), all vault content passes through the Epistemic Scrubber before entering the vector archive, and the Sensitivity Gate prevents any vault data from being sent to the cloud.

→ Full setup guide: [docs/linux_obsidian_setup.md](linux_obsidian_setup.md)

---

## 9. Common Problems

### "Ollama is not running"
```
RuntimeError: Ollama is not running. Start it first:
  ollama serve
```
**Fix:** Run `ollama serve` in a terminal and keep it running. Then pull models: `ollama pull nomic-embed-text`.

### "GEMINI_API_KEY environment variable not set"
```
ValueError: GEMINI_API_KEY environment variable not set.
```
**Fix:** Either set the env var (`export GEMINI_API_KEY=...`) or use `--sensitive` flag to force local-only inference.

### "Python 3.10+ is required"
**Fix:** On Ubuntu 20.04: `sudo apt install python3.10`. Then use `python3.10` instead of `python3`.

### "Airlock Breach"
**Fix:** You are trying to write a file outside `OPENCLAW_WORKSPACE`. Check your `OPENCLAW_WORKSPACE` env var and ensure it points to a directory inside your home folder.

---

## 10. Next Steps

→ **[How to Create Your First Custom Agent](how_to_create_agent.md)**

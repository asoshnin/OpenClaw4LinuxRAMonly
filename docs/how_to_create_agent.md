# How to Create a Custom Agent

This guide walks you through the complete process of creating your own OpenClaw agent, from writing the persona to running your first task and optionally pre-loading it with knowledge from your Obsidian vault.

---

## Overview: What an Agent Needs

An agent requires two things:
1. **A database record** in `factory.db` (the mandatory part — defines the agent's ID, name, and capabilities)
2. **A persona profile** (optional Markdown file in the workspace that shapes the agent's behaviour and identity)

---

## Step 1: Write a Persona Profile

Create a Markdown file that describes your agent's identity, role, and constraints. This is not code — it is the agent's "system prompt" that gets injected into every task.

**Example: `my-analyst-01.md`**

```markdown
---
agent_id: my-analyst-01
name: Research Summariser
version: 1.0
role: analyst
---

# Identity

You are a Research Summariser agent for the OpenClaw Agentic Factory. Your sole purpose is
to distil research notes and audit logs into concise, actionable summaries.

# Capabilities

- Summarise long documents into bullet-point executive summaries
- Extract key entities (people, organisations, dates, decisions) from raw text
- Propose knowledge base updates when you identify reusable patterns

# Constraints

- You never deploy workflows or modify the database directly
- You never send sensitive information to the cloud
- When uncertain, propose rather than act — use submit_kb_proposal()
- Always cite the source document or vault path in your summaries
```

Save this file anywhere locally for now — you will pass its path to `register-agent` in Step 2.

---

## Step 2: Register the Agent via CLI

Use `librarian_ctl.py register-agent` to add the agent to `factory.db`:

```bash
DB="$HOME/.openclaw/workspace/factory.db"

python3 openclaw_skills/librarian/librarian_ctl.py register-agent \
  "$DB" \
  my-analyst-01 \
  "Research Summariser" \
  --description "Distils research notes and audit logs into actionable summaries" \
  --tool-names "run_agent,find_faint_paths,submit_kb_proposal" \
  --profile-file path/to/my-analyst-01.md
```

**What the flags do:**

| Flag | Required? | Description |
|---|---|---|
| `db_path` | ✅ Yes | Path to `factory.db` |
| `agent_id` | ✅ Yes | Unique kebab-case ID (used in all CLI commands) |
| `name` | ✅ Yes | Human-readable display name |
| `--description` | Optional | Shown in `REGISTRY.md` |
| `--tool-names` | Optional | Comma-separated list of tools (informational) |
| `--profile-file` | Optional | Path to .md persona file (written to workspace) |
| `--version` | Optional | Version string, default `1.0` |
| `--force` | Optional | Overwrite if agent_id already exists |

**Expected output:**
```
Agent 'my-analyst-01' registered successfully.
Run refresh-registry to update REGISTRY.md.
```

---

## Step 3: Refresh the Registry

Regenerate `REGISTRY.md` to include your new agent:

```bash
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry \
  "$HOME/.openclaw/workspace/factory.db" \
  "$HOME/.openclaw/workspace/REGISTRY.md"
```

Your agent now appears in the registry:
```markdown
## Active Agents

- **Mega-Orchestrator (Kimi)** (`kimi-orch-01`) - v1.3
  - *Core orchestration and workflow management*
- **The Librarian** (`lib-keeper-01`) - v1.0
  - *Database, registry, and memory management*
- **Research Summariser** (`my-analyst-01`) - v1.0
  - *Distils research notes and audit logs into actionable summaries*
  - Tools: `run_agent,find_faint_paths,submit_kb_proposal`
```

---

## Step 4: Run a Task with Your New Agent

```bash
python3 openclaw_skills/architect/architect_tools.py run \
  "$HOME/.openclaw/workspace/factory.db" \
  my-analyst-01 \
  "Summarise the key security rules currently enforced by this system."
```

The agent will respond using its persona profile, the Knowledge Base rules, and any relevant faint paths retrieved from the vector archive.

---

## Step 5: Verify in REGISTRY.md and audit_logs

Check the audit log to confirm your agent ran:

```bash
sqlite3 "$HOME/.openclaw/workspace/factory.db" \
  "SELECT timestamp, agent_id, action FROM audit_logs \
   WHERE agent_id = 'my-analyst-01' ORDER BY timestamp DESC LIMIT 5;"
```

Expected output:
```
2026-03-27T10:30:00|my-analyst-01|RUN_AGENT
2026-03-27T10:29:55|my-analyst-01|AGENT_REGISTERED
```

---

## Step 6 (Advanced): Pre-load Your Agent with Vault Knowledge

If you use Obsidian, you can feed your own notes directly into your agent's semantic memory before it runs a task. This gives the agent personalised, high-quality context beyond the system audit logs.

**Prerequisites:** Obsidian must be running with the Local REST API plugin enabled. See the [Linux Obsidian Setup guide](linux_obsidian_setup.md) for full setup instructions.

### What `ingest-vault-note` does

It fetches a note from your vault, runs it through the Epistemic Scrubber (stripping any active instructions or PII), embeds it as a 768-dim vector, and stores it in the vector archive. The next time your agent runs, the Faint Path retrieval will find this note if it is semantically relevant to the task.

### Example workflow

Imagine you have a research note in your vault at `30 - RESOURCES/ai-safety-principles.md` that you want your Research Summariser to be aware of:

```bash
# Set your API key (get from Obsidian → Settings → Local REST API)
export OBSIDIAN_API_KEY="your-key-here"

# Ingest the note (uses Gemini for distillation since not sensitive)
python3 openclaw_skills/librarian/librarian_ctl.py ingest-vault-note \
  "$HOME/.openclaw/workspace/factory.db" \
  "30 - RESOURCES/ai-safety-principles.md"
```

**Expected output:**
```
Archived as passage_id=3
```

Now run your agent on a related task:

```bash
python3 openclaw_skills/architect/architect_tools.py run \
  "$HOME/.openclaw/workspace/factory.db" \
  my-analyst-01 \
  "What safety principles should we apply when designing assistant workflows?"
```

The response will naturally incorporate the content from your vault note, retrieved via semantic similarity (Faint Path).

### Security note

- Vault content is **always** treated as `source_type='external'` — it always passes through the Epistemic Scrubber before storage.
- The `--sensitive` flag forces local Ollama distillation (no Gemini) for vault notes containing private information.
- Notes larger than 50,000 bytes are blocked before any LLM call.

---

## Step 7: Customising the Knowledge Base

Your agent can propose new rules to the Knowledge Base. This requires Navigator approval via a HITL Burn-on-Read token.

**Agent proposes a rule:**
```bash
python3 openclaw_skills/kb.py submit \
  "$HOME/.openclaw/workspace/factory.db" \
  my-analyst-01 rule_add security_rules \
  "Always cite the source document path in every summary output." \
  "Observed gap: summaries lack traceability to source material."
```

**Navigator reviews proposals:**
```bash
python3 openclaw_skills/kb.py list-proposals \
  "$HOME/.openclaw/workspace/factory.db"
```

**Navigator approves (requires HITL token):**
```bash
python3 openclaw_skills/kb.py approve \
  "$HOME/.openclaw/workspace/factory.db" \
  <update_id> <HITL_TOKEN>
```

---

## Complete Example: Research Summariser Agent

Here is the full sequence end-to-end for a Research Summariser that draws on your Obsidian notes:

```bash
DB="$HOME/.openclaw/workspace/factory.db"
REGISTRY="$HOME/.openclaw/workspace/REGISTRY.md"

# 1. Register the agent
python3 openclaw_skills/librarian/librarian_ctl.py register-agent \
  "$DB" my-analyst-01 "Research Summariser" \
  --description "Distils research from vault notes and audit logs" \
  --tool-names "run_agent,find_faint_paths,submit_kb_proposal"

# 2. Refresh registry
python3 openclaw_skills/librarian/librarian_ctl.py refresh-registry "$DB" "$REGISTRY"

# 3. Pre-load a vault note (optional, requires Obsidian running)
export OBSIDIAN_API_KEY="your-key-here"
python3 openclaw_skills/librarian/librarian_ctl.py ingest-vault-note \
  "$DB" "30 - RESOURCES/research-topic.md"

# 4. Run the agent
python3 openclaw_skills/architect/architect_tools.py run \
  "$DB" my-analyst-01 "Summarise the key findings from my research notes."

# 5. Verify
sqlite3 "$DB" "SELECT timestamp, action, rationale FROM audit_logs \
  WHERE agent_id = 'my-analyst-01' ORDER BY timestamp DESC LIMIT 5;"
```

# OpenClaw Telegram Interface (BETA)

This document describes how to interact with your Agentic Factory via Telegram. 

> [!WARNING]
> The Telegram interface is currently in **BETA**. It acts as a "Thin Client" that bridges your mobile device to the OpenClaw `architect_tools.py` runner on your local Linux machine.

---

## 1. Overview

The Telegram interface allows you to send tasks to your agents from anywhere. 
- **Inbound:** Telegram Message $\rightarrow$ OpenClaw Bridge $\rightarrow$ `architect_tools.py run`
- **Outbound:** Agent Response $\rightarrow$ OpenClaw Bridge $\rightarrow$ Telegram Reply

## 2. Basic Commands

Once connected, you can interact with the factory using the following syntax:

### `/run <agent_id> <task>`
Executes a task through a specific agent.
*Example:* `/run obsidian-vault-architect "Check the taxonomy of my 20 - AREAS folder"`

### `/status`
Returns the current status of the OpenClaw Gateway and local Ollama instance.

### `/list`
Lists all currently registered agents in your `factory.db`.

---

## 3. Security & HITL

**Human-In-The-Loop (HITL)** is maintained even on mobile:
- If a task requires a pipeline deployment, the system will **pause** and wait for approval.
- You will receive a Telegram message with an `[APPROVE]` button. 
- **Security Constraint:** Consequential actions still require the local OS dialog to be confirmed if you are at your machine, or a specific mobile-authorization token if configured.

---

## 4. Troubleshooting

### "Agent Not Found"
Ensure the `agent_id` you are using matches exactly what is shown in `/list` or your `REGISTRY.md`.

### No Response
The OpenClaw process on your Linux machine must be active. Check that the bridge service is running:
```bash
# On your Linux machine
systemctl --user status openclaw-bridge
```

---
*For setup instructions, see the internal [Maintenance Guide](../_Development/OpenClaw/maintenance.md).*

# OpenClaw Telegram Interface (BETA)

This document describes how to interact with your Agentic Factory via Telegram. 

> [!WARNING]
> The Telegram interface is currently in **BETA**. It acts as a "Thin Client" that bridges your mobile device to the OpenClaw `architect_tools.py` runner on your local Linux machine.

---

## 1. Overview

The Telegram interface allows you to send tasks to your agents from anywhere. 
- **Inbound:** Telegram Message $\rightarrow$ OpenClaw Bridge $\rightarrow$ `architect_tools.py run`
- **Outbound:** Agent Response $\rightarrow$ OpenClaw Bridge $\rightarrow$ Telegram Reply

---

## 2. Getting Connected

If you are setting up the Telegram interface for the first time, follow these steps:

### Step 1: Create your Bot (via BotFather)
1.  Open Telegram and search for [@BotFather](https://t.me/botfather).
2.  Send `/newbot` and follow the prompts to choose a Name and Username.
3.  **Capture the Token:** BotFather will provide an HTTP API token. Keep this private.

### Step 2: Bridge to OpenClaw
1.  On your Linux machine, run:
    ```bash
    openclaw setup telegram
    ```
2.  Paste your token when prompted. OpenClaw will now monitor your bot.

### Step 3: Pairing & Handshake
1.  Open your new bot in Telegram and send `/start`.
2.  The bot will reply with an **8-character Pairing Code** (e.g., `QNUD6B24`).
3.  In your Linux terminal, run the approval command:
    ```bash
    openclaw pairing approve telegram <YOUR_CODE>
    ```
4.  Once approved, the bot will send you a **Handshake Message** confirming that the Epistemic Navigator is online.

---

## 3. Basic Commands

Once connected, you can interact with the factory using the following syntax:

### `/run <agent_id> <task>`
Executes a task through a specific agent.
*Example:* `/run obsidian-vault-architect "Check the taxonomy of my 20 - AREAS folder"`

### `/status`
Returns the current status of the OpenClaw Gateway and local Ollama instance.

### `/list`
Lists all currently registered agents in your `factory.db`.

---

## 4. Security & HITL

**Human-In-The-Loop (HITL)** is maintained even on mobile:
- If a task requires a pipeline deployment, the system will **pause** and wait for approval.
- You will receive a Telegram message with an `[APPROVE]` button. 
- **Security Constraint:** Consequential actions still require the local OS dialog to be confirmed if you are at your machine, or a specific mobile-authorization token if configured.

---

## 5. Troubleshooting

### "Agent Not Found"
Ensure the `agent_id` you are using matches exactly what is shown in `/list` or your `REGISTRY.md`.

### No Response
The OpenClaw process on your Linux machine must be active. Check that the bridge service is running:
```bash
# On your Linux machine
systemctl --user status openclaw-gateway
```

---
*For more technical details, see the internal [Maintenance Guide](../_Development/OpenClaw/maintenance.md).*

---

## Appendix: Common Interaction Prompts

### 📓 Obsidian & Knowledge Management
*   **Reading/Searching:**
    `/run obsidian-vault-architect "Find all notes in my '20 - AREAS/23 - AI' folder that discuss 'agentic workflows' and summarize the main points."`
*   **Creating from URL:**
    `/run lib-keeper-01 "Save this article to my '30 - RESOURCES' folder: https://example.com/ai-safety. Extract a summary, identify 5 key concepts, and ensure the YAML frontmatter includes 'domain: AI'."`
*   **Taxonomy Check:**
    `/run obsidian-vault-architect "Run a health check on the '20 - AREAS' directory and report any duplicate numeric prefixes or missing tags."`

### 📧 Communication & Tasks
*   **Email Summary:**
    `/run kimi-orch-01 "Access my inbox and summarize the 5 most recent unread emails. Highlight any action items or meeting requests."`
*   **Calendar Audit:**
    `/run kimi-orch-01 "What does my calendar look like for the next 2 days? List all high-priority events and check if I have any overlapping appointments."`

### 🛠️ System & Discovery Commands
*   **Discovery:**
    `/list`
    *(Use this to see all registered agents currently available to the Factory.)*
*   **Health Check:**
    `/status`
    *(Use this to verify that OpenClaw and Ollama are online and responsive.)*

### ✈️ Planning & Research
*   **Trip Planning:**
    `/run lib-keeper-01 "I'm planning a trip to Amsterdam. Search my '30 - RESOURCES/33 - Clippings' for any restaurant recommendations or museums I've saved, and draft a 3-day itinerary in a new note."`
*   **Project Kickoff:**
    `/run kimi-orch-01 "I'm starting a new project called 'Project Hyperion'. Suggest a project folder structure in '10 - PROJECTS' and initialize a 'Project Log' note with standard metadata."`

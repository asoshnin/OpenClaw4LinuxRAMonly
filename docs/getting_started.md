# Quickstart for Vibe Coders: The OpenClaw Factory

Welcome to the **OpenClaw Agentic Factory**. This guide is for the Epistemic Navigator ("vibe coder") who wants to command the factory primarily through natural language chat with their primary orchestrator assistant (Kimi).

## 1. The Autonomous Factory (How it Works)

The Factory operates like an autonomous assembly line where agents collaborate to achieve your goals:

1.  **You give a goal** and Kimi plans out the specific steps required to build it.
2.  **The Planner (Kimi)** queues these steps into the Factory's database.
3.  **The Coder (Pi)** picks up the first step and writes the actual code.
4.  **The Auditor (Red Team)** ruthlessly reviews the Coder's work. It checks for logic gaps, security flaws, and missed requirements.
5.  If the Auditor rejects the code, the Coder tries again. If it fails 3 times, the factory pauses and Kimi asks you for help.
6.  If the Auditor signs off, the next step in the queue is automatically unblocked and the cycle repeats.

You don't need to micromanage the pipeline. Once you submit a plan, the Factory takes over.

## 2. Starting a New Project

To keep your workspaces clean and isolated without typing out long paths, ask Kimi to set up a new project silo for you.

**Copy-paste this exact prompt into your chat:**
> Kimi, please initialize a new Factory project folder called 'weather_app'.

Kimi will use its `factory-init` skill to create the folder, set up an isolated database, and link it to the global Factory registry.

## 3. Submitting Tasks (The Intake)

Kimi uses the `SKILL.md` instructions to translate your natural language requests into queued tasks for the Factory.

**To plan and build a new feature:**
**Copy-paste this prompt into your chat:**
> Kimi, use the Factory to plan and build a Python script that fetches the weather. Break it down into steps.

Kimi will decompose your high-level goal into a series of dependent tasks and submit them all to the queue.

**To submit a single, isolated task:**
**Copy-paste this prompt into your chat:**
> Kimi, use the Factory to submit a single task: Fix the CSS on the login page.

## 4. Monitoring Progress & Circuit Breakers

The Agentic Factory runs automatically in the background driven by Kimi's Heartbeat. You do not need to sit and wait or even keep the chat open.

**The Circuit Breaker**
If the Coder writes bad code and the Auditor rejects it 3 times, the factory pauses to prevent endless loops.

When this happens, you will see a Circuit Breaker pause. Kimi will proactively message you in this chat with the Auditor's feedback, the Coder's last attempt, and ask you what to do next to unblock the pipeline.

## 5. Appendix: Under the Hood (For Debugging Only)

If Kimi is offline or you prefer to bypass the chat interface, you can manually trigger the Factory pipelines via the terminal.

- To manually submit a plan via CLI:
  `python3 openclaw_skills/orchestrator/factory_cli.py plan "Your goal here"`
- To manually submit a single task:
  `python3 openclaw_skills/orchestrator/factory_cli.py submit "Your task here"`
- To manually step the orchestrator (Force Heartbeat):
  `python3 openclaw_skills/orchestrator/factory_cli.py trigger`

**Siloed Database Path:** By default, the queue runs out of the global hub: `/home/alexey/openclaw-inbox/agentic_factory/workspace/factory.db`.

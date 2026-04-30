---
name: "Backlog Management & Factory Pipeline"
description: "Tool definitions for instructing the factory to plan new goals or submit atomic tasks."
version: 1.0.0
---

# Agentic Factory Orchestrator Workflow

This skill represents the Agentic Factory Orchestrator workflow logic. It enables the primary OpenClaw agent to submit and decompose new goals into atomic actionable tasks. 
It supports the "depends_on" sequential mapping logic through the native intake module.

## Available Actions

Whenever the human Navigator asks to "plan", "submit", or "start" a new Agentic Factory project, the agent MUST use the native `exec` tool to call the `factory_cli.py` CLI wrapper:

1. **Submit a Direct Task**  
`python3 openclaw_skills/orchestrator/factory_cli.py submit "Goal"`

2. **Plan & Decompose a Complex Goal**  
`python3 openclaw_skills/orchestrator/factory_cli.py plan "Complex Goal"`

3. **Trigger the Orchestrator Execution Loop**  
`python3 openclaw_skills/orchestrator/factory_cli.py trigger`
*(Note: This starts a continuous background daemon with Loop Backoff and Watchdog interval protections. It processes the queue sequentially until stopped).*

Always log the task IDs successfully returned.

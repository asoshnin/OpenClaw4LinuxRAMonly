---
name: architect_skills
description: Tools for discovering and deploying Factory pipelines and agents.
---

# Architect Skills

This skill set enables the Agentic Architect to query existing infrastructure and to securely deploy new pipelines into the Agentic Factory database `factory.db`.

## Tools Available (via `architect_tools.py` CLI)

1. **Discovery / Search Factory**
   - Interacts with the `search_factory` function internally to query `factory.db` for existing `agents`, `pipelines`, or `audit` logs.

2. **Deploy Pipeline**
   - Provisions new pipelines in the DB using the `deploy` CLI command.

## MANDATORY SECURITY / HITL WORKFLOW (BURN-ON-READ)
The deployment process uses an underlying Burn-on-Read token. However, you NO LONGER need to ask the human Navigator to manually run `gen-token` in their terminal.

You must now use the wrapper tool `deploy_pipeline_with_ui(db_path, pipeline_id, pipeline_name, topology_json)`. 

**Execute your workflow exactly as follows:**
1. Design the pipeline logic and verify the required schema/topology json internally.
2. Directly call the `deploy_pipeline_with_ui` tool.
3. **Execution will freeze:** A native GUI popup will appear on the human Navigator's screen describing the deployment. 
4. Wait for the tool to return. 
   - If the human clicks "Yes", the tool internally generates a token, passes the security gate, and returns success.
   - If the human clicks "No", the tool immediately raises a `PermissionError("Deployment rejected by human Navigator via UI.")`.

**CRITICAL LIMITATION**: Do not attempt to generate or validate tokens yourself via CLI anymore; simply use the UI wrapper tool. Attempting to bypass this UI gateway will result in an Airlock Breach.

# Tasks: Sprint 2 (The Architect & HITL Gates)

- [ ] **Step 1: Skill Initialization**
  - Create directory: `/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/architect/`.
  - Initialize `architect_tools.py` with DB connectivity (Read-Only).
  - *Ref: [DES-06]*

- [ ] **Step 2: Discovery Tools**
  - Implement `search_factory()` to query Librarian tables.
  - Implement `get_agent_persona(agent_id)` for retrieval of existing designs.
  - *Ref: [DES-07], Realizes: [REQ-06]*

- [ ] **Step 3: Token Generation CLI**
  - Add `gen-token` command to `architect_tools.py` CLI.
  - Ensure UUID4 generation and secure file write (`/home/alexey/openclaw-inbox/workspace/.hitl_token`).
  - *Ref: [DES-08], Realizes: [REQ-09]*

- [ ] **Step 4: Token Validation & Burn Logic**
  - Implement the `validate_token()` function with mandatory `os.remove()` call.
  - Test validation with both correct and incorrect tokens.
  - *Ref: [DES-09], Realizes: [REQ-07], [REQ-08]*

- [ ] **Step 5: Secure Deployment Tool**
  - Implement `deploy_pipeline()` with integrated Path and Token validation.
  - Add atomic write logic for resulting agent `.md` profiles in the workspace.
  - *Ref: [DES-10], Realizes: [REQ-07]*

- [ ] **Step 6: Skill Definition**
  - Author `SKILL.md` to expose these tools to the Architect agent in OpenClaw.

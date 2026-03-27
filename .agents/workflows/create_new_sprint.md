---
description: Create a new OpenClaw Sprint specification with requirements, design, and tasks
---
# Create a New Sprint

When asked to create a new sprint for OpenClaw, follow these steps exactly:

1. **Create the Sprint Directory**:
   Create a new folder at `_Development/OpenClaw/Sprint_N_Name/` (replace `N_Name` with the sprint number and name).

2. **Generate Kiro Spec Files**:
   Inside the new sprint directory, create the following three files:
   - `requirements.md` — define user stories with acceptance criteria for the Navigator.
   - `design.md` — architecture decisions, sequence diagrams, and data flow.
   - `tasks.md` — discrete tasks derived from the design using the standard status format (`- [ ]`, `- [~]`, `- [x]`, `- [!]`).

3. **Update the Backlog**:
   Locate the live backlog file (`_Development/OpenClaw/YYYY-MM-DD_backlog.md`), and update it to mark the new sprint as active.

4. **Completion Step (Future)**:
   Remind the user that after sprint completion, they should create a state snapshot in `docs/YYYY-MM-DD__HH-MM_current_state.md`.

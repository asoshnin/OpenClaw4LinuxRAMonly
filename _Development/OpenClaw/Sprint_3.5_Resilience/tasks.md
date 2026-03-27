# Tasks: Sprint 3.5 (Lifecycle & Resilience)

- [ ] **Step 1: DB Migration**
  - Run `ALTER TABLE agents ADD COLUMN is_system BOOLEAN DEFAULT 0`.
  - Create `pipeline_agents` table for tracking dependencies.
  - Update Bootstrap logic to set `is_system=1` for core agents (Kimi, Librarian).
  - *Ref: [DES-15], [REQ-15]*

- [ ] **Step 2: Teardown Tool**
  - Implement `teardown_pipeline()` in `architect_tools.py`.
  - Add logic to verify participants and shared references before deletion.
  - Ensure physical file deletion uses `validate_path`.
  - *Ref: [DES-16], [REQ-16]*

- [ ] **Step 3: Safety Engine Hardening (Timeouts)**
  - Update `safety_engine.py` to include `timeout=30.0` in all `urllib.request.urlopen` calls.
  - Test with a non-responsive local port to verify timeout behavior.
  - *Ref: [DES-17], [REQ-17]*

- [ ] **Step 4: Context Window Protection (Truncation)**
  - Implement `truncate_for_distillation()` in `safety_engine.py`.
  - Integrate truncation before sending payloads to Ollama/Gemini.
  - *Ref: [DES-18], [REQ-18]*

- [ ] **Step 5: Audit Verification**
  - Ensure all teardown and truncation events are correctly logged to the audit system.

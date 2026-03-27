# Tasks: Sprint 3 (Hybrid Vector Archive)

- [ ] **Step 1: Vector Foundation**
  - Install/Verify `sqlite-vec` binary for the ThinkPad W540 environment.
  - Implement `init_vector_db()` in `vector_archive.py`.
  - *Ref: [DES-13], Realizes: [REQ-10]*

- [ ] **Step 2: Engine Implementation (Local)**
  - Implement `SafetyDistillationEngine._distill_local` using Ollama.
  - Test with `nn-tsuzu/lfm2.5-1.2b-instruct`.
  - *Ref: [DES-12], [DES-14]*

- [ ] **Step 3: Engine Implementation (Cloud)**
  - Implement `SafetyDistillationEngine._distill_cloud` using OpenClaw Gemini API.
  - Test with `gemini-3.1-flash-lite-preview`.
  - *Ref: [DES-12], [DES-14]*

- [ ] **Step 4: Embedding Logic**
  - Implement `_get_embedding()` using `nomic-embed-text` for ALL inputs.
  - *Ref: [DES-12], Realizes: [REQ-10]*

- [ ] **Step 5: Hybrid Router**
  - Finalize `distill_safety()` logic with sensitivity routing.
  - Ensure strict JSON validation of Scrubber outputs.
  - *Ref: [DES-12], Realizes: [REQ-11], [REQ-12]*

- [ ] **Step 6: Semantic Search (Faint Paths)**
  - Implement `find_faint_paths()` tool.
  - Integrate with Architect's Discovery Phase.
  - *Ref: [REQ-13]*

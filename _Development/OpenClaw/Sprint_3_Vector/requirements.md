# Requirements: Sprint 3 (Hybrid Vector Archive)

## [REQ-10] Uniform Vector Persistence (sqlite-vec)
The Librarian must utilize the `sqlite-vec` extension to store 768-dimension embeddings in `factory.db`.
- Constraint: Use `nomic-embed-text` for ALL embeddings (Local and Cloud routes) to ensure a single, consistent virtual table.
- Status: Mandatory [cite: Spec 5.2]

## [REQ-11] Hybrid Safety Distillation Engine
Implement a routing engine (`SafetyDistillationEngine`) that selects the Scrubber LLM based on data sensitivity.
- **Sensitive (is_sensitive=True)**: Local CPU-optimized LLM (`nn-tsuzu/lfm2.5-1.2b-instruct` via Ollama).
- **Non-Sensitive (is_sensitive=False)**: Cloud-based LLM (`gemini-3.1-flash-lite-preview`).
- Status: Critical

## [REQ-12] Normalized Output Schema
Regardless of the engine used, the distillation result must follow a strict JSON schema:
`{"facts": ["fact1", "fact2"], "scrubbed_log": "neutralized content"}`.
- Status: Mandatory

## [REQ-13] Semantic Search (Faint Paths)
The Architect must be able to retrieve "Faint Paths" (top-k semantic matches) from the distilled archive using cosine similarity.
- Status: Mandatory [cite: Spec 3.0]

## [REQ-14] Hardware Constraint (W540 Alignment)
The local route must be optimized for CPU execution. The `lfm2.5-1.2b-instruct` model is selected for its high performance-to-RAM ratio on ThinkPad W540 hardware.
- Status: Mandatory

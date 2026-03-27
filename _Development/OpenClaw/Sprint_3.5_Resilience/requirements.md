# Requirements: Sprint 3.5 (Lifecycle & Resilience)

## [REQ-15] Dependency Tracking in SQLite
The system must track agent-to-pipeline relationships to prevent accidental deletion of shared resources.
- Status: Mandatory
- Baseline: Spec v1.3 [cite: 5.1]

## [REQ-16] Safe Pipeline Teardown (Garbage Collection)
The Architect must be able to decommission a pipeline and its associated agents/skills while ensuring "is_system" agents and shared components are preserved.
- Status: Mandatory [cite: 6.0]

## [REQ-17] Network Resilience (urllib timeouts)
To prevent zombie Python processes on the ThinkPad W540, all network calls to Ollama and Gemini must have hard timeouts.
- Implementation: Use `urllib.request.urlopen(req, timeout=30.0)`.
- Status: Critical

## [REQ-18] Context Window Protection (Middle-Truncate)
To prevent OOM or Context Window crashes in the Scrubber LLM (lfm2.5-1.2b), raw logs exceeding 12,000 characters must be safely truncated before distillation.
- Logic: Keep the first 6,000 and the last 6,000 characters.
- Status: Critical

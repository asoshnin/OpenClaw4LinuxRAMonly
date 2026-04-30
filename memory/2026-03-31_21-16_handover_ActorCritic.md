# Handover Notes (2026-03-31 21:16) - Actor-Critic Workflow

## Current State
The major initiative to upgrade the `Agentic Factory` document improvement pipeline is complete. We successfully transitioned the architecture from a brittle, chunk-based editing model to a robust, **Full-Context / Delta-Write** Actor-Critic-Evaluator loop. 

The pipeline now utilizes a sophisticated `JSON Bounding Box` mechanism (inspired by human manual editing) where the LLM provides specific `start_fragment` and `end_fragment` anchors to surgically insert, replace, or delete text without modifying the surrounding Markdown structure.

## Key Accomplishments
1. **Mechanical Safeguards Implemented:**
   - **No-Op Guard:** Rejecting edits if anchors aren't 100% unique.
   - **Strict-First & Whitespace-Agnostic Matching:** Handling LLM spacing hallucinations safely.
   - **Lazy-Patch & Length Ratio Detection:** Catching and rejecting LLM shortcuts (e.g., `// existing code`).
   - **Intentional Deletion Bypass:** Allowing massive text deletions when specifically flagged with `<INTENTIONAL_DELETION/>`.
   - **Header Locking:** Forbidding the LLM from renaming `##` headers to protect document stitching.

2. **Architectural Upgrades:**
   - **The Split Actor:** Divided the editing role into a `Strategist` (Pro-tier model for reasoning/drafting) and a `Splicer` (Flash-tier model for mechanical JSON diff generation).
   - **Atomic Patch Rejection:** Scrapped the "all-or-nothing" global rollback. The pipeline now evaluates each patch individually, discarding only those that degrade the score.
   - **Diff Retry Loop:** Built a 3-attempt micro-loop that sends validation errors (e.g., "Anchor not unique") back to the Splicer, allowing it to autonomously heal its own formatting mistakes.
   - **JSON Self-Healing:** Integrated the existing `parse_json_with_retry` circuit-breaker to survive syntax errors from the Evaluator.

3. **Traceability:**
   - The orchestrator now generates a dedicated run folder for every execution.
   - It outputs a detailed `_AUDIT.md` log containing the Red Team report, Strategist proposals, Splicer JSON, and the exact reasons for any rejected patches, providing 100% transparency.

## Validation
The pipeline was successfully tested against `SYSTEM_PROJECT_The Tuning Layer.md` using the external `QWorld` Red Team recommendations. The pipeline correctly parsed the feedback, triggered the 3-attempt retry loop to fix a bad anchor, applied the valid edits, caught a subsequent global contradiction, and safely rolled back to a **9.0** Golden Master. 

There are no hanging tasks or pending migrations. The `improver_workflow.py` script and the new Agent Prompts (`MultiCriteriaEvaluationAssistant`, `StrategistAgent`, `SplicerAgent`) are production-ready.
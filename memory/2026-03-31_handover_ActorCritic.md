# Handover Notes (2026-03-31) - Actor-Critic Loop Upgrade

## Current State
The Actor-Critic-Evaluator loop (Sprint 12) has been fully upgraded to use a **JSON Bounding Box (Start/End Fragment)** editing mechanism instead of the fragile Aider-style diff blocks. 

This change was inspired by your highly effective manual LLM prompting strategy. By forcing the Splicer to identify unique, single-line "Start" and "End" strings (or a single "Anchor" string for insertions), we completely eliminate the massive failure rates caused by LLMs hallucinating newlines (`\n`), indentations, or intermediate text in standard `SEARCH` blocks.

## What Was Changed Tonight:
1. **`workspace/SplicerAgent.md`**: Rewritten. The agent no longer outputs `<diff>...<<<< SEARCH...` blocks. It now outputs a strict JSON array containing `{action: "replace/insert/delete"}` and the single-line string fragments.
2. **`openclaw_skills/orchestrator/delta_improver_workflow.py`**:
   - Ripped out the old complex regex chunk extractor.
   - Added `parse_splicer_edits()` which uses the native `self_healing.py` parser to safely extract the JSON array.
   - Replaced `apply_diffs_in_memory` with `apply_bounding_box_edits`.
3. **Pre-Flight Batch Validation (All-or-Nothing)**:
   - Added the "Cohesive Batch Validation" safeguard we discussed. The orchestrator iterates through the JSON array and checks `.find()` on every single fragment.
   - If *even one* fragment is not found or is not perfectly unique, the script immediately prints an error and **rejects the entire batch**. It will not apply a partial edit, guaranteeing we never end up with a "Frankenstein" document where Section 1 was patched but Section 2 failed.

---

## 🚨 PENDING UPGRADE: The Mechanical Diff Retry Loop (Identified by Red Team)
During the final Red Team audit of the night, a critical fragility was discovered in the new JSON Bounding Box mechanism. Currently, if the Splicer picks a `start_fragment` that is not 100% unique (or has a tiny typo), the Pre-Flight Validation correctly throws a `ValueError` and safely aborts the entire loop. 

**The Flaw:** The script just gives up. It does not send the error back to the Splicer to let it fix the mistake.

### How to Implement the Fix (Next Session):
To make the pipeline truly resilient, the following "Mechanical Repair Loop" must be implemented tomorrow:

#### 1. Update `workspace/SplicerAgent.md`
Add a "Troubleshooting Guidelines" section to the system prompt telling the Splicer exactly how to react to validation errors:
*   *If an error says "Not Unique":* Expand the `start_fragment` or `end_fragment` to include more words from the same continuous line to guarantee uniqueness.
*   *If an error says "Not Found":* Check for typos or hallucinations and pick a completely different, verbatim string from the source text.

#### 2. Create `repair_splicer_diffs()` in Python
In `openclaw_skills/orchestrator/delta_improver_workflow.py`, write a new function that takes the `rejected` error messages (e.g., "Start fragment not unique: 'The laptop...'") and sends them back to the Splicer model alongside the original document and the Strategist's proposals.
```python
def repair_splicer_diffs(original_text, strategist_proposal, errors):
    # Construct a prompt saying: "Your previous JSON failed for these reasons: {errors}. 
    # Re-generate the JSON edits using longer, strictly unique fragments."
    # Call Inference
    return new_json_text
```

#### 3. Wrap Step [5] in a 3-Attempt Micro-Loop
Inside `run_delta_improvement_loop`, wrap the Splicer generation and Pre-Flight Validation in a `for attempt in range(1, 4):` block:
1. Splicer generates JSON edits.
2. `apply_bounding_box_edits` runs the Pre-Flight check.
3. If no errors: `break` the micro-loop and proceed to Document Stitching & Evaluation.
4. If errors occur (`rejected` is populated):
   * Do NOT abort the main loop yet.
   * Print `"[!] Attempt {attempt}/3: Anchor Validation Failed. Sending errors back to Splicer for repair..."`
   * Call `repair_splicer_diffs()` with the exact error strings.
   * Loop and try parsing the repaired JSON on Attempt 2.
5. If the Splicer fails 3 times in a row, *then* log a `[FATAL]` error, retain the original document, and gracefully abort the entire pipeline.

## Next Steps for Tomorrow:
The codebase is currently stable and patched with the V1 Bounding Box logic. 

**First action tomorrow:** Implement the 3-Step "Mechanical Diff Retry Loop" detailed above into `delta_improver_workflow.py` and `SplicerAgent.md`. Once implemented and tested, the pipeline will be invincible to LLM formatting/anchoring hallucinations.

Have a good night!
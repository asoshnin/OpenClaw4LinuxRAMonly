import os

code = r"""import os
import re
import json
import shutil
import logging
import argparse
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from openclaw_skills.librarian.self_healing import parse_json_with_retry
from openclaw_skills.config import call_inference, LOCAL_MODEL

log = logging.getLogger(__name__)

# =============================================================================
# PHASE 2: DELTA-WRITE APPLICATOR & MECHANICAL SAFEGUARDS (JSON BOUNDING BOX)
# =============================================================================

def parse_splicer_edits(text: str) -> list[dict]:
    \"\"\"Extracts the JSON array of edits from the Splicer output.\"\"\"
    try:
        def _parse_fix(p):
            res = p.strip()
            if res.startswith("```json"): res = res[7:]
            elif res.startswith("```"): res = res[3:]
            if res.endswith("```"): res = res[:-3]
            return res.strip()
            
        res_cleaned = _parse_fix(text)
        
        # Try direct load first
        try:
            return json.loads(res_cleaned)
        except json.JSONDecodeError:
            # Fallback to LLM self-healing
            def _llm_repair(broken_text):
                return call_inference(tier="cloud", model="gemini-3-flash-preview", prompt=broken_text)
            
            edits = parse_json_with_retry(res_cleaned, _llm_repair, max_retries=1)
            if isinstance(edits, list):
                return edits
            elif isinstance(edits, dict) and "edits" in edits:
                return edits["edits"]
            return []
    except Exception as e:
        log.warning(f"Failed to parse Splicer JSON: {e}")
        return []

def apply_bounding_box_edits(document: str, edits: list[dict]) -> tuple[str, list, list]:
    \"\"\"
    Safely applies JSON Bounding Box patches to the document buffer using Reverse-Index patching.
    Implements Pre-Flight Cohesive Batch Validation: If ONE edit fails to anchor, the ENTIRE BATCH is rejected.
    \"\"\"
    valid_patches = []
    rejected = []

    # 1. Pre-Flight Anchor Validation
    for i, edit in enumerate(edits):
        action = edit.get("action")
        
        try:
            if action in ["replace", "delete"]:
                sf = edit.get("start_fragment", "")
                ef = edit.get("end_fragment", "")
                
                if document.count(sf) != 1:
                    raise ValueError(f"Start fragment not unique or missing: '{sf}'")
                if document.count(ef) != 1:
                    raise ValueError(f"End fragment not unique or missing: '{ef}'")
                    
                s_idx = document.find(sf)
                e_idx_start = document.find(ef, s_idx)
                if e_idx_start == -1:
                    raise ValueError(f"End fragment found, but not after the start fragment.")
                    
                e_idx = e_idx_start + len(ef)
                new_text = edit.get("new_text", "") if action == "replace" else ""
                
                # Strip special tags
                new_text = new_text.replace("<INTENTIONAL_DELETION/>", "").strip()
                
                valid_patches.append({
                    "start": s_idx, "end": e_idx, "new_text": new_text, "original_idx": i, "edit": edit
                })
                
            elif action == "insert":
                af = edit.get("anchor_fragment", "")
                pos = edit.get("position", "after")
                
                if document.count(af) != 1:
                    raise ValueError(f"Anchor fragment not unique or missing: '{af}'")
                    
                idx = document.find(af)
                if pos == "after":
                    idx += len(af)
                    
                new_text = edit.get("new_text", "").replace("<INTENTIONAL_DELETION/>", "").strip()
                valid_patches.append({
                    "start": idx, "end": idx, "new_text": new_text, "original_idx": i, "edit": edit
                })
            else:
                raise ValueError(f"Unknown action: '{action}'")
                
        except ValueError as e:
            log.warning(f"Edit #{i+1} REJECTED during Pre-Flight: {e}")
            rejected.append({"edit": edit, "reason": str(e)})

    # COHESIVE BATCH VALIDATION (ALL-OR-NOTHING PRE-FLIGHT)
    if rejected:
        return document, [], rejected

    # 2. Sort patches in reverse index order
    valid_patches.sort(key=lambda x: x['start'], reverse=True)

    # 3. Apply patches
    current_doc = document
    applied = []
    last_start_idx = float('inf')

    for patch in valid_patches:
        start_idx = patch['start']
        end_idx = patch['end']
        
        if end_idx > last_start_idx:
            msg = f"Overlap Collision: Patch overlaps with a previously applied patch."
            rejected.append({"edit": patch['edit'], "reason": msg})
            return document, [], rejected

        current_doc = current_doc[:start_idx] + patch['new_text'] + current_doc[end_idx:]
        applied.append(patch['edit'])
        last_start_idx = start_idx

    applied.reverse()
    return current_doc, applied, []

# =============================================================================
# PHASE 3: THE DELTA-WRITE LOOP (FULL CONTEXT INTEGRATION)
# =============================================================================

def load_agent_prompt(agent_name: str) -> str:
    workspace = os.environ.get("OPENCLAW_WORKSPACE", "/home/alexey/openclaw-inbox/agentic_factory/workspace")
    path = os.path.join(workspace, f"{agent_name}.md")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return ""

def run_evaluation(text: str) -> dict:
    sys_prompt = load_agent_prompt("MultiCriteriaEvaluationAssistant")
    full_prompt = f"{sys_prompt}\n\nEVALUATE THIS ARTIFACT:\n{text}"
    
    def _call(p):
        res = call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=p).strip()
        if res.startswith("```json"): res = res[7:]
        elif res.startswith("```"): res = res[3:]
        if res.endswith("```"): res = res[:-3]
        return res.strip()
        
    try:
        return parse_json_with_retry(full_prompt, _call, max_retries=2)
    except Exception as e:
        log.error(f"Evaluator parsing failed: {e}")
        return {"raw_weighted_average": 0.0, "capped_weighted_average": 0.0}

def run_red_team(text: str) -> str:
    prompt = f"You are the Red Team Auditor. Audit this document for security, logic, and clarity. List critical findings.\n\n{text}"
    return call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=prompt)

def run_strategist(text: str, red_team_report: str) -> str:
    sys_prompt = load_agent_prompt("StrategistAgent")
    prompt = f"{sys_prompt}\n\n=== ORIGINAL DOCUMENT ===\n{text}\n\n=== RED TEAM AUDIT ===\n{red_team_report}"
    return call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=prompt)

def run_splicer(text: str, strategy: str) -> str:
    sys_prompt = load_agent_prompt("SplicerAgent")
    prompt = f"{sys_prompt}\n\n=== ORIGINAL DOCUMENT ===\n{text}\n\n=== STRATEGIST PROPOSALS ===\n{strategy}"
    return call_inference(tier="cloud", model="gemini-3-flash-preview", prompt=prompt)

def repair_splicer_diffs(original_text: str, strategist_proposal: str, errors: list[dict]) -> str:
    \"\"\"Sends validation errors back to the Splicer for re-anchoring.\"\"\"
    sys_prompt = load_agent_prompt("SplicerAgent")
    error_report = "\n".join([f"- {e['reason']}" for e in errors])
    
    prompt = f\"\"\"{sys_prompt}
    
    === FAILURE REPORT ===
    Your previous JSON edits failed validation for the following reasons:
    {error_report}
    
    === ORIGINAL DOCUMENT ===
    {original_text}
    
    === STRATEGIST PROPOSALS ===
    {strategist_proposal}
    
    INSTRUCTIONS:
    Re-generate the JSON edits. Ensure all fragments are UNIQUE and exist VERBATIM in the original document. 
    If a fragment was 'not unique', choose a longer or more specific fragment from the same line.
    \"\"\"
    return call_inference(tier="cloud", model="gemini-3-flash-preview", prompt=prompt)

def run_delta_improvement_loop(file_path: str, target_score: float = 8.0, max_loops: int = 3, feedback_file: str = None):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    base_name = os.path.basename(file_path)
    name_no_ext, ext = os.path.splitext(base_name)
    
    run_dir_name = f"ImprovementRun_{name_no_ext}_{timestamp}"
    run_dir = os.path.join(os.path.dirname(file_path), run_dir_name)
    os.makedirs(run_dir, exist_ok=True)
    print(f"Created run directory: {run_dir}")

    with open(file_path, 'r', encoding='utf-8') as f:
        current_text = f.read()

    print("\n[1] Running Baseline Evaluation...")
    base_eval = run_evaluation(current_text)
    current_raw = base_eval.get("raw_weighted_average", 0.0)
    current_capped = base_eval.get("capped_weighted_average", 0.0)
    print(f"Baseline - Raw: {current_raw}, Capped: {current_capped}")

    baseline_file = os.path.join(run_dir, f"{name_no_ext}_BASELINE_score_{current_raw}{ext}")
    with open(baseline_file, 'w', encoding='utf-8') as f:
        f.write(current_text)

    if current_capped >= target_score:
        print("Target already met. Exiting.")
        return

    for loop in range(1, max_loops + 1):
        print(f"\n=== Delta Improvement Loop {loop}/{max_loops} ===")
        
        if loop == 1 and feedback_file and os.path.exists(feedback_file):
            print("[2] Bypassing Internal Red Team. Using External Feedback...")
            with open(feedback_file, 'r', encoding='utf-8') as ff:
                active_feedback = ff.read()
        else:
            print("[2] Running Internal Red Team Audit...")
            active_feedback = run_red_team(current_text)

        print("[3] Strategist Pass (Pro-Tier)...")
        strategy = run_strategist(current_text, active_feedback)

        print("[4] Splicer Pass (Flash-Tier) generating Diffs...")
        diffs_text = run_splicer(current_text, strategy)
        
        diff_retry_limit = 3
        applied, rejected = [], []

        for attempt in range(1, diff_retry_limit + 1):
            diff_blocks = parse_splicer_edits(diffs_text)
            if not diff_blocks:
                print(f"    [!] Attempt {attempt}: No valid JSON found.")
                break

            print(f"    -> Splicer generated {len(diff_blocks)} edits (Attempt {attempt}).")
            new_text, applied, rejected = apply_bounding_box_edits(current_text, diff_blocks)
            
            if not rejected:
                print(f"    [+] Pre-Flight Validation Passed!")
                break
                
            print(f"    [!] Attempt {attempt}: {len(rejected)} anchors failed. Requesting repair...")
            if attempt < diff_retry_limit:
                diffs_text = repair_splicer_diffs(current_text, strategy, rejected)

        audit_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_AUDIT.md")
        with open(audit_file, 'w', encoding='utf-8') as f:
            f.write(f"# Loop {loop} Audit Log\n\n## Feedback Source\n{active_feedback}\n\n## Strategist Proposals\n{strategy}\n\n## Splicer Output\n{diffs_text}\n")

        if rejected or not applied:
            print("Batch validation failed. Aborting loop.")
            break

        print("\n[6] Running Global Validation...")
        new_eval = run_evaluation(new_text)
        new_raw = new_eval.get("raw_weighted_average", 0.0)
        new_capped = new_eval.get("capped_weighted_average", 0.0)
        
        print(f"New Global Eval - Raw: {new_raw}, Capped: {new_capped}")

        delta = new_raw - current_raw
        if delta <= 0.2:
            print(f"\n[!] Stagnation Break: Delta ({delta:.2f}) <= 0.2.")
            rej_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_REJECTED_score_{new_raw}{ext}")
            with open(rej_file, 'w', encoding='utf-8') as f:
                f.write(new_text)
            break
        
        print(f"\n[+] Success! Improved by {delta:.2f}.")
        current_text = new_text
        current_raw = new_raw
        current_capped = new_capped
        
        acc_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_ACCEPTED_score_{new_raw}{ext}")
        with open(acc_file, 'w', encoding='utf-8') as f:
            f.write(current_text)

        if current_capped >= target_score:
            print(f"\n✅ Target {target_score} reached.")
            break

    print("\nPipeline finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delta-Write Applicator")
    parser.add_argument("file", help="Path to markdown file")
    parser.add_argument("--target", type=float, default=8.0, help="Target score")
    parser.add_argument("--feedback", type=str, default=None, help="Path to feedback")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run_delta_improvement_loop(args.file, args.target, feedback_file=args.feedback)
"""

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)

import os
import re
import json
import logging
import argparse
import shutil
from datetime import datetime

import sys
# Ensure imports work from skills dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from openclaw_skills.config import call_inference
from openclaw_skills.librarian.self_healing import parse_json_with_retry

log = logging.getLogger(__name__)

# CONFIG OVERRIDE
MODEL_PRO = "gemini-3.1-pro-preview"
MODEL_FLASH = "gemini-3-flash-preview"

# =============================================================================
# PHASE 2: DELTA-WRITE APPLICATOR & MECHANICAL SAFEGUARDS
# =============================================================================

def extract_diff_blocks(text: str) -> list[dict]:
    """
    Safely extract <<<< SEARCH ... ==== ... >>>> REPLACE sequences via regex.
    Ignores conversational padding outside the blocks.
    """
    blocks = []
    pattern = r'<<<< SEARCH\n(.*?)\n====\n(.*?)\n>>>> REPLACE'
    matches = re.finditer(pattern, text, re.DOTALL)
    for m in matches:
        blocks.append({
            "search": m.group(1),
            "replace": m.group(2)
        })
    return blocks


def find_unique_match(search_block: str, document: str) -> tuple[int, int]:
    """
    Locates the exact start/end index of the search_block in the document.
    Safeguard 1: Strict-First matching.
    Safeguard 2: Whitespace-Agnostic fallback.
    Safeguard 3: No-Op Guard (Raises ValueError if matches != 1).
    """
    count = document.count(search_block)
    if count == 1:
        idx = document.find(search_block)
        return idx, idx + len(search_block)
    elif count > 1:
        raise ValueError(f"No-Op Guard [Strict]: Collision! Found {count} exact matches for SEARCH block.")

    log.debug("Strict match failed. Falling back to whitespace-agnostic search.")
    
    escaped_search = re.escape(search_block)
    pattern_str = re.sub(r'(\\[\sntr])+', r'\\s+', escaped_search)
    
    try:
        regex = re.compile(pattern_str, re.MULTILINE)
        matches = list(regex.finditer(document))
    except re.error as e:
        raise ValueError(f"Regex compilation failed during whitespace fallback: {e}")

    if len(matches) == 1:
        return matches[0].start(), matches[0].end()
    elif len(matches) > 1:
        raise ValueError(f"No-Op Guard [Whitespace]: Collision! Found {len(matches)} fuzzy matches for SEARCH block.")
    else:
        raise ValueError("No-Op Guard: SEARCH block not found in document (0 matches).")


def detect_lazy_patch(search_block: str, replace_block: str):
    """
    Scans the REPLACE block for lazy LLM shortcuts.
    Safeguard 4: Lazy Pattern Detection.
    Safeguard 5: Length Ratio Check.
    """
    lazy_patterns = [r'\.\.\.', r'\[existing code\]', r'existing code remains', r'rest of section', r'same as above']
    for p in lazy_patterns:
        if re.search(p, replace_block, re.IGNORECASE):
            raise ValueError(f"Lazy Patch Detected: Found forbidden trigger '{p}' in REPLACE block.")
            
    s_len = len(search_block.strip())
    r_len = len(replace_block.strip())
    
    if s_len > 50 and r_len > 0:
        if r_len < (s_len * 0.2):
            raise ValueError(f"Length Ratio Failed: REPLACE block is suspiciously short ({r_len} chars vs {s_len} chars).")


def apply_diffs_in_memory(document: str, diff_blocks: list) -> tuple[str, list, list]:
    """
    Sequentially applies a list of diff patches to the document buffer.
    Returns (patched_document, applied_diffs, rejected_diffs).
    """
    current_doc = document
    applied = []
    rejected = []

    for i, diff in enumerate(diff_blocks):
        search_block = diff['search']
        replace_block = diff['replace']

        try:
            detect_lazy_patch(search_block, replace_block)
            start_idx, end_idx = find_unique_match(search_block, current_doc)
            
            current_doc = current_doc[:start_idx] + replace_block + current_doc[end_idx:]
            applied.append(diff)
            log.info(f"Diff #{i+1} applied successfully.")
            
        except ValueError as e:
            log.warning(f"Diff #{i+1} REJECTED: {e}")
            rejected.append({"diff": diff, "reason": str(e)})

    return current_doc, applied, rejected

# =============================================================================
# PHASE 3: THE DELTA-WRITE LOOP (FULL CONTEXT INTEGRATION)
# =============================================================================

def load_agent_prompt(agent_name: str) -> str:
    paths = [
        os.path.join(os.environ.get("OPENCLAW_WORKSPACE", "/home/alexey/.openclaw/workspace"), f"{agent_name}.md"),
        os.path.join("/home/alexey/.openclaw/workspace", f"{agent_name}.md"),
        os.path.join("/home/alexey/openclaw-inbox/agentic_factory/workspace", f"{agent_name}.md")
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()
    return ""

def run_evaluation(text: str) -> dict:
    sys_prompt = load_agent_prompt("MultiCriteriaEvaluationAssistant")
    full_prompt = f"{sys_prompt}\n\nEVALUATE THIS ARTIFACT:\n{text}"
    
    def _call(p):
        res = call_inference(tier="cloud", model=MODEL_PRO, prompt=p).strip()
        if res.startswith("```json"): res = res[7:]
        elif res.startswith("```"): res = res[3:]
        if res.endswith("```"): res = res[:-3]
        return res.strip()
        
    try:
        initial_response = _call(full_prompt)
        return parse_json_with_retry(initial_response, _call, max_retries=2)
    except Exception as e:
        log.error(f"Evaluator parsing failed: {e}")
        return {"raw_weighted_average": 0.0, "capped_weighted_average": 0.0}

def run_red_team(text: str) -> str:
    prompt = f"You are the Red Team Auditor. Audit this document for security, logic, and clarity. List critical findings.\n\n{text}"
    return call_inference(tier="cloud", model=MODEL_PRO, prompt=prompt)

def run_strategist(text: str, red_team_report: str) -> str:
    sys_prompt = load_agent_prompt("StrategistAgent")
    prompt = f"{sys_prompt}\n\n=== ORIGINAL DOCUMENT ===\n{text}\n\n=== RED TEAM AUDIT ===\n{red_team_report}"
    return call_inference(tier="cloud", model=MODEL_PRO, prompt=prompt)

def run_splicer(text: str, strategy: str) -> str:
    sys_prompt = load_agent_prompt("SplicerAgent")
    prompt = f"{sys_prompt}\n\n=== ORIGINAL DOCUMENT ===\n{text}\n\n=== STRATEGIST PROPOSALS ===\n{strategy}"
    return call_inference(tier="cloud", model=MODEL_FLASH, prompt=prompt)

def run_delta_improvement_loop(file_path: str, target_score: float = 8.0, max_loops: int = 3):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    base, ext = os.path.splitext(file_path)
    work_file = f"{base}_{timestamp}{ext}"
    shutil.copy2(file_path, work_file)
    print(f"Created working copy: {work_file}")

    with open(work_file, 'r', encoding='utf-8') as f:
        current_text = f.read()

    print("\n[1] Running Baseline Evaluation...")
    base_eval = run_evaluation(current_text)
    current_raw = base_eval.get("raw_weighted_average", 0.0)
    current_capped = base_eval.get("capped_weighted_average", 0.0)
    print(f"Baseline - Raw: {current_raw}, Capped: {current_capped}")

    if current_capped >= target_score:
        print("Target already met. Exiting.")
        return

    for loop in range(1, max_loops + 1):
        print(f"\n=== Delta Improvement Loop {loop}/{max_loops} ===")
        
        print("[2] Running Red Team Audit (Full Context)...")
        red_team_report = run_red_team(current_text)

        print("[3] Strategist Pass (Pro-Tier)...")
        strategy = run_strategist(current_text, red_team_report)

        print("[4] Splicer Pass (Flash-Tier) generating Diffs...")
        diffs_text = run_splicer(current_text, strategy)
        
        diff_blocks = extract_diff_blocks(diffs_text)
        print(f"    -> Splicer generated {len(diff_blocks)} SEARCH/REPLACE blocks.")
        
        if not diff_blocks:
            print("No valid diff blocks found. Aborting loop.")
            break

        print("[5] Applying Diffs in Memory (Mechanical Safeguards)...")
        new_text, applied, rejected = apply_diffs_in_memory(current_text, diff_blocks)
        
        print(f"    -> Applied: {len(applied)}, Rejected: {len(rejected)}")
        if not applied:
            print("All diffs rejected by safeguards. Aborting loop to prevent degradation.")
            break

        print("[6] Running Consistency Check & Global Validation...")
        new_eval = run_evaluation(new_text)
        new_raw = new_eval.get("raw_weighted_average", 0.0)
        new_capped = new_eval.get("capped_weighted_average", 0.0)
        
        print(f"New Eval - Raw: {new_raw}, Capped: {new_capped}")

        delta = new_raw - current_raw
        if delta <= 0.2:
            print(f"\n[!] Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")
            print("Rolling back batch patch to previous best version and aborting loop.")
            break
        
        print(f"\n[+] Global validation passed! Raw score improved by {delta:.2f}.")
        current_text = new_text
        current_raw = new_raw
        current_capped = new_capped
        with open(work_file, 'w', encoding='utf-8') as f:
            f.write(current_text)

        if current_capped >= target_score:
            print(f"\n✅ Success! Target capped score {target_score} reached.")
            break

    print("\nPipeline finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delta-Write Applicator")
    parser.add_argument("file", help="Path to markdown file")
    parser.add_argument("--target", type=float, default=8.0, help="Target capped score")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    run_delta_improvement_loop(args.file, args.target)

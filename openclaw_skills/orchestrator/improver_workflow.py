import os
import re
import json
import logging
import argparse
import shutil
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from openclaw_skills.config import call_inference
from openclaw_skills.librarian.self_healing import parse_json_with_retry

log = logging.getLogger(__name__)

# =============================================================================
# ACTOR-CRITIC-EVALUATOR WORKFLOW
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

def extract_frontmatter_and_h1(text: str) -> tuple[str, str]:
    """Safely extracts YAML frontmatter and H1 title. Returns (frontmatter_h1, remaining_text)."""
    frontmatter = ""
    remaining = text
    
    yaml_match = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if yaml_match:
        frontmatter = yaml_match.group(0)
        remaining = text[yaml_match.end():]
        
    h1_match = re.match(r'^\s*(# [^\n]+)\n+', remaining)
    if h1_match:
        frontmatter += "\n" + h1_match.group(0) + "\n"
        remaining = remaining[h1_match.end():]
        
    return frontmatter.strip(), remaining.strip()

def recursive_chunk_markdown(text: str, max_chunks: int = 50, token_limit: int = 2000) -> list[dict]:
    """Safely extracts YAML/H1, splits by H2, falls back to H3. Enforces a max-chunk limit."""
    front, body = extract_frontmatter_and_h1(text)
    chunks = []
    
    h2_sections = re.split(r'(?=\n## )', "\n" + body)
    
    for section in h2_sections:
        if not section.strip():
            continue
        
        estimated_tokens = len(section) // 4
        
        if estimated_tokens > token_limit:
            h3_sections = re.split(r'(?=\n### )', section)
            for sub_sec in h3_sections:
                if sub_sec.strip():
                    lines = sub_sec.strip().split('\n')
                    header = lines[0] if lines[0].startswith('#') else ""
                    chunks.append({"header": header, "content": sub_sec.strip()})
        else:
            lines = section.strip().split('\n')
            header = lines[0] if lines[0].startswith('#') else ""
            chunks.append({"header": header, "content": section.strip()})
            
    # Fallback for headerless text blocks that are just paragraphs
    if len(chunks) == 1 and estimated_tokens > token_limit:
        paragraphs = [p.strip() for p in body.split('\n\n') if p.strip()]
        chunks = [{"header": "", "content": p} for p in paragraphs]

    if len(chunks) > max_chunks:
        raise ValueError(f"Max-Chunk limit exceeded: {len(chunks)} chunks (limit {max_chunks}).")
        
    if front:
        chunks.insert(0, {"header": "FRONTMATTER_H1", "content": front})
        
    return chunks

def extract_toc(text: str) -> str:
    headers = re.findall(r'^(#{1,4})\s+(.+)$', text, re.MULTILINE)
    toc = []
    for level, name in headers:
        indent = "  " * (len(level) - 1)
        toc.append(f"{indent}- {name}")
    return "\n".join(toc)

def extract_global_context(text: str) -> dict:
    toc = extract_toc(text)
    prompt = f"You are a summarization assistant. Provide a very concise, 3-sentence high-level summary of the following document to be used as global context for editors.\n\n{text[:4000]}"
    summary = call_inference(tier="cloud", model="gemini-3-flash-preview", prompt=prompt)
    return {"summary": summary.strip(), "toc": toc}

def map_findings_to_chunks(global_findings: str, chunks: list, global_context: dict) -> dict:
    headers = [c['header'] for c in chunks if c['header'] and c['header'] != "FRONTMATTER_H1"]
    prompt = f"""You map feedback to headers. Output only JSON.
Map Red Team findings to specific headers. Output strict JSON mapping headers to specific feedback strings. If it doesn't fit, map to 'GLOBAL'.
Headers: {json.dumps(headers)}
Findings:
{global_findings}"""
    
    def _llm_call(p):
        res = call_inference(tier="cloud", model="gemini-3-flash-preview", prompt=p).strip()
        if res.startswith("```json"): res = res[7:]
        elif res.startswith("```"): res = res[3:]
        if res.endswith("```"): res = res[:-3]
        return res.strip()
        
    try:
        return parse_json_with_retry(prompt, _llm_call, max_retries=2)
    except Exception as e:
        log.warning(f"Failed to map findings cleanly: {e}")
        return {}

def run_improvement_loop(file_path: str, target_score: float = 8.0, max_loops: int = 3):
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

    improver_prompt_sys = load_agent_prompt("BlockImproverAgent")

    for loop in range(1, max_loops + 1):
        print(f"\n=== Improvement Loop {loop}/{max_loops} ===")
        
        print("[2] Running Red Team Audit...")
        global_findings = run_red_team(current_text)

        print("[3] Extracting Global Context & Chunking...")
        chunks = recursive_chunk_markdown(current_text)
        global_context = extract_global_context(current_text)
        mapped_feedback = map_findings_to_chunks(global_findings, chunks, global_context)

        new_chunks = []
        applied_count = 0

        for chunk in chunks:
            if chunk['header'] == "FRONTMATTER_H1":
                new_chunks.append(chunk['content'])
                continue

            print(f"  -> Processing Chunk: {chunk['header'][:40]}...")
            feedback = mapped_feedback.get(chunk['header'], global_findings)
            
            prompt = f"GLOBAL SUMMARY:\n{global_context.get('summary')}\n\nTOC:\n{global_context.get('toc')}\n\nFEEDBACK:\n{feedback}\n\nCHUNK TO IMPROVE:\n{chunk['content']}"
            
            improved_output = call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=f"{improver_prompt_sys}\n\n{prompt}")
            
            if "<no_change/>" in improved_output:
                print("     (No change requested)")
                new_chunks.append(chunk['content'])
                continue
                
            match = re.search(r'<improved_content>(.*?)</improved_content>', improved_output, re.DOTALL)
            if match:
                new_content = match.group(1).strip()
                # HEADER INTEGRITY CHECK
                if chunk['header'] and not new_content.startswith(chunk['header']):
                    print(f"     [!] WARNING: Header Integrity Check failed! Expected '{chunk['header']}'. Rejecting chunk edit.")
                    new_chunks.append(chunk['content'])
                else:
                    print("     (Chunk improved successfully)")
                    new_chunks.append(new_content)
                    applied_count += 1
            else:
                print("     [!] Warning: XML tags missing. Rejecting chunk.")
                new_chunks.append(chunk['content'])

        if applied_count == 0:
            print("All edits rejected or no changes made. Aborting loop to prevent degradation.")
            break

        print("\n[4] Stitching & Running Global Validation...")
        new_text = "\n\n".join(new_chunks)
        new_eval = run_evaluation(new_text)
        new_raw = new_eval.get("raw_weighted_average", 0.0)
        new_capped = new_eval.get("capped_weighted_average", 0.0)
        
        print(f"New Eval - Raw: {new_raw}, Capped: {new_capped}")

        # Rollback & Stagnation Logic
        delta = new_raw - current_raw
        
        audit_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_AUDIT.md")
        with open(audit_file, 'w', encoding='utf-8') as f:
            f.write(f"# Loop {loop} Audit Log\n\n## Red Team Report\n{global_findings}\n")
            f.write(f"\n## Evaluation\nRaw Score: {new_raw}\nCapped Score: {new_capped}\nDelta: {delta}\n")
            f.write(f"Justification: {json.dumps(new_eval.get('justification', {}), indent=2)}\n")

        if delta <= 0.2:
            print(f"\n[!] Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")
            print("Rolling back to previous best version and aborting loop.")
            rej_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_REJECTED_score_{new_raw}{ext}")
            with open(rej_file, 'w', encoding='utf-8') as f:
                f.write(new_text)
            break
        
        print(f"\n[+] Global validation passed! Raw score improved by {delta:.2f}.")
        current_text = new_text
        current_raw = new_raw
        current_capped = new_capped
        
        acc_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_ACCEPTED_score_{new_raw}{ext}")
        with open(acc_file, 'w', encoding='utf-8') as f:
            f.write(current_text)

        if current_capped >= target_score:
            print(f"\n✅ Success! Target capped score {target_score} reached.")
            break

    print("\nPipeline finished.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Improver Workflow")
    parser.add_argument("file", help="Path to markdown file")
    parser.add_argument("--target", type=float, default=8.0, help="Target capped score")
    args = parser.parse_args()
    
    # Configure basic logging to console
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    run_improvement_loop(args.file, args.target)

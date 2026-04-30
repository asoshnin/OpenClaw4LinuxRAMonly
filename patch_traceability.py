import re

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'r') as f:
    code = f.read()

# Replace run_delta_improvement_loop entirely
new_func = """def run_delta_improvement_loop(file_path: str, target_score: float = 8.0, max_loops: int = 3):
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

    print("\\n[1] Running Baseline Evaluation...")
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
        print(f"\\n=== Delta Improvement Loop {loop}/{max_loops} ===")
        
        print("[2] Running Red Team Audit (Full Context)...")
        red_team_report = run_red_team(current_text)

        print("[3] Strategist Pass (Pro-Tier)...")
        strategy = run_strategist(current_text, red_team_report)

        print("[4] Splicer Pass (Flash-Tier) generating Diffs...")
        diffs_text = run_splicer(current_text, strategy)
        
        diff_blocks = extract_diff_blocks(diffs_text)
        print(f"    -> Splicer generated {len(diff_blocks)} SEARCH/REPLACE blocks.")
        
        audit_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_AUDIT.md")
        with open(audit_file, 'w', encoding='utf-8') as f:
            f.write(f"# Loop {loop} Audit Log\\n\\n## Red Team Report\\n{red_team_report}\\n\\n## Strategist Proposals\\n{strategy}\\n\\n## Splicer Output\\n{diffs_text}\\n")

        if not diff_blocks:
            print("No valid diff blocks found. Aborting loop.")
            break

        print("[5] Applying Diffs in Memory (Mechanical Safeguards)...")
        new_text, applied, rejected = apply_diffs_in_memory(current_text, diff_blocks)
        
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(f"\\n## Diff Application\\nApplied: {len(applied)}\\nRejected: {len(rejected)}\\n")
            for r in rejected:
                f.write(f"- Rejected Diff Reason: {r['reason']}\\n")

        print(f"    -> Applied: {len(applied)}, Rejected: {len(rejected)}")
        if not applied:
            print("All diffs rejected by safeguards. Aborting loop to prevent degradation.")
            break

        print("[6] Running Consistency Check & Global Validation...")
        new_eval = run_evaluation(new_text)
        new_raw = new_eval.get("raw_weighted_average", 0.0)
        new_capped = new_eval.get("capped_weighted_average", 0.0)
        
        print(f"New Eval - Raw: {new_raw}, Capped: {new_capped}")
        
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(f"\\n## Evaluation\\nRaw Score: {new_raw}\\nCapped Score: {new_capped}\\nDelta: {new_raw - current_raw}\\n")
            f.write(f"Justification: {json.dumps(new_eval.get('justification', {}), indent=2)}\\n")

        delta = new_raw - current_raw
        if delta <= 0.2:
            print(f"\\n[!] Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")
            print("Rolling back batch patch to previous best version and aborting loop.")
            rej_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_REJECTED_score_{new_raw}{ext}")
            with open(rej_file, 'w', encoding='utf-8') as f:
                f.write(new_text)
            break
        
        print(f"\\n[+] Global validation passed! Raw score improved by {delta:.2f}.")
        current_text = new_text
        current_raw = new_raw
        current_capped = new_capped
        
        acc_file = os.path.join(run_dir, f"{name_no_ext}_Loop{loop}_ACCEPTED_score_{new_raw}{ext}")
        with open(acc_file, 'w', encoding='utf-8') as f:
            f.write(current_text)

        if current_capped >= target_score:
            print(f"\\n✅ Success! Target capped score {target_score} reached.")
            break

    print("\\nPipeline finished.")"""

code = re.sub(r'def run_delta_improvement_loop.*', new_func, code, flags=re.DOTALL)

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)

print("Traceability patch applied.")

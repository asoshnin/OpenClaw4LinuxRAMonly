import re
import os

filepath = '/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py'
with open(filepath, 'r') as f:
    code = f.read()

# 1. Fix Regex Fragility & Lazy Patching in extract_diff_blocks & detect_lazy_patch
# Make the extractor robust to leading/trailing whitespace and optional markdown code blocks
old_extract = r"pattern = r'<<<< SEARCH\s*\n(.*?)\n====\s*\n(.*?)\n>>>> REPLACE\s*'"
new_extract = r"pattern = r'(?:```\w*\n)?<<<< SEARCH\s*\n(.*?)\n====\s*\n(.*?)\n>>>> REPLACE\s*(?:\n```)?'"
code = code.replace(old_extract, new_extract)

# Expand lazy patterns
old_lazy = r"lazy_patterns = \[r'\.\.\.', r'\[existing code\]', r'existing code remains', r'rest of section', r'same as above'\]"
new_lazy = r"lazy_patterns = [r'\.\.\.', r'\[existing code\]', r'existing code remains', r'rest of section', r'same as above', r'//\s*\.\.\.', r'#\s*\.\.\.', r'<!--.*?-->', r'\[\.\.\.\]']"
code = code.replace(old_lazy, new_lazy)

# 2. Implement Granular Score Validation (Atomic Rollback)
# Replace the global evaluation loop with a chunk-level evaluation loop
old_eval_loop = """        print("[6] Running Consistency Check & Global Validation...")
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
            break"""

new_eval_loop = """        print("[6] Running Granular Score Validation (Atomic Rollback)...")
        # Validate each applied patch individually against its baseline chunk
        final_valid_patches = []
        for patch in applied:
            print(f"  -> Validating Patch: {patch['search'][:40]}...")
            
            # Evaluate the baseline chunk
            baseline_chunk_eval = run_evaluation(patch['search'])
            base_score = baseline_chunk_eval.get("raw_weighted_average", 0.0)
            
            # Evaluate the new chunk
            new_chunk_eval = run_evaluation(patch['replace'])
            new_score = new_chunk_eval.get("raw_weighted_average", 0.0)
            
            delta = new_score - base_score
            if delta > 0:
                print(f"     [+] Patch Improved! (Delta: +{delta:.2f})")
                final_valid_patches.append(patch)
            else:
                print(f"     [-] Patch Degraded/Stagnated (Delta: {delta:.2f}). Rejecting.")
                rejected.append({"edit": patch, "reason": f"Failed Granular Validation (Delta: {delta:.2f})"})
        
        # If all patches were rejected during granular validation, abort
        if not final_valid_patches:
            print("\\n[!] Stagnation Break Triggered: No patches improved the score.")
            print("Rolling back all patches and aborting loop.")
            break
            
        # Re-apply ONLY the validated patches to the original text
        print("\\n[7] Stitching Final Validated Document...")
        # Sort back to reverse index order to apply safely
        valid_patches_for_apply = []
        for v in final_valid_patches:
            s_idx, e_idx = find_unique_match(v['search'], current_text)
            valid_patches_for_apply.append({"diff": v, "start": s_idx, "end": e_idx})
        valid_patches_for_apply.sort(key=lambda x: x['start'], reverse=True)
        
        new_text = current_text
        for p in valid_patches_for_apply:
            new_text = new_text[:p['start']] + p['diff']['replace'] + new_text[p['end']:]
            
        print("\\n[8] Running Consistency Check & Global Validation...")
        new_eval = run_evaluation(new_text)
        new_raw = new_eval.get("raw_weighted_average", 0.0)
        new_capped = new_eval.get("capped_weighted_average", 0.0)
        
        print(f"New Global Eval - Raw: {new_raw}, Capped: {new_capped}")
        
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(f"\\n## Evaluation\\nRaw Score: {new_raw}\\nCapped Score: {new_capped}\\nDelta: {new_raw - current_raw}\\n")
            f.write(f"Justification: {json.dumps(new_eval.get('justification', {}), indent=2)}\\n")
            f.write(f"\\n## Final Patch Application\\nApplied: {len(final_valid_patches)}\\nRejected: {len(rejected)}\\n")
            for r in rejected:
                f.write(f"- Rejected Diff Reason: {r['reason']}\\n")

        # Global Stagnation Break
        delta = new_raw - current_raw
        if delta <= 0.2:
            print(f"\\n[!] Global Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")
            print("Rolling back to previous best version and aborting loop.")
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
            break"""

code = code.replace(old_eval_loop, new_eval_loop)

# 3. Fix the "Loop 1 External Feedback" bypass
old_rt_call = """        print("\\n[2] Running Red Team Audit (Full Context)...")
        red_team_report = run_red_team(current_text)"""
new_rt_call = """        # 1. Loop 1 External Feedback Bypass
        if loop == 1 and 'feedback_file' in globals() and feedback_file and os.path.exists(feedback_file):
            print("\\n[2] Bypassing Internal Red Team. Using External Feedback...")
            with open(feedback_file, 'r', encoding='utf-8') as ff:
                red_team_report = ff.read()
        else:
            print("\\n[2] Running Internal Red Team Audit (Full Context)...")
            red_team_report = run_red_team(current_text)"""

# In the main function, add feedback_file to globals for the patch to work simply
old_args = "run_delta_improvement_loop(args.file, args.target)"
new_args = """    global feedback_file
    feedback_file = args.feedback if hasattr(args, 'feedback') else None
    run_delta_improvement_loop(args.file, args.target)"""
code = code.replace(old_args, new_args)
code = code.replace(old_rt_call, new_rt_call)

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)

print("Workflow patched")

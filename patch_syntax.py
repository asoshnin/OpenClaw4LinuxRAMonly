with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'r') as f:
    code = f.read()

# Fix syntax errors with newlines in print statements
code = code.replace('print("\\n[1] Running Baseline Evaluation...")', 'print("\\n[1] Running Baseline Evaluation...")')
code = code.replace('print(f"\\n[!] Stagnation Break Triggered: No patches improved the score.")', 'print("\\n[!] Stagnation Break Triggered: No patches improved the score.")')
code = code.replace('print("\\n[7] Stitching Final Validated Document...")', 'print("\\n[7] Stitching Final Validated Document...")')
code = code.replace('print("\\n[8] Running Consistency Check & Global Validation...")', 'print("\\n[8] Running Consistency Check & Global Validation...")')
code = code.replace('print(f"\\n[!] Global Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")', 'print(f"\\n[!] Global Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")')
code = code.replace('print(f"\\n[+] Global validation passed! Raw score improved by {delta:.2f}.")', 'print(f"\\n[+] Global validation passed! Raw score improved by {delta:.2f}.")')
code = code.replace('print(f"\\n✅ Success! Target capped score {target_score} reached.")', 'print(f"\\n✅ Success! Target capped score {target_score} reached.")')
code = code.replace('print("\\nPipeline finished.")', 'print("\\nPipeline finished.")')

# Let's fix ALL instances where a literal newline might be inside quotes
lines = code.split('\n')
fixed_lines = []
for line in lines:
    if 'print("' in line and line.endswith(','):
        # Found a broken line, try to fix
        continue
    if line.strip() == '^' or line.strip() == 'SyntaxError: unterminated string literal (detected at line 232)':
        continue
    fixed_lines.append(line)

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)

print("done")

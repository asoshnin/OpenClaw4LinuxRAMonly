import re

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'r') as f:
    code = f.read()

# Update run_evaluation signature and logic
old_eval = """def run_evaluation(text: str) -> dict:
    sys_prompt = load_agent_prompt("MultiCriteriaEvaluationAssistant")
    full_prompt = f"{sys_prompt}\\n\\nEVALUATE THIS ARTIFACT:\\n{text}"
    
    def _call(p):
        res = call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=p).strip()"""

new_eval = """def run_evaluation(text: str, red_team_report: str = "") -> dict:
    sys_prompt = load_agent_prompt("MultiCriteriaEvaluationAssistant")
    
    context = ""
    if red_team_report:
        context = f"\\n\\n=== RED TEAM MANDATES (GRADE AGAINST THESE) ===\\n{red_team_report}\\n"
        
    full_prompt = f"{sys_prompt}{context}\\n\\nEVALUATE THIS ARTIFACT:\\n{text}"
    
    def _call(p):
        res = call_inference(tier="cloud", model="gemini-3.1-pro-preview", prompt=p).strip()"""

code = code.replace(old_eval, new_eval)

# Update calls to run_evaluation
code = code.replace("base_eval = run_evaluation(current_text)", "base_eval = run_evaluation(current_text, red_team_report if 'red_team_report' in locals() else '')")
code = code.replace("new_eval = run_evaluation(new_text)", "new_eval = run_evaluation(new_text, red_team_report)")

# Update the stagnation break threshold logic
old_stag = """        delta = new_raw - current_raw
        if delta <= 0.2:
            print(f"\\n[!] Stagnation Break Triggered: Delta ({delta:.2f}) <= 0.2.")"""

new_stag = """        delta = new_raw - current_raw
        required_delta = 0.05 if current_raw >= 8.5 else 0.2
        if delta <= required_delta:
            print(f"\\n[!] Stagnation Break Triggered: Delta ({delta:.2f}) <= {required_delta}.")"""

code = code.replace(old_stag, new_stag)

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)

print("Evaluator patched")

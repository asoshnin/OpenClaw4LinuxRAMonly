import re

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'r') as f:
    code = f.read()

code = code.replace('"gemini-1.5-flash"', '"gemini-3-flash-preview"')
code = code.replace('"gemini-1.5-pro"', '"gemini-3.1-pro-preview"')

with open('/home/alexey/openclaw-inbox/agentic_factory/openclaw_skills/orchestrator/delta_improver_workflow.py', 'w') as f:
    f.write(code)
print("done")

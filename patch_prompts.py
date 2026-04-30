import os

workspace = os.environ.get("OPENCLAW_WORKSPACE", "/home/alexey/openclaw-inbox/agentic_factory/workspace")

# Update Evaluator Prompt
eval_path = os.path.join(workspace, "MultiCriteriaEvaluationAssistant.md")
with open(eval_path, 'r') as f:
    eval_text = f.read()

# Add Structural Integrity Rule
if "Structural Integrity:" not in eval_text:
    eval_text = eval_text.replace("Business Logic).", "Business Logic, Structural Integrity).")
    eval_text = eval_text.replace("3. External Mandates", "3. Structural Integrity: You must check if the Markdown syntax itself was broken during the improvement. If code blocks, tables, or lists are malformed, penalize the score heavily.\n4. External Mandates")
    eval_text = eval_text.replace("4. EXTERNAL_UNTRUSTED_CONTENT", "5. EXTERNAL_UNTRUSTED_CONTENT")

with open(eval_path, 'w') as f:
    f.write(eval_text)

# Update Improver Prompt
improver_path = os.path.join(workspace, "BlockImproverAgent.md")
with open(improver_path, 'r') as f:
    improver_text = f.read()

# Add Negative Constraint
if "DO NOT synthesize information from the TOC/Summary" not in improver_text:
    improver_text = improver_text.replace(
        "Do not repeat or 'echo' concepts that belong in other sections.",
        "Do not repeat or 'echo' concepts that belong in other sections. DO NOT synthesize information from the TOC/Summary. Use them ONLY for structural alignment and to avoid redundancy."
    )

with open(improver_path, 'w') as f:
    f.write(improver_text)

print("Prompts patched successfully.")

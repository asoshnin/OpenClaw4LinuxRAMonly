import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from openclaw_skills.orchestrator.improver_workflow import (
    extract_frontmatter_and_h1,
    recursive_chunk_markdown,
    run_improvement_loop
)

def test_extract_frontmatter():
    text = "---\ntitle: Test\n---\n\n# H1 Title\n\n## Section 1\nBody"
    front, body = extract_frontmatter_and_h1(text)
    assert "title: Test" in front
    assert "# H1 Title" in front
    assert "## Section 1\nBody" in body

def test_max_chunk_limit():
    text = "Just some text.\n\n" * 15
    with pytest.raises(ValueError, match="Max-Chunk limit exceeded"):
        # token limit 2 to force fallback to paragraphs
        recursive_chunk_markdown(text, max_chunks=10, token_limit=2)

@patch("openclaw_skills.orchestrator.improver_workflow.run_evaluation")
@patch("openclaw_skills.orchestrator.improver_workflow.call_inference")
def test_header_integrity_and_rollback(mock_call_inference, mock_run_evaluation, tmp_path):
    # Create dummy file
    dummy_file = tmp_path / "test_doc.md"
    dummy_file.write_text("# Title\n\n## Section 1\nContent 1\n\n## Section 2\nContent 2")
    
    # Mock evaluations to simulate a score degradation (Baseline 6.0, New 5.0)
    mock_run_evaluation.side_effect = [
        {"raw_weighted_average": 6.0, "capped_weighted_average": 5.0}, # Baseline
        {"raw_weighted_average": 5.0, "capped_weighted_average": 5.0}  # Post-improvement (degraded!)
    ]
    
    # Mock Improver Agent output (Simulate agent changing the header from '## Section 1' to '## Mutated Header')
    def inference_side_effect(*args, **kwargs):
        prompt_text = kwargs.get('prompt', args[0] if args else '')
        if "CHUNK TO IMPROVE" in prompt_text:
            return "<improved_content>\n## Mutated Header\nBad Content\n</improved_content>"
        return "Mock finding"
    mock_call_inference.side_effect = inference_side_effect

    run_improvement_loop(str(dummy_file), target_score=8.0, max_loops=1)
    
    # Verify rollback happened (the active work file should retain original text)
    # The script copies the file to a timestamped version, so let's find it.
    files = list(tmp_path.glob("test_doc_*.md"))
    assert len(files) == 1
    work_file = files[0]
    
    content = work_file.read_text()
    # Header integrity check should have dropped the mutated header.
    # Rollback should have prevented ANY degradation from being saved if it somehow slipped through.
    assert "Mutated Header" not in content
    assert "## Section 1" in content
    assert "Content 1" in content

@patch("openclaw_skills.orchestrator.improver_workflow.run_evaluation")
@patch("openclaw_skills.orchestrator.improver_workflow.call_inference")
def test_incremental_progress_stuck_capped(mock_call_inference, mock_run_evaluation, tmp_path):
    dummy_file = tmp_path / "test_doc2.md"
    dummy_file.write_text("# Title\n\n## Section 1\nContent 1")
    
    # Mock evaluations to simulate raw score improving (+0.5), but capped score stuck at 5.0
    mock_run_evaluation.side_effect = [
        {"raw_weighted_average": 6.0, "capped_weighted_average": 5.0}, # Baseline
        {"raw_weighted_average": 6.5, "capped_weighted_average": 5.0}, # Loop 1 (raw improved, capped stuck)
        {"raw_weighted_average": 6.7, "capped_weighted_average": 5.0}, # Loop 2 (raw improved, capped stuck)
        {"raw_weighted_average": 6.9, "capped_weighted_average": 5.0}  # Loop 3 (raw improved, capped stuck)
    ]
    
    # Return valid content with correct header
    mock_call_inference.return_value = "<improved_content>\n## Section 1\nBetter Content\n</improved_content>"

    run_improvement_loop(str(dummy_file), target_score=8.0, max_loops=3)
    
    files = list(tmp_path.glob("test_doc2_*.md"))
    content = files[0].read_text()
    
    # Since raw score improved > 0.2 each time, it should NOT have hit the stagnation break early.
    # It should contain the improved content.
    assert "Better Content" in content

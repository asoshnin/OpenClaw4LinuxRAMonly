import pytest
from unittest.mock import patch, MagicMock
import json

# Ensure we can import from openclaw_skills
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'openclaw_skills')))

try:
    from architect.architect_tools import run_audit
except ImportError:
    from architect_tools import run_audit

class TestRT01Auditor:

    @patch("architect.architect_tools.call_inference")
    @patch("architect.architect_tools.get_agent_persona")
    def test_run_audit_parses_xml_correctly(self, mock_get_persona, mock_call_infer):
        # Setup mocks
        mock_get_persona.return_value = {
            "name": "Red Team Auditor",
            "description": "Mock RT-01 system prompt"
        }
        
        # Mock LLM XML response
        mock_call_infer.return_value = """
Here is my review.

<AUDIT_REPORT>
  <EPISTEMIC_CHALLENGE>
    The logic makes leap of faith assumptions about database connectivity.
  </EPISTEMIC_CHALLENGE>
  <STATUS>
    🟡 CONDITIONAL PASS
  </STATUS>
  <FINDINGS>
    - [Severity: Low] Hardcoded timeout.
    - [Severity: Med] Missing try/except on db connect.
  </FINDINGS>
  <RECOMMENDATIONS>
    1. Add try/except block.
    2. Extract timeout into config.
  </RECOMMENDATIONS>
</AUDIT_REPORT>
"""

        # Execute
        result = run_audit("mock artifact", "mock context")

        # Verify parsing
        assert "database connectivity." in result["epistemic_challenge"]
        assert result["status"] == "🟡 CONDITIONAL PASS"
        assert len(result["findings"]) == 2
        assert "[Severity: Low] Hardcoded timeout." in result["findings"]
        assert len(result["recommendations"]) == 2
        assert "Add try/except block" in result["recommendations"]

    @patch("architect.architect_tools.get_agent_persona")
    def test_run_audit_refuses_empty_artifact(self, mock_get_persona):
        result = run_audit("", "Given the task to refactor...")
        assert result["status"] == "🔴 NO GO"
        assert "empty" in result["epistemic_challenge"].lower()

    @patch("architect.architect_tools.get_agent_persona")
    def test_run_audit_refuses_empty_context(self, mock_get_persona):
        result = run_audit("some generated code", "")
        assert result["status"] == "🔴 NO GO"
        assert "empty" in result["epistemic_challenge"].lower()

    @patch("architect.architect_tools.call_inference")
    @patch("architect.architect_tools.get_agent_persona")
    def test_run_audit_handles_missing_tags(self, mock_get_persona, mock_call_infer):
        mock_get_persona.return_value = {"description": "mock persona"}
        
        # A response that totally omits tags or fails
        mock_call_infer.return_value = "I think it is ok but I didn't use tags."
        
        result = run_audit("mock artifact", "mock context")
        
        # Should fail closed securely
        assert result["status"] == "🔴 NO GO"
        assert "No specific challenge extracted." in result["epistemic_challenge"]

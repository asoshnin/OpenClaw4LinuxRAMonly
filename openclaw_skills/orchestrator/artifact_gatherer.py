"""
MP-01: Artifact Gatherer
Extracts code diffs safely for Red Team Auditor.
"""
import subprocess
import logging

log = logging.getLogger(__name__)

def get_safe_diff(project_root: str, baseline_commit: str) -> str:
    """Run git diff from baseline, filtering locks and truncating >12k chars."""
    cmd = ["git", "diff", baseline_commit, "HEAD", "--", ".", ":(exclude)*.lock", ":(exclude)*.json.bak"]
    try:
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, check=True)
        diff = result.stdout
        
        if len(diff) > 12000:
            return diff[:12000] + "\n\n[DIFF TRUNCATED: Exceeds 12k chars]"
        return diff
    except subprocess.CalledProcessError as e:
        log.error(f"Failed to get diff: {e.stderr}")
        return ""
    except Exception as e:
        log.error(f"Diff execution error: {e}")
        return ""

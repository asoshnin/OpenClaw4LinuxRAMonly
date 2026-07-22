# Post-Mortem: Subprocess Hang (2026-06-12)

## Description
The orchestrator's queue was occasionally hanging when spawning an openclaw agent subprocess. The agent process could freeze or wait on input/output indefinitely, halting the entire event loop.

## Root Cause
The `subprocess.run` call in `factory_cli.py` was completely synchronous without any timeout. When an agent experienced issues and failed to exit, the orchestrator blocked indefinitely.

## Resolution
Implemented Option 1 (Hard Timeout):
Added a `timeout=300` parameter to the `subprocess.run()` call and wrapped it in a `try...except subprocess.TimeoutExpired` block.
This ensures the orchestrator loop gracefully recovers and proceeds to the audit phase or the next iteration if the agent gets stuck.

## Action Items
- Monitor the queue for frequent timeouts, which may indicate systemic agent failure.
- Ensure the audit phase can handle partial/failed task completions due to timeouts.

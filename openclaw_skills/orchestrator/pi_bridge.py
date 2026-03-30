"""
EV-01: Pi Coding Agent Bridge
Formats OpenClaw `sessions_spawn` payloads for ACP subagents.
"""

class CodingAgentBridge:
    def format_spawn_request(self, task_id: str, task_payload: str, project_root: str, factory_context: str = "") -> dict:
        """
        Produce a JSON tool call requesting a 'pi' subagent.
        """
        
        # Concat context and payload securely, handling empty context
        task_str = f"{factory_context}\n\n{task_payload}\n" if factory_context else f"{task_payload}\n"
            
        payload = {
            "runtime": "acp",
            "agentId": "pi",
            "mode": "run",
            "task": task_str,
            "cwd": project_root,
            "label": f"Factory-Task-{task_id}"
        }
        
        return payload

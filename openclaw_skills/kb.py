"""
Knowledge Base — Sprint 6
Static KB loader, prompt formatter, and HITL-supervised reflection queue.

Design invariants (from SKILL.md):
  - knowledge_base.json is a STATIC committed file — never vectorized, never auto-modified.
  - Agents may PROPOSE updates via submit_kb_proposal().
  - Only the Navigator may APPLY updates via approve_kb_proposal() + HITL token.
  - Atomic KB writes: tmpfile + os.replace() pattern.
"""

import os
import sys
import json
import sqlite3
import logging
import argparse
from datetime import datetime
from pathlib import Path

try:
    from config import WORKSPACE_ROOT
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from config import WORKSPACE_ROOT

try:
    from librarian.librarian_ctl import validate_path as _validate_path_impl
    from architect.architect_tools import validate_token
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "librarian"))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "architect"))
    from librarian_ctl import validate_path as _validate_path_impl
    from architect_tools import validate_token


def _get_validate_path():
    """Return live validate_path so monkeypatch in tests is always reflected."""
    try:
        import librarian_ctl as _lctl
        return _lctl.validate_path
    except ImportError:
        return _validate_path_impl

logger = logging.getLogger(__name__)

# Default KB path — same directory as this file
_DEFAULT_KB_PATH = Path(__file__).parent / "knowledge_base.json"

VALID_UPDATE_TYPES = ("rule_add", "rule_modify", "rule_delete")


# ---------------------------------------------------------------------------
# KB loading and prompt formatting
# ---------------------------------------------------------------------------

def load_knowledge_base(kb_path: str = None) -> dict:
    """
    Load and return the knowledge base JSON.

    Args:
        kb_path: Path to knowledge_base.json. Defaults to the file
                 co-located with this module.

    Returns:
        Parsed dict with keys: security_rules, capability_boundaries,
        epistemic_invariants.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is malformed JSON.
    """
    path = Path(kb_path) if kb_path else _DEFAULT_KB_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"knowledge_base.json not found at {path}. "
            "Ensure the file is committed to the repository."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)  # raises json.JSONDecodeError on malformed content


def format_kb_for_prompt(kb: dict) -> str:
    """
    Format the knowledge base as a structured prefix for LLM prompts.

    The block order is fixed: security_rules → capability_boundaries →
    epistemic_invariants → vault_qa_protocol. This prefix is prepended BEFORE
    any dynamic content (memory context, task text) so rules cannot be overridden.
    """
    lines = []

    rules = kb.get("security_rules", [])
    if rules:
        lines.append("[SYSTEM RULES]")
        for rule in rules:
            lines.append(f"  - {rule}")
        lines.append("")

    caps = kb.get("capability_boundaries", [])
    if caps:
        lines.append("[CAPABILITIES]")
        for cap in caps:
            lines.append(f"  - {cap}")
        lines.append("")

    invariants = kb.get("epistemic_invariants", [])
    if invariants:
        lines.append("[INVARIANTS]")
        for inv in invariants:
            lines.append(f"  - {inv}")
        lines.append("")

    vault_protocol = kb.get("vault_qa_protocol", [])
    if vault_protocol:
        lines.append("[VAULT QA PROTOCOL]")
        for rule in vault_protocol:
            lines.append(f"  - {rule}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Reflection queue — proposal submission (agent-facing)
# ---------------------------------------------------------------------------

def submit_kb_proposal(
    db_path: str,
    agent_id: str,
    update_type: str,
    target_key: str,
    proposed_value: str,
    rationale: str,
) -> int:
    """
    Submit a KB update proposal to the reflection queue.

    Only the Navigator can approve it via approve_kb_proposal().
    Agents must never call approve_kb_proposal() directly.

    Args:
        db_path:        Path to factory.db.
        agent_id:       ID of the proposing agent.
        update_type:    One of 'rule_add', 'rule_modify', 'rule_delete'.
        target_key:     Key in knowledge_base.json to modify.
        proposed_value: The new value (JSON-serializable string).
        rationale:      Human-readable explanation.

    Returns:
        update_id (int): Row ID of the new proposal.

    Raises:
        ValueError: If update_type is not in the allowed set.
    """
    if update_type not in VALID_UPDATE_TYPES:
        raise ValueError(
            f"Invalid update_type '{update_type}'. "
            f"Must be one of: {VALID_UPDATE_TYPES}"
        )

    valid_db = _get_validate_path()(db_path)
    with sqlite3.connect(valid_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO proposed_kb_updates
                (proposed_by, update_type, target_key, proposed_value, rationale)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, update_type, target_key, proposed_value, rationale),
        )
        update_id = cursor.lastrowid
        conn.commit()

    logger.info(
        "KB proposal submitted: update_id=%d by agent=%s type=%s key=%s",
        update_id, agent_id, update_type, target_key,
    )
    return update_id


# ---------------------------------------------------------------------------
# Reflection queue — approval (Navigator-facing, requires HITL token)
# ---------------------------------------------------------------------------

def approve_kb_proposal(
    db_path: str,
    update_id: int,
    navigator_token: str,
    kb_path: str = None,
) -> None:
    """
    Apply a pending KB proposal after HITL token validation.

    Only the Navigator can call this. The burn-on-read token ensures
    that agents cannot approve their own proposals.

    Args:
        db_path:         Path to factory.db.
        update_id:       ID of the proposal to approve.
        navigator_token: The current HITL burn-on-read token.
        kb_path:         Override path to knowledge_base.json.

    Raises:
        PermissionError: If navigator_token is invalid/expired.
        ValueError:      If update_id does not exist or is not pending,
                         or if update_type is unrecognised.
    """
    # Step 1: Validate HITL burn-on-read token (consumed on use)
    if not validate_token(navigator_token):
        raise PermissionError(
            "Invalid or expired HITL token. KB approval aborted."
        )

    valid_db = _get_validate_path()(db_path)

    # Step 2: Fetch the proposal
    with sqlite3.connect(valid_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM proposed_kb_updates WHERE update_id = ? AND status = 'pending'",
            (update_id,),
        ).fetchone()

    if not row:
        raise ValueError(
            f"No pending proposal found with update_id={update_id}."
        )

    update_type    = row["update_type"]
    target_key     = row["target_key"]
    proposed_value = row["proposed_value"]

    # Step 3: Load current KB
    kb_file = Path(kb_path) if kb_path else _DEFAULT_KB_PATH
    kb = load_knowledge_base(str(kb_file))

    # Step 4: Apply the change
    if update_type == "rule_add":
        if target_key not in kb:
            kb[target_key] = []
        if not isinstance(kb[target_key], list):
            raise ValueError(f"Target key '{target_key}' is not a list.")
        kb[target_key].append(proposed_value)

    elif update_type == "rule_modify":
        # proposed_value is expected to be a JSON object: {"index": N, "value": "..."}
        try:
            mod = json.loads(proposed_value)
            idx = int(mod["index"])
            kb[target_key][idx] = mod["value"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise ValueError(
                f"rule_modify proposed_value must be JSON with 'index' and 'value': {e}"
            )

    elif update_type == "rule_delete":
        # proposed_value is the index (as string) to delete
        try:
            idx = int(proposed_value)
            del kb[target_key][idx]
        except (ValueError, IndexError) as e:
            raise ValueError(f"rule_delete proposed_value must be a valid index: {e}")

    # Step 5: Atomic write — tmpfile + os.replace()
    tmp_path = str(kb_file) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(kb, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, str(kb_file))
    logger.info("knowledge_base.json updated via approved proposal update_id=%d", update_id)

    # Step 6: Mark approved + audit log
    now = datetime.now().isoformat()
    with sqlite3.connect(valid_db) as conn:
        conn.execute(
            "UPDATE proposed_kb_updates SET status='approved', reviewed_at=? WHERE update_id=?",
            (now, update_id),
        )
        conn.execute(
            "INSERT INTO audit_logs (action, rationale) VALUES ('KB_APPROVED', ?)",
            (f"Proposal update_id={update_id} approved. key={target_key} type={update_type}",),
        )
        conn.commit()

    logger.info("KB proposal approved: update_id=%d key=%s", update_id, target_key)


# ---------------------------------------------------------------------------
# Proposal listing helper
# ---------------------------------------------------------------------------

def _list_proposals(db_path: str) -> None:
    """Print all pending KB proposals in a human-readable table."""
    valid_db = _get_validate_path()(db_path)
    with sqlite3.connect(valid_db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM proposed_kb_updates WHERE status='pending' ORDER BY update_id"
        ).fetchall()

    if not rows:
        print("No pending proposals.")
        return

    print(f"\n{'ID':>4}  {'Agent':<20}  {'Type':<14}  {'Key':<25}  {'Rationale'}")
    print("-" * 90)
    for row in rows:
        print(
            f"{row['update_id']:>4}  {row['proposed_by']:<20}  "
            f"{row['update_type']:<14}  {row['target_key']:<25}  {row['rationale']}"
        )
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="OpenClaw Knowledge Base CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list-proposals
    lp = subparsers.add_parser("list-proposals", help="List pending KB proposals")
    lp.add_argument("db_path", help="Path to factory.db")

    # submit
    sp = subparsers.add_parser("submit", help="Submit a KB update proposal")
    sp.add_argument("db_path")
    sp.add_argument("agent_id")
    sp.add_argument("update_type", choices=list(VALID_UPDATE_TYPES))
    sp.add_argument("target_key")
    sp.add_argument("proposed_value")
    sp.add_argument("rationale")

    # approve
    ap = subparsers.add_parser("approve", help="Approve a KB proposal (requires HITL token)")
    ap.add_argument("db_path")
    ap.add_argument("update_id", type=int)
    ap.add_argument("token", help="HITL burn-on-read token")

    args = parser.parse_args()

    try:
        if args.command == "list-proposals":
            _list_proposals(args.db_path)
        elif args.command == "submit":
            uid = submit_kb_proposal(
                args.db_path, args.agent_id, args.update_type,
                args.target_key, args.proposed_value, args.rationale,
            )
            print(f"Proposal submitted. update_id={uid}")
        elif args.command == "approve":
            approve_kb_proposal(args.db_path, args.update_id, args.token)
            print(f"Proposal {args.update_id} approved and applied.")
    except (PermissionError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

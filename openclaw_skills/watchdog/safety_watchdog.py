"""
safety_watchdog.py — OpenClaw Safety Watchdog Daemon
=====================================================
Runs as a background daemon, polling every 30 seconds for two failure modes:

  1. COST BREACH: Daily cloud API spend exceeds OPENCLAW_DAILY_COST_LIMIT_USD.
  2. LOOP CYCLING: Same agent+action repeats > OPENCLAW_LOOP_THRESHOLD times
     within OPENCLAW_LOOP_WINDOW_MINUTES.

On detecting either condition:
  1. Writes a WATCHDOG_KILL entry to factory.db audit_logs.
  2. Marks all active tasks as 'pending_hitl' (forensic preservation, not wipe).
  3. Writes the halt sentinel file (workspace/.watchdog_halt).
  4. SIGTERMs the orchestrator process (via workspace/.orchestrator.pid).
  5. Attempts a tkinter HITL popup if $DISPLAY is available.

Usage (run in a terminal or at startup):
    python3 -m openclaw_skills.watchdog.safety_watchdog

Or with explicit config:
    OPENCLAW_DAILY_COST_LIMIT_USD=5.0 python3 -m openclaw_skills.watchdog.safety_watchdog
"""

import os
import sys
import signal
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure repo root is importable
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from openclaw_skills.watchdog.cost_ledger import get_ledger

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
POLL_INTERVAL_SECONDS   = int(os.environ.get("OPENCLAW_WATCHDOG_INTERVAL", "30"))
DAILY_COST_LIMIT_USD    = float(os.environ.get("OPENCLAW_DAILY_COST_LIMIT_USD", "10.0"))
LOOP_THRESHOLD          = int(os.environ.get("OPENCLAW_LOOP_THRESHOLD", "5"))
LOOP_WINDOW_MINUTES     = int(os.environ.get("OPENCLAW_LOOP_WINDOW_MINUTES", "5"))


def _get_factory_db() -> Path:
    """Natively points to the Global Hub factory.db."""
    try:
        from openclaw_skills.config import GLOBAL_DB_PATH
        return GLOBAL_DB_PATH
    except ImportError:
        return Path.home() / ".openclaw" / "workspace" / "factory.db"


def _get_halt_file() -> Path:
    """Natively points to the Global Hub halt file."""
    try:
        from openclaw_skills.config import GLOBAL_HALT_FILE
        return GLOBAL_HALT_FILE
    except ImportError:
        return Path.home() / ".openclaw" / "workspace" / ".watchdog_halt"


def _get_pid_file() -> Path:
    try:
        from openclaw_skills.config import GLOBAL_WORKSPACE_ROOT
        return GLOBAL_WORKSPACE_ROOT / ".orchestrator.pid"
    except ImportError:
        return Path.home() / ".openclaw" / "workspace" / ".orchestrator.pid"


# ---------------------------------------------------------------------------
# Audit log writer (direct sqlite3 — no librarian_ctl to avoid import loops)
# ---------------------------------------------------------------------------

def _write_audit_log(action: str, rationale: str) -> None:
    db_path = _get_factory_db()
    if not db_path.exists():
        log.warning("factory.db not found at %s — skipping audit log write.", db_path)
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            "INSERT INTO audit_logs (agent_id, pipeline_id, action, rationale) VALUES (?, ?, ?, ?)",
            ("watchdog", None, action, rationale),
        )
        conn.commit()
        conn.close()
        log.info("Audit log written: %s", action)
    except Exception as exc:
        log.error("Failed to write audit log: %s", exc)


def _mark_active_tasks_pending_hitl() -> int:
    """Set all processing/processing_subagent tasks to pending_hitl.
    Returns count of rows updated.
    """
    db_path = _get_factory_db()
    
    # Try both factory.db (Global Hub/Legacy) and any active project.db
    ws = os.environ.get("OPENCLAW_WORKSPACE", "")
    project_candidate = Path(ws).expanduser().resolve() / "factory.db" if ws else Path.cwd() / "workspace" / "project.db"
    
    affected = 0
    for candidate in [db_path, project_candidate]:
        if not candidate.exists():
            continue
        try:
            conn = sqlite3.connect(str(candidate), timeout=5)
            conn.execute("PRAGMA journal_mode=WAL;")
            # Check if this db even has a tasks table
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            ).fetchall()]
            if "tasks" not in tables:
                conn.close()
                continue
            cur = conn.execute("""
                UPDATE tasks
                SET status='pending_hitl', last_error='WATCHDOG KILL: runaway loop or cost breach detected',
                    updated_at=CURRENT_TIMESTAMP
                WHERE status IN ('processing', 'processing_subagent', 'in_progress')
            """)
            affected += cur.rowcount
            conn.commit()
            conn.close()
            log.warning("Watchdog: %d tasks frozen to pending_hitl in %s", cur.rowcount, candidate.name)
        except Exception as exc:
            log.error("Failed to freeze tasks in %s: %s", candidate, exc)
    return affected


def _kill_orchestrator() -> bool:
    """Send SIGTERM to the orchestrator PID if the pid file exists."""
    pid_file = _get_pid_file()
    if not pid_file.exists():
        log.warning("No orchestrator PID file found at %s.", pid_file)
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        log.warning("Watchdog: sent SIGTERM to orchestrator PID %d", pid)
        return True
    except (ValueError, ProcessLookupError) as exc:
        log.warning("Could not kill orchestrator: %s", exc)
        pid_file.unlink(missing_ok=True)
        return False
    except PermissionError as exc:
        log.error("Permission denied killing orchestrator PID: %s", exc)
        return False


def _write_halt_file(reason: str) -> None:
    halt_file = _get_halt_file()
    halt_file.parent.mkdir(parents=True, exist_ok=True)
    halt_file.write_text(
        f"WATCHDOG HALT\nTime: {datetime.now().isoformat()}\nReason: {reason}\n"
    )
    log.warning("Halt sentinel written: %s", halt_file)


def _show_hitl_popup(title: str, message: str) -> None:
    """Try to show a tkinter popup. Silently skip if no display available."""
    display = os.environ.get("DISPLAY", "")
    if not display:
        log.warning("No $DISPLAY — skipping tkinter popup. Halt file is active.")
        return
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showwarning(title, message)
        root.destroy()
    except Exception as exc:
        log.warning("tkinter popup failed: %s", exc)


# ---------------------------------------------------------------------------
# Detection Logic
# ---------------------------------------------------------------------------

def _check_cost_breach() -> tuple[bool, str]:
    """Returns (breached, reason_string)."""
    try:
        today_total = get_ledger().get_today_total_usd()
        log.debug("Cost check: $%.4f / $%.2f daily limit", today_total, DAILY_COST_LIMIT_USD)
        if today_total >= DAILY_COST_LIMIT_USD:
            reason = (
                f"COST BREACH: Daily cloud spend ${today_total:.4f} "
                f"exceeded limit ${DAILY_COST_LIMIT_USD:.2f}"
            )
            return True, reason
    except Exception as exc:
        log.error("Cost check failed: %s", exc)
    return False, ""


def _check_loop_cycling() -> tuple[bool, str]:
    """Detect runaway loop: same agent+action repeating > threshold in window."""
    db_path = _get_factory_db()
    if not db_path.exists():
        return False, ""
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL;")
        window_start = (datetime.utcnow() - timedelta(minutes=LOOP_WINDOW_MINUTES)).isoformat()
        rows = conn.execute("""
            SELECT agent_id, action, COUNT(*) as cnt
            FROM audit_logs
            WHERE timestamp >= ?
            GROUP BY agent_id, action
            HAVING cnt >= ?
            ORDER BY cnt DESC
            LIMIT 1
        """, (window_start, LOOP_THRESHOLD)).fetchall()
        conn.close()
        if rows:
            agent_id, action, cnt = rows[0]
            reason = (
                f"LOOP CYCLING: agent='{agent_id}' action='{action}' "
                f"repeated {cnt}x in {LOOP_WINDOW_MINUTES} min (threshold={LOOP_THRESHOLD})"
            )
            return True, reason
    except Exception as exc:
        log.error("Loop cycling check failed: %s", exc)
    return False, ""


# ---------------------------------------------------------------------------
# Kill Path
# ---------------------------------------------------------------------------

def _execute_kill(reason: str) -> None:
    """Full kill sequence: audit → freeze tasks → halt file → SIGTERM → popup."""
    log.critical("WATCHDOG KILL TRIGGERED: %s", reason)

    _write_audit_log("WATCHDOG_KILL", reason)
    frozen = _mark_active_tasks_pending_hitl()
    _write_halt_file(reason)
    killed = _kill_orchestrator()

    summary = (
        f"OpenClaw Safety Watchdog\n\n"
        f"🛑 EMERGENCY HALT TRIGGERED\n\n"
        f"Reason: {reason}\n\n"
        f"Tasks frozen: {frozen}\n"
        f"Orchestrator killed: {killed}\n\n"
        f"Inspect factory.db and clear workspace/.watchdog_halt to resume."
    )
    print(f"\n{'='*60}\n{summary}\n{'='*60}\n", file=sys.stderr)
    _show_hitl_popup("OpenClaw Watchdog — Emergency Halt", summary)


# ---------------------------------------------------------------------------
# Main Daemon Loop
# ---------------------------------------------------------------------------

def run_watchdog() -> None:
    """Main polling loop. Runs until interrupted or kill is triggered."""
    log.info(
        "Safety Watchdog started (poll=%ds, cost_cap=$%.2f, loop_threshold=%dx/%dmin)",
        POLL_INTERVAL_SECONDS, DAILY_COST_LIMIT_USD, LOOP_THRESHOLD, LOOP_WINDOW_MINUTES,
    )

    # Ensure halt file is clear on startup (allows restart after manual resolution)
    halt_file = _get_halt_file()
    if halt_file.exists():
        log.warning(
            "Halt file already present at startup: %s\n"
            "Remove it manually to allow the orchestrator to run.",
            halt_file,
        )

    while True:
        try:
            breached, reason = _check_cost_breach()
            if breached:
                _execute_kill(reason)
                # Continue polling so UI can still read state; don't exit daemon
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            looped, reason = _check_loop_cycling()
            if looped:
                _execute_kill(reason)
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            log.debug("Watchdog: all clear.")
        except KeyboardInterrupt:
            log.info("Watchdog shutting down (KeyboardInterrupt).")
            break
        except Exception as exc:
            log.error("Watchdog poll error (non-fatal): %s", exc)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [WATCHDOG] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    run_watchdog()

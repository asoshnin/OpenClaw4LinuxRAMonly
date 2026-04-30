#!/usr/bin/env python3
"""
control_tower.py — OpenClaw Control Tower (Safe Mode)
=====================================================
A refined, more stable version of the monitor dashboard.
Moves complex logic out of construction to prevent Segfaults on Ubuntu 22.04.
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

# ── Import path setup ────────────────────────────────────────────────────────
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

log = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────

def _get_factory_db() -> Path:
    """Natively points to the Global Hub factory.db to fix Split-Brain."""
    try:
        from openclaw_skills.config import GLOBAL_DB_PATH
        return GLOBAL_DB_PATH
    except ImportError:
        # Fallback if config is broken
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


DAILY_COST_LIMIT_USD = float(os.environ.get("OPENCLAW_DAILY_COST_LIMIT_USD", "10.0"))

# ── Static Styles (Stable) ──────────────────────────────────────────────────
COL = {
    "bg":        "#000000", # Pure black for stability
    "bg2":       "#1a1a1a",
    "bg3":       "#2d2d2d",
    "border":    "#404040",
    "text":      "#ffffff",
    "text_dim":  "#aaaaaa",
    "accent":    "#4faaff",
    "green":     "#00cc44",
    "yellow":    "#ffcc00",
    "red":       "#ff3333",
    "orange":    "#ff8800",
}

# ── Data Helpers (Direct Connections, No URI Strings) ─────────────────────────

def _db_read(sql: str, params: tuple = ()) -> list[dict]:
    db_path = _get_factory_db()
    if not db_path.exists():
        return []
    try:
        # Avoid URI/ro strings which can be unstable across sqlite versions
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.debug("DB read error: %s", exc)
        return []


def _get_agents() -> list[dict]:
    return _db_read("SELECT agent_id, name, is_system FROM agents ORDER BY is_system DESC, name ASC")


def _get_pipelines() -> list[dict]:
    return _db_read("SELECT pipeline_id, name, status FROM pipelines")


def _get_audit_log(limit: int = 30) -> list[dict]:
    return _db_read("SELECT timestamp, agent_id, action, rationale FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))


def _get_cost_today() -> float:
    try:
        from openclaw_skills.watchdog.cost_ledger import get_ledger
        return get_ledger().get_today_total_usd()
    except Exception:
        return 0.0


def _get_recent_cost_events(limit: int = 20) -> list[dict]:
    try:
        from openclaw_skills.watchdog.cost_ledger import get_ledger
        return get_ledger().get_recent_events(limit)
    except Exception:
        return []


def _get_procs() -> list[str]:
    try:
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=3)
        matches = []
        for line in res.stdout.splitlines():
            if "python" in line and any(k in line for k in ["openclaw", "factory", "watchdog"]):
                matches.append(line[:100])
        return matches or ["(no active processes)"]
    except Exception:
        return ["(ps check failed)"]

# ── Main UI ──────────────────────────────────────────────────────────────────

class ControlTower(tk.Tk):
    def __init__(self, refresh_interval: int = 5):
        super().__init__()
        self.refresh_interval = refresh_interval * 1000
        self.title("🛡 OpenClaw Control Tower (Safe Mode)")
        self.geometry("1100x750")
        self.configure(bg=COL["bg"])

        # Fonts
        self._font_title = tkfont.Font(family="Helvetica", size=12, weight="bold")
        self._font_mono  = tkfont.Font(family="monospace", size=9)
        self._font_small = tkfont.Font(family="Helvetica", size=9)

        self._build_ui()
        
        # KEY FIX: Delay the first data load until AFTER construction and mainloop entry
        self.after(200, self._schedule_refresh)

    def _build_ui(self):
        # ── Top Bar ──
        top = tk.Frame(self, bg=COL["bg2"], pady=5)
        top.pack(fill="x")
        
        tk.Label(top, text="🛡 CONTROL TOWER", font=self._font_title, bg=COL["bg2"], fg=COL["accent"]).pack(side="left", padx=15)
        
        self._cost_var = tk.StringVar(value="Spend: $0.0000")
        self._cost_label = tk.Label(top, textvariable=self._cost_var, font=self._font_title, bg=COL["bg2"], fg=COL["green"])
        self._cost_label.pack(side="left", padx=20)

        # Emergency Buttons
        btn_frame = tk.Frame(top, bg=COL["bg2"])
        btn_frame.pack(side="right", padx=10)
        
        self._stop_btn = tk.Button(btn_frame, text="🛑 STOP", bg=COL["red"], fg="white", font=self._font_title, command=self._on_stop)
        self._stop_btn.pack(side="right", padx=5)
        
        self._pause_var = tk.StringVar(value="Pause")
        self._pause_btn = tk.Button(btn_frame, textvariable=self._pause_var, bg=COL["yellow"], fg="black", command=self._on_pause)
        self._pause_btn.pack(side="right", padx=5)

        # ── Main Content Area (Simple Grid, No Notebook) ──
        self.content = tk.Frame(self, bg=COL["bg"])
        self.content.pack(fill="both", expand=True, padx=5, pady=5)

        # Audit Log (Top Half)
        tk.Label(self.content, text="RECENT ACTIONS", bg=COL["bg"], fg=COL["text_dim"], font=self._font_small).pack(anchor="w")
        self._audit_text = self._make_listbox(self.content, height=12)

        # Agents & Pipelines (Bottom Half)
        mid_frame = tk.Frame(self.content, bg=COL["bg"])
        mid_frame.pack(fill="both", expand=True, pady=5)
        
        # Left: Agents
        left = tk.Frame(mid_frame, bg=COL["bg"])
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="AGENTS", bg=COL["bg"], fg=COL["text_dim"], font=self._font_small).pack(anchor="w")
        self._agents_text = self._make_listbox(left)

        # Right: Processes
        right = tk.Frame(mid_frame, bg=COL["bg"])
        right.pack(side="left", fill="both", expand=True)
        tk.Label(right, text="PROCESSES", bg=COL["bg"], fg=COL["text_dim"], font=self._font_small).pack(anchor="w")
        self._procs_text = self._make_listbox(right)

        # Status Bar
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var, bg=COL["bg3"], fg=COL["text_dim"], font=self._font_small, pady=2).pack(fill="x", side="bottom")

    def _make_listbox(self, parent, height=8):
        container = tk.Frame(parent, bg=COL["bg3"])
        container.pack(fill="both", expand=True)
        listbox = tk.Listbox(container, bg=COL["bg2"], fg=COL["text"], font=self._font_mono, bd=0, height=height, highlightthickness=0)
        vsb = tk.Scrollbar(container, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=vsb.set)
        listbox.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return listbox

    def _schedule_refresh(self):
        self._refresh()
        self.after(self.refresh_interval, self._schedule_refresh)

    def _refresh(self):
        try:
            # 1. Cost
            cost = _get_cost_today()
            self._cost_var.set(f"Spend: ${cost:.4f}")
            self._cost_label.configure(fg=COL["red"] if cost > (DAILY_COST_LIMIT_USD*0.8) else COL["green"])

            # 2. Audit (Fast)
            self._audit_text.delete(0, "end")
            for r in _get_audit_log(25):
                ts  = (r.get('timestamp') or "0000-00-00 00:00:00")[11:19]
                aid = str(r.get('agent_id') or "None")
                act = str(r.get('action') or "None")
                rat = str(r.get('rationale') or "")
                entry = f"[{ts}] {aid:<10} | {act:<15} | {rat[:80]}"
                self._audit_text.insert("end", entry)

            # 3. Agents
            self._agents_text.delete(0, "end")
            for r in _get_agents():
                aid = str(r.get('agent_id') or "None")
                name = str(r.get('name') or "Unknown")
                self._agents_text.insert("end", f"{aid:<20} | {name}")

            # 4. Processes
            self._procs_text.delete(0, "end")
            for p in _get_procs():
                self._procs_text.insert("end", str(p))

            # 5. Pause state
            is_halted = _get_halt_file().exists()
            self._pause_var.set("▶ RESUME" if is_halted else "⏸ PAUSE")
            
            # Show active DB in status bar for transparency (fixes Split-Brain)
            db_disp = str(_get_factory_db()).replace(str(Path.home()), "~")
            self._status_var.set(f"DB: {db_disp} | Updated: {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            self._status_var.set(f"Error: {e}")

    def _on_stop(self):
        if messagebox.askyesno("Confirm", "KILL all active orchestrators and freeze tasks?"):
            try:
                from openclaw_skills.watchdog.safety_watchdog import _execute_kill
                _execute_kill("Manual Kill via Control Tower")
            except Exception as e:
                # Backup manual kill
                _get_halt_file().write_text(f"FORCE HALT {datetime.now().isoformat()}")
            self._refresh()

    def _on_pause(self):
        path = _get_halt_file()
        if path.exists():
            path.unlink()
        else:
            path.write_text("PAUSE sentinel set by UI")
        self._refresh()

if __name__ == "__main__":
    if not os.environ.get("DISPLAY"):
        print("Error: No graphical display (DISPLAY) found.")
        sys.exit(1)
    app = ControlTower()
    app.mainloop()

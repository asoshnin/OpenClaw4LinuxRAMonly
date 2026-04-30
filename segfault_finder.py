import tkinter as tk
from tkinter import ttk
import sqlite3
import os
import sys
from pathlib import Path

# Add repo to sys.path
_repo_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_repo_root))

print("[1] Initializing Tk...")
root = tk.Tk()
root.withdraw()
print("[2] Tk Initialized.")

print("[3] Testing SQLite...")
db_path = _repo_root / "database" / "factory.db"
# Use the same URI that control_tower.py uses
try:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=3)
    conn.row_factory = sqlite3.Row
    res = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone()
    print("[4] SQLite Reading Ok:", dict(res) if res else "None")
    conn.close()
except Exception as e:
    print("[4] SQLite Errored (handled):", e)

print("[5] Testing TTK Style...")
style = ttk.Style()
style.theme_use("clam")
print("[6] TTK Style Initialized.")

print("[7] All clear. No segfault in minimal combination.")
root.destroy()

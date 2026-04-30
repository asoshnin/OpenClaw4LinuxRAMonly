"""
cost_ledger.py — Cloud API Spend Tracker
=========================================
Records every call_inference() cloud invocation and estimates USD cost.
Stored in a SEPARATE database (cost_ledger.db) to avoid sqlite-vec extension
conflicts with factory.db.

Cost rates are approximations based on public model pricing.
The goal is a reliable trip-wire, not penny-perfect billing accounting.

Usage:
    from openclaw_skills.watchdog.cost_ledger import CostLedger
    ledger = CostLedger()
    ledger.record(model="gemini-1.5-pro", prompt_chars=5000, response_chars=2000)
    print(ledger.get_today_total_usd())
"""

import sqlite3
import logging
import os
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-model cost rate estimates (USD per 1K characters, approximated)
# Gemini pricing as of 2025: input ~$0.00125/1K chars, output ~$0.005/1K chars
# These are conservative estimates; adjust via OPENCLAW_COST_RATES_JSON env var.
# ---------------------------------------------------------------------------
DEFAULT_RATES: dict[str, dict] = {
    # Format: {input_per_1k_chars, output_per_1k_chars}
    "gemini-1.5-pro":           {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash":         {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash":         {"input": 0.000075, "output": 0.0003},
    "gemini-2.5-pro-preview":   {"input": 0.00125, "output": 0.010},
    "gemini-2.5-flash-preview": {"input": 0.000075, "output": 0.0003},
    "gemini-3-flash-preview":   {"input": 0.000075, "output": 0.0003},
    "gemini-3.1-pro-preview":   {"input": 0.00125, "output": 0.010},
    # Fallback for unknown models — assume pro pricing (conservative)
    "__default__":              {"input": 0.00125, "output": 0.005},
}


def _get_db_path() -> Path:
    """Resolve the cost ledger DB path.
    Strictly uses the Global Hub path to ensure cost tracking isn't siloed.
    """
    try:
        from openclaw_skills.config import GLOBAL_COST_LEDGER_PATH
        return GLOBAL_COST_LEDGER_PATH
    except ImportError:
        # Fallback if config is broken
        base = Path.home() / ".openclaw" / "workspace"
        base.mkdir(parents=True, exist_ok=True)
        return base / "cost_ledger.db"


class CostLedger:
    """Append-only ledger of cloud inference calls and their estimated cost."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else _get_db_path()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()
        log.debug("CostLedger initialized at %s", self.db_path)

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cost_events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                model          TEXT NOT NULL,
                prompt_chars   INTEGER NOT NULL DEFAULT 0,
                response_chars INTEGER NOT NULL DEFAULT 0,
                estimated_usd  REAL NOT NULL DEFAULT 0.0,
                caller_context TEXT
            );
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cost_ts ON cost_events(ts);"
        )
        self._conn.commit()

    def _estimate_usd(self, model: str, prompt_chars: int, response_chars: int) -> float:
        """Estimate cost in USD based on character counts and per-model rates."""
        rates = DEFAULT_RATES.get(model, DEFAULT_RATES["__default__"])
        input_cost  = (prompt_chars   / 1000.0) * rates["input"]
        output_cost = (response_chars / 1000.0) * rates["output"]
        return round(input_cost + output_cost, 6)

    def record(
        self,
        model: str,
        prompt_chars: int,
        response_chars: int,
        caller_context: str | None = None,
    ) -> float:
        """Record a cloud inference call and return the estimated cost in USD.

        Args:
            model:           Model name string (e.g. 'gemini-1.5-pro').
            prompt_chars:    Character count of the prompt sent.
            response_chars:  Character count of the response received.
            caller_context:  Optional free-text tag for traceability (agent ID etc.).

        Returns:
            Estimated cost in USD for this single call.
        """
        cost = self._estimate_usd(model, prompt_chars, response_chars)
        try:
            self._conn.execute(
                """INSERT INTO cost_events (model, prompt_chars, response_chars,
                   estimated_usd, caller_context) VALUES (?, ?, ?, ?, ?)""",
                (model, prompt_chars, response_chars, cost, caller_context),
            )
            self._conn.commit()
            log.info(
                "CostLedger: model=%s prompt=%d resp=%d cost=$%.4f  (today total soon updated)",
                model, prompt_chars, response_chars, cost,
            )
        except Exception as exc:
            log.error("CostLedger: failed to record cost event: %s", exc)
        return cost

    def get_today_total_usd(self) -> float:
        """Return the sum of estimated costs for today (UTC date)."""
        today = date.today().isoformat()
        try:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(estimated_usd), 0.0) FROM cost_events WHERE date(ts) = ?",
                (today,),
            ).fetchone()
            return round(row[0], 4)
        except Exception as exc:
            log.error("CostLedger: get_today_total_usd failed: %s", exc)
            return 0.0

    def get_recent_events(self, limit: int = 50) -> list[dict]:
        """Return the most recent cost events as a list of dicts."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            rows = conn.execute(
                """SELECT ts, model, prompt_chars, response_chars, estimated_usd, caller_context
                   FROM cost_events ORDER BY ts DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            log.error("CostLedger: get_recent_events failed: %s", exc)
            return []

    def get_period_total_usd(self, since_iso: str) -> float:
        """Return total cost since a given ISO datetime string."""
        try:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(estimated_usd), 0.0) FROM cost_events WHERE ts >= ?",
                (since_iso,),
            ).fetchone()
            return round(row[0], 4)
        except Exception as exc:
            log.error("CostLedger: get_period_total_usd failed: %s", exc)
            return 0.0

    def close(self) -> None:
        self._conn.close()


# Module-level singleton for use by config.py hook
_singleton: CostLedger | None = None


def get_ledger() -> CostLedger:
    """Return the module-level CostLedger singleton (lazy-init)."""
    global _singleton
    if _singleton is None:
        _singleton = CostLedger()
    return _singleton

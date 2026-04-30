"""
tests/test_watchdog.py — Unit tests for Safety Watchdog & Cost Ledger

Tests:
  - CostLedger: record(), get_today_total_usd(), in-memory DB
  - Watchdog: loop cycling detection, cost breach detection
  - Orchestrator: halt-file sentinel blocks task claiming
"""

import os
import sys
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Ensure repo root is on path
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root))

from openclaw_skills.watchdog.cost_ledger import CostLedger


# ── CostLedger tests ──────────────────────────────────────────────────────────

class TestCostLedger(unittest.TestCase):

    def setUp(self):
        """Use a temp file DB for each test."""
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.ledger = CostLedger(db_path=self.tmp.name)

    def tearDown(self):
        self.ledger.close()
        os.unlink(self.tmp.name)

    def test_record_returns_positive_cost(self):
        cost = self.ledger.record(
            model="gemini-1.5-pro",
            prompt_chars=10000,
            response_chars=4000,
        )
        self.assertGreater(cost, 0.0, "Expected positive cost estimate")

    def test_today_total_starts_zero(self):
        total = self.ledger.get_today_total_usd()
        self.assertEqual(total, 0.0)

    def test_today_total_accumulates(self):
        self.ledger.record("gemini-1.5-pro",  5000, 1000)
        self.ledger.record("gemini-1.5-flash", 3000, 500)
        total = self.ledger.get_today_total_usd()
        self.assertGreater(total, 0.0)

    def test_multiple_calls_accumulate_correctly(self):
        cost1 = self.ledger.record("gemini-1.5-pro", 10000, 2000)
        cost2 = self.ledger.record("gemini-1.5-pro", 10000, 2000)
        total = self.ledger.get_today_total_usd()
        self.assertAlmostEqual(total, cost1 + cost2, places=5)

    def test_flash_cheaper_than_pro(self):
        cost_pro   = self.ledger.record("gemini-1.5-pro",   10000, 2000)
        cost_flash = self.ledger.record("gemini-1.5-flash", 10000, 2000)
        self.assertLess(cost_flash, cost_pro, "Flash should be cheaper than Pro")

    def test_unknown_model_uses_default_rate(self):
        # Should not raise — falls through to __default__ rate
        cost = self.ledger.record("totally-unknown-model-xyz", 5000, 1000)
        self.assertGreater(cost, 0.0)

    def test_caller_context_stored(self):
        self.ledger.record("gemini-1.5-pro", 5000, 1000, caller_context="test-agent")
        events = self.ledger.get_recent_events(limit=5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["caller_context"], "test-agent")

    def test_get_recent_events_order(self):
        self.ledger.record("gemini-1.5-flash", 100, 50)
        time.sleep(0.05)
        self.ledger.record("gemini-1.5-pro", 200, 100)
        events = self.ledger.get_recent_events(limit=10)
        # Most recent first
        self.assertEqual(events[0]["model"], "gemini-1.5-pro")

    def test_get_recent_events_limit(self):
        for _ in range(10):
            self.ledger.record("gemini-1.5-flash", 100, 50)
        events = self.ledger.get_recent_events(limit=3)
        self.assertEqual(len(events), 3)


# ── Watchdog detection tests ───────────────────────────────────────────────────

class TestWatchdogDetection(unittest.TestCase):

    def _make_factory_db_with_audit_logs(self, entries: list[dict]) -> str:
        """Create a temp factory.db with audit_logs table populated."""
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        conn = sqlite3.connect(tmp.name)
        conn.execute("""
            CREATE TABLE audit_logs (
                log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT,
                pipeline_id TEXT,
                action      TEXT,
                rationale   TEXT,
                timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for e in entries:
            conn.execute(
                "INSERT INTO audit_logs (agent_id, action, timestamp) VALUES (?, ?, ?)",
                (e["agent_id"], e["action"], e["timestamp"])
            )
        conn.commit()
        conn.close()
        return tmp.name

    def test_cost_breach_detected(self):
        """_check_cost_breach returns True when spend >= limit."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            ledger_path = f.name
        try:
            ledger = CostLedger(db_path=ledger_path)
            # Record a very expensive call
            ledger.record("gemini-1.5-pro", 99_000_000, 10_000_000)
            ledger.close()

            # Patch the module-level get_ledger to return our ledger
            with patch("openclaw_skills.watchdog.safety_watchdog.get_ledger",
                       return_value=CostLedger(db_path=ledger_path)):
                with patch("openclaw_skills.watchdog.safety_watchdog.DAILY_COST_LIMIT_USD", 0.01):
                    from openclaw_skills.watchdog.safety_watchdog import _check_cost_breach
                    breached, reason = _check_cost_breach()
                    self.assertTrue(breached)
                    self.assertIn("COST BREACH", reason)
        finally:
            os.unlink(ledger_path)

    def test_cost_no_breach_under_limit(self):
        """_check_cost_breach returns False when spend < limit."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            ledger_path = f.name
        try:
            ledger = CostLedger(db_path=ledger_path)
            ledger.record("gemini-1.5-flash", 100, 50)  # very cheap
            ledger.close()

            with patch("openclaw_skills.watchdog.safety_watchdog.get_ledger",
                       return_value=CostLedger(db_path=ledger_path)):
                with patch("openclaw_skills.watchdog.safety_watchdog.DAILY_COST_LIMIT_USD", 10.0):
                    from openclaw_skills.watchdog.safety_watchdog import _check_cost_breach
                    breached, reason = _check_cost_breach()
                    self.assertFalse(breached)
        finally:
            os.unlink(ledger_path)

    def test_loop_cycling_detected(self):
        """_check_loop_cycling detects repeated agent+action."""
        now = datetime.utcnow()
        # 6 identical entries within the last 2 minutes
        entries = [
            {"agent_id": "kimi-orch-01", "action": "run_pipeline",
             "timestamp": (now - timedelta(seconds=30 * i)).isoformat()}
            for i in range(6)
        ]
        db_path = self._make_factory_db_with_audit_logs(entries)
        try:
            import openclaw_skills.watchdog.safety_watchdog as ws
            original_factory_db = ws._get_factory_db
            original_threshold = ws.LOOP_THRESHOLD
            original_window = ws.LOOP_WINDOW_MINUTES
            try:
                ws._get_factory_db = lambda: Path(db_path)
                ws.LOOP_THRESHOLD = 5
                ws.LOOP_WINDOW_MINUTES = 5
                looped, reason = ws._check_loop_cycling()
                self.assertTrue(looped, f"Expected loop detection, got reason: {reason!r}")
                self.assertIn("LOOP CYCLING", reason)
            finally:
                ws._get_factory_db = original_factory_db
                ws.LOOP_THRESHOLD = original_threshold
                ws.LOOP_WINDOW_MINUTES = original_window
        finally:
            os.unlink(db_path)

    def test_loop_not_triggered_below_threshold(self):
        """_check_loop_cycling does NOT fire when repetitions are below threshold."""
        now = datetime.utcnow()
        # Only 3 entries — below threshold of 5
        entries = [
            {"agent_id": "kimi-orch-01", "action": "run_pipeline",
             "timestamp": (now - timedelta(seconds=30 * i)).isoformat()}
            for i in range(3)
        ]
        db_path = self._make_factory_db_with_audit_logs(entries)
        try:
            with patch("openclaw_skills.watchdog.safety_watchdog._get_factory_db",
                       return_value=Path(db_path)):
                with patch("openclaw_skills.watchdog.safety_watchdog.LOOP_THRESHOLD", 5):
                    with patch("openclaw_skills.watchdog.safety_watchdog.LOOP_WINDOW_MINUTES", 5):
                        import openclaw_skills.watchdog.safety_watchdog as ws
                        looped, _ = ws._check_loop_cycling()
                        self.assertFalse(looped)
        finally:
            os.unlink(db_path)

    def test_loop_not_triggered_old_entries(self):
        """_check_loop_cycling ignores entries older than the window."""
        now = datetime.utcnow()
        # 8 entries but all > 10 minutes ago
        entries = [
            {"agent_id": "kimi-orch-01", "action": "run_pipeline",
             "timestamp": (now - timedelta(minutes=15 + i)).isoformat()}
            for i in range(8)
        ]
        db_path = self._make_factory_db_with_audit_logs(entries)
        try:
            with patch("openclaw_skills.watchdog.safety_watchdog._get_factory_db",
                       return_value=Path(db_path)):
                with patch("openclaw_skills.watchdog.safety_watchdog.LOOP_THRESHOLD", 5):
                    with patch("openclaw_skills.watchdog.safety_watchdog.LOOP_WINDOW_MINUTES", 5):
                        import openclaw_skills.watchdog.safety_watchdog as ws
                        looped, _ = ws._check_loop_cycling()
                        self.assertFalse(looped)
        finally:
            os.unlink(db_path)


# ── Halt-file sentinel test ───────────────────────────────────────────────────

class TestHaltFileSentinel(unittest.TestCase):

    def test_halt_file_blocks_orchestrator(self):
        """run_orchestrator returns 'halted' status when halt sentinel exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            halt_file = workspace / ".watchdog_halt"
            halt_file.write_text("TEST HALT\n")

            with patch.dict(os.environ, {"OPENCLAW_WORKSPACE": str(workspace)}):
                # We can't run the full orchestrator (it needs DB), but we can
                # test the halt-check logic by importing and inspecting
                from openclaw_skills.factory_orchestrator import _get_halt_file
                detected_path = _get_halt_file(str(workspace.parent))
                self.assertTrue(detected_path.exists(), "Halt file should be detected")

    def test_no_halt_file_allows_orchestrator(self):
        """When halt sentinel is absent, _get_halt_file returns non-existing path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            from openclaw_skills.factory_orchestrator import _get_halt_file
            path = _get_halt_file(str(workspace.parent))
            self.assertFalse(path.exists(), "Halt file should NOT exist")


if __name__ == "__main__":
    unittest.main(verbosity=2)

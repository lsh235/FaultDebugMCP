#!/usr/bin/env python3
"""Local durable retry contract, including separate connections/processes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier, Timer
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from faultdebug.retry_ledger import (RetryCapacityExceeded, RetryConflict,
                                    RetryDeadlineExceeded, RetryLedger)


class RetryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "inventory.sqlite3"
        self.ledger = RetryLedger(self.path)
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE inventory (sku TEXT PRIMARY KEY, quantity INTEGER NOT NULL)")
            conn.execute("INSERT INTO inventory VALUES ('widget', 10)")

    def quantity(self):
        with sqlite3.connect(self.path) as conn:
            return conn.execute("SELECT quantity FROM inventory WHERE sku='widget'").fetchone()[0]

    @staticmethod
    def reserve(conn):
        conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE sku='widget'")
        return {"quantity": conn.execute("SELECT quantity FROM inventory WHERE sku='widget'").fetchone()[0]}

    def test_replay_uses_canonical_payload_and_detaches_result(self):
        first = self.ledger.apply_once("order:1", {"sku": "widget", "count": 1}, self.reserve)
        self.assertFalse(first.replayed)
        self.assertEqual(first.value, {"quantity": 9})
        first.value["quantity"] = -100
        def forbidden(conn):
            self.fail("replay must never invoke the callback")
        again = self.ledger.apply_once("order:1", {"count": 1, "sku": "widget"}, forbidden)
        self.assertTrue(again.replayed)
        self.assertEqual(again.value, {"quantity": 9})
        self.assertEqual(self.quantity(), 9)

    def test_same_id_different_payload_conflicts_without_mutation(self):
        self.ledger.apply_once("order:1", {"count": 1}, self.reserve)
        with self.assertRaises(RetryConflict):
            self.ledger.apply_once("order:1", {"count": 2}, self.reserve)
        self.assertEqual(self.quantity(), 9)

    def test_subprocess_commit_survives_lost_response_and_reopen(self):
        script = """
import os, sys
from faultdebug.retry_ledger import RetryLedger
def reserve(conn):
    conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE sku='widget'")
    return {"quantity": 9}
RetryLedger(sys.argv[1]).apply_once("lost-response", {"count": 1}, reserve)
os._exit(73)  # The server committed, but the caller saw no success response.
"""
        proc = subprocess.run([sys.executable, "-c", script, str(self.path)], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 73, proc.stderr)
        self.assertEqual(proc.stdout, "")
        replay = RetryLedger(self.path).apply_once("lost-response", {"count": 1}, self.reserve)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.value, {"quantity": 9})
        self.assertEqual(self.quantity(), 9)

    def test_subprocess_crash_during_callback_rolls_back(self):
        script = """
import os, sys
from faultdebug.retry_ledger import RetryLedger
def reserve(conn):
    conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE sku='widget'")
    os._exit(74)
RetryLedger(sys.argv[1]).apply_once("crashed", {}, reserve)
"""
        proc = subprocess.run([sys.executable, "-c", script, str(self.path)], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 74, proc.stderr)
        self.assertEqual(self.quantity(), 10)
        result = RetryLedger(self.path).apply_once("crashed", {}, self.reserve)
        self.assertFalse(result.replayed)
        self.assertEqual(self.quantity(), 9)

    def test_concurrent_separate_connections_mutate_once(self):
        start = Barrier(8)
        def attempt(_):
            ledger = RetryLedger(self.path)
            start.wait(timeout=10)
            return ledger.apply_once("parallel", {"count": 1}, self.reserve)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(not result.replayed for result in results), 1)
        self.assertTrue(all(result.value == {"quantity": 9} for result in results))
        self.assertEqual(self.quantity(), 9)

    def test_callback_failure_rolls_back_and_allows_retry(self):
        def fail(conn):
            self.reserve(conn)
            raise RuntimeError("business failure")
        with self.assertRaisesRegex(RuntimeError, "business failure"):
            self.ledger.apply_once("failure", {}, fail)
        self.assertEqual(self.quantity(), 10)
        self.assertFalse(self.ledger.apply_once("failure", {}, self.reserve).replayed)
        self.assertEqual(self.quantity(), 9)

    def test_expired_deadline_rejects_new_operations_and_replays(self):
        self.ledger.apply_once("existing", {}, self.reserve)
        for operation_id in ("expired", "existing"):
            with self.subTest(operation_id=operation_id), self.assertRaises(RetryDeadlineExceeded):
                self.ledger.apply_once(operation_id, {}, self.reserve,
                                       deadline_ns=time.monotonic_ns() - 1)
        self.assertEqual(self.quantity(), 9)

    def test_precommit_expiration_rolls_back_business_and_result(self):
        now = [1_000_000]
        def expire(conn):
            result = self.reserve(conn)
            now[0] = 2_000_000
            return result
        with patch("faultdebug.retry_ledger.time.monotonic_ns", side_effect=lambda: now[0]):
            with self.assertRaises(RetryDeadlineExceeded):
                self.ledger.apply_once("expired-in-callback", {}, expire, deadline_ns=2_000_000)
        self.assertEqual(self.quantity(), 10)
        self.assertFalse(self.ledger.apply_once("expired-in-callback", {}, self.reserve).replayed)
        self.assertEqual(self.quantity(), 9)

    def test_lock_wait_is_bounded_by_remaining_deadline(self):
        owner = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(owner.close)
        owner.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        with self.assertRaises((RetryDeadlineExceeded, sqlite3.OperationalError)):
            self.ledger.apply_once("locked", {}, self.reserve,
                                   deadline_ns=time.monotonic_ns() + 30_000_000)
        self.assertLess(time.monotonic() - started, 1.0)
        owner.rollback()
        self.assertEqual(self.quantity(), 10)
        self.assertFalse(self.ledger.apply_once("locked", {}, self.reserve).replayed)

    def test_commit_wait_refreshes_budget_consumed_by_callback(self):
        reader = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.addCleanup(reader.close)
        reader.execute("BEGIN")
        reader.execute("SELECT quantity FROM inventory").fetchone()
        # The reader unlocks after the operation's deadline but before a stale
        # initial busy timeout would finish. The transaction must not commit.
        release = Timer(0.30, reader.rollback)
        release.start()
        self.addCleanup(release.join)
        called = []
        def slow(conn):
            called.append(True)
            value = self.reserve(conn)
            time.sleep(0.15)
            return value
        try:
            with self.assertRaises((RetryDeadlineExceeded, sqlite3.OperationalError)):
                self.ledger.apply_once("commit-blocked", {}, slow,
                                       deadline_ns=time.monotonic_ns() + 250_000_000)
        finally:
            release.join()
        self.assertEqual(called, [True])
        self.assertEqual(self.quantity(), 10)
        self.assertFalse(self.ledger.apply_once("commit-blocked", {}, self.reserve).replayed)

    def test_invalid_json_payload_never_invokes_mutation(self):
        cycle = {}
        cycle["self"] = cycle
        deep = {}
        for _ in range(18):
            deep = {"child": deep}
        bad = [None, [], {1: "key"}, {"x": float("nan")}, {"x": float("inf")},
               {"x": (1, 2)}, {"x": object()}, {"x": 2**63}, {"x": "\ud800"},
               {"x": "a" * 65536}, {"x": [None] * 4097}, deep, cycle]
        def forbidden(conn):
            self.fail("invalid payload must be rejected before mutation")
        for payload in bad:
            with self.subTest(payload_type=type(payload)), self.assertRaises((TypeError, ValueError)):
                self.ledger.apply_once("invalid", payload, forbidden)
        self.assertEqual(self.quantity(), 10)

    def test_invalid_result_rolls_back_business_mutation(self):
        for result in ([], {"bad": float("nan")}, {"x": "b" * 65536}):
            def invalid(conn):
                self.reserve(conn)
                return result
            with self.subTest(result_type=type(result)), self.assertRaises((TypeError, ValueError)):
                self.ledger.apply_once("invalid-result", {}, invalid)
            self.assertEqual(self.quantity(), 10)
        self.assertFalse(self.ledger.apply_once("invalid-result", {}, self.reserve).replayed)

    def test_invalid_identifiers_deadlines_and_callback(self):
        for value in (None, True, 1, b"x"):
            with self.subTest(value=value), self.assertRaises(TypeError):
                self.ledger.apply_once(value, {}, self.reserve)
        for value in ("", "a b", "a\n", "한글", "x" * 129):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.ledger.apply_once(value, {}, self.reserve)
        for value in (True, False, 1.0, "100", []):
            with self.subTest(deadline=value), self.assertRaises(TypeError):
                self.ledger.apply_once("deadline", {}, self.reserve, deadline_ns=value)
        for value in (-1, 2**63):
            with self.subTest(deadline=value), self.assertRaises(ValueError):
                self.ledger.apply_once("deadline", {}, self.reserve, deadline_ns=value)
        with self.assertRaises(TypeError):
            self.ledger.apply_once("callback", {}, None)
        self.assertEqual(self.quantity(), 10)

    def test_capacity_preserves_replays_and_never_evicts_identity(self):
        bounded = RetryLedger(self.path, max_operations=1)
        bounded.apply_once("first", {}, self.reserve)
        with self.assertRaises(RetryCapacityExceeded):
            bounded.apply_once("second", {}, self.reserve)
        self.assertTrue(RetryLedger(self.path, max_operations=1)
                        .apply_once("first", {}, self.reserve).replayed)
        self.assertEqual(self.quantity(), 9)

    def test_accidental_callback_commit_or_ledger_write_is_denied(self):
        def commit(conn):
            self.reserve(conn)
            conn.commit()
            return {}
        def remove(conn):
            self.reserve(conn)
            conn.execute("DELETE FROM faultdebug_retry_operations")
            return {}
        for callback in (commit, remove):
            with self.subTest(callback=callback.__name__), self.assertRaises(sqlite3.DatabaseError):
                self.ledger.apply_once("guarded", {}, callback)
            self.assertEqual(self.quantity(), 10)

    def test_safe_persistent_path_and_capacity_setup(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        linked = self.path.parent / "linked.db"
        linked.symlink_to(self.path)
        for path in (linked, self.path.parent, "", ":memory:"):
            with self.subTest(path=path), self.assertRaises((ValueError, IsADirectoryError)):
                RetryLedger(path)
        for limit in (True, "1", 1.0):
            with self.subTest(limit=limit), self.assertRaises(TypeError):
                RetryLedger(self.path, max_operations=limit)
        for limit in (0, -1, 1_000_001):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                RetryLedger(self.path, max_operations=limit)

    def test_valid_json_values_and_distinct_numeric_payloads(self):
        payload = {"unicode": "한글", "data": [None, True, False, -1, 1.5, {"x": "y"}]}
        result = self.ledger.apply_once("json", payload, lambda conn: payload)
        self.assertEqual(result.value, payload)
        self.ledger.apply_once("numeric", {"n": 1}, lambda conn: {})
        with self.assertRaises(RetryConflict):
            self.ledger.apply_once("numeric", {"n": 1.0}, lambda conn: {})


if __name__ == "__main__":
    unittest.main()

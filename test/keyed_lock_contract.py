#!/usr/bin/env python3
"""Synchronization and bounded-resource contracts for process-local keyed locks."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faultdebug.keyed_lock import KeyedLockCapacityError, KeyedLockPool, KeyedLockTimeout


class KeyedLockContract(unittest.TestCase):
    def test_distinct_keys_enter_together(self):
        pool = KeyedLockPool(2)
        both_inside = threading.Barrier(2)

        def enter(key):
            with pool.hold(key, timeout=1):
                both_inside.wait(timeout=2)
                self.assertEqual(pool.active_keys, 2)
                both_inside.wait(timeout=2)

        with ThreadPoolExecutor(2) as workers:
            futures = [workers.submit(enter, key) for key in ("a", "b")]
            for future in futures:
                future.result(timeout=3)
        self.assertEqual(pool.active_keys, 0)

    def test_same_key_serializes_all_holders(self):
        pool = KeyedLockPool()
        start = threading.Barrier(12)
        active, maximum, count = 0, 0, 0

        def enter():
            nonlocal active, maximum, count
            start.wait(timeout=3)
            with pool.hold("shared", timeout=2):
                active += 1
                maximum = max(maximum, active)
                count += 1
                time.sleep(0.002)
                active -= 1

        with ThreadPoolExecutor(12) as workers:
            futures = [workers.submit(enter) for _ in range(12)]
            for future in futures:
                future.result(timeout=4)
        self.assertEqual((maximum, count, pool.active_keys), (1, 12, 0))

    def test_waiter_retains_capacity_and_shared_identity(self):
        pool = KeyedLockPool(1)
        entered, finish = threading.Event(), threading.Event()

        def waiter():
            with pool.hold("same", timeout=2):
                entered.set()
                self.assertTrue(finish.wait(2))

        with ThreadPoolExecutor(1) as worker:
            with pool.hold("same"):
                future = worker.submit(waiter)
                # Inspect references solely to establish that the waiter is
                # registered before the holder leaves; no scheduler guess.
                end = time.monotonic() + 2
                while True:
                    with pool._guard:
                        registered = pool._entries["same"].references == 2
                    if registered or time.monotonic() >= end:
                        break
                    time.sleep(0.001)
                self.assertTrue(registered)
                self.assertFalse(entered.is_set())
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(KeyedLockCapacityError), pool.hold("other"):
                    self.fail("new live key must be rejected at capacity")
                with self.assertRaises(KeyedLockTimeout), pool.hold("same", timeout=0):
                    self.fail("shared key must retain the waiter's lock")
            finally:
                finish.set()
            future.result(timeout=3)
        self.assertEqual(pool.active_keys, 0)

    def test_timeout_cleanup_preserves_owner_and_releases_idle_key(self):
        pool = KeyedLockPool(1)
        with pool.hold("a"):
            with self.assertRaises(KeyedLockTimeout), pool.hold("a", timeout=0.01):
                self.fail("held key must time out")
            self.assertEqual(pool.active_keys, 1)
            with self.assertRaises(KeyedLockCapacityError), pool.hold("b"):
                self.fail("timed-out waiter must not remove the owner")
        with pool.hold("b", timeout=0):
            self.assertEqual(pool.active_keys, 1)
        self.assertEqual(pool.active_keys, 0)

    def test_exceptions_release_entry_and_long_key_churn_is_bounded(self):
        pool = KeyedLockPool(1)
        with self.assertRaisesRegex(RuntimeError, "body"), pool.hold("failure"):
            raise RuntimeError("body")
        for number in range(2000):
            with pool.hold(str(number), timeout=0):
                self.assertEqual(pool.active_keys, 1)
        self.assertEqual(pool.active_keys, 0)

    def test_acquire_error_does_not_leak_entry(self):
        pool = KeyedLockPool(1)
        entry = mock.Mock(references=0)
        entry.lock.acquire.side_effect = RuntimeError("acquire interrupted")
        with mock.patch("faultdebug.keyed_lock._Entry", return_value=entry):
            with self.assertRaisesRegex(RuntimeError, "interrupted"), pool.hold("x"):
                self.fail("acquisition must fail")
        self.assertEqual(pool.active_keys, 0)
        entry.lock.release.assert_not_called()
        with pool.hold("x", timeout=0):
            pass

    def test_key_validation(self):
        pool = KeyedLockPool()
        for key in (None, True, 1, b"key", []):
            with self.subTest(key=key), self.assertRaises(TypeError), pool.hold(key):
                self.fail("invalid key")
        for key in ("", "x" * 1025, "한" * 342, "\ud800"):
            with self.subTest(length=len(key)), self.assertRaises(ValueError), pool.hold(key):
                self.fail("invalid key")
        for key in ("한글", "x" * 1024):
            with pool.hold(key, timeout=0):
                pass
        self.assertEqual(pool.active_keys, 0)

    def test_timeout_and_capacity_validation(self):
        for capacity in (True, None, "1", 1.0):
            with self.subTest(capacity=capacity), self.assertRaises(TypeError):
                KeyedLockPool(capacity)
        for capacity in (0, -1, 1_000_001):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                KeyedLockPool(capacity)
        pool = KeyedLockPool()
        for timeout in (True, "1", [], object()):
            with self.subTest(timeout=timeout), self.assertRaises(TypeError), pool.hold("a", timeout=timeout):
                self.fail("invalid timeout")
        for timeout in (-1, float("nan"), float("inf"), threading.TIMEOUT_MAX * 2, 10**400):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError), pool.hold("a", timeout=timeout):
                self.fail("invalid timeout")
        self.assertEqual(pool.active_keys, 0)


if __name__ == "__main__":
    unittest.main()

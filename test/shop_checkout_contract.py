#!/usr/bin/env python3
"""Real HTTP checkout concurrency; native callbacks are explicitly fake here.

Independent native acceptance lives in shop_concurrency.py. Synchronization
barriers/events establish overlap and blocked work without latency thresholds.
"""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))
from faultdebug.keyed_lock import KeyedLockPool
from shop_http_context import load_service


class CheckoutHTTPContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="faultdebug-checkout-contract-")
        self.directory = Path(self.temp.name)
        self.services, self.servers, self.threads = {}, {}, []
        self.hooks = {}
        self.release = threading.Event()
        for role in ("checkout", "inventory", "payment", "shipping", "notification"):
            with mock.patch.dict(os.environ, {"SHOP_CHECKOUT_LOCK_MODE": "keyed", "SHOP_CHECKOUT_MAX_KEYS": "1024"}):
                service, recorder = load_service(self.directory / role)
            self.assertIsNotNone(recorder, "this suite must label native callbacks as fake")
            service.ROLE = role
            original = service.dispatch

            def dispatch(path, body, ctx, deadline, *, role=role, original=original):
                hook = self.hooks.get(role)
                if hook is not None:
                    hook(path, body, ctx, deadline)
                return original(path, body, ctx, deadline)

            service.dispatch = dispatch
            server = service.ServiceServer(("127.0.0.1", 0), service.Handler)
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            self.services[role], self.servers[role] = service, server
            self.threads.append(thread)
        peers = {role: f"127.0.0.1:{server.server_address[1]}" for role, server in self.servers.items()}
        self.services["checkout"].PEERS.update(peers)

    def tearDown(self):
        self.release.set()
        for server in self.servers.values():
            server.shutdown()
        for thread in self.threads:
            thread.join(5)
        for server in self.servers.values():
            server.server_close()
        self.temp.cleanup()

    def request(self, order="order", quantity=1, *, timeout_ms=5000):
        port = self.servers["checkout"].server_address[1]
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request("POST", "/checkout", json.dumps({"order_id": order, "quantity": quantity}),
                               {"Content-Type": "application/json", "X-Shop-Timeout-Ms": str(timeout_ms)})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def events(self, role, kind=None):
        path = self.directory / role / "events.jsonl"
        # emit flushes whole JSON rows under its event lock; take that lock when
        # reading concurrent requests to avoid observing a partial buffered row.
        with self.services[role].EVENT_LOCK:
            rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return rows if kind is None else [row for row in rows if row["kind"] == kind]

    def wait_events(self, role, kind, count):
        end = time.monotonic() + 2
        while time.monotonic() < end:
            rows = self.events(role, kind)
            if len(rows) >= count:
                return rows
            time.sleep(0.001)
        self.fail(f"{role} did not emit {count} {kind} events")

    def block_reserve(self):
        entered = threading.Event()

        def wait(path, *_):
            if path == "/reserve":
                entered.set()
                if not self.release.wait(2):
                    raise RuntimeError("test reserve release was not signaled")

        self.hooks["inventory"] = wait
        return entered

    def test_distinct_orders_reach_remote_reservation_together(self):
        simultaneous = threading.Barrier(2)
        self.hooks["inventory"] = lambda *_: simultaneous.wait(timeout=2)
        with ThreadPoolExecutor(2) as workers:
            futures = [workers.submit(self.request, order) for order in ("a", "b")]
            results = [future.result(timeout=4) for future in futures]
        self.assertEqual([status for status, _ in results], [200, 200])
        rows = self.events("checkout")
        starts = {row["order_id"]: row for row in rows if row["kind"] == "checkout_begin"}
        ends = {row["order_id"]: row for row in rows if row["kind"] == "checkout_end"}
        self.assertLess(max(row["monotonic_ns"] for row in starts.values()),
                        min(row["monotonic_ns"] for row in ends.values()))
        for order in ("a", "b"):
            self.assertEqual(starts[order]["lock_mode"], "keyed")
            self.assertEqual(starts[order]["rpc_id"], ends[order]["rpc_id"])
        self.assertEqual(self.services["checkout"].CHECKOUT_LOCKS.active_keys, 0)

    def test_duplicate_order_runs_one_sequence_and_changed_quantity_conflicts(self):
        entered = self.block_reserve()
        with ThreadPoolExecutor(2) as workers:
            first = workers.submit(self.request, "shared", 2)
            self.assertTrue(entered.wait(2))
            second = workers.submit(self.request, "shared", 2)
            self.wait_events("checkout", "server_begin", 2)
            self.release.set()
            results = [first.result(timeout=4), second.result(timeout=4)]
        self.assertEqual([status for status, _ in results], [200, 200])
        self.assertEqual(sorted(result["replayed"] for _, result in results), [False, True])
        for role in ("inventory", "payment", "shipping", "notification"):
            self.assertEqual(len(self.events(role, "server_begin")), 1, role)
        self.assertEqual(len(self.events("payment", "payment_charge")), 1)
        self.assertEqual(self.request("shared", 3)[0], 409)
        self.assertEqual(len(self.events("inventory", "server_begin")), 1)
        self.assertEqual(self.services["inventory"].STATE["reservations"], {"shared": 2})

    def test_waiting_duplicate_expires_before_downstream_work(self):
        entered = self.block_reserve()
        with ThreadPoolExecutor(2) as workers:
            first = workers.submit(self.request, "shared")
            self.assertTrue(entered.wait(2))
            try:
                status, result = self.request("shared", timeout_ms=30)
                self.assertEqual((status, result["code"]), (504, "checkout_lock_deadline"))
                self.assertEqual(len(self.events("checkout", "checkout_begin")), 1)
                self.assertEqual(len(self.events("inventory", "server_begin")), 1)
            finally:
                self.release.set()
            self.assertEqual(first.result(timeout=4)[0], 200)
        self.assertEqual(self.request("shared")[1]["replayed"], True)
        self.assertEqual(self.services["checkout"].CHECKOUT_LOCKS.active_keys, 0)

    def test_capacity_rejects_new_order_without_downstream_or_lock_leak(self):
        self.services["checkout"].CHECKOUT_LOCKS = KeyedLockPool(1)
        entered = self.block_reserve()
        with ThreadPoolExecutor(1) as worker:
            first = worker.submit(self.request, "a")
            self.assertTrue(entered.wait(2))
            try:
                status, result = self.request("b")
                self.assertEqual((status, result["code"]), (503, "checkout_lock_capacity"))
                self.assertEqual(len(self.events("inventory", "server_begin")), 1)
            finally:
                self.release.set()
            self.assertEqual(first.result(timeout=4)[0], 200)
        self.assertEqual(self.request("b")[0], 200)
        self.assertEqual(self.services["checkout"].CHECKOUT_LOCKS.active_keys, 0)

    def test_state_and_new_rpc_ids_progress_while_global_baseline_waits(self):
        checkout = self.services["checkout"]
        checkout.CHECKOUT_LOCK_MODE = "global"
        entered = self.block_reserve()
        with ThreadPoolExecutor(2) as workers:
            first = workers.submit(self.request, "a")
            self.assertTrue(entered.wait(2))
            try:
                # This independent worker would block on alpha2's STATE lock.
                self.assertGreater(workers.submit(checkout.new_id).result(timeout=1), 0)
                status, result = self.request("b", timeout_ms=30)
                self.assertEqual((status, result["code"]), (504, "checkout_lock_deadline"))
                self.assertEqual(len(self.events("checkout", "checkout_begin")), 1)
            finally:
                self.release.set()
            self.assertEqual(first.result(timeout=4)[0], 200)
        self.assertFalse(checkout.CHECKOUT_GLOBAL_LOCK.locked())
        self.assertEqual(self.request("b")[0], 200)
        self.assertTrue(all(row["lock_mode"] == "global" for row in self.events("checkout", "checkout_begin")))

    def test_exception_releases_order_and_emits_matching_end(self):
        checkout = self.services["checkout"]
        original = checkout.call
        with mock.patch.object(checkout, "call", side_effect=RuntimeError("test downstream exception")):
            self.assertEqual(self.request("exception")[0], 500)
        self.assertEqual(checkout.CHECKOUT_LOCKS.active_keys, 0)
        self.assertEqual(self.events("checkout", "checkout_end")[-1]["status"], 500)
        self.assertEqual(checkout.call, original)
        self.assertEqual(self.request("exception")[0], 200)

    def test_already_expired_receiver_never_calls_a_peer(self):
        checkout = self.services["checkout"]
        ctx = {"request_id": "expired", "rpc_id": 123}
        status, result = checkout.dispatch("/checkout", {"order_id": "expired"}, ctx, time.monotonic_ns() - 1)
        self.assertEqual((status, result["code"]), (504, "checkout_lock_deadline"))
        self.assertEqual(checkout.CHECKOUT_LOCKS.active_keys, 0)
        self.assertEqual(self.events("inventory"), [])
        self.assertEqual(self.events("checkout", "checkout_begin"), [])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Exercise the shop's production HTTP paths, with explicit native proof modes.

Default mode uses a labeled fake recorder, while HTTP servers and clients are
real. --boundary/--runtime-dir repeat the suite under a native collector for two
process generations and inspect the producer's decoded RPC events.
"""
from __future__ import annotations

import argparse
import ctypes
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faultdebug.http_context import TraceParent

BOUNDARY: Path | None = None
GENERATION = 7
HI_A, HI_B, LO = 0x1111111111111111, 0x2222222222222222, 0xABCDEF


class FakeFunction:
    def __init__(self, recorder, name):
        self.recorder, self.name = recorder, name

    def __call__(self, *args):
        self.recorder.calls.append((self.name, args))
        return 1


class ExplicitFakeRecorder:
    def __init__(self):
        self.calls = []
        for name in ("fd_rpc_begin", "fd_rpc_end", "shop_request_boundary", "shop_payment_fault"):
            setattr(self, name, FakeFunction(self, name))


def load_service(directory: Path, *, generation: str | None = None):
    environment = {"SHOP_ROLE": "catalog", "SHOP_ORDINAL": "2", "SHOP_PEERS": "{}",
                   "FAULTDEBUG_PROCESS_ID": "shop-http-test", "FAULTDEBUG_SESSION_ID": "http-context-test",
                   "FAULTDEBUG_PROCESS_GENERATION": str(GENERATION) if generation is None else generation,
                   "SHOP_BOUNDARY": str(BOUNDARY or "/explicit-fake-recorder.so"),
                   "SHOP_EVENT_PATH": str(directory / "events.jsonl")}
    spec = importlib.util.spec_from_file_location("shop_http_test_service", ROOT / "test/shop/service.py")
    service = importlib.util.module_from_spec(spec)
    recorder = None if BOUNDARY else ExplicitFakeRecorder()
    with mock.patch.dict(os.environ, environment):
        if recorder is None:
            spec.loader.exec_module(service)
        else:
            with mock.patch.object(ctypes, "CDLL", return_value=recorder):
                spec.loader.exec_module(service)
    return service, recorder


class ProductionShopHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="faultdebug-shop-http-")
        self.directory = Path(self.temp.name)
        self.service, self.recorder = load_service(self.directory)
        self.server = self.service.ServiceServer(("127.0.0.1", 0), self.service.Handler)
        self.port = self.server.server_address[1]
        self.service.PEERS["catalog"] = f"127.0.0.1:{self.port}"
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.worker.start()

    def tearDown(self):
        self.server.shutdown()
        self.worker.join(5)
        self.server.server_close()
        self.temp.cleanup()

    def request(self, headers=(), body=None, *, path="/products"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        payload = json.dumps({} if body is None else body)
        try:
            connection.putrequest("POST", path)
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(payload)))
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders(payload.encode())
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def events(self, kind=None):
        path = self.directory / "events.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return rows if kind is None else [row for row in rows if row["kind"] == kind]

    def state(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request("GET", "/state")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            return json.loads(response.read())
        finally:
            connection.close()

    def durable_inventory(self):
        self.service.ROLE = "inventory"
        self.service.configure_inventory_ledger(self.directory / "inventory.sqlite3")

    def parent(self):
        return {"trace_id_hi": HI_A, "trace_id": LO, "span_id": 0x3333333333333333,
                "trace_flags": 0, "rpc_id": 901, "request_id": "outbound-test"}

    def test_no_header_and_legacy_compatibility(self):
        self.assertEqual(self.request()[0], 200)
        root = self.events("server_begin")[-1]
        self.assertNotEqual((root["trace_id_hi"], root["trace_id"]), (0, 0))
        self.assertEqual((root["parent_span_id"], root["context_source"]), (0, "local_root"))
        self.assertEqual(self.request([("X-Shop-Trace", "42"), ("X-Shop-Rpc", "43")])[0], 200)
        legacy = self.events("server_begin")[-1]
        self.assertEqual((legacy["trace_id_hi"], legacy["trace_id"], legacy["rpc_id"]), (0, 42, 43))
        self.assertEqual((legacy["parent_span_id"], legacy["context_source"]), (0, "legacy_shop_trace"))

    def test_high_word_identity_and_unsampled_context_survive(self):
        for high in (HI_A, HI_B):
            incoming = TraceParent(high, LO, 0x4444444444444444, 0)
            self.assertEqual(self.request([("traceparent", incoming.to_header()), ("X-Shop-Rpc", "5050")])[0], 200)
        rows = self.events("server_begin")
        self.assertEqual([(row["trace_id_hi"], row["trace_id"]) for row in rows], [(HI_A, LO), (HI_B, LO)])
        for row in rows:
            self.assertEqual(row["trace_flags"], 0)
            self.assertEqual(row["parent_span_id"], 0x4444444444444444)
            self.assertNotEqual(row["span_id"], row["parent_span_id"])
        for raw_flags, current_flags in ((0xFE, 0), (0xFF, 1)):
            # Use a literal wire value: the serializer correctly clears v00's
            # reserved bits, so it cannot create this adversarial input.
            incoming = f"00-{HI_A:016x}{LO:016x}-4444444444444444-{raw_flags:02x}"
            self.assertEqual(self.request([("traceparent", incoming)])[0], 200)
            current = self.events("server_begin")[-1]
            self.assertEqual(current["trace_flags"], current_flags)
            self.assertEqual((current["trace_id_hi"], current["trace_id"]), (HI_A, LO))

    def test_duplicate_invalid_and_conflicting_headers_are_rejected(self):
        header = TraceParent(HI_A, LO, 9, 0).to_header()
        invalid = [
            [("traceparent", "malformed")],
            [("traceparent", header), ("TraceParent", header)],
            [("traceparent", header + "," + header)],
            [("traceparent", header), ("X-Shop-Trace", str(LO))],
            [("traceparent", TraceParent(0, LO, 9, 0).to_header()), ("X-Shop-Trace", str(LO + 1))],
            [("X-Shop-Trace", "1"), ("x-shop-trace", "1")],
            [("X-Shop-Rpc", "1"), ("X-Shop-Rpc", "1")],
            [("X-Shop-Parent", "1"), ("X-Shop-Parent", "1")],
            [("X-Shop-Request", "a"), ("X-Shop-Request", "a")],
            [("X-Shop-Timeout-Ms", "1"), ("X-Shop-Timeout-Ms", "2")],
            [("X-Shop-Deadline", "1"), ("X-Shop-Deadline", "1")],
        ]
        # Keep malformed representations separate from valid decimal bounds.
        invalid += [[("X-Shop-Timeout-Ms", value)] for value in ("0", "5001", "-1", "1.5")]
        invalid += [[("X-Shop-Rpc", "0")], [("X-Shop-Trace", "0")], [("X-Shop-Trace", str(2**64))]]
        for headers in invalid:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers), (400, {"code": "invalid_request"}))
        self.assertEqual(self.events("server_begin"), [])
        matching = TraceParent(0, LO, 9, 0)
        self.assertEqual(self.request([("traceparent", matching.to_header()), ("X-Shop-Trace", str(LO))])[0], 200)

    def test_outbound_w3c_spans_and_shared_rpc_are_distinct(self):
        parent = self.parent()
        for _ in range(2):
            self.assertEqual(self.service.call("catalog", "/products", {}, parent)[0], 200)
        clients, servers = self.events("client_begin"), self.events("server_begin")
        self.assertEqual(len(clients), 2)
        self.assertEqual(len(servers), 2)
        self.assertEqual(len({row["rpc_id"] for row in clients}), 2)
        self.assertEqual(len({row["span_id"] for row in clients}), 2)
        for client, server in zip(clients, servers):
            self.assertEqual(client["rpc_id"], server["rpc_id"])
            self.assertEqual(client["parent_span_id"], parent["span_id"])
            self.assertEqual(server["parent_span_id"], client["span_id"])
            self.assertNotEqual(server["span_id"], client["span_id"])
            self.assertEqual((client["trace_id_hi"], client["trace_id"], client["trace_flags"]), (HI_A, LO, 0))
            self.assertEqual((server["trace_id_hi"], server["trace_id"], server["trace_flags"]), (HI_A, LO, 0))
            self.assertEqual(server["context_source"], "w3c_traceparent")
            self.assertEqual(server["timeout_ms"], 3000)
            self.assertFalse(server["legacy_deadline_ignored"])
        if self.recorder is not None:
            begin = [args for name, args in self.recorder.calls if name == "fd_rpc_begin"]
            self.assertTrue(begin)
            self.assertTrue(all(args[1:3] == (HI_A, LO) for args in begin))

    def test_relative_timeout_uses_receiver_clock_and_ignores_absolute_legacy(self):
        local_now = 123456
        received_deadlines = []
        original_deadline, original_dispatch = self.service.local_deadline_ns, self.service.dispatch

        def receiver_deadline(timeout_ms):
            return original_deadline(timeout_ms, now_ns=local_now)

        def dispatch(path, body, context, deadline):
            received_deadlines.append(deadline)
            return original_dispatch(path, body, context, deadline)

        with mock.patch.object(self.service, "local_deadline_ns", side_effect=receiver_deadline), \
             mock.patch.object(self.service, "dispatch", side_effect=dispatch):
            self.assertEqual(self.request([("X-Shop-Timeout-Ms", "30"), ("X-Shop-Deadline", "1")])[0], 200)
            self.assertEqual(self.request([("X-Shop-Deadline", str(2**64 - 1))])[0], 200)
        self.assertEqual(received_deadlines, [local_now + 30_000_000, local_now + 5_000_000_000])
        self.assertTrue(all(row["legacy_deadline_ignored"] for row in self.events("server_begin")))

    def test_process_generation_and_local_clock_are_emitted(self):
        self.service.emit("process_started")
        self.assertEqual(self.request()[0], 200)
        for row in self.events():
            self.assertEqual(row["process_generation"], GENERATION)
            self.assertEqual(row["clock"], self.service.CLOCK)
            self.assertEqual(row["clock"]["clock"], "monotonic")
        for invalid in ("0", "-1", str(2**32), "bad", "+7", " 7", "07", "7_0", "7.0"):
            with self.subTest(generation=invalid), self.assertRaises(ValueError):
                load_service(self.directory, generation=invalid)

    def test_expired_receiver_budget_prevents_inventory_mutation(self):
        self.service.ROLE = "inventory"
        status, body = self.request([("X-Shop-Timeout-Ms", "1"), ("X-Shop-Deadline", str(2**64 - 1))],
                                    {"scenario": "inventory_timeout", "order_id": "expired-order"}, path="/reserve")
        self.assertEqual((status, body["code"]), (504, "expired_before_reservation"))
        self.assertEqual(self.service.STATE["reservations"], {})
        self.assertEqual(self.service.STATE["stock"], 10000)

    def test_attempt_mapping_is_explicit_paired_and_bounded(self):
        invalid = [
            [("X-Shop-Operation", "reserve-1")], [("X-Shop-Attempt", "1")],
            [("X-Shop-Operation", "reserve-1"), ("X-Shop-Attempt", "1"), ("x-shop-attempt", "1")],
            [("X-Shop-Operation", "reserve-1"), ("x-shop-operation", "reserve-1"), ("X-Shop-Attempt", "1")],
        ]
        invalid += [[("X-Shop-Operation", "reserve-1"), ("X-Shop-Attempt", value)]
                    for value in ("0", "4", "01", "+1", "1,2", "1.0", "1x")]
        invalid += [[("X-Shop-Operation", value), ("X-Shop-Attempt", "1")]
                    for value in ("has space", "x" * 129, "x,y")]
        for headers in invalid:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers), (400, {"code": "invalid_request"}))
        self.assertEqual(self.events("server_begin"), [])
        for attempt in (1, 2, 3):
            self.assertEqual(self.request([("X-Shop-Operation", "reserve-1"), ("X-Shop-Attempt", str(attempt))])[0], 200)
        rows = self.events("server_begin")
        self.assertEqual([row["attempt"] for row in rows], [1, 2, 3])
        self.assertTrue(all(row["operation_id"] == "reserve-1" and row["attempt_source"] == "peer_self_reported" for row in rows))

    def test_outbound_retry_has_fresh_rpc_and_spans_with_generation_namespace(self):
        parent = self.parent()
        for attempt in (1, 2):
            self.assertEqual(self.service.call("catalog", "/products", {}, parent,
                                               operation_id="logical-operation", attempt=attempt)[0], 200)
        clients, servers = self.events("client_begin"), self.events("server_begin")
        self.assertEqual([row["attempt"] for row in clients], [1, 2])
        self.assertTrue(all(row["operation_id"] == "logical-operation" for row in clients + servers))
        self.assertEqual(len({row["rpc_id"] for row in clients}), 2)
        self.assertEqual(len({row["span_id"] for row in clients + servers}), 4)
        self.assertTrue(all(row["rpc_id"] >> 32 == GENERATION for row in clients))
        before = self.service.new_id()
        with mock.patch.object(self.service, "PROCESS_GENERATION", GENERATION + 1):
            after = self.service.new_id()
        self.assertNotEqual(before, after)
        self.assertEqual(after >> 32, GENERATION + 1)
        with mock.patch.object(self.service, "COUNTER", 2**24 - 1), self.assertRaises(RuntimeError):
            self.service.new_id()
        for attempt in (True, 0, 4, 1.0):
            with self.subTest(attempt=attempt), self.assertRaises(ValueError):
                self.service.call("catalog", "/products", {}, parent, operation_id="logical-operation", attempt=attempt)

    def test_durable_response_loss_retry_and_conflict_count_actual_mutations(self):
        self.durable_inventory()
        body = {"order_id": "lost-order", "quantity": 3, "scenario": "inventory_response_loss"}
        headers = [("X-Shop-Operation", "reserve-lost"), ("X-Shop-Attempt", "1")]
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request(headers, body, path="/reserve")
        state = self.state()
        self.assertEqual((state["stock"], state["reservations"], state["mutation_counts"], state["ledger_operations"]),
                         (9997, {"lost-order": 3}, {"reserve": 1, "release": 0}, 1))
        # Reopen the same database to exercise committed replay from a new
        # ledger instance; separate-process restart proof lives in acceptance.
        self.service.configure_inventory_ledger(self.directory / "inventory.sqlite3")
        headers[-1] = ("X-Shop-Attempt", "2")
        self.assertEqual(self.request(headers, body, path="/reserve"), (200, {"reserved": 3, "replayed": True}))
        status, result = self.request(headers, {**body, "quantity": 4}, path="/reserve")
        self.assertEqual((status, result["code"]), (409, "inventory_operation_conflict"))
        self.assertEqual(self.state()["mutation_counts"], {"reserve": 1, "release": 0})
        faults = [row for row in self.events("fault_triggered") if row["code"] == "inventory_response_loss_after_commit"]
        self.assertEqual(len(faults), 1)

    def test_durable_release_and_old_reserve_replay_never_resurrect(self):
        self.durable_inventory()
        body = {"order_id": "released-order", "quantity": 2}
        headers = [("X-Shop-Operation", "reserve-release"), ("X-Shop-Attempt", "1")]
        self.assertEqual(self.request(headers, body, path="/reserve"), (200, {"reserved": 2, "replayed": False}))
        self.assertEqual(self.request(headers, body, path="/release"), (200, {"released": True, "replayed": False}))
        self.assertEqual(self.request(headers, body, path="/release"), (200, {"released": True, "replayed": True}))
        self.assertEqual(self.request(headers, body, path="/reserve"), (200, {"reserved": 2, "replayed": True}))
        headers[0] = ("X-Shop-Operation", "new-reserve-same-order")
        self.assertEqual(self.request(headers, body, path="/reserve")[0], 409)
        state = self.state()
        self.assertEqual((state["stock"], state["reservations"], state["mutation_counts"]),
                         (10000, {}, {"reserve": 1, "release": 1}))
        self.assertEqual(state["reservation_history"]["released-order"], {"quantity": 2, "state": "released"})

    def test_durable_deadline_and_concurrent_duplicate_are_atomic(self):
        self.durable_inventory()
        expired = {"order_id": "durable-expired", "quantity": 2, "scenario": "inventory_timeout"}
        self.assertEqual(self.request([("X-Shop-Timeout-Ms", "1")], expired, path="/reserve")[0], 504)
        self.assertEqual((self.state()["stock"], self.state()["ledger_operations"]), (10000, 0))
        headers = [("X-Shop-Operation", "concurrent-reserve"), ("X-Shop-Attempt", "1")]
        body = {"order_id": "concurrent-order", "quantity": 5}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request(headers, body, path="/reserve"), range(4)))
        self.assertTrue(all(status == 200 for status, _ in results))
        self.assertEqual(sum(not result["replayed"] for _, result in results), 1)
        state = self.state()
        self.assertEqual((state["stock"], state["reservations"], state["mutation_counts"], state["ledger_operations"]),
                         (9995, {"concurrent-order": 5}, {"reserve": 1, "release": 0}, 1))

    def test_release_before_first_reserve_persists_cancellation(self):
        self.durable_inventory()
        body = {"order_id": "cancelled-before-reserve", "quantity": 2}
        headers = [("X-Shop-Operation", "early-release"), ("X-Shop-Attempt", "1")]
        self.assertEqual(self.request(headers, body, path="/release"), (200, {"released": True, "replayed": False}))
        headers[0] = ("X-Shop-Operation", "delayed-reserve")
        self.assertEqual(self.request(headers, body, path="/reserve")[0], 409)
        state = self.state()
        self.assertEqual((state["stock"], state["reservations"]), (10000, {}))
        self.assertEqual(state["reservation_history"][body["order_id"]], {"quantity": 2, "state": "released"})
        self.assertEqual(state["mutation_counts"], {"reserve": 0, "release": 1})


def run_suite() -> bool:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProductionShopHTTPTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main() -> int:
    global BOUNDARY, GENERATION
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--native-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.native_child:
        BOUNDARY = args.boundary.resolve()
        GENERATION = int(os.environ["FAULTDEBUG_PROCESS_GENERATION"])
        return 0 if run_suite() else 1
    if args.boundary is None:
        if args.runtime_dir is not None:
            parser.error("--runtime-dir requires --boundary")
        ok = run_suite()
        print(json.dumps({"status": "PASS" if ok else "FAIL", "http": "real_loopback", "application_processes": 1,
                          "native": "EXPLICIT_FAKE_RECORDER", "native_runtime": "NOT RUN"}))
        return 0 if ok else 1
    boundary = args.boundary.resolve()
    runtime = args.runtime_dir.resolve() if args.runtime_dir else boundary.parents[2]
    if not boundary.is_file() or not (runtime / "libfaultdebug_runtime.so").is_file():
        print(json.dumps({"status": "NOT RUN", "reason": "requested native boundary or runtime is unavailable"}))
        return 2
    from faultdebug.run import run_target
    results = []
    with tempfile.TemporaryDirectory(prefix="faultdebug-shop-native-") as temp, \
         mock.patch.dict(os.environ, {"FAULTDEBUG_RUNTIME_DIR": str(runtime)}):
        for generation in (7, 8):
            report = run_target([sys.executable, str(Path(__file__).resolve()), "--native-child", "--boundary", str(boundary)],
                                timeout=30, artifact_dir=Path(temp) / f"g{generation}", collect_success=True,
                                identity={"session_id": "http-context-test", "process_id": "shop-http-test",
                                          "process_generation": generation, "role": "catalog"})
            events = (report.get("rpc") or {}).get("events", [])
            identities = {(row["trace_id_hi"], row["trace_id_lo"]) for row in events}
            ok = (report.get("collector", {}).get("ok") is True
                  and report.get("target", {}).get("returncode") == 0 and bool(events)
                  and {(HI_A, LO), (HI_B, LO)} <= identities
                  and all(row["process_generation"] == generation for row in events))
            results.append({"generation": generation, "status": "PASS" if ok else "FAIL",
                            "target_pid": report.get("process", {}).get("pid"), "rpc_events": len(events)})
    ok = all(row["status"] == "PASS" for row in results)
    print(json.dumps({"status": "PASS" if ok else "FAIL", "http": "real_loopback", "application_processes_per_generation": 1,
                      "native": "REAL_BOUNDARY_AND_RUNTIME", "restart_generations": results}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

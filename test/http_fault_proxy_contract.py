#!/usr/bin/env python3
"""Real socket fault-fixture controls, framing, recovery, and resource bounds."""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent / "shop"))
from fault_proxy import FaultProxy, MAX_BODY


class Upstream:
    """Independent application state; proxy events cannot establish mutation."""

    def __init__(self):
        self.rows = []
        self.lock = threading.Lock()
        self.observed = threading.Event()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                with fixture.lock:
                    fixture.rows.append({"body": body, "headers": list(self.headers.raw_items())})
                    count = len(fixture.rows)
                fixture.observed.set()
                if self.path == "/truncated":
                    self.send_response(200)
                    self.send_header("Content-Length", "100")
                    self.end_headers()
                    self.wfile.write(b"short")
                    self.close_connection = True
                    return
                result = json.dumps({"mutations": count}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(result)))
                self.send_header("X-Repeated", "first")
                self.send_header("X-Repeated", "second")
                self.end_headers()
                self.wfile.write(result)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05}, daemon=True)

    @property
    def port(self):
        return self.server.server_address[1]

    def snapshot(self):
        with self.lock:
            return list(self.rows)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)


def post(port, *, timeout=2):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("POST", "/mutate", b"{}", {"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def raw(port, wire):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
        connection.sendall(wire)
        received = bytearray()
        while True:
            try:
                piece = connection.recv(4096)
            except ConnectionResetError:
                # Rejecting before reading a request body may reset after the
                # explicit bounded HTTP rejection has already been received.
                if received:
                    return bytes(received)
                raise
            if not piece:
                return bytes(received)
            received.extend(piece)


class FaultProxyContract(unittest.TestCase):
    @staticmethod
    def wait_worker(proxy):
        waiter = threading.Event()
        for _ in range(200):
            if proxy.active_workers == 1:
                return
            waiter.wait(0.005)
        raise AssertionError("proxy did not accept the pending connection")

    def test_pass_preserves_repeated_identity_headers_and_response_headers(self):
        trace = b"00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-00"
        with Upstream() as app, FaultProxy("127.0.0.1", app.port) as proxy:
            response = raw(proxy.port,
                           b"POST /mutate HTTP/1.1\r\nHost: local\r\nContent-Length: 2\r\n"
                           b"traceparent: " + trace + b"\r\ntraceparent: " + trace +
                           b"\r\nX-Shop-Rpc: 18446744073709551615\r\nX-Shop-Rpc: 7\r\n"
                           b"X-Shop-Attempt: 1\r\nX-Shop-Operation: immutable-op\r\n\r\n{}")
            self.assertTrue(response.startswith(b"HTTP/1.1 200"))
            self.assertIn(b"X-Repeated: first\r\nX-Repeated: second\r\n", response)
            headers = app.snapshot()[0]["headers"]
            self.assertEqual([v for k, v in headers if k.lower() == "traceparent"],
                             [trace.decode(), trace.decode()])
            self.assertEqual([v for k, v in headers if k.lower() == "x-shop-rpc"],
                             ["18446744073709551615", "7"])
            event = proxy.wait_for_events(1)[0]
            self.assertEqual(event["upstream_response_status"], 200)
            self.assertTrue(event["upstream_response_complete"])
            self.assertEqual(event["forwarded_response_status"], 200)
            self.assertEqual(event["caller_receipt"], "unknown")

    def test_reset_does_not_forward_and_pass_recovers(self):
        with Upstream() as app, FaultProxy("127.0.0.1", app.port, mode="reset_before_forward") as proxy:
            with self.assertRaises((OSError, http.client.HTTPException)):
                post(proxy.port)
            event = proxy.wait_for_events(1)[0]
            self.assertFalse(event["upstream_request_sent"])
            self.assertIsNone(event["upstream_response_status"])
            self.assertEqual(app.snapshot(), [])
            proxy.set_mode("pass")
            self.assertEqual(post(proxy.port), (200, {"mutations": 1}))
            proxy.wait_for_events(2)
            self.assertEqual(len(app.snapshot()), 1)

    def test_response_loss_requires_complete_observed_upstream_response(self):
        with Upstream() as app, FaultProxy("127.0.0.1", app.port, mode="drop_after_response") as proxy:
            with self.assertRaises((OSError, http.client.HTTPException)):
                post(proxy.port)
            event = proxy.wait_for_events(1)[0]
            self.assertEqual(len(app.snapshot()), 1)
            self.assertEqual(event["outcome"], "dropped_after_response")
            self.assertTrue(event["upstream_request_sent"])
            self.assertTrue(event["upstream_response_complete"])
            self.assertEqual(event["upstream_response_status"], 200)
            self.assertIsNone(event["forwarded_response_status"])
            self.assertFalse(event["forwarded_response_complete"])
            proxy.set_mode("pass")
            self.assertEqual(post(proxy.port), (200, {"mutations": 2}))

    def test_incomplete_upstream_response_is_not_classified_as_completed_loss(self):
        with Upstream() as app, FaultProxy("127.0.0.1", app.port, mode="drop_after_response") as proxy:
            response = raw(proxy.port,
                           b"POST /truncated HTTP/1.1\r\nHost: local\r\nContent-Length: 0\r\n\r\n")
            self.assertTrue(response.startswith(b"HTTP/1.1 502"))
            event = proxy.wait_for_events(1)[0]
            self.assertEqual(event["upstream_response_status"], 200)
            self.assertFalse(event["upstream_response_complete"])
            self.assertEqual(event["outcome"], "incomplete_body")
            self.assertEqual(len(app.snapshot()), 1)

    def test_mode_snapshot_is_fixed_on_accept(self):
        with Upstream() as app, FaultProxy("127.0.0.1", app.port) as proxy:
            pending = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
            try:
                pending.sendall(b"POST / HTTP/1.1\r\n")
                self.wait_worker(proxy)
                proxy.set_mode("reset_before_forward")
                pending.sendall(b"Host: local\r\nContent-Length: 0\r\n\r\n")
                self.assertTrue(pending.recv(4096).startswith(b"HTTP/1.1 200"))
                self.assertEqual(proxy.wait_for_events(1)[0]["mode"], "pass")
                with self.assertRaises((OSError, http.client.HTTPException)):
                    post(proxy.port)
                self.assertEqual(proxy.wait_for_events(2)[1]["mode"], "reset_before_forward")
                self.assertEqual(len(app.snapshot()), 1)
            finally:
                pending.close()

    def test_delays_timeout_real_caller_then_recover(self):
        for mode in ("delay_before_forward", "delay_after_response"):
            with self.subTest(mode=mode), Upstream() as app, FaultProxy(
                    "127.0.0.1", app.port, mode=mode, delay_ms=250) as proxy:
                with self.assertRaises((TimeoutError, socket.timeout)):
                    post(proxy.port, timeout=0.05)
                event = proxy.wait_for_events(1)[0]
                # Verify application receipt and a full response independently;
                # elapsed-time thresholds alone do not establish an injection.
                self.assertEqual(len(app.snapshot()), 1)
                self.assertEqual(event["upstream_response_status"], 200)
                self.assertTrue(event["upstream_response_complete"])
                self.assertEqual((event["mode"], event["delay_ms"]), (mode, 250))
                proxy.set_mode("pass")
                self.assertEqual(post(proxy.port), (200, {"mutations": 2}))

    def test_framing_and_body_limits_never_reach_upstream(self):
        invalid = [
            (b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: 65537\r\n\r\n", 413),
            (b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n", 400),
            (b"POST / HTTP/1.1\r\nHost: local\r\nTransfer-Encoding: chunked\r\n\r\n", 400),
            (b"POST / HTTP/1.1\r\nHost: local\r\n\r\n", 411),
            (b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: +2\r\n\r\n{}", 400),
            (b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: 0\r\n bad: fold\r\n\r\n", 400),
            (b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: 0\r\nUpgrade: websocket\r\n\r\n", 400),
        ]
        with Upstream() as app, FaultProxy("127.0.0.1", app.port) as proxy:
            for wire, expected in invalid:
                with self.subTest(wire=wire):
                    self.assertTrue(raw(proxy.port, wire).startswith(f"HTTP/1.1 {expected}".encode()))
            rows = proxy.wait_for_events(len(invalid))
            self.assertTrue(all(not row["upstream_request_sent"] for row in rows))
            self.assertEqual(app.snapshot(), [])
            self.assertEqual(post(proxy.port), (200, {"mutations": 1}))

    def test_exact_body_limit_is_preserved(self):
        body = b"x" * MAX_BODY
        with Upstream() as app, FaultProxy("127.0.0.1", app.port) as proxy:
            response = raw(proxy.port,
                           b"POST / HTTP/1.1\r\nHost: local\r\nContent-Length: 65536\r\n\r\n" + body)
            self.assertTrue(response.startswith(b"HTTP/1.1 200"))
            self.assertEqual(app.snapshot()[0]["body"], body)

    def test_worker_limit_and_shutdown_interrupt_pending_io(self):
        with Upstream() as app:
            proxy = FaultProxy("127.0.0.1", app.port, max_workers=1)
            proxy.start()
            slow = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
            try:
                slow.sendall(b"POST / HTTP/1.1\r\n")
                # Synchronize against the fixture's accepted worker count.
                self.wait_worker(proxy)
                self.assertEqual(proxy.active_workers, 1)
                response = raw(proxy.port, b"POST / HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
                self.assertTrue(response.startswith(b"HTTP/1.1 503"))
                event = proxy.wait_for_events(1)[0]
                self.assertEqual(event["outcome"], "worker_limit")
                self.assertEqual(event["forwarded_response_status"], 503)
                self.assertTrue(event["forwarded_response_complete"])
                self.assertEqual(event["caller_receipt"], "unknown")
                self.assertFalse(event["upstream_request_sent"])
                proxy.stop()
                self.assertEqual(proxy.active_workers, 0)
                self.assertEqual(app.snapshot(), [])
                with self.assertRaises(OSError):
                    socket.create_connection(("127.0.0.1", proxy.port), timeout=0.1)
            finally:
                slow.close()
                proxy.stop()

    def test_stop_interrupts_delay_without_forward(self):
        with Upstream() as app:
            proxy = FaultProxy("127.0.0.1", app.port, mode="delay_before_forward", delay_ms=5000)
            proxy.start()
            pending = socket.create_connection(("127.0.0.1", proxy.port), timeout=2)
            try:
                pending.sendall(b"POST / HTTP/1.1\r\nContent-Length: 0\r\n\r\n")
                self.wait_worker(proxy)
                proxy.stop()
                self.assertEqual(proxy.active_workers, 0)
                self.assertEqual(app.snapshot(), [])
            finally:
                pending.close()
                proxy.stop()

    def test_configuration_rejected_atomically_and_event_log_is_self_reported(self):
        for kwargs in ({"mode": "fault"}, {"delay_ms": 1}, {"delay_ms": True},
                       {"mode": "delay_before_forward", "delay_ms": 5001},
                       {"max_workers": 0}, {"max_workers": True},
                       {"socket_timeout": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                FaultProxy("127.0.0.1", 1, **kwargs)
        with tempfile.TemporaryDirectory() as directory, Upstream() as app:
            path = Path(directory) / "proxy.jsonl"
            with FaultProxy("127.0.0.1", app.port, event_path=path) as proxy:
                with self.assertRaises(ValueError):
                    proxy.set_mode("drop_after_response", delay_ms=1)
                self.assertEqual(post(proxy.port), (200, {"mutations": 1}))
                event = proxy.wait_for_events(1)[0]
                self.assertEqual(event["mode"], "pass")
                self.assertEqual(event["evidence_source"], "proxy_self_reported")
                self.assertEqual(json.loads(path.read_text()), event)
                event["mode"] = "changed-external-copy"
                self.assertEqual(proxy.events[0]["mode"], "pass")


if __name__ == "__main__":
    unittest.main()

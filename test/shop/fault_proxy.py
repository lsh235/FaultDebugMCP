"""Bounded, buffered HTTP/1 fault fixture for local acceptance tests.

This is a test transport, not a native recorder. Its events describe its own
socket observations; a completed send does not prove receipt or application
mutation. Each accepted connection carries one GET/POST and one response. TLS,
chunked transfer, streaming, upgrades, and pipelining are deliberately rejected.
Ordinary headers, including repeated trace/identity headers, retain their wire
order and values so the receiver can validate them without silent collapsing.
"""
from __future__ import annotations

from collections import deque
import json
import math
from pathlib import Path
import re
import socket
import struct
import threading
import time


MODES = frozenset({"pass", "reset_before_forward", "drop_after_response",
                   "delay_before_forward", "delay_after_response"})
MAX_BODY = 65536
MAX_RESPONSE = 262144
MAX_HEADERS = 32768
MAX_EVENTS = 4096
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
_LENGTH = re.compile(rb"(?:0|[1-9][0-9]*)\Z")


class _Rejected(ValueError):
    def __init__(self, status: int, reason: str):
        self.status, self.reason = status, reason
        super().__init__(reason)


def _configuration(mode: str, delay_ms: int) -> tuple[str, int]:
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("unsupported proxy mode")
    if type(delay_ms) is not int or not 0 <= delay_ms <= 5000:
        raise ValueError("delay_ms must be an integer in 0..5000")
    if mode not in {"delay_before_forward", "delay_after_response"} and delay_ms:
        raise ValueError("delay is only valid for delay modes")
    return mode, delay_ms


def _headers(sock: socket.socket) -> tuple[bytes, list[tuple[bytes, bytes]], bytes]:
    buffer = bytearray()
    deadline = time.monotonic() + sock.gettimeout()
    while b"\r\n\r\n" not in buffer:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("header deadline expired")
        sock.settimeout(remaining)
        chunk = sock.recv(min(4096, MAX_HEADERS + 4 - len(buffer)))
        if not chunk:
            raise _Rejected(400, "incomplete_headers")
        buffer.extend(chunk)
        marker = buffer.find(b"\r\n\r\n")
        if marker > MAX_HEADERS or (marker < 0 and len(buffer) >= MAX_HEADERS + 4):
            raise _Rejected(431, "headers_too_large")
    head, tail = bytes(buffer).split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    if len(lines) > 257:
        raise _Rejected(431, "too_many_headers")
    result = []
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator or not _TOKEN.fullmatch(name):
            raise _Rejected(400, "invalid_header_name")
        if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
            raise _Rejected(400, "invalid_header_value")
        result.append((name, value))
    return lines[0], result, tail


def _length(headers: list[tuple[bytes, bytes]], maximum: int, *, required: bool) -> int:
    values = [value.strip(b" \t") for name, value in headers if name.lower() == b"content-length"]
    if any(name.lower() in {b"transfer-encoding", b"trailer", b"upgrade", b"expect"}
           for name, _ in headers):
        raise _Rejected(400, "unsupported_transfer")
    if len(values) > 1:
        raise _Rejected(400, "duplicate_content_length")
    if not values:
        if required:
            raise _Rejected(411, "content_length_required")
        return 0
    if not _LENGTH.fullmatch(values[0]) or len(values[0]) > 9:
        raise _Rejected(400, "invalid_content_length")
    length = int(values[0])
    if length > maximum:
        raise _Rejected(413, "body_too_large")
    return length


def _body(sock: socket.socket, tail: bytes, length: int) -> bytes:
    if len(tail) > length:
        raise _Rejected(400, "pipelining_or_excess_body")
    body = bytearray(tail)
    deadline = time.monotonic() + sock.gettimeout()
    while len(body) < length:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("body deadline expired")
        sock.settimeout(remaining)
        chunk = sock.recv(min(4096, length - len(body)))
        if not chunk:
            raise _Rejected(400, "incomplete_body")
        body.extend(chunk)
    return bytes(body)


def _wire(first: bytes, headers: list[tuple[bytes, bytes]], body: bytes) -> bytes:
    # Connection: close makes buffering/EOF deterministic. All other header
    # occurrences are kept, including duplicate trace and numeric identities.
    lines = [first] + [name + b":" + value for name, value in headers
                       if name.lower() != b"connection"]
    return b"\r\n".join(lines + [b"Connection: close", b"", body])


class FaultProxy:
    """A loopback listener with a fixed maximum of active worker threads.

    ``set_mode`` affects connections accepted afterward; active workers retain
    their mode snapshot. Rejected framing never reaches the upstream. Events
    use monotonic timestamps in this fixture's clock, without native provenance.
    The in-memory window retains at most 4096 events; event_path preserves the
    full JSONL stream when a longer fixture run needs a durable observation log.
    """

    def __init__(self, upstream_host: str, upstream_port: int, *, mode: str = "pass",
                 delay_ms: int = 0, event_path: str | Path | None = None,
                 max_workers: int = 8, socket_timeout: float = 3.0):
        if not isinstance(upstream_host, str) or not upstream_host:
            raise ValueError("upstream_host must be nonempty")
        if type(upstream_port) is not int or not 1 <= upstream_port <= 65535:
            raise ValueError("upstream_port must be in 1..65535")
        if type(max_workers) is not int or not 1 <= max_workers <= 32:
            raise ValueError("max_workers must be in 1..32")
        if (isinstance(socket_timeout, bool) or not isinstance(socket_timeout, (int, float))
                or not math.isfinite(socket_timeout) or not 0.05 <= socket_timeout <= 10):
            raise ValueError("socket_timeout must be in 0.05..10 seconds")
        self.upstream_host, self.upstream_port = upstream_host, upstream_port
        self.max_workers, self.socket_timeout = max_workers, float(socket_timeout)
        self.event_path = Path(event_path) if event_path is not None else None
        self._mode, self._delay_ms = _configuration(mode, delay_ms)
        self._lock = threading.RLock()
        self._changed = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._workers: set[threading.Thread] = set()
        self._sockets: set[socket.socket] = set()
        self._events: deque[dict] = deque(maxlen=MAX_EVENTS)
        self._sequence = 0
        self._listener: socket.socket | None = None
        self._acceptor: threading.Thread | None = None
        self._port: int | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("proxy has not started")
        return self._port

    @property
    def events(self) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self._events]

    @property
    def active_workers(self) -> int:
        with self._lock:
            return len(self._workers)

    def set_mode(self, mode: str, delay_ms: int = 0) -> None:
        configuration = _configuration(mode, delay_ms)
        with self._lock:
            self._mode, self._delay_ms = configuration

    def start(self) -> "FaultProxy":
        with self._lock:
            if self._listener is not None or self._stop.is_set():
                raise RuntimeError("proxy can only be started once")
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                listener.bind(("127.0.0.1", 0))
                listener.listen(self.max_workers)
                listener.settimeout(0.1)
            except BaseException:
                listener.close()
                raise
            self._listener, self._port = listener, listener.getsockname()[1]
            self._acceptor = threading.Thread(target=self._accept, name="fault-proxy-accept", daemon=True)
            self._acceptor.start()
        return self

    def wait_for_events(self, count: int, timeout: float = 3.0) -> list[dict]:
        if (type(count) is not int or not 0 <= count <= MAX_EVENTS
                or not math.isfinite(timeout) or not 0 <= timeout <= 30):
            raise ValueError("invalid bounded event wait")
        deadline = time.monotonic() + timeout
        with self._changed:
            while len(self._events) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"expected {count} proxy events, observed {len(self._events)}")
                self._changed.wait(remaining)
            return self.events

    def _event(self, row: dict) -> None:
        row.update(event="request_complete", evidence_source="proxy_self_reported",
                   caller_receipt="unknown", finished_monotonic_ns=time.monotonic_ns())
        with self._changed:
            self._events.append(dict(row))
            if self.event_path is not None:
                self.event_path.parent.mkdir(parents=True, exist_ok=True)
                with self.event_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
            self._changed.notify_all()

    def _accept(self) -> None:
        listener = self._listener
        assert listener is not None
        while not self._stop.is_set():
            try:
                client, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            client.settimeout(self.socket_timeout)
            with self._lock:
                self._sequence += 1
                row = dict(sequence=self._sequence, mode=self._mode, delay_ms=self._delay_ms,
                           started_monotonic_ns=time.monotonic_ns(), upstream_request_sent=False,
                           upstream_response_status=None, upstream_response_complete=False,
                           forwarded_response_status=None, forwarded_response_complete=False)
                if self._stop.is_set() or len(self._workers) >= self.max_workers:
                    try:
                        client.settimeout(0.1)
                        self._error(client, 503)
                        row["forwarded_response_status"] = 503
                        row["forwarded_response_complete"] = True
                    except OSError:
                        pass
                    finally:
                        client.close()
                    row["outcome"] = "worker_limit" if not self._stop.is_set() else "stopped"
                    self._event(row)
                    continue
                worker = threading.Thread(target=self._run, args=(client, row),
                                          name=f"fault-proxy-{self._sequence}", daemon=True)
                self._sockets.add(client)
                self._workers.add(worker)
                worker.start()

    @staticmethod
    def _error(client: socket.socket, status: int) -> None:
        reason = {400: "Bad Request", 405: "Method Not Allowed", 411: "Length Required",
                  413: "Content Too Large", 431: "Request Header Fields Too Large",
                  502: "Bad Gateway", 503: "Service Unavailable"}[status]
        client.sendall(f"HTTP/1.1 {status} {reason}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())

    def _delay(self, delay_ms: int) -> None:
        if self._stop.wait(delay_ms / 1000):
            raise OSError("proxy stopped")

    def _run(self, client: socket.socket, row: dict) -> None:
        upstream = None
        try:
            first, headers, tail = _headers(client)
            parts = first.split(b" ")
            if len(parts) != 3 or parts[2] not in {b"HTTP/1.0", b"HTTP/1.1"}:
                raise _Rejected(400, "invalid_request_line")
            if parts[0] not in {b"GET", b"POST"}:
                raise _Rejected(405, "unsupported_method")
            if not parts[1].startswith(b"/") or any(byte <= 32 or byte == 127 for byte in parts[1]):
                raise _Rejected(400, "invalid_request_target")
            length = _length(headers, MAX_BODY, required=parts[0] == b"POST")
            body = _body(client, tail, length)
            if row["mode"] == "reset_before_forward":
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                row["outcome"] = "reset_before_forward"
                return
            if row["mode"] == "delay_before_forward":
                self._delay(row["delay_ms"])
            upstream = socket.create_connection((self.upstream_host, self.upstream_port), self.socket_timeout)
            with self._lock:
                if self._stop.is_set():
                    raise OSError("proxy stopped")
                self._sockets.add(upstream)
            upstream.sendall(_wire(first, headers, body))
            row["upstream_request_sent"] = True
            response_first, response_headers, response_tail = _headers(upstream)
            status = response_first.split(b" ", 2)
            if (len(status) < 2 or status[0] not in {b"HTTP/1.0", b"HTTP/1.1"}
                    or not re.fullmatch(rb"[2-5][0-9]{2}", status[1])):
                raise _Rejected(502, "unsupported_upstream_response")
            row["upstream_response_status"] = int(status[1])
            response_length = _length(response_headers, MAX_RESPONSE, required=True)
            response_body = _body(upstream, response_tail, response_length)
            row["upstream_response_complete"] = True
            if row["mode"] == "drop_after_response":
                row["outcome"] = "dropped_after_response"
                return
            if row["mode"] == "delay_after_response":
                self._delay(row["delay_ms"])
            client.sendall(_wire(response_first, response_headers, response_body))
            row["forwarded_response_status"] = row["upstream_response_status"]
            row["forwarded_response_complete"] = True
            row["outcome"] = "forwarded"
        except _Rejected as error:
            row["outcome"] = error.reason
            # Upstream framing failures become 502, never a request-side 4xx.
            status = 502 if row["upstream_request_sent"] else error.status
            try:
                self._error(client, status)
                row["forwarded_response_status"] = status
                row["forwarded_response_complete"] = True
            except OSError:
                pass
        except (OSError, TimeoutError) as error:
            row["outcome"] = "stopped" if self._stop.is_set() else type(error).__name__
        finally:
            for connection in (client, upstream):
                if connection is not None:
                    with self._lock:
                        self._sockets.discard(connection)
                    connection.close()
            try:
                self._event(row)
            finally:
                with self._lock:
                    self._workers.discard(threading.current_thread())

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            listener, acceptor = self._listener, self._acceptor
            self._listener = None
            sockets = list(self._sockets)
        if listener is not None:
            listener.close()
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if acceptor is not None:
            acceptor.join(timeout=1)
        with self._lock:
            workers = list(self._workers)
        deadline = time.monotonic() + self.socket_timeout + 1
        for worker in workers:
            worker.join(timeout=max(0, deadline - time.monotonic()))
        if (acceptor is not None and acceptor.is_alive()) or self.active_workers:
            raise RuntimeError("proxy workers did not stop within the bounded timeout")

    def __enter__(self) -> "FaultProxy":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

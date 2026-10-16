"""Real HTTP shopping processes with explicit, bounded demo fault injection."""
from __future__ import annotations

import ctypes
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import inspect
import json
import os
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from faultdebug.clock import local_clock_identity, local_deadline_ns
from faultdebug.http_context import TraceParent, child_traceparent, extract_traceparent, new_traceparent
from faultdebug.session import identity_from_env
from faultdebug.retry_ledger import RetryCapacityExceeded, RetryConflict, RetryDeadlineExceeded, RetryLedger

ROLE = os.environ["SHOP_ROLE"]
ORDINAL = int(os.environ["SHOP_ORDINAL"])
if not 1 <= ORDINAL <= 255:
    raise ValueError("SHOP_ORDINAL must be 1..255 and unique within a generation")
PROCESS_ID = os.environ["FAULTDEBUG_PROCESS_ID"]
SESSION = os.environ["FAULTDEBUG_SESSION_ID"]
PROCESS_GENERATION = identity_from_env({
    "session_id": SESSION, "process_id": PROCESS_ID,
    "process_generation": os.environ.get("FAULTDEBUG_PROCESS_GENERATION", "1"),
}, env={}).process_generation
CLOCK = local_clock_identity()
PEERS = json.loads(os.environ["SHOP_PEERS"])
SCENARIOS = {"success", "inventory_shortage", "payment_decline", "payment_crash",
             "inventory_timeout", "notification_failure", "inventory_response_loss"}
METHODS = {"/products": 1, "/cart": 2, "/checkout": 3, "/reserve": 4,
           "/release": 5, "/authorize": 6, "/ship": 7, "/notify": 8, "/risk": 9}
# Linux/glibc also exports no-op __cyg_profile hooks. Prefer this module's
# runtime dependency so its instrumented callbacks cannot bind to those stubs.
NATIVE = ctypes.CDLL(os.environ["SHOP_BOUNDARY"], mode=os.RTLD_NOW | os.RTLD_DEEPBIND)
NATIVE.fd_rpc_begin.argtypes = [ctypes.c_uint64] * 4 + [ctypes.c_uint32, ctypes.c_uint64]
NATIVE.fd_rpc_end.argtypes = [ctypes.c_uint64] * 4 + [ctypes.c_uint32] * 2 + [ctypes.c_uint64, ctypes.c_uint32]
NATIVE.fd_rpc_begin.restype = NATIVE.fd_rpc_end.restype = ctypes.c_int
NATIVE.shop_request_boundary.argtypes = NATIVE.shop_payment_fault.argtypes = []
NATIVE.shop_request_boundary.restype = NATIVE.shop_payment_fault.restype = None
LOCK = threading.RLock()
EVENT_LOCK = threading.Lock()
COUNTER = 0
STATE = {"stock": 10000, "reservations": {}, "charges": {}, "orders": {},
         "carts": {}, "shipments": {}, "notifications": {}}
EVENT_PATH = Path(os.environ.get("SHOP_EVENT_PATH", "/evidence/events.jsonl"))
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)
LEDGER = None
LEDGER_PATH = None


def configure_inventory_ledger(path: str | Path) -> None:
    """Opt in to this fixture's SQLite-only atomic inventory mutation."""
    global LEDGER, LEDGER_PATH
    LEDGER_PATH = Path(path)
    LEDGER = RetryLedger(LEDGER_PATH)
    with sqlite3.connect(LEDGER_PATH, timeout=5) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS shop_inventory_stock (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                stock INTEGER NOT NULL CHECK (stock >= 0));
            INSERT OR IGNORE INTO shop_inventory_stock VALUES (1, 10000);
            CREATE TABLE IF NOT EXISTS shop_inventory_reservations (
                order_id TEXT PRIMARY KEY, quantity INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('reserved', 'released')));
            CREATE TABLE IF NOT EXISTS shop_inventory_mutations (
                sequence INTEGER PRIMARY KEY, operation_id TEXT NOT NULL,
                action TEXT NOT NULL, order_id TEXT NOT NULL, quantity INTEGER NOT NULL);
        """)


if os.environ.get("SHOP_LEDGER_PATH"):
    configure_inventory_ledger(os.environ["SHOP_LEDGER_PATH"])


def emit(kind: str, ctx: dict | None = None, **fields) -> None:
    caller = inspect.currentframe().f_back
    row = {"schema": 1, "kind": kind, "service": ROLE, "process_id": PROCESS_ID,
           "process_generation": PROCESS_GENERATION, "session_id": SESSION, "pid": os.getpid(), "tid": threading.get_native_id(),
           "clock": CLOCK,
           "monotonic_ns": time.monotonic_ns(), "source_file": "test/shop/service.py",
           "source_line": caller.f_lineno, **(ctx or {}), **fields}
    with EVENT_LOCK, EVENT_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, separators=(",", ":")) + "\n")
        stream.flush()
        if kind in {"failure", "fault_triggered"}:
            os.fsync(stream.fileno())


def new_id() -> int:
    global COUNTER
    with LOCK:
        COUNTER += 1
        if COUNTER >= 2**24:
            raise RuntimeError("fixture RPC identity budget exhausted; start a new generation")
        # A restart must increment process generation. Ordinals are unique among
        # this fixture's peers; the bounded counter must never silently wrap.
        return (PROCESS_GENERATION << 32) | (ORDINAL << 24) | COUNTER


def span(ctx: dict, path: str, direction: int, status: int | None = None) -> None:
    # rpc_id is the explicit correlation shared by this demo's HTTP peers.
    # Native numeric RPC records do not carry W3C span IDs or prove retry pairing.
    args = (ctx["rpc_id"], ctx["trace_id_hi"], ctx["trace_id"], METHODS[path], direction)
    accepted = (NATIVE.fd_rpc_begin(*args, time.monotonic_ns()) if status is None else
                NATIVE.fd_rpc_end(*args, status, time.monotonic_ns(), 2))
    if accepted != 1:
        raise RuntimeError("numeric RPC event not accepted by native runtime")


def valid_operation_id(value: object) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 128
            and "," not in value and all(33 <= ord(char) <= 126 for char in value))


def call(peer: str, path: str, body: dict, parent: dict, timeout: float = 3,
         *, operation_id: str | None = None, attempt: int = 1) -> tuple[int, dict]:
    if operation_id is None:
        # Stable across explicit caller retries; each service action remains a
        # separate operation even when an order spans several downstream calls.
        identity = json.dumps([path, body.get("order_id", parent["request_id"])], ensure_ascii=True)
        operation_id = "shop:" + hashlib.sha256(identity.encode()).hexdigest()
    if not valid_operation_id(operation_id) or type(attempt) is not int or not 1 <= attempt <= 3:
        raise ValueError("invalid logical operation or bounded attempt")
    timeout_ms = int(timeout * 1000)
    local_deadline_ns(timeout_ms)  # Validate the bounded relative wire budget.
    outgoing = child_traceparent(TraceParent(parent["trace_id_hi"], parent["trace_id"],
                                             parent["span_id"], parent["trace_flags"]))
    ctx = {"trace_id_hi": outgoing.trace_id_hi, "trace_id": outgoing.trace_id_lo,
           "span_id": outgoing.parent_id, "parent_span_id": parent["span_id"],
           "trace_flags": outgoing.trace_flags, "rpc_id": new_id(),
           "parent_rpc_id": parent["rpc_id"], "request_id": parent["request_id"],
           "operation_id": operation_id, "attempt": attempt, "attempt_source": "local_explicit",
           "attempt_evidence_class": "application_self_report"}
    span(ctx, path, 2)
    emit("client_begin", ctx, peer=peer, path=path, timeout_ms=timeout_ms)
    connection = http.client.HTTPConnection(PEERS[peer], timeout=timeout)
    # Legacy X-Shop-Trace is accepted on ingress only. Mixed-version peers that
    # only understand that header cannot preserve a full 128-bit outgoing ID.
    headers = {"Content-Type": "application/json", "traceparent": outgoing.to_header(),
               "X-Shop-Rpc": str(ctx["rpc_id"]), "X-Shop-Parent": str(ctx["parent_rpc_id"]),
               "X-Shop-Request": ctx["request_id"],
               "X-Shop-Timeout-Ms": str(timeout_ms),
               "X-Shop-Operation": operation_id, "X-Shop-Attempt": str(attempt)}
    try:
        connection.request("POST", path, json.dumps(body), headers)
        response = connection.getresponse()
        status, result = response.status, json.loads(response.read(65537))
    except TimeoutError:
        status, result = 504, {"code": "upstream_deadline", "peer": peer}
        emit("symptom", ctx, peer=peer, status=status, code="upstream_deadline",
             reason="No response arrived within the caller's RPC timeout.")
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        status, result = 502, {"code": "upstream_transport", "peer": peer}
        emit("symptom", ctx, peer=peer, status=status, code="upstream_transport",
             reason=f"Upstream connection failed: {type(exc).__name__}")
    finally:
        connection.close()
    span(ctx, path, 2, status)
    emit("client_end", ctx, peer=peer, path=path, status=status)
    return status, result


def failure(ctx: dict, code: str, reason: str, status: int) -> tuple[int, dict]:
    emit("failure", ctx, code=code, reason=reason, status=status,
         source_line=inspect.currentframe().f_back.f_lineno)
    return status, {"code": code, "service": ROLE}


def inventory_state() -> dict:
    if LEDGER is None:
        return STATE
    with sqlite3.connect(LEDGER_PATH, timeout=5) as connection:
        connection.execute("BEGIN")
        stock = connection.execute("SELECT stock FROM shop_inventory_stock WHERE singleton=1").fetchone()[0]
        history = {order: {"quantity": quantity, "state": state} for order, quantity, state in
                   connection.execute("SELECT order_id, quantity, state FROM shop_inventory_reservations")}
        counts = {"reserve": 0, "release": 0}
        counts.update(dict(connection.execute("SELECT action, COUNT(*) FROM shop_inventory_mutations GROUP BY action")))
        ledger_count = connection.execute("SELECT COUNT(*) FROM faultdebug_retry_operations").fetchone()[0]
    return {**STATE, "inventory_backend": "sqlite", "stock": stock,
            "reservations": {order: row["quantity"] for order, row in history.items() if row["state"] == "reserved"},
            "reservation_history": history, "mutation_counts": counts, "ledger_operations": ledger_count}


def durable_inventory(path: str, order: str, quantity: int, ctx: dict, deadline: int) -> tuple[int, dict]:
    action = path.removeprefix("/")
    # The action namespaces the key; caller IDs remain bounded at 128 bytes.
    operation_id = ctx.get("operation_id") or "order:" + hashlib.sha256(order.encode()).hexdigest()
    ledger_id = "inventory:" + hashlib.sha256(json.dumps([action, operation_id]).encode()).hexdigest()

    def mutate(connection: sqlite3.Connection) -> dict:
        existing = connection.execute("SELECT quantity, state FROM shop_inventory_reservations WHERE order_id=?", (order,)).fetchone()
        if existing and existing[0] != quantity:
            raise RetryConflict("order quantity conflicts with durable reservation")
        if action == "reserve":
            if existing and existing[1] == "released":
                raise RetryConflict("released order requires a new order identity")
            if not existing:
                stock = connection.execute("SELECT stock FROM shop_inventory_stock WHERE singleton=1").fetchone()[0]
                if stock < quantity:
                    raise RetryConflict("insufficient remaining stock")
                connection.execute("UPDATE shop_inventory_stock SET stock=stock-? WHERE singleton=1", (quantity,))
                connection.execute("INSERT INTO shop_inventory_reservations VALUES (?, ?, 'reserved')", (order, quantity))
                connection.execute("INSERT INTO shop_inventory_mutations(operation_id,action,order_id,quantity) VALUES (?,?,?,?)",
                                   (operation_id, action, order, quantity))
            return {"reserved": quantity}
        if existing and existing[1] == "reserved":
            connection.execute("UPDATE shop_inventory_stock SET stock=stock+? WHERE singleton=1", (quantity,))
            connection.execute("UPDATE shop_inventory_reservations SET state='released' WHERE order_id=?", (order,))
            connection.execute("INSERT INTO shop_inventory_mutations(operation_id,action,order_id,quantity) VALUES (?,?,?,?)",
                               (operation_id, action, order, quantity))
        elif existing is None:
            # Compensation can arrive before a delayed first reserve. Persist
            # cancellation so that arrival cannot resurrect this order later.
            connection.execute("INSERT INTO shop_inventory_reservations VALUES (?, ?, 'released')", (order, quantity))
            connection.execute("INSERT INTO shop_inventory_mutations(operation_id,action,order_id,quantity) VALUES (?,?,?,?)",
                               (operation_id, action, order, 0))
        return {"released": True}

    try:
        result = LEDGER.apply_once(ledger_id, {"action": action, "order_id": order, "quantity": quantity},
                                   mutate, deadline_ns=deadline)
    except RetryConflict:
        return failure(ctx, "inventory_operation_conflict", "Logical operation or order payload conflicts with durable inventory history.", 409)
    except RetryDeadlineExceeded:
        return failure(ctx, "expired_before_reservation", "Receiver-local RPC budget expired; the inventory transaction was rolled back.", 504)
    except (RetryCapacityExceeded, sqlite3.OperationalError):
        return failure(ctx, "inventory_ledger_unavailable", "Durable inventory is busy or at its fixed operation capacity; no result was acknowledged.", 503)
    emit("inventory_operation", ctx, order_id=order, action=action, replayed=result.replayed,
         atomic_scope="local_sqlite_transaction")
    return 200, {**result.value, "replayed": result.replayed}


def dispatch(path: str, body: dict, ctx: dict, deadline: int) -> tuple[int, dict]:
    scenario = body.get("scenario", "success")
    if scenario not in SCENARIOS:
        return 400, {"code": "invalid_scenario"}
    order = body.get("order_id", ctx["request_id"])
    quantity = body.get("quantity", 1)
    if not isinstance(order, str) or not order or len(order) > 80 or type(quantity) is not int or not 1 <= quantity <= 20:
        return 400, {"code": "invalid_order"}
    if ROLE == "retry-client" and path in {"/reserve", "/release"}:
        return call("inventory", path, body, ctx, timeout=ctx["timeout_ms"] / 1000,
                    operation_id=ctx.get("operation_id"), attempt=ctx.get("attempt") or 1)
    if ROLE == "gateway":
        if path == "/products":
            return call("catalog", path, body, ctx)
        if path == "/cart":
            return call("cart", path, body, ctx)
        if path == "/checkout":
            # A real cart process participates in every order.
            status, cart = call("cart", "/cart", body, ctx)
            if status != 200:
                return status, cart
            return call("checkout", path, {**body, "quantity": cart["quantity"]}, ctx)
    if ROLE == "catalog" and path == "/products":
        return 200, {"products": [{"sku": "FD-01", "name": "FaultDebug hoodie", "price": 39000}]}
    if ROLE == "cart" and path == "/cart":
        status, products = call("catalog", "/products", body, ctx)
        if status != 200:
            return status, products
        with LOCK:
            STATE["carts"][order] = quantity
        return 200, {"order_id": order, "quantity": quantity,
                     "amount": products["products"][0]["price"] * quantity}
    if ROLE == "checkout" and path == "/checkout":
        # Serialize this fixture's orchestration to make replay deterministic.
        with LOCK:
            if order in STATE["orders"]:
                return 200, {**STATE["orders"][order], "replayed": True}
            for peer in sorted(p for p in PEERS if p.startswith("risk-")):
                status, result = call(peer, "/risk", body, ctx)
                if status != 200:
                    return status, result
            status, result = call("inventory", "/reserve", body, ctx, timeout=0.3)
            if status != 200:
                return status, result
            status, result = call("payment", "/authorize", body, ctx)
            if status != 200:
                rollback, _ = call("inventory", "/release", body, ctx)
                emit("compensation", ctx, peer="inventory", status=rollback, order_id=order)
                return status, {**result, "reservation_released": rollback == 200}
            status, shipping = call("shipping", "/ship", body, ctx)
            if status != 200:
                return status, shipping
            status, notification = call("notification", "/notify", body, ctx)
            result = {"order_id": order, "state": "completed", "quantity": quantity,
                      "notification": "sent" if status == 200 else "deferred",
                      "shipment": shipping["shipment_id"], "replayed": False}
            STATE["orders"][order] = result
            emit("order_completed", ctx, order_id=order, notification_status=status)
            return 200, result
    if ROLE == "inventory":
        if scenario == "inventory_response_loss" and LEDGER is None:
            return 400, {"code": "durable_ledger_required"}
        if path == "/reserve":
            if scenario == "inventory_shortage":
                return failure(ctx, "inventory_shortage", "Injected stock budget is zero; requested quantity cannot be reserved.", 409)
            if scenario == "inventory_timeout":
                emit("fault_triggered", ctx, code="inventory_latency", delay_ms=900,
                     reason="Injected 900 ms inventory delay exceeds the checkout RPC timeout of 300 ms.")
                time.sleep(0.9)
            if LEDGER is not None:
                return durable_inventory(path, order, quantity, ctx, deadline)
            with LOCK:
                if time.monotonic_ns() >= deadline:
                    return failure(ctx, "expired_before_reservation", "Receiver-local RPC budget expired before stock mutation; no reservation was created.", 504)
                if order not in STATE["reservations"]:
                    if STATE["stock"] < quantity:
                        return failure(ctx, "stock_exhausted", "Insufficient remaining stock.", 409)
                    STATE["stock"] -= quantity
                    STATE["reservations"][order] = quantity
                return 200, {"reserved": STATE["reservations"][order]}
        if path == "/release":
            if LEDGER is not None:
                return durable_inventory(path, order, quantity, ctx, deadline)
            with LOCK:
                STATE["stock"] += STATE["reservations"].pop(order, 0)
                return 200, {"released": True}
    if ROLE == "payment" and path == "/authorize":
        if scenario == "payment_decline":
            return failure(ctx, "payment_declined", "Injected authorization policy rejects this demo payment before charging.", 402)
        if scenario == "payment_crash":
            emit("fault_triggered", ctx, code="payment_native_trap",
                 reason="Injected invalid authorization transition calls the native payment invariant trap.")
            NATIVE.shop_payment_fault()
        with LOCK:
            STATE["charges"].setdefault(order, quantity * 39000)
            return 200, {"authorized": True, "amount": STATE["charges"][order]}
    if ROLE == "shipping" and path == "/ship":
        with LOCK:
            STATE["shipments"].setdefault(order, "shipment-" + order)
            return 200, {"shipment_id": STATE["shipments"][order]}
    if ROLE == "notification" and path == "/notify":
        if scenario == "notification_failure":
            return failure(ctx, "notification_unavailable", "Injected notification provider outage; the paid order remains completed.", 503)
        with LOCK:
            STATE["notifications"][order] = "sent"
        return 200, {"sent": True}
    if ROLE.startswith("risk-") and path == "/risk":
        # Every extra application process runs a distinct risk check.
        return 200, {"approved": True, "worker": ROLE}
    return 404, {"code": "unknown_route"}


class ServiceServer(ThreadingHTTPServer):
    """Bounded, persistent workers preserve native per-thread ring history."""
    request_queue_size = 128

    def __init__(self, *args):
        super().__init__(*args)
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="shop-http")

    def process_request(self, request, client_address):
        self.pool.submit(self.process_request_thread, request, client_address)

    def server_close(self):
        super().server_close()
        self.pool.shutdown(wait=True)


def single_header(headers, name: str) -> str | None:
    values = headers.get_all(name, [])
    if len(values) > 1:
        raise ValueError(f"duplicate {name}")
    if not values:
        return None
    value = values[0]
    if not isinstance(value, str) or not value or "," in value:
        raise ValueError(f"invalid {name}")
    return value


def numeric_header(headers, name: str, default: int, *, minimum: int = 0) -> int:
    value = single_header(headers, name)
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal():
        raise ValueError(f"invalid {name}")
    result = int(value)
    if not minimum <= result < 2**64:
        raise ValueError(f"invalid {name}")
    return result


def request_context(headers, body: dict) -> tuple[dict, int]:
    operation_id = single_header(headers, "X-Shop-Operation")
    attempt_text = single_header(headers, "X-Shop-Attempt")
    if (operation_id is None) != (attempt_text is None):
        raise ValueError("partial logical operation mapping")
    if operation_id is not None and (not valid_operation_id(operation_id) or attempt_text not in {"1", "2", "3"}):
        raise ValueError("invalid logical operation mapping")
    incoming = extract_traceparent(headers)
    legacy = single_header(headers, "X-Shop-Trace")
    legacy_trace = numeric_header(headers, "X-Shop-Trace", 0, minimum=1) if legacy is not None else None
    if incoming is not None and legacy_trace is not None:
        if incoming.trace_id_hi != 0 or incoming.trace_id_lo != legacy_trace:
            raise ValueError("conflicting trace identities")
    if incoming is not None:
        current = child_traceparent(incoming)
        parent_span_id = incoming.parent_id
        context_source = "w3c_traceparent"
    else:
        current = new_traceparent()
        parent_span_id = 0  # A legacy RPC ID does not establish a W3C parent span.
        context_source = "legacy_shop_trace" if legacy_trace is not None else "local_root"
        if legacy_trace is not None:
            current = TraceParent(0, legacy_trace, current.parent_id, current.trace_flags)
    request_id = single_header(headers, "X-Shop-Request") or body.get("order_id") or str(new_id())
    if not isinstance(request_id, str) or len(request_id) > 80:
        raise ValueError("request identity")
    timeout_ms = numeric_header(headers, "X-Shop-Timeout-Ms", 5000, minimum=1)
    # Absolute monotonic timestamps cannot be compared across hosts or time
    # namespaces. Old X-Shop-Deadline is deliberately ignored, even if present.
    legacy_deadline = single_header(headers, "X-Shop-Deadline")
    deadline = local_deadline_ns(timeout_ms)
    ctx = {"rpc_id": numeric_header(headers, "X-Shop-Rpc", new_id(), minimum=1),
           "trace_id_hi": current.trace_id_hi, "trace_id": current.trace_id_lo,
           "span_id": current.parent_id, "parent_span_id": parent_span_id,
           "trace_flags": current.trace_flags, "context_source": context_source,
           "parent_rpc_id": numeric_header(headers, "X-Shop-Parent", 0),
           "request_id": request_id, "timeout_ms": timeout_ms,
           "operation_id": operation_id, "attempt": int(attempt_text) if attempt_text else None,
           "attempt_source": "peer_self_reported" if operation_id else "unknown",
           "attempt_evidence_class": "application_self_report" if operation_id else "unknown",
           "legacy_deadline_ignored": legacy_deadline is not None}
    return ctx, deadline


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def respond(self, status: int, data: dict | bytes, content_type="application/json"):
        encoded = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/health":
            return self.respond(200, {"role": ROLE, "pid": os.getpid(), "process_id": PROCESS_ID})
        if self.path == "/state":
            with LOCK:
                return self.respond(200, inventory_state() if ROLE == "inventory" else STATE)
        if self.path == "/" and ROLE == "gateway":
            return self.respond(200, Path(__file__).with_name("store.html").read_bytes(), "text/html; charset=utf-8")
        self.respond(404, {"code": "unknown_route"})

    def do_POST(self):
        if self.path == "/shutdown":
            self.respond(200, {"stopping": True})
            threading.Thread(target=self.server.shutdown).start()
            return
        if self.path not in METHODS:
            return self.respond(404, {"code": "unknown_route"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= 65536:
                raise ValueError("body size")
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("object required")
            ctx, deadline = request_context(self.headers, body)
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.respond(400, {"code": "invalid_request"})
        span(ctx, self.path, 1)
        NATIVE.shop_request_boundary()
        emit("server_begin", ctx, path=self.path)
        try:
            status, result = dispatch(self.path, body, ctx, deadline)
        except Exception as exc:
            status, result = failure(ctx, "unhandled_service_error", f"Service exception: {type(exc).__name__}", 500)
        span(ctx, self.path, 1, status)
        emit("server_end", ctx, path=self.path, status=status)
        if (ROLE == "inventory" and LEDGER is not None and self.path == "/reserve" and status == 200
                and body.get("scenario") == "inventory_response_loss" and not result.get("replayed", True)):
            # Explicit fixture only: mutation and ledger result have committed,
            # but the caller receives a transport failure. Replays never drop.
            emit("fault_triggered", ctx, code="inventory_response_loss_after_commit",
                 reason="Explicit fixture discarded the first committed reserve response.")
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        self.respond(status, result)


if __name__ == "__main__":
    emit("process_started")
    server = ServiceServer((os.environ.get("SHOP_HOST", "0.0.0.0"), int(os.environ.get("SHOP_PORT", "8080"))), Handler)
    server.daemon_threads = False
    server.serve_forever(poll_interval=0.1)
    server.server_close()
    emit("process_stopped")

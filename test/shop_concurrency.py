#!/usr/bin/env python3
"""Captured multi-process checkout concurrency and real TCP fault controls.

The bounded loopback fixture compares four distinct orders in independently
captured eight-service sessions. A separate durable inventory session checks
before-forward failure, committed-response loss, and recovery after restart.
No wall-clock speedup threshold or container/remote-network claim is made.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test/shop"))
from fault_proxy import FaultProxy
from shop_http_retry import (CollectedService, TRACE_HI, TRACE_LO, TraceParent,
                             build_service_report, events, request, require,
                             rpc_edges, rpc_trace, unused_port)

CORE = ["gateway", "catalog", "cart", "checkout", "inventory", "payment", "shipping", "notification"]


def ports(count: int) -> list[int]:
    result: set[int] = set()
    while len(result) < count:
        result.add(unused_port())
    return list(result)


def operation(port: int, index: int, order: str, quantity: int = 1, *,
              path: str = "/checkout", logical: str | None = None,
              attempt: int = 1, barrier: threading.Barrier | None = None) -> dict:
    body = {"order_id": order, "quantity": quantity, "scenario": "success"}
    headers = {
        "traceparent": TraceParent(TRACE_HI, TRACE_LO + index, index + 100, 0).to_header(),
        "X-Shop-Rpc": str(2_000_000_000_000 + index),
        "X-Shop-Request": f"request-{index}",
        "X-Shop-Operation": logical or f"checkout:{order}",
        "X-Shop-Attempt": str(attempt), "X-Shop-Timeout-Ms": "5000",
    }
    if barrier:
        barrier.wait(timeout=5)
    started = time.perf_counter_ns()
    status, result = request(port, path, body, headers, timeout=8)
    return {"order_id": order, "quantity": quantity, "attempt": attempt,
            "operation_id": headers["X-Shop-Operation"], "request_id": headers["X-Shop-Request"],
            "status": status, "result": result,
            "latency_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
            "json_request_body_bytes": len(json.dumps(body).encode()),
            "json_response_body_bytes": len(json.dumps(result).encode())}


def workload(port: int, orders: list[str], start: int) -> dict:
    barrier = threading.Barrier(len(orders))
    started = time.perf_counter_ns()
    with ThreadPoolExecutor(max_workers=len(orders)) as pool:
        futures = [pool.submit(operation, port, start + index, order, barrier=barrier)
                   for index, order in enumerate(orders)]
        responses = [future.result(timeout=12) for future in futures]
    latencies = [row["latency_ms"] for row in responses]
    return {"requests": len(orders), "concurrency": len(orders), "responses": responses,
            "wall_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
            "median_latency_ms": statistics.median(latencies), "max_latency_ms": max(latencies),
            "json_request_body_bytes": sum(row["json_request_body_bytes"] for row in responses),
            "json_response_body_bytes": sum(row["json_response_body_bytes"] for row in responses)}


def overlap(rows: list[dict], orders: set[str]) -> int:
    selected = sorted((row for row in rows if row.get("kind") in {"checkout_begin", "checkout_end"}
                       and row.get("order_id") in orders), key=lambda row: row["monotonic_ns"])
    active: set[str] = set()
    maximum = 0
    for row in selected:
        key = row["request_id"]
        if row["kind"] == "checkout_begin":
            require(key not in active, "duplicate checkout begin")
            active.add(key)
            maximum = max(maximum, len(active))
        else:
            require(key in active, "checkout ended without begin")
            active.remove(key)
    require(not active and len(selected) == 2 * len(orders), "checkout overlap evidence is incomplete")
    return maximum


def captured_summary(directory: Path, services: list[CollectedService]) -> tuple[dict, dict]:
    reports = [service.report for service in services]
    decoded = [rpc_trace(report) for report in reports]
    rpc_dropped = sum(int(report.get("rpc", {}).get("header", {}).get("dropped_count", 0)) for report in reports)
    thread_dropped = sum(int(thread.get("dropped_count", 0)) for report in reports for thread in report.get("threads", []))
    require(rpc_dropped == thread_dropped == 0, "native capture dropped events")
    model = build_service_report(directory)
    forbidden = {"application_identity_unmatched", "application_status_not_corroborated", "rpc_decode_error",
                 "rpc_sequence_gap", "rpc_sequence_not_monotonic", "native_capture_incomplete"}
    require(not any(row.get("reason") in forbidden for row in model["unresolved"]),
            "service report lost native or application integrity")
    (directory / "service-report.json").write_text(json.dumps(model, indent=2) + "\n")
    summary = {
        "application_executions": len(services), "application_pids": [service.pid for service in services],
        "native_rpc_events": sum(len(row["observed"]) for row in decoded),
        "native_cross_process_relations": len(rpc_edges(reports)),
        "native_rpc_dropped": rpc_dropped, "native_thread_dropped": thread_dropped,
        "native_capture_bytes": sum(row["bytes"] for row in model["evidence_files"]
                                    if row["kind"] == "checksummed_native_capture"),
        "application_log_bytes": sum(row["bytes"] for row in model["evidence_files"]
                                     if row["kind"] == "application_self_report"),
        "unresolved_count": len(model["unresolved"]),
        "unresolved_reasons": sorted({row["reason"] for row in model["unresolved"]}),
    }
    return summary, model


def checkout_session(directory: Path, boundary: Path, runtime: Path, *, mode: str) -> dict:
    directory.mkdir()
    assigned = dict(zip(CORE, ports(len(CORE))))
    ledger = directory / "inventory.sqlite3"
    services: list[CollectedService] = []
    session_id = f"http-concurrent-checkout-{mode}"
    proxy = FaultProxy("127.0.0.1", assigned["inventory"], mode="delay_after_response",
                       delay_ms=50, event_path=directory / "proxy-fixture.jsonl")
    try:
        proxy.start()
        peers = {name: f"127.0.0.1:{port}" for name, port in assigned.items()}
        peers["inventory"] = f"127.0.0.1:{proxy.port}"
        for ordinal, role in enumerate(reversed(CORE), 1):
            # Each role gets a unique native ordinal and explicit process ID.
            service = CollectedService(
                directory, role, role=role, generation=1, ordinal=ordinal,
                port=assigned[role], peers=peers, boundary=boundary, runtime=runtime,
                ledger=ledger if role == "inventory" else None, session_id=session_id,
                extra_env={"SHOP_CHECKOUT_LOCK_MODE": "global"} if mode == "global" else {},
            )
            services.append(service)
            service.start()
        require(len({service.pid for service in services}) == 8, "services did not execute in eight distinct processes")
        fresh = workload(assigned["gateway"], [f"distinct-{index}" for index in range(4)], 1)
        require(all(row["status"] == 200 and row["result"].get("state") == "completed"
                    and not row["result"].get("replayed") for row in fresh["responses"]),
                "distinct-order checkout failed")
        duplicate = workload(assigned["gateway"], ["shared-order", "shared-order"], 10)
        require(all(row["status"] == 200 and row["result"].get("state") == "completed"
                    for row in duplicate["responses"]), "concurrent same-order checkout failed")
        require(sorted(row["result"]["replayed"] for row in duplicate["responses"]) == [False, True],
                "concurrent duplicate did not return one fresh and one cached result")
        first, second = ({key: value for key, value in row["result"].items() if key != "replayed"}
                         for row in duplicate["responses"])
        require(first == second, "cached same-order response differs from first completion")
        conflict = operation(assigned["gateway"], 20, "shared-order", 2)
        require(conflict["status"] == 409, "changed quantity replay was accepted")
        states = {role: request(assigned[role], "/state")[1] for role in
                  ("checkout", "inventory", "payment", "shipping", "notification")}
        require(len(states["checkout"]["orders"]) == len(states["payment"]["charges"]) == 5,
                "checkout completion or charge count differs from five unique orders")
        require(states["inventory"]["stock"] == 9995
                and states["inventory"]["mutation_counts"] == {"reserve": 5, "release": 0},
                "same-order duplicate or conflict repeated an inventory mutation")
        require(len(states["shipping"]["shipments"]) == len(states["notification"]["notifications"]) == 5,
                "shipment/notification task count differs from five unique orders")
        with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as connection:
            shared_mutations = connection.execute(
                "SELECT COUNT(*) FROM shop_inventory_mutations WHERE order_id=? AND action='reserve'",
                ("shared-order",),
            ).fetchone()[0]
        require(shared_mutations == 1, "shared order has multiple durable reserve mutations")
        checkout = next(service for service in services if service.spec["role"] == "checkout")
        payment = next(service for service in services if service.spec["role"] == "payment")
        max_active = overlap(events(checkout.directory), {f"distinct-{index}" for index in range(4)})
        require(max_active >= 2 if mode == "keyed" else max_active == 1,
                f"unexpected checkout critical section overlap in {mode} mode: {max_active}")
        shared_charges = [row for row in events(payment.directory)
                          if row.get("kind") == "payment_charge" and row.get("order_id") == "shared-order"]
        require(len(shared_charges) == 1, "shared order did not have exactly one observed payment mutation")
        for service in reversed(services):
            service.stop()
        captured, model = captured_summary(directory, services)
        # Four fresh orders have seven internal RPCs each; the concurrent
        # duplicate adds seven plus three, and the conflicting replay adds
        # three. The external harness is deliberately absent from native pairs.
        require(len(model["calls"]) == captured["native_cross_process_relations"] == 41,
                "native checkout topology lost or invented an internal HTTP endpoint pair")
        client_begins = [row for service in services for row in events(service.directory)
                         if row.get("kind") == "client_begin"]
        require(len(client_begins) == 41
                and len({row["rpc_id"] for row in client_begins}) == 41,
                "native ordinals failed to keep outgoing RPC identities distinct")
        touched = {row["from_service"] for row in model["calls"]} | {row["to_service"] for row in model["calls"]}
        require(touched == set(CORE), "native topology did not involve all eight application roles")
        require(all(row["from_pid"] != row["to_pid"] for row in rpc_edges([service.report for service in services])),
                "native HTTP endpoints are not cross-process")
        require(not model["causes"] or all(row.get("code") == "checkout_order_conflict" for row in model["causes"]),
                "proxy delay configuration was promoted to a service-report cause")
        return {"status": "PASS", "lock_mode": mode, "session_id": session_id,
                "distinct_orders_max_active_in_checkout": max_active,
                "fresh_workload": fresh, "concurrent_duplicate": duplicate, "changed_quantity": conflict,
                "business": {"completed_unique_orders": len(states["checkout"]["orders"]),
                             "inventory_reserve_mutations": states["inventory"]["mutation_counts"]["reserve"],
                             "shared_order_reserve_mutations": shared_mutations, "shared_order_payment_mutations": len(shared_charges),
                             "charge_entries": len(states["payment"]["charges"]),
                             "remaining_stock": states["inventory"]["stock"]},
                "capture": captured, "proxy_evidence_class": "fixture_self_report",
                "proxy_event_count": len(proxy.events)}
    finally:
        for service in reversed(services):
            service.stop(verify=False)
        proxy.stop()


def proxy_session(directory: Path, boundary: Path, runtime: Path) -> dict:
    directory.mkdir()
    inventory_port, client_port = ports(2)
    ledger = directory / "inventory.sqlite3"
    services: list[CollectedService] = []
    attempts = []
    session_id = "http-proxy-fault-recovery"
    proxy = FaultProxy("127.0.0.1", inventory_port, event_path=directory / "proxy-fixture.jsonl")

    def receiver(generation: int) -> CollectedService:
        return CollectedService(directory, f"inventory-g{generation}", role="inventory",
                                generation=generation, ordinal=2, port=inventory_port, peers={},
                                boundary=boundary, runtime=runtime, ledger=ledger, session_id=session_id)

    def state() -> dict:
        status, value = request(inventory_port, "/state")
        require(status == 200 and value.get("inventory_backend") == "sqlite", "durable state missing")
        return value

    def attempt(mode: str, order: str, index: int, number: int = 1) -> dict:
        proxy.set_mode(mode)
        row = operation(client_port, index, order, 3, path="/reserve", logical=f"reserve:{order}", attempt=number)
        proxy.wait_for_events(len(attempts) + 1)
        attempts.append(row)
        return row

    try:
        proxy.start()
        old = receiver(7)
        services.append(old)
        old.start()
        caller = CollectedService(directory, "caller-g7", role="retry-client", generation=7,
                                  ordinal=1, port=client_port, peers={"inventory": f"127.0.0.1:{proxy.port}"},
                                  boundary=boundary, runtime=runtime, session_id=session_id)
        services.append(caller)
        caller.start()
        initial = state()
        before = attempt("reset_before_forward", "blocked-order", 101)
        require(before["status"] == 502 and state()["stock"] == initial["stock"],
                "before-forward fault unexpectedly reached inventory")
        require(not [row for row in events(old.directory) if row.get("kind") == "server_begin"],
                "native receiver application observed a before-forward request")
        lost = attempt("drop_after_response", "lost-order", 102)
        committed = state()
        require(lost["status"] == 502 and committed["stock"] == 9997
                and committed["mutation_counts"]["reserve"] == 1, "response loss did not leave one committed reservation")
        old.stop()
        new = receiver(8)
        services.append(new)
        new.start()
        require(new.pid not in (old.pid, caller.pid), "recovery did not start a new receiver PID")
        retry = attempt("pass", "lost-order", 103, 2)
        recovered = state()
        require(retry["status"] == 200 and retry["result"].get("replayed") is True
                and recovered["stock"] == committed["stock"]
                and recovered["mutation_counts"] == committed["mutation_counts"],
                "recovery retry repeated the durable business mutation")
        control = attempt("pass", "blocked-order", 104, 2)
        final = state()
        require(control["status"] == 200 and not control["result"].get("replayed")
                and final["stock"] == 9994 and final["mutation_counts"]["reserve"] == 2,
                "before-forward fault did not recover through a fresh successful reservation")
        with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as connection:
            lost_mutations = connection.execute(
                "SELECT COUNT(*) FROM shop_inventory_mutations WHERE order_id=? AND action='reserve'",
                ("lost-order",),
            ).fetchone()[0]
        require(lost_mutations == 1, "persistent response-loss audit did not contain exactly one reservation")
        for service in reversed(services):
            service.stop()
        captured, model = captured_summary(directory, services)
        native_clients = [row for row in events(caller.directory) if row.get("kind") == "client_begin"]
        native_receivers = [row for service in (old, new) for row in events(service.directory)
                            if row.get("kind") == "server_begin"]
        require(len(native_clients) == 4 and len(native_receivers) == 3, "fault-stage endpoint count mismatch")
        edges = rpc_edges([service.report for service in services])
        require(len(edges) == 3, "before-forward request created an unsupported receiver edge")
        before_rpc = next(row["rpc_id"] for row in native_clients if row["request_id"] == "request-101")
        require(not any(row["rpc_id"] == before_rpc for row in edges)
                and any(row.get("rpc_id") == before_rpc
                        and row.get("reason") == "rpc_endpoint_pair_not_unique"
                        for row in model["unresolved"]),
                "before-forward missing receiver endpoint did not remain explicitly unresolved")
        require({row["to_process_generation"] for row in edges} == {7, 8}, "native recovery generation missing")
        lost_calls = [row for row in model["calls"] if row.get("operation_id") == "reserve:lost-order"]
        require(any(row.get("status") == 502 and row.get("receiver_status") == 200 for row in lost_calls),
                "caller transport failure and receiver success were not preserved")
        require(any(row.get("status") == row.get("receiver_status") == 200 for row in lost_calls),
                "native recovery success not paired")
        require(not model["causes"], "proxy self-report was promoted into a service-report cause")
        require(captured["unresolved_count"] > 0, "unpaired external/before-forward gaps were hidden")
        fixture = proxy.events
        require(len(fixture) == 4, "proxy request completion count mismatch")
        require(fixture[0]["upstream_request_sent"] is False
                and fixture[1]["upstream_response_complete"] is True
                and fixture[1]["upstream_response_status"] == 200
                and fixture[1]["forwarded_response_complete"] is False,
                "proxy did not execute distinct before-forward and after-response controls")
        return {"status": "PASS", "attempts": attempts, "capture": captured,
                "receiver_generations": [7, 8], "receiver_request_count": 3,
                "native_endpoint_pairs": len(edges), "business_reserve_mutations": final["mutation_counts"]["reserve"],
                "lost_order_reserve_mutations": lost_mutations, "final_stock": final["stock"],
                "proxy_fixture_events": fixture, "proxy_evidence_class": "fixture_self_report",
                "service_report_causes": 0,
                "interpretation": "Application/native observations show endpoint status and mutation effects. The harness proxy records its injected action separately; the service report preserves unpaired gaps and makes no proxy-cause attribution."}
    finally:
        for service in reversed(services):
            service.stop(verify=False)
        proxy.stop()


def run_acceptance(evidence: Path, boundary: Path, runtime: Path) -> dict:
    keyed = checkout_session(evidence / "keyed", boundary, runtime, mode="keyed")
    baseline = checkout_session(evidence / "global", boundary, runtime, mode="global")
    faults = proxy_session(evidence / "tcp-fault-recovery", boundary, runtime)
    checks = ["eight_separate_process_native_topology", "default_distinct_order_checkout_overlap",
              "global_baseline_serialized_checkout", "concurrent_same_order_one_reserve_one_charge",
              "changed_quantity_conflict", "before_forward_no_receiver_endpoint_or_mutation",
              "after_response_caller_502_receiver_200", "restart_generation_retry_one_mutation",
              "healthy_recovery_control", "proxy_cause_kept_separate_and_unknown_gaps_preserved",
              "complete_zero_drop_native_captures"]
    return {"schema": 1, "status": "PASS", "native": "REAL_BOUNDARY_AND_RUNTIME",
            "http": "real_cross_process_loopback", "checks": checks,
            "task_completion": {"completed": len(checks), "total": len(checks)},
            "application_executions": 19, "checkout": {"keyed": keyed, "global_baseline": baseline},
            "tcp_fault_recovery": faults,
            "efficiency": {"workload": "same_four_distinct_orders_concurrency_four_50ms_proxy_response_delay",
                           "keyed_wall_ms": keyed["fresh_workload"]["wall_ms"],
                           "global_wall_ms": baseline["fresh_workload"]["wall_ms"],
                           "keyed_median_latency_ms": keyed["fresh_workload"]["median_latency_ms"],
                           "global_median_latency_ms": baseline["fresh_workload"]["median_latency_ms"],
                           "interpretation": "Descriptive fixed-fixture observations only. Correctness acceptance uses same-process critical-section overlap, unique completion/mutation counts, native endpoint pairs and zero capture loss."},
            "limitations": ["Loopback uses distinct processes on one host; no container or remote-host claim.",
                            "Native records cover C++ boundary calls and explicit numeric RPC endpoints, not Python stacks.",
                            "Inventory replay atomicity is confined to its SQLite transaction; checkout/payment are memory-only.",
                            "Proxy records and operation/attempt labels are self-reports; proxy configuration does not establish a native cause edge.",
                            "Uncaptured external harness requests and before-forward receiver absence remain unresolved in service reports."],
            "evidence": str(evidence)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    boundary = args.boundary.resolve() if args.boundary else None
    runtime = args.runtime_dir.resolve() if args.runtime_dir else (boundary.parents[2] if boundary else None)
    if boundary is None or not boundary.is_file() or runtime is None or not (runtime / "libfaultdebug_runtime.so").is_file():
        print(json.dumps({"status": "NOT RUN", "reason": "--boundary and a built native runtime are required"}))
        return 2
    temporary = None
    if args.output:
        output = args.output.resolve()
        evidence = output.with_name(output.stem + "-evidence")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() or evidence.exists():
            parser.error("output or evidence already exists; choose a fresh --output")
        evidence.mkdir()
    else:
        temporary = tempfile.TemporaryDirectory(prefix="faultdebug-shop-concurrency-")
        evidence = Path(temporary.name)
    try:
        try:
            result = run_acceptance(evidence, boundary, runtime)
        except Exception as exc:
            result = {"schema": 1, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "evidence": str(evidence)}
        if args.output:
            output.write_text(json.dumps(result, indent=2) + "\n")
        else:
            result["evidence_retained"] = False
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Real native HTTP peers, durable response-loss retry, and bounded measurements.

Requires the compiled shop boundary and runtime. Each service executes in its
own Python process under run_target; there is no fake-recorder mode. Supplying
--output preserves the checksummed native captures and application event logs
beside the JSON result. Measurements describe this fixed local fixture only.
"""
from __future__ import annotations

import argparse
import copy
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faultdebug.http_context import TraceParent
from faultdebug.rpc import process_relations, rpc_trace
from faultdebug.service_report import build_service_report

TRACE_HI = 0x1234567890ABCDEF
TRACE_LO = 0xFEDCBA0987654321
SESSION = "http-durable-retry-acceptance"


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AssertionError(reason)


def request(port: int, path: str, body: dict | None = None,
            headers: dict | None = None, *, timeout: float = 5) -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request("GET" if body is None else "POST", path,
                           None if body is None else json.dumps(body),
                           {"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        return response.status, json.loads(response.read(65537))
    finally:
        connection.close()


def unused_port() -> int:
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        return bound.getsockname()[1]


def events(directory: Path) -> list[dict]:
    path = directory / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


class CollectedService:
    def __init__(self, evidence: Path, name: str, *, role: str, generation: int,
                 ordinal: int, port: int, peers: dict, boundary: Path,
                 runtime: Path, ledger: Path | None = None,
                 extra_env: dict[str, str] | None = None,
                 session_id: str = SESSION, process_id: str | None = None):
        self.directory = evidence / name
        self.directory.mkdir()
        self.port, self.process, self.pid = port, None, None
        self.report = None
        self.log = None
        self.spec = {
            "directory": str(self.directory), "boundary": str(boundary),
            "runtime": str(runtime), "role": role, "generation": generation,
            "ordinal": ordinal, "port": port, "peers": peers,
            "ledger": str(ledger) if ledger else None,
            "process_id": process_id or role, "session_id": session_id,
            "extra_env": dict(extra_env or {}),
        }

    def start(self) -> None:
        path = self.directory / "collector-spec.json"
        path.write_text(json.dumps(self.spec))
        self.log = (self.directory / "service.log").open("w")
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--collector-spec", str(path)],
            cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"{self.spec['role']} exited during startup; see {self.directory / 'service.log'}")
            try:
                status, health = request(self.port, "/health", timeout=0.2)
                if status == 200:
                    self.pid = health["pid"]
                    return
            except (OSError, http.client.HTTPException):
                pass
            time.sleep(0.025)
        raise AssertionError(f"{self.spec['role']} did not become healthy")

    def stop(self, *, verify: bool = True) -> dict | None:
        if self.process is None:
            return self.report
        try:
            if self.process.poll() is None:
                try:
                    request(self.port, "/shutdown", {}, timeout=1)
                except (OSError, http.client.HTTPException):
                    pass
                try:
                    self.process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    # Kill the application first so its collector can close the
                    # mapping and reap it. This path fails verification.
                    if self.pid:
                        try:
                            os.kill(self.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
            path = self.directory / "collection.json"
            if path.exists():
                self.report = json.loads(path.read_text())
            if verify:
                require(self.process.returncode == 0, f"collector wrapper failed: {self.directory}")
                require(isinstance(self.report, dict), "collector report absent")
                require(self.report.get("collector", {}).get("ok") is True, "native collector failed")
                require(self.report.get("target", {}).get("returncode") == 0, "application did not stop cleanly")
                require(self.report.get("complete") is True, "native capture is incomplete")
                decoded = rpc_trace(self.report)
                require(decoded["status"] == "complete", f"incomplete RPC evidence: {decoded['unresolved']}")
                require(bool(decoded["observed"]), "no native RPC events")
                require(all(row["process_generation"] == self.spec["generation"]
                            for row in decoded["observed"]), "native generation was not preserved")
            return self.report
        finally:
            if self.log:
                self.log.close()


def collector_child(spec_path: Path) -> int:
    from faultdebug.run import run_target
    spec = json.loads(spec_path.read_text())
    directory = Path(spec["directory"])
    os.environ.update({
        "FAULTDEBUG_RUNTIME_DIR": spec["runtime"],
        "SHOP_BOUNDARY": spec["boundary"], "SHOP_ROLE": spec["role"],
        "SHOP_ORDINAL": str(spec["ordinal"]), "SHOP_PEERS": json.dumps(spec["peers"]),
        "SHOP_HOST": "127.0.0.1", "SHOP_PORT": str(spec["port"]),
        "SHOP_EVENT_PATH": str(directory / "events.jsonl"),
    })
    os.environ.update(spec.get("extra_env", {}))
    os.environ["PYTHONPATH"] = str(ROOT) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    if spec["ledger"]:
        os.environ["SHOP_LEDGER_PATH"] = spec["ledger"]
    else:
        os.environ.pop("SHOP_LEDGER_PATH", None)
    report = run_target(
        [sys.executable, str(ROOT / "test/shop/service.py")], timeout=45,
        artifact_dir=directory, collect_success=True,
        identity={"session_id": spec.get("session_id", SESSION), "process_id": spec["process_id"],
                  "process_generation": spec["generation"], "role": spec["role"]},
    )
    (directory / "collection.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report.get("collector", {}).get("ok") is True and report.get("target", {}).get("returncode") == 0 else 1


def rpc_edges(reports: list[dict]) -> list[dict]:
    return [row for row in process_relations(reports)["observed"] if row.get("kind") == "rpc"]


def run_acceptance(evidence: Path, boundary: Path, runtime: Path) -> dict:
    inventory_port, client_port = unused_port(), unused_port()
    while inventory_port == client_port:
        client_port = unused_port()
    ledger = evidence / "inventory.sqlite3"
    services, attempts, checks = [], [], []
    caller = CollectedService(evidence, "caller-g7", role="retry-client", generation=7,
                              ordinal=1, port=client_port,
                              peers={"inventory": f"127.0.0.1:{inventory_port}"},
                              boundary=boundary, runtime=runtime)

    def inventory(generation: int) -> CollectedService:
        return CollectedService(evidence, f"inventory-g{generation}", role="inventory",
                                generation=generation, ordinal=2, port=inventory_port,
                                peers={}, boundary=boundary, runtime=runtime, ledger=ledger)

    def operation(name: str, order: str, quantity: int, *, attempt: int = 1,
                  scenario: str = "success", path: str = "/reserve", timeout_ms: int = 3000) -> tuple[int, dict]:
        index = len(attempts) + 1
        body = {"order_id": order, "quantity": quantity, "scenario": scenario}
        headers = {"traceparent": TraceParent(TRACE_HI, TRACE_LO, index + 100, 0).to_header(),
                   "X-Shop-Rpc": str(1_000_000_000_000 + index), "X-Shop-Request": f"request-{index}",
                   "X-Shop-Operation": name, "X-Shop-Attempt": str(attempt),
                   "X-Shop-Timeout-Ms": str(timeout_ms)}
        started = time.perf_counter_ns()
        status, result = request(client_port, path, body, headers)
        attempts.append({"operation_id": name, "attempt": attempt, "path": path,
                         "status": status, "result": result,
                         "latency_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
                         "json_request_body_bytes": len(json.dumps(body).encode())})
        return status, result

    def state() -> dict:
        status, result = request(inventory_port, "/state")
        require(status == 200 and result.get("inventory_backend") == "sqlite", "durable inventory state unavailable")
        return result

    try:
        old_inventory = inventory(7)
        services.append(old_inventory)
        old_inventory.start()
        services.append(caller)
        caller.start()
        require(caller.pid != old_inventory.pid, "HTTP peers must be separate application processes")
        status, result = operation("control-reserve", "control-order", 2)
        require(status == 200 and result["reserved"] == 2 and not result.get("replayed"), "healthy control failed")
        require(state()["stock"] == 9998, "healthy control stock mismatch")
        checks.append("healthy_control")

        status, result = operation("lost-reserve", "lost-order", 3, scenario="inventory_response_loss")
        require(status == 502 and result.get("code") == "upstream_transport", "committed response was not actually lost")
        committed = state()
        require(committed["stock"] == 9995 and committed["mutation_counts"]["reserve"] == 2,
                "response loss did not leave exactly one committed reservation")
        require(any(row.get("code") == "inventory_response_loss_after_commit" for row in events(old_inventory.directory)),
                "response loss application evidence absent")
        checks.append("commit_then_real_http_response_loss")
        old_inventory.stop()

        new_inventory = inventory(8)
        services.append(new_inventory)
        new_inventory.start()
        require(new_inventory.pid not in (old_inventory.pid, caller.pid), "restart did not execute a new application PID")
        require(state()["stock"] == committed["stock"], "stock did not persist across restart")
        status, result = operation("lost-reserve", "lost-order", 3, attempt=2, scenario="inventory_response_loss")
        replay_state = state()
        require(status == 200 and result["reserved"] == 3 and result.get("replayed") is True, "durable retry did not replay result")
        require(replay_state["stock"] == committed["stock"]
                and replay_state["mutation_counts"] == committed["mutation_counts"], "retry repeated a durable mutation")
        checks.append("restart_generation_7_to_8_same_database_one_mutation")

        status, _ = operation("lost-reserve", "lost-order", 4, attempt=3)
        require(status == 409 and state()["stock"] == committed["stock"], "conflicting retry payload was accepted")
        checks.append("conflicting_payload_rejected")

        status, result = operation("lost-release", "lost-order", 3, path="/release")
        require(status == 200 and result["released"] is True, "compensating release failed")
        released = state()
        require(released["stock"] == 9998 and released["mutation_counts"]["release"] == 1, "release stock mismatch")
        status, result = operation("lost-reserve", "lost-order", 3, attempt=3)
        require(status == 200 and result.get("replayed") is True and state()["stock"] == released["stock"],
                "replaying old reserve after release mutated stock")
        checks.append("release_and_old_result_replay_without_resurrection")

        before_deadline = state()
        status, _ = operation("expired-reserve", "expired-order", 1, scenario="inventory_timeout", timeout_ms=30)
        require(status == 504, "short timeout was not reported")
        finish_deadline = time.monotonic() + 3
        while time.monotonic() < finish_deadline:
            ended = [row for row in events(new_inventory.directory)
                     if row.get("kind") == "server_end" and row.get("operation_id") == "expired-reserve"]
            if ended:
                break
            time.sleep(0.025)
        require(ended and ended[-1]["status"] == 504, "receiver deadline completion evidence absent")
        after_deadline = state()
        require(after_deadline["stock"] == before_deadline["stock"]
                and after_deadline["mutation_counts"] == before_deadline["mutation_counts"]
                and after_deadline["ledger_operations"] == before_deadline["ledger_operations"]
                and "expired-order" not in after_deadline["reservations"], "receiver mutated after budget expiration")
        checks.append("receiver_budget_expires_before_mutation")

        # Fixed sequential workload measures the mutation cost avoided by
        # durable replay. It makes no timing threshold or scalability claim.
        batches = {}
        before_workload = state()
        for phase, attempt in (("fresh", 1), ("replay", 2)):
            selected = []
            started = time.perf_counter_ns()
            for index in range(8):
                status, result = operation(f"workload-{index}", f"workload-order-{index}", 1, attempt=attempt)
                require(status == 200 and bool(result.get("replayed")) == (phase == "replay"), "fixed workload task failed")
                selected.append(attempts[-1])
            batches[phase] = {"requests": 8, "completed": 8,
                              "wall_ms": round((time.perf_counter_ns() - started) / 1e6, 3),
                              "median_request_ms": round(statistics.median(row["latency_ms"] for row in selected), 3),
                              "json_request_body_bytes": sum(row["json_request_body_bytes"] for row in selected)}
            if phase == "fresh":
                after_fresh = state()
        final_state = state()
        require(after_fresh["mutation_counts"]["reserve"] - before_workload["mutation_counts"]["reserve"] == 8,
                "fresh workload did not execute eight mutations")
        require(final_state["mutation_counts"] == after_fresh["mutation_counts"]
                and final_state["stock"] == after_fresh["stock"], "replay workload repeated durable mutations")
        batches["fresh"]["durable_mutations"] = 8
        batches["replay"]["durable_mutations"] = 0
        checks.append("fixed_8_fresh_and_8_replay_task_completion")

        for service in reversed(services):
            service.stop()
        with sqlite3.connect(f"file:{ledger}?mode=ro", uri=True) as connection:
            lost_mutations = connection.execute(
                "SELECT COUNT(*) FROM shop_inventory_mutations WHERE operation_id=? AND action='reserve'",
                ("lost-reserve",),
            ).fetchone()[0]
        require(lost_mutations == 1, "persistent mutation audit does not contain exactly one lost-response reserve")
        reports = [service.report for service in services]
        clients = [row for row in events(caller.directory) if row.get("kind") == "client_begin"]
        receivers = [row for service in (old_inventory, new_inventory) for row in events(service.directory)
                     if row.get("kind") == "server_begin"]
        require(len(clients) == len(attempts) == len(receivers), "HTTP attempt evidence count mismatch")
        require(len({row["rpc_id"] for row in clients}) == len(clients), "RPC identity reused across attempts")
        require(len({row["span_id"] for row in clients}) == len(clients), "client span identity reused across attempts")
        receiver_by_rpc = {row["rpc_id"]: row for row in receivers}
        for client in clients:
            server = receiver_by_rpc[client["rpc_id"]]
            require((client["trace_id_hi"], client["trace_id"], server["trace_id_hi"], server["trace_id"])
                    == (TRACE_HI, TRACE_LO, TRACE_HI, TRACE_LO), "full 128-bit trace identity lost")
            require(server["parent_span_id"] == client["span_id"] and server["span_id"] != client["span_id"],
                    "client/server W3C span relationship lost")
            require((server["operation_id"], server["attempt"]) == (client["operation_id"], client["attempt"]),
                    "explicit operation/attempt labels lost")
        edges = rpc_edges(reports)
        require(len(edges) == len(attempts), "decoded native endpoints did not pair for every HTTP attempt")
        require(all(edge["from_pid"] != edge["to_pid"] and edge["from_process_id"] == "retry-client"
                    and edge["to_process_id"] == "inventory" for edge in edges), "native pair is not cross-process")
        require({edge["to_process_generation"] for edge in edges} == {7, 8}, "native relations lost restart generation")
        checks.append("real_native_cross_process_full128_and_fresh_attempt_identities")

        model = build_service_report(evidence)
        require(len(model["calls"]) == len(attempts), "service report lost observed native HTTP calls")
        for call in model["calls"]:
            require(isinstance(call.get("operation_id"), str) and call.get("attempt") in (1, 2, 3),
                    "service report lost explicitly labeled operation/attempt")
            require(call.get("attempt_evidence_class") == "application_self_report",
                    "service report did not preserve application attempt evidence class")
        lost_calls = [call for call in model["calls"] if call.get("operation_id") == "lost-reserve"]
        require(any(call.get("status") == 502 and call.get("receiver_status") == 200 for call in lost_calls),
                "report did not distinguish committed receiver status from caller response loss")
        (evidence / "service-report.json").write_text(json.dumps(model, indent=2) + "\n")
        checks.append("service_report_distinguishes_transport_failure_from_receiver_commit")

        # Perturb decoded copies of real captures. These are reader rejection
        # fixtures, separately labeled from the real network evidence above.
        selected_rpc = next(row["rpc_id"] for row in clients if row["operation_id"] == "control-reserve")
        changed_trace = copy.deepcopy(reports)
        for report in changed_trace:
            if report["process"]["identity"]["process_id"] == "inventory":
                for event in report["rpc"]["events"]:
                    if event["rpc_id"] == selected_rpc:
                        event["trace_id_hi"] ^= 1
        require(not any(edge["rpc_id"] == selected_rpc for edge in rpc_edges(changed_trace)),
                "mismatched high trace word created a false native edge")
        changed_generation = copy.deepcopy(reports)
        for report in changed_generation:
            if report["process"]["identity"]["process_id"] == "inventory":
                for event in report["rpc"]["events"]:
                    if event["rpc_id"] == selected_rpc:
                        event["process_generation"] += 1
        require(not any(edge["rpc_id"] == selected_rpc for edge in rpc_edges(changed_generation)),
                "conflicting native generation created a false edge")
        checks.append("decoded_fixture_high_word_and_generation_negatives")

        return {"schema": 1, "status": "PASS", "native": "REAL_BOUNDARY_AND_RUNTIME",
                "http": "real_cross_process_loopback", "application_executions": 3,
                "application_pids": [service.pid for service in services], "checks": checks,
                "task_completion": {"completed": len(checks), "total": len(checks)},
                "attempts": attempts, "native_rpc_events": sum(len(rpc_trace(report)["observed"]) for report in reports),
                "native_cross_process_relations": len(edges),
                "durable_state": {key: final_state[key] for key in ("stock", "reservations", "mutation_counts", "ledger_operations")},
                "response_loss_operation": {"mutation_count": lost_mutations, "stock_decrement": 3,
                                            "retry_replayed_after_restart": True},
                "efficiency": {"workload": "fixed_sequential_8_fresh_8_replay", **batches,
                               "interpretation": "Descriptive local timings; durable replay avoids eight mutations while still sending eight HTTP requests."},
                "evidence": str(evidence), "service_report_unresolved": len(model["unresolved"]),
                "limitations": ["Application operation/attempt labels are peer self-reports, not native retry edges.",
                                "HTTP runs on one host with distinct application processes; no container or scale claim.",
                                "High-word and generation negatives modify decoded copies of real captures.",
                                "The external harness is not captured; its inbound caller endpoints remain unpaired."]}
    finally:
        for service in reversed(services):
            service.stop(verify=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--collector-spec", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.collector_spec:
        return collector_child(args.collector_spec)
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
        temporary = tempfile.TemporaryDirectory(prefix="faultdebug-http-retry-")
        evidence = Path(temporary.name)
    try:
        try:
            result = run_acceptance(evidence, boundary, runtime)
        except Exception as exc:
            result = {"schema": 1, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}",
                      "evidence": str(evidence)}
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

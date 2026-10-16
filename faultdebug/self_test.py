"""Run a bounded capture smoke using the installed FaultDebug setup.

The command compiles and launches only a fixed C fixture in a temporary
directory. It does not inspect or execute a user's project.
"""
from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from . import __version__
from .doctor import collect_doctor_report
from .format import collect_file
from .run import run_target


def _status_row(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": status, "message": message, **details}


def _finish(report: dict[str, Any], started_ns: int) -> dict[str, Any]:
    report["elapsed_ms"] = (time.perf_counter_ns() - started_ns) / 1_000_000
    return report


def collect_self_test_report() -> dict[str, Any]:
    """Compile a generated fixture, capture it, and verify the stored artifact."""
    started_ns = time.perf_counter_ns()
    report: dict[str, Any] = {
        "schema": 1,
        "schema_name": "faultdebug.self_test",
        "version": __version__,
        "status": "NOT RUN",
        "checks": [],
        "limitations": [
            "Only a generated C fixture is compiled and executed; no user project or binary is touched.",
            "This verifies function-event capture, not project-wide instrumentation or source resolution.",
            "Runtime performance and production workload behavior are not measured.",
        ],
    }
    checks: list[dict[str, Any]] = report["checks"]
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        checks.append(_status_row("platform", "NOT RUN",
                                  "self-test currently supports Linux x86_64 only",
                                  system=platform.system(), machine=platform.machine()))
        checks.extend((_status_row("compile", "NOT RUN", "supported platform is unavailable"),
                       _status_row("capture", "NOT RUN", "supported platform is unavailable")))
        return _finish(report, started_ns)

    checks.append(_status_row("platform", "PASS", "Linux x86_64"))
    doctor = collect_doctor_report()
    doctor_checks = {row.get("name"): row for row in doctor.get("checks", [])}
    required = (
        ("tool:clang", "compiler"),
        ("wrapper:faultdebug-cc", "compiler_wrapper"),
        ("package:pyelftools", "elf_decoder"),
        ("runtime-library", "runtime_library"),
    )
    prerequisites: dict[str, dict[str, Any]] = {}
    for doctor_name, name in required:
        source = doctor_checks.get(doctor_name, {"status": "NOT RUN", "message": "doctor check is missing"})
        row = _status_row(name, str(source.get("status", "NOT RUN")),
                          str(source.get("message", "setup check did not report a result")))
        for key in ("path", "version", "error", "command", "selected_from"):
            if key in source:
                row[key] = source[key]
        checks.append(row)
        prerequisites[name] = row

    unavailable = [row for row in prerequisites.values() if row["status"] != "PASS"]
    if unavailable:
        reason = "required local setup checks did not all pass"
        checks.extend((_status_row("compile", "NOT RUN", reason),
                       _status_row("capture", "NOT RUN", reason)))
        return _finish(report, started_ns)

    wrapper = Path(prerequisites["compiler_wrapper"]["path"])
    compiler = Path(prerequisites["compiler"]["path"])
    runtime = Path(prerequisites["runtime_library"]["path"])
    env = os.environ.copy()
    env["FAULTDEBUG_REAL_CC"] = str(compiler)
    env["FAULTDEBUG_RUNTIME_DIR"] = str(runtime.parent)

    try:
        with tempfile.TemporaryDirectory(prefix="faultdebug-self-test-") as raw:
            root = Path(raw)
            source = root / "self_test.c"
            binary = root / "self_test"
            artifact_dir = root / "artifacts"
            source.write_text(
                "__attribute__((noinline)) int faultdebug_self_test_step(int value) {\n"
                "  return value + 1;\n"
                "}\n"
                "int main(void) {\n"
                "  return faultdebug_self_test_step(40) == 41 ? 0 : 1;\n"
                "}\n",
                encoding="utf-8",
            )
            try:
                compiled = subprocess.run(
                    [str(wrapper), "-O0", "-g", "-fno-inline", str(source), "-o", str(binary)],
                    cwd=root, env=env, capture_output=True, text=True,
                    timeout=30, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                checks.append(_status_row("compile", "FAIL", str(exc)[:512]))
                checks.append(_status_row("capture", "NOT RUN", "fixture compilation did not complete"))
                report["status"] = "FAIL"
                return _finish(report, started_ns)
            if compiled.returncode != 0 or not binary.is_file():
                checks.append(_status_row(
                    "compile", "FAIL", "compiler wrapper did not produce the smoke executable",
                    returncode=compiled.returncode, stderr=compiled.stderr[-1024:]))
                checks.append(_status_row("capture", "NOT RUN", "fixture compilation failed"))
                report["status"] = "FAIL"
                return _finish(report, started_ns)
            checks.append(_status_row("compile", "PASS", "generated instrumented C fixture built",
                                      compiler=str(compiler)))

            try:
                run = run_target([str(binary)], timeout=10, artifact_dir=artifact_dir,
                                 collect_success=True)
                artifact = Path(str(run.get("artifact", "")))
                captured = collect_file(artifact) if artifact.is_file() else {}
            except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
                checks.append(_status_row("capture", "FAIL", str(exc)[:512]))
                report["status"] = "FAIL"
                return _finish(report, started_ns)

            target = run.get("target") or {}
            threads = captured.get("threads", [])
            events = sum(int(row.get("event_count", 0)) for row in threads)
            dropped = sum(int(row.get("dropped_count", 0)) for row in threads)
            rpc = captured.get("rpc") or {}
            rpc_header = rpc.get("header") or {}
            rpc_dropped = int(rpc_header.get("dropped_count", 0))
            complete = captured.get("complete") is True
            stable = (captured.get("snapshot_consistency") or {}).get("stable") is True
            passed = (run.get("collector", {}).get("ok") is True and
                      target.get("returncode") == 0 and artifact.is_file() and
                      complete and stable and events > 0 and dropped == 0 and rpc_dropped == 0)
            checks.append(_status_row(
                "capture", "PASS" if passed else "FAIL",
                "valid complete trace artifact captured" if passed else
                "capture did not satisfy the complete, loss-free smoke contract",
                artifact=artifact.name if artifact.name else None,
                target_returncode=target.get("returncode"), complete=complete,
                snapshot_stable=stable, event_count=events, dropped_count=dropped,
                rpc_dropped_count=rpc_dropped, artifact_retained=False,
            ))
            report["status"] = "PASS" if passed else "FAIL"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(_status_row("capture", "FAIL", str(exc)[:512]))
        report["status"] = "FAIL"
    return _finish(report, started_ns)


def format_self_test_report(report: dict[str, Any]) -> str:
    lines = [f"FaultDebug self-test: {report['status']}"]
    lines.extend(f"  {row['name']}: {row['status']} — {row['message']}"
                 for row in report.get("checks", []))
    lines.append("  Source resolution: NOT TESTED")
    lines.append(f"  Elapsed: {report.get('elapsed_ms', 0):.1f} ms")
    return "\n".join(lines)

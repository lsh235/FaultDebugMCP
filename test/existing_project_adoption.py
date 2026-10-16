#!/usr/bin/env python3
"""Independent, offline acceptance for adoption of an existing CMake project.

The fixture deliberately has a pre-existing build, a nested executable, an
opt-in static library, excluded vendor code, and shell metacharacters in paths.
No network or external-project downloads are needed by this mandatory gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


class Acceptance:
    def __init__(self, root: Path, prefix: Path, cc: str, cxx: str, resource_dir=None):
        self.root, self.prefix, self.cc, self.cxx = root, prefix, cc, cxx
        self.rows: dict[str, dict] = {}
        self.counter = 0
        self.env = dict(os.environ)
        self.env["PYTHONPATH"] = str(ROOT)
        self.cli = [sys.executable, "-m", "faultdebug.cli"]
        self.compiler_args = [f"-DCMAKE_C_COMPILER={cc}", f"-DCMAKE_CXX_COMPILER={cxx}"]
        if resource_dir:
            self.compiler_args += [f"-DCMAKE_C_FLAGS=-resource-dir={resource_dir}",
                                   f"-DCMAKE_CXX_FLAGS=-resource-dir={resource_dir}"]

    def command(self, argv, *, expected=0, cwd=None, timeout=180):
        self.counter += 1
        result = subprocess.run([str(arg) for arg in argv], cwd=cwd or self.root,
                                env=self.env, text=True, capture_output=True,
                                timeout=timeout, check=False)
        (self.root / f"command-{self.counter:03d}.json").write_text(json.dumps({
            "argv": [str(arg) for arg in argv], "cwd": str(cwd or self.root),
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2) + "\n")
        if expected is not None:
            assert result.returncode == expected, (
                f"exit {result.returncode}, expected {expected}: {argv}\n"
                f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}")
        return result

    def cli_json(self, *args, expected=None):
        result = self.command([*self.cli, *args], expected=expected)
        return result, json.loads(result.stdout)

    def check(self, name, work, *, requires=()):
        missing = [key for key in requires if self.rows[key]["status"] != "PASS"]
        if missing:
            self.rows[name] = {"status": "NOT RUN", "reason": "failed prerequisite: " + ", ".join(missing)}
            print(f"{name}: NOT RUN", flush=True)
            return
        try:
            detail = work()
            self.rows[name] = {"status": "PASS", "evidence": detail}
        except Exception as exc:
            self.rows[name] = {"status": "FAIL", "error": str(exc),
                               "traceback": traceback.format_exc()}
        print(f"{name}: {self.rows[name]['status']}", flush=True)

    def fixture(self):
        source = self.root / "source project $(touch SHELL_INJECTION)"
        source.mkdir()
        (source / "app").mkdir()
        (source / "lib").mkdir()
        (source / "vendor").mkdir()
        (source / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.20)
project(existing_adoption_fixture LANGUAGES C)
add_library(adoption_library STATIC lib/library.c)
add_subdirectory(app)
''')
        (source / "app/CMakeLists.txt").write_text('''add_executable(adoption_app main.c ../vendor/vendor.c)
target_link_libraries(adoption_app PRIVATE adoption_library)
set_target_properties(adoption_app PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/custom output")
''')
        (source / "app/main.c").write_text('''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int adoption_library(int crash);
int vendor_value(void);
int main(int argc, char **argv) {
  const char *marker = getenv("ADOPTION_EXECUTION_MARKER");
  if (marker) { FILE *f = fopen(marker, "w"); if (f) fclose(f); }
  if (argc > 1 && strcmp(argv[1], "--fixture-arg") == 0) {
    if (argc != 3 || strcmp(argv[2], "value with spaces") != 0) return 8;
    puts("ADOPTION_ARGUMENT=value with spaces");
  }
  int crash = argc > 1 && strcmp(argv[1], "--crash") == 0;
  int value = adoption_library(crash) + vendor_value();
  printf("ADOPTION_RESULT=%d\\n", value);
  return value == 42 ? 0 : 1;
}
''')
        (source / "lib/library.c").write_text('''__attribute__((noinline)) int adoption_leaf(int crash) {
  if (crash) { volatile int *invalid = (int *)0; *invalid = 7; }
  return 40;
}
__attribute__((noinline)) int adoption_library(int crash) {
  return adoption_leaf(crash);
}
''')
        (source / "vendor/vendor.c").write_text("int vendor_value(void) { return 2; }\n")
        self.source = source
        self.original_build = self.root / "original build"
        self.command(["cmake", "-S", source, "-B", self.original_build, "-G", "Ninja",
                      *self.compiler_args, "-DCMAKE_BUILD_TYPE=Debug"])
        self.command(["cmake", "--build", self.original_build, "--target", "adoption_app"])
        self.original_binary = self.original_build / "custom output/adoption_app"
        self.baseline = self.command([self.original_binary]).stdout
        self.source_before = tree_hashes(source)
        self.build_before = tree_hashes(self.original_build)
        return {"normal_stdout": self.baseline, "source": str(source)}

    def preflight(self):
        marker = self.root / "must-not-execute"
        self.env["ADOPTION_EXECUTION_MARKER"] = str(marker)
        result, report = self.cli_json("preflight", "--binary", str(self.original_binary), "--json")
        self.env.pop("ADOPTION_EXECUTION_MARKER")
        assert not marker.exists(), "preflight executed the target"
        assert report["kind"] == "faultdebug-preflight" and report["schema"] == 1
        assert report["status"] == "needs-rebuild", report
        assert report["runtime_capture"] == "NOT RUN", report
        assert set(report["checks"]) >= {"elf", "platform", "build_id", "runtime_linkage",
                                          "hook_imports", "debug_info", "provenance"}
        for binary in (self.root / "absent-binary", self.source / "app/main.c"):
            failed, invalid = self.cli_json("preflight", "--binary", str(binary), "--json")
            assert failed.returncode != 0 and invalid["status"] in {"unsupported", "unresolved"}
        dso = self.prefix / "lib/libfaultdebug_runtime.so"
        _, shared = self.cli_json("preflight", "--binary", str(dso), "--json")
        assert shared["status"] == "unsupported", "shared library cannot be launched as an executable"
        return {"prebuilt_status": report["status"], "exit": result.returncode,
                "target_execution": "NOT RUN"}

    def plan(self):
        build = self.root / "instrumented build $(touch SHELL_INJECTION)"
        self.instrumented_build = build
        self.plan_args = ["integrate", "--source-root", str(self.source), "--build-dir", str(build),
                          "--target", "adoption_app", "--instrument-target", "adoption_library",
                          "--faultdebug-prefix", str(self.prefix), "--profile", "recommended",
                          "--json",
                          *(f"--cmake-arg={arg}" for arg in self.compiler_args),
                          "--cmake-arg=-DCMAKE_BUILD_TYPE=Debug"]
        _, self.integration = self.cli_json(*self.plan_args, expected=0)
        assert self.integration["status"] == "prepared", self.integration
        assert self.integration["kind"] == "faultdebug-integration-plan"
        assert tree_hashes(self.source) == self.source_before
        assert tree_hashes(self.original_build) == self.build_before
        assert not (build / "CMakeCache.txt").exists(), "plan configured a target"
        self.script = Path(self.integration["script"])
        assert self.script.is_file()
        return {"script": str(self.script), "commands": self.integration["commands"]}

    def execute_build(self):
        build = self.root / "execute-build integration"
        marker = self.root / "execute-build-must-not-launch"
        args = self.plan_args[:]
        args[args.index("--build-dir") + 1] = str(build)
        args.insert(args.index("--json"), "--execute-build")
        self.env["ADOPTION_EXECUTION_MARKER"] = str(marker)
        try:
            _, result = self.cli_json(*args, expected=0)
        finally:
            self.env.pop("ADOPTION_EXECUTION_MARKER", None)
        execution = result.get("execution", {})
        assert result["status"] == "prepared", result
        assert execution.get("status") == "PASS", execution
        assert [row["stage"] for row in execution["stages"]] == ["configure", "build", "index", "bundle"]
        assert execution.get("target_launch") == "NOT RUN", execution
        assert Path(execution["log"]).is_file() and Path(execution["log"]).stat().st_size > 0
        assert Path(execution["bundle"]).is_dir(), execution
        assert not marker.exists(), "--execute-build launched the adopted application"
        assert not (build / ".faultdebug-adopt/artifacts").exists(), "build created capture artifacts"
        assert tree_hashes(self.source) == self.source_before
        assert tree_hashes(self.original_build) == self.build_before
        return {"stages": execution["stages"], "bundle": execution["bundle"],
                "target_launch": execution["target_launch"], "original_inputs_unchanged": True}

    def execute_target(self):
        from faultdebug.format import collect_file

        build = self.root / "execute-target integration"
        marker = self.root / "execute-target-was-run"
        args = self.plan_args[:]
        args[args.index("--build-dir") + 1] = str(build)
        args.insert(args.index("--json"), "--execute-build")
        args.insert(args.index("--json"), "--execute-target")
        args.insert(args.index("--json"), "--fault-report")
        args.insert(args.index("--json"), "--fault-report-language=ko")
        args.insert(args.index("--json"), "--fault-report-max-events=1")
        args.extend(["--target-arg=--fixture-arg", "--target-arg=value with spaces"])
        self.env["ADOPTION_EXECUTION_MARKER"] = str(marker)
        try:
            result, report = self.cli_json(*args, expected=0)
        finally:
            self.env.pop("ADOPTION_EXECUTION_MARKER", None)
        execution = report.get("execution", {})
        target = execution.get("target_execution", {})
        fault_report = execution.get("fault_report", {})
        assert execution.get("status") == "PASS", execution
        assert execution.get("overall_status") == "PASS", execution
        assert execution.get("target_launch") == "RAN", execution
        assert target.get("status") == "PASS" and target.get("target_returncode") == 0, target
        assert fault_report.get("status") == "PASS", execution
        report_dir = Path(fault_report["output"])
        report_model = json.loads((report_dir / "report.json").read_text())
        assert report_model["bundle"]["verified"] is True
        assert report_model["artifact"]["checksum_verified"] is True
        assert report_model["language"] == "ko"
        assert all(len(thread["events"]) <= 1 for thread in report_model["threads"])
        assert sum(thread["omitted_from_view"] for thread in report_model["threads"]) == (
            sum(thread["retained_events"] for thread in report_model["threads"])
            - sum(len(thread["events"]) for thread in report_model["threads"]))
        assert report_model["crashes"] == []
        assert {path.name for path in report_dir.iterdir()} == {
            "report.json", "report.md", "report.html"}
        assert "장애 레코드 없음" in (report_dir / "report.md").read_text()
        assert "장애 실행 흐름" in (report_dir / "report.html").read_text()
        capture_summary = target.get("capture", {})
        assert capture_summary.get("complete") is True and capture_summary.get("snapshot_stable") is True, target
        assert capture_summary.get("event_count", 0) > 0, target
        assert capture_summary.get("dropped_count") == 0 and capture_summary.get("rpc_dropped_count") == 0, target
        assert Path(target["artifact"]).is_file(), target
        capture = collect_file(Path(target["artifact"]))
        assert capture.get("complete") is True
        assert marker.is_file(), "explicit target execution did not reach the application"
        assert "ADOPTION_ARGUMENT=value with spaces" in result.stderr, result.stderr[-2000:]
        assert "$(touch SHELL_INJECTION)" not in str(target)
        assert not (build / "SHELL_INJECTION").exists(), "target args were interpreted by a shell"

        # A fatal target may still leave a reportable capture, while the CLI
        # must preserve target and overall failure.
        crash_build = self.root / "execute-target crash integration"
        crash_marker = self.root / "execute-target-crash-was-run"
        crash_args = self.plan_args[:]
        crash_args[crash_args.index("--build-dir") + 1] = str(crash_build)
        crash_args.insert(crash_args.index("--json"), "--execute-build")
        crash_args.insert(crash_args.index("--json"), "--execute-target")
        crash_args.insert(crash_args.index("--json"), "--fault-report")
        crash_args.append("--target-arg=--crash")
        self.env["ADOPTION_EXECUTION_MARKER"] = str(crash_marker)
        try:
            _, crash_payload = self.cli_json(*crash_args, expected=1)
        finally:
            self.env.pop("ADOPTION_EXECUTION_MARKER", None)
        crash_execution = crash_payload.get("execution", {})
        crash_target = crash_execution.get("target_execution", {})
        crash_report = crash_execution.get("fault_report", {})
        assert crash_target.get("status") == "FAIL", crash_execution
        assert crash_report.get("status") == "PASS", crash_execution
        assert crash_execution.get("overall_status") == "FAIL", crash_execution
        crash_model = json.loads((Path(crash_report["output"]) / "report.json").read_text())
        assert crash_model["language"] == "en", crash_model
        assert len(crash_model["crashes"]) == 1, crash_model["crashes"]
        assert crash_model["crashes"][0]["signal"] == 11, crash_model["crashes"]
        assert crash_model["crashes"][0]["source_verified"] is True, crash_model["crashes"]
        assert crash_marker.is_file(), "fatal target did not reach the application"

        assert tree_hashes(self.source) == self.source_before
        assert tree_hashes(self.original_build) == self.build_before
        return {"status": target["status"], "target_returncode": target["target_returncode"],
                "capture": target["capture"], "artifact": target["artifact"],
                "fault_report": str(report_dir / "report.json"),
                "fatal_target_status": crash_target["status"],
                "fatal_report": str(Path(crash_report["output"]) / "report.json"),
                "fatal_signal": crash_model["crashes"][0]["signal"],
                "fatal_source_verified": crash_model["crashes"][0]["source_verified"],
                "target_argument_with_spaces": "PASS", "target_marker": str(marker),
                "original_inputs_unchanged": True}

    def rejection(self):
        cases = [self.original_build, self.source / "new-build", self.source.parent]
        for build in cases:
            args = self.plan_args[:]
            args[args.index("--build-dir") + 1] = str(build)
            result = self.command([*self.cli, *args], expected=None)
            assert result.returncode != 0, f"unsafe build directory accepted: {build}"
        options = ["-DCMAKE_PROJECT_INCLUDE=/tmp/another-project.cmake", "-P/tmp/evil-script.cmake", "-P"]
        for index, option in enumerate(options):
            conflict = self.plan_args[:] + [f"--cmake-arg={option}"]
            conflict[conflict.index("--build-dir") + 1] = str(self.root / f"rejected-option-{index}")
            result = self.command([*self.cli, *conflict], expected=None)
            assert result.returncode != 0, f"unsafe configure option accepted: {option}"
        cmake_source = self.source / "CMakeLists.txt"
        original = cmake_source.read_bytes()
        try:
            cmake_source.write_bytes(original + b'\nset(CMAKE_PROJECT_INCLUDE "/tmp/existing-hook.cmake")\n')
            conflict = self.plan_args[:]
            conflict[conflict.index("--build-dir") + 1] = str(self.root / "rejected-existing-hook")
            result = self.command([*self.cli, *conflict], expected=None)
            assert result.returncode != 0, "source-defined project hook silently replaced"
        finally:
            cmake_source.write_bytes(original)
        return {"unsafe_directories_rejected": len(cases), "unsafe_options_rejected": options}

    def stages(self, *names):
        for name in names:
            row = next(item for item in self.integration["commands"] if item["stage"] == name)
            self.command(row["argv"], timeout=300)

    def instrument(self):
        # Exercise the actual generated shell script, including literal $().
        self.command(["sh", self.script], timeout=300)
        assert tree_hashes(self.source) == self.source_before
        assert tree_hashes(self.original_build) == self.build_before
        assert not list(self.root.rglob("SHELL_INJECTION")), "shell expansion executed injected text"
        compdb = json.loads((self.instrumented_build / "compile_commands.json").read_text())
        selected = {Path(row["file"]).name: row.get("command", " ".join(row.get("arguments", [])))
                    for row in compdb}
        assert "-finstrument-functions" in selected["main.c"], selected
        assert "-finstrument-functions" in selected["library.c"], selected
        assert "-finstrument-functions" not in selected["vendor.c"], selected
        binary = self.instrumented_build / "custom output/adoption_app"
        self.binary = binary
        normal = self.command([binary]).stdout
        assert normal == self.baseline, (normal, self.baseline)
        _, report = self.cli_json("preflight", "--binary", str(binary), "--json", expected=0)
        assert report["status"] == "ready", report
        assert report["runtime_capture"] == "NOT RUN", report
        return {"normal_output_matches": True, "preflight": report,
                "nested_executable_and_opt_in_library": "instrumented", "vendor": "excluded"}

    def captured_sources(self):
        # Mutation occurs only in this disposable test source, after compilation.
        source = self.source / "lib/library.c"
        captured = source.read_text()
        source.write_text("// LIVE_SOURCE_MUST_NOT_BE_VERIFIED\n" + captured)
        self.stages("index")
        current_index = json.loads((self.instrumented_build / ".faultdebug-adopt/index.json").read_text())
        indexed_leaf = next(row for row in current_index["functions"] if row.get("name") == "adoption_leaf")
        assert indexed_leaf["line"] == 1, "index consulted edited live source"
        self.stages("bundle")
        self.bundle = Path(json.loads((self.instrumented_build /
            ".faultdebug-adopt/current-bundle.json").read_text())["bundle"])
        from faultdebug.bundle import load_bundle
        from faultdebug.inspect import verified_function_source
        bundle = load_bundle(self.bundle)
        rows = bundle.index_rows()
        leaf = next(row for row in rows if row.get("name") == "adoption_leaf")
        snippet = verified_function_source(leaf["id"], bundle)
        assert snippet["resolved"] and "LIVE_SOURCE_MUST_NOT_BE_VERIFIED" not in snippet["source"]
        assert (self.bundle / "source/lib/library.c").read_text() == captured
        assert leaf.get("line") == 1, leaf
        return {"bundle": str(self.bundle), "leaf_source": snippet,
                "live_edit_substituted": False}

    def metadata_tampering(self):
        # The live CMake database may change; evidence must use the pinned copy.
        database = self.instrumented_build / "compile_commands.json"
        original = database.read_bytes()
        rows = json.loads(original)
        if "command" in rows[0]:
            rows[0]["command"] += " -DADOPTION_WRONG_BINARY=1"
        else:
            rows[0]["arguments"].append("-DADOPTION_WRONG_BINARY=1")
        try:
            database.write_text(json.dumps(rows))
            command = next(row["argv"] for row in self.integration["commands"] if row["stage"] == "index")
            self.command(command)
            pinned_index = (self.instrumented_build / ".faultdebug-adopt/captured-compile-commands.json").read_text()
            assert "ADOPTION_WRONG_BINARY" not in pinned_index, "index consumed mutable live compile database"
        finally:
            database.write_bytes(original)
        captured = json.loads((self.instrumented_build / ".faultdebug-adopt/build-evidence.json").read_text())
        for database in (Path(captured["compile_commands"]["path"]), Path(captured["snapshot"]["source_manifest"])):
            original = database.read_bytes()
            try:
                database.write_bytes(original + b"\n")
                result = self.command(command, expected=None)
                assert result.returncode != 0, f"tampered captured metadata accepted: {database}"
            finally:
                database.write_bytes(original)
        binary_bytes = self.binary.read_bytes()
        marker = self.root / "replaced-binary-executed"
        self.env["ADOPTION_EXECUTION_MARKER"] = str(marker)
        try:
            self.binary.write_bytes(self.original_binary.read_bytes())
            command = next(row["argv"] for row in self.integration["commands"] if row["stage"] == "run")
            result = self.command(command, expected=None)
            assert result.returncode != 0 and not marker.exists(), "replaced binary was launched"
        finally:
            self.binary.write_bytes(binary_bytes)
            self.env.pop("ADOPTION_EXECUTION_MARKER")
        pointer = self.instrumented_build / ".faultdebug-adopt/binary-adoption_app.txt"
        original_pointer = pointer.read_bytes()
        self.env["ADOPTION_EXECUTION_MARKER"] = str(marker)
        try:
            pointer.write_text(str(self.original_binary) + "\n")
            result = self.command(command, expected=None)
            assert result.returncode != 0 and not marker.exists(), "changed target metadata redirected launch"
        finally:
            pointer.write_bytes(original_pointer)
            self.env.pop("ADOPTION_EXECUTION_MARKER")
        return {"live_compilation_database": "pinned captured input used",
                "captured_compilation_database_and_source_manifest_tamper": "rejected",
                "binary_replacement_before_launch": "rejected", "target_path_metadata_tamper": "rejected"}

    def capture(self):
        from faultdebug.format import collect_file
        artifacts = self.root / "artifacts"
        self.command([*self.cli, "run", "--collect-success", "--artifact-dir", artifacts,
                      "--", self.binary])
        success = next(artifacts.glob("*.fault"))
        self.command([*self.cli, "fault-report", success, "--bundle", self.bundle,
                      "--output", self.root / "success-report"])
        self.command([*self.cli, "run", "--artifact-dir", artifacts, "--", self.binary, "--crash"],
                     expected=139)
        fault = next(path for path in artifacts.glob("*.fault") if path != success)
        self.command([*self.cli, "fault-report", fault, "--bundle", self.bundle,
                      "--output", self.root / "fatal-report"])
        report = json.loads((self.root / "fatal-report/report.json").read_text())
        assert report["bundle"]["verified"] is True
        names = {node.get("resolution", {}).get("symbol") for thread in report["threads"]
                 for node in thread["events"]}
        assert {"main", "adoption_library", "adoption_leaf"} <= names, names
        assert any(node.get("source_verified") for node in report["crashes"]), report["crashes"]
        assert "LIVE_SOURCE_MUST_NOT_BE_VERIFIED" not in json.dumps(report["sources"])
        trace = collect_file(fault)
        return {"normal_artifact": str(success), "fatal_artifact": str(fault),
                "verified_symbols": sorted(name for name in names if name),
                "fatal_source": report["crashes"], "trace": trace.get("trace", {})}

    def stale_rebuild(self):
        from faultdebug.bundle import load_bundle
        from faultdebug.inspect import verified_function_source
        old_bundle = self.bundle
        old_build_id = load_bundle(old_bundle).manifest["binaries"][0]["build_id"]
        self.stages("build", "index", "bundle")
        current = json.loads((self.instrumented_build /
            ".faultdebug-adopt/current-bundle.json").read_text())
        new_bundle = load_bundle(current["bundle"])
        assert new_bundle.root != old_bundle
        assert new_bundle.manifest["binaries"][0]["build_id"] != old_build_id
        leaf = next(row for row in new_bundle.index_rows() if row.get("name") == "adoption_leaf")
        assert leaf["line"] == 2, leaf
        snippet = verified_function_source(leaf["id"], new_bundle)
        assert snippet["resolved"] and snippet["start_line"] == 2
        assert "LIVE_SOURCE_MUST_NOT_BE_VERIFIED" in (new_bundle.root / "source/lib/library.c").read_text()
        artifacts = self.root / "rebuilt-artifacts"
        self.command([*self.cli, "run", "--artifact-dir", artifacts, "--", self.binary, "--crash"], expected=139)
        fault = next(artifacts.glob("*.fault"))
        self.command([*self.cli, "fault-report", fault, "--bundle", old_bundle,
                      "--output", self.root / "old-bundle-report"])
        stale = json.loads((self.root / "old-bundle-report/report.json").read_text())
        assert not stale["sources"], "old bundle exposed source for new binary"
        assert all(not node["source_verified"] for node in stale["crashes"])
        return {"new_bundle": str(new_bundle.root), "old_bundle_source_for_new_binary": "unresolved",
                "new_leaf_line": leaf["line"]}

    def external_project(self, kind: str, supplied: Path):
        """Exercise real upstream sources; the libuv executable is a small driver."""
        directory = self.root / f"external-{kind}"
        directory.mkdir()
        source = directory / "source"
        upstream_hashes = tree_hashes(supplied)
        if kind == "cjson":
            shutil.copytree(supplied, source)
            target, library = "cJSON_test", "cjson"
            extras = ["-DBUILD_SHARED_LIBS=OFF", "-DENABLE_CJSON_TEST=ON"]
            wanted = "cJSON_"
            identity = {"repository": "https://github.com/DaveGamble/cJSON", "tag": "v1.7.18",
                        "declared_revision": "acc76239bee01d8e9c858ae2cab296704e52d916", "scope": "upstream cJSON_test and static cjson"}
        else:
            source.mkdir()
            shutil.copytree(supplied, source / "upstream")
            (source / "CMakeLists.txt").write_text('''cmake_minimum_required(VERSION 3.20)
project(libuv_adoption_driver LANGUAGES C)
set(LIBUV_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LIBUV_BUILD_BENCH OFF CACHE BOOL "" FORCE)
add_subdirectory(upstream)
add_executable(uv_adoption main.c)
target_link_libraries(uv_adoption PRIVATE uv_a)
''')
            (source / "main.c").write_text('''#include <uv.h>
#include <stdio.h>
#include <signal.h>
static uv_loop_t loop;
static uv_timer_t timer;
static int callback_seen;
static void on_timer(uv_timer_t *handle) {
  callback_seen = 1;
  uv_timer_stop(handle);
  uv_close((uv_handle_t *)handle, NULL);
  uv_stop(&loop);
}
int main(int argc, char **argv) {
  if (uv_loop_init(&loop) || uv_timer_init(&loop, &timer) || uv_timer_start(&timer, on_timer, 0, 0)) return 2;
  uv_run(&loop, UV_RUN_DEFAULT);
  if (!callback_seen) return 3;
  puts("LIBUV_TIMER_RESULT=1");
  fflush(stdout);
  if (argc > 1) raise(SIGABRT);
  return 0;
}
''')
            target, library, extras, wanted = "uv_adoption", "uv_a", [], "uv_"
            identity = {"repository": "https://github.com/libuv/libuv", "tag": "v1.48.0",
                        "declared_revision": "e9f29cb984231524e3931aa0ae2c5dae1a32884e", "scope": "upstream static uv_a and disposable timer driver"}
        before = tree_hashes(source)
        original = directory / "original"
        self.command(["cmake", "-S", source, "-B", original, "-G", "Ninja",
                      *self.compiler_args, *extras])
        self.command(["cmake", "--build", original, "--target", target, "--parallel", "2"], timeout=300)
        baseline = self.command([original / target]).stdout
        original_before = tree_hashes(original)
        instrumented = directory / "instrumented"
        _, plan = self.cli_json("integrate", "--source-root", str(source), "--build-dir", str(instrumented),
                                "--target", target, "--instrument-target", library,
                                "--faultdebug-prefix", str(self.prefix), "--json",
                                *(f"--cmake-arg={arg}" for arg in [*self.compiler_args, *extras]), expected=0)
        self.command(["sh", plan["script"]], timeout=300)
        state = instrumented / ".faultdebug-adopt"
        binary = Path((state / f"binary-{target}.txt").read_text().strip())
        normal = self.command([binary]).stdout
        assert normal == baseline, "instrumented external output differs from original"
        assert tree_hashes(source) == before and tree_hashes(original) == original_before
        assert tree_hashes(supplied) == upstream_hashes, "external source input changed"
        run = next(row["argv"] for row in plan["commands"] if row["stage"] == "run")
        self.command(run)
        fault = next((state / "artifacts").glob("*.fault"))
        bundle = Path(json.loads((state / "current-bundle.json").read_text())["bundle"])
        report_dir = directory / "success-report"
        self.command([*self.cli, "fault-report", fault, "--bundle", bundle, "--output", report_dir])
        report = json.loads((report_dir / "report.json").read_text())
        names = sorted({node["resolution"].get("symbol", "") for thread in report["threads"]
                        for node in thread["events"] if node["source_verified"]
                        and node["resolution"].get("symbol", "").startswith(wanted)})
        assert names, "no actual upstream library function retained and source verified"
        fatal = None
        if kind == "libuv":
            self.command([*run, *([] if run[-1:] == ["--"] else ["--"]), "--crash"], expected=134)
            fatal_fault = next(path for path in (state / "artifacts").glob("*.fault") if path != fault)
            fatal_dir = directory / "fatal-report"
            self.command([*self.cli, "fault-report", fatal_fault, "--bundle", bundle, "--output", fatal_dir])
            fatal_report = json.loads((fatal_dir / "report.json").read_text())
            assert fatal_report["crashes"][0]["signal"] == 6
            fatal = {"artifact": str(fatal_fault), "report": str(fatal_dir / "report.json")}
        source_digest = hashlib.sha256(json.dumps(upstream_hashes, sort_keys=True).encode()).hexdigest()
        return {"identity": identity, "upstream_source_tree_sha256": source_digest,
                "upstream_source_files": len(upstream_hashes), "original_output_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
                "instrumented_output_matches": True, "original_inputs_unchanged": True,
                "source_verified_library_symbols": names, "bundle": str(bundle),
                "capture": report["capture"], "report": str(report_dir / "report.json"), "fatal": fatal}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--resource-dir", type=Path,
                        default=os.environ.get("FAULTDEBUG_CLANG_RESOURCE_DIR"),
                        help="explicit matching Clang resource-header directory")
    parser.add_argument("--external-cjson-source", type=Path)
    parser.add_argument("--external-libuv-source", type=Path)
    args = parser.parse_args()
    build = args.build_dir.resolve()
    cache = (build / "CMakeCache.txt").read_text()
    def setting(name):
        return next(line.split("=", 1)[1] for line in cache.splitlines()
                    if line.startswith(name + ":"))
    root = args.work_dir.resolve() if args.work_dir else Path(tempfile.mkdtemp(prefix="faultdebug-adoption-"))
    root.mkdir(parents=True, exist_ok=True)
    prefix = root / "installed prefix"
    suite = Acceptance(root, prefix, setting("CMAKE_C_COMPILER"), setting("CMAKE_CXX_COMPILER"), args.resource_dir)
    suite.check("installed_runtime", lambda: suite.command(["cmake", "--install", build, "--prefix", prefix]).returncode)
    suite.check("existing_original_build", suite.fixture)
    suite.check("preflight_read_only", suite.preflight, requires=("existing_original_build",))
    suite.check("isolated_plan", suite.plan, requires=("existing_original_build", "installed_runtime"))
    suite.check("integrate_execute_build", suite.execute_build, requires=("isolated_plan",))
    suite.check("integrate_execute_target", suite.execute_target, requires=("installed_runtime", "existing_original_build"))
    suite.check("unsafe_reuse_rejected", suite.rejection, requires=("isolated_plan",))
    suite.check("nested_profile_and_shell_paths", suite.instrument, requires=("isolated_plan",))
    suite.check("immutable_source_index_and_bundle", suite.captured_sources, requires=("nested_profile_and_shell_paths",))
    suite.check("normal_and_fatal_verified_capture", suite.capture, requires=("immutable_source_index_and_bundle",))
    suite.check("source_mutation_rebuild_refresh", suite.stale_rebuild, requires=("normal_and_fatal_verified_capture",))
    suite.check("build_metadata_and_launch_tampering_rejected", suite.metadata_tampering,
                requires=("source_mutation_rebuild_refresh",))
    for kind, supplied in (("cjson", args.external_cjson_source), ("libuv", args.external_libuv_source)):
        if supplied:
            suite.check(f"external_{kind}", lambda kind=kind, supplied=supplied: suite.external_project(kind, supplied.resolve()),
                        requires=("installed_runtime",))
    failed = any(row["status"] != "PASS" for row in suite.rows.values())
    external = [suite.rows.get(f"external_{kind}", {}).get("status") for kind in ("cjson", "libuv")]
    external_status = "FAIL" if "FAIL" in external else "PASS" if external == ["PASS", "PASS"] else "NOT RUN"
    report = {"schema": 1, "kind": "faultdebug-existing-project-acceptance",
              "status": "FAIL" if failed else "PASS", "checks": suite.rows,
              "work_dir": str(root), "external_projects": {
                  "status": external_status,
                  "reason": "two explicit upstream source inputs required for external acceptance"}}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

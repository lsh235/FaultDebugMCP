#!/usr/bin/env python3
"""Verify explicit integration build and target execution boundaries."""
from __future__ import annotations

import json
import contextlib
import io
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faultdebug.adoption import (AdoptionError, execute_integration_build,
                                 execute_integration_target,
                                 write_integration_fault_report)
from faultdebug.bundle import create_bundle
from faultdebug.cli import main as cli_main


def _stage_command(name: str, *, exit_code: int = 0) -> list[str]:
    code = (
        "from pathlib import Path; "
        f"Path({('stage-' + name)!r}).write_text('ran'); "
        f"raise SystemExit({exit_code})"
    )
    return [sys.executable, "-c", code]


def _target_command(artifact_dir: Path, args_file: Path, *, target_exit: int = 0) -> list[str]:
    report = {"header": {"status": 0},
              "threads": [{"tid": 1, "generation": 1, "slot": 0,
                            "event_count": 1, "dropped_count": 0,
                            "events": [{"sequence": 0, "monotonic_ns": 1,
                                        "type": 1, "function": 1, "callsite": 0,
                                        "generation": 1}]}],
              "rpc": {"header": {"dropped_count": 0}, "complete": True},
              "complete": True, "snapshot_consistency": {"stable": True, "unstable_records": []},
              "collector": {"ok": True},
              "target": {"returncode": target_exit, "signal": None}}
    code = (
        "import json, os, sys; from pathlib import Path; "
        f"Path({str(args_file)!r}).write_text(json.dumps(sys.argv[1:])); "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "from faultdebug.artifact import write_artifact; "
        f"write_artifact({report!r}, Path({str(artifact_dir)!r}), os.getpid(), artifact_stem='target'); "
        f"raise SystemExit({target_exit})"
    )
    return [sys.executable, "-c", code, "--"]


def _assert_cli_rejects(*options: str, message: str) -> None:
    old_argv = sys.argv
    sys.argv = ["faultdebug", "integrate", "--source-root", "/missing/source",
                "--build-dir", "/tmp/missing/build", "--target", "app",
                "--faultdebug-prefix", "/missing/prefix", *options]
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            try:
                cli_main()
            except SystemExit as exc:
                assert exc.code == 2, exc.code
            else:
                raise AssertionError("invalid execution option combination was accepted")
    finally:
        sys.argv = old_argv
    assert message in stderr.getvalue(), stderr.getvalue()


def main() -> int:
    _assert_cli_rejects("--execute-target", message="--execute-target requires --execute-build")
    _assert_cli_rejects("--target-arg=unexpected", message="--target-arg requires --execute-target")
    _assert_cli_rejects("--fault-report", message="--fault-report requires --execute-target")
    with tempfile.TemporaryDirectory(prefix="faultdebug-integration-execute-") as raw:
        root = Path(raw)
        source = root / "source"
        source.mkdir()
        (source / "main.c").write_text("int main(void) { return 0; }\n")
        build = root / "build"
        state = build / ".faultdebug-adopt"
        state.mkdir(parents=True)
        (state / "plan.json").write_text("{}\n")
        bundle = create_bundle(source, root / "bundle")
        (state / "current-bundle.json").write_text(json.dumps({"bundle": str(bundle.root)}))
        run_marker = build / "stage-run"
        commands = [
            {"stage": name, "argv": _stage_command(name)}
            for name in ("configure", "build", "index", "bundle")
        ]
        commands.append({"stage": "run", "argv": _stage_command("run")})
        plan = {"kind": "faultdebug-integration-plan", "status": "prepared",
                "build_dir": str(build), "commands": commands}
        result = execute_integration_build(plan)
        assert result["status"] == "PASS", result
        assert [row["stage"] for row in result["stages"]] == [
            "configure", "build", "index", "bundle"]
        assert result["target_launch"] == "NOT RUN"
        assert result["bundle"] == str(bundle.root)
        assert result["bundle_file_count"] == len(bundle.files)
        assert Path(result["log"]).is_file()
        assert all((build / f"stage-{name}").is_file()
                   for name in ("configure", "build", "index", "bundle"))
        assert not run_marker.exists(), "application launch stage was executed"

        target_build = root / "target-build"
        target_state = target_build / ".faultdebug-adopt"
        target_state.mkdir(parents=True)
        (target_state / "plan.json").write_text("{}\n")
        target_artifacts = target_state / "artifacts"
        target_args_file = root / "target-args.json"
        target_marker = target_build / "TARGET_SHELL_INJECTION"
        target_plan_commands = [
            {"stage": name, "argv": _stage_command(name)}
            for name in ("configure", "build", "index", "bundle")
        ]
        target_plan_commands.append({"stage": "run", "argv": _target_command(
            target_artifacts, target_args_file)})
        target_plan = {**plan, "build_dir": str(target_build), "commands": target_plan_commands}
        target_build_result = {"status": "PASS", "bundle": str(bundle.root)}
        target_result = execute_integration_target(
            target_plan, target_build_result,
            ["--config", "value with spaces", "$(touch TARGET_SHELL_INJECTION)"])
        assert target_result["status"] == "PASS", target_result
        assert target_result["target_launch"] == "RAN"
        assert target_result["capture"] == {"complete": True, "snapshot_stable": True,
                                             "event_count": 1, "dropped_count": 0,
                                             "rpc_dropped_count": 0}
        assert json.loads(target_args_file.read_text()) == [
            "--", "--config", "value with spaces", "$(touch TARGET_SHELL_INJECTION)"]
        assert len(list(target_artifacts.glob("*.fault"))) == 1
        assert not target_marker.exists(), "application arguments were interpreted by a shell"

        target_report = write_integration_fault_report(target_result, target_build_result)
        assert target_report["status"] == "PASS", target_report
        assert target_report["crashes"] == 0, target_report
        target_report_dir = Path(target_report["output"])
        report_model = json.loads((target_report_dir / "report.json").read_text())
        assert report_model["bundle"]["verified"] is True
        assert report_model["artifact"]["checksum_verified"] is True
        assert report_model["crashes"] == []
        assert {path.name for path in target_report_dir.iterdir()} == {
            "report.json", "report.md", "report.html"}
        assert "No crash record" in (target_report_dir / "report.md").read_text()
        assert write_integration_fault_report(target_result, target_build_result)["status"] == "FAIL"
        symlink_artifacts = root / "symlink-artifacts"
        symlink_artifacts.mkdir()
        symlink_artifact = symlink_artifacts / Path(target_result["artifact"]).name
        shutil.copyfile(target_result["artifact"], symlink_artifact)
        occupied = symlink_artifacts / "target-report"
        occupied.symlink_to(root / "missing-report-target")
        symlink_report = write_integration_fault_report(
            {"target_launch": "RAN", "artifact": str(symlink_artifact)}, target_build_result)
        assert symlink_report["status"] == "FAIL" and occupied.is_symlink(), symlink_report

        failed_target_build = root / "failed-target-build"
        failed_target_state = failed_target_build / ".faultdebug-adopt"
        failed_target_state.mkdir(parents=True)
        (failed_target_state / "plan.json").write_text("{}\n")
        failed_target_artifacts = failed_target_state / "artifacts"
        failed_target_args = root / "failed-target-args.json"
        failed_target_commands = [
            {"stage": name, "argv": _stage_command(name)}
            for name in ("configure", "build", "index", "bundle")
        ]
        failed_target_commands.append({"stage": "run", "argv": _target_command(
            failed_target_artifacts, failed_target_args, target_exit=9)})
        failed_target_plan = {**plan, "build_dir": str(failed_target_build),
                              "commands": failed_target_commands}
        failed_target = execute_integration_target(
            failed_target_plan, {"status": "PASS", "bundle": str(bundle.root)})
        assert failed_target["status"] == "FAIL", failed_target
        assert failed_target["target_launch"] == "RAN"
        assert failed_target["launcher_returncode"] == 9
        assert failed_target["target_returncode"] == 9
        assert Path(failed_target["artifact"]).is_file()
        failed_report = write_integration_fault_report(
            failed_target, {"status": "PASS", "bundle": str(bundle.root)})
        assert failed_target["status"] == "FAIL", failed_target
        assert failed_report["status"] == "PASS", failed_report
        assert Path(failed_report["output"]).is_dir()

        # The CLI preserves target failure even when its requested report succeeds.
        cli_plan = {**target_plan, "script": "build script"}
        old_argv = sys.argv
        sys.argv = ["faultdebug", "integrate", "--source-root", str(source),
                    "--build-dir", str(target_build), "--target", "app",
                    "--faultdebug-prefix", str(root / "prefix"), "--execute-build",
                    "--execute-target", "--fault-report", "--json"]
        stdout = io.StringIO()
        try:
            with contextlib.redirect_stdout(stdout), \
                 patch("faultdebug.adoption.prepare_integration", return_value=cli_plan), \
                 patch("faultdebug.adoption.execute_integration_build",
                       return_value={"status": "PASS", "log": "build.log",
                                     "bundle": str(bundle.root)}), \
                 patch("faultdebug.adoption.execute_integration_target",
                       return_value=failed_target), \
                 patch("faultdebug.adoption.write_integration_fault_report",
                       return_value=failed_report) as report_writer:
                cli_status = cli_main()
        finally:
            sys.argv = old_argv
        cli_result = json.loads(stdout.getvalue())
        assert cli_status == 1, cli_result
        assert cli_result["execution"]["target_execution"]["status"] == "FAIL", cli_result
        assert cli_result["execution"]["fault_report"]["status"] == "PASS", cli_result
        assert cli_result["execution"]["overall_status"] == "FAIL", cli_result
        report_writer.assert_called_once()

        failed_build = root / "failed-build"
        failed_state = failed_build / ".faultdebug-adopt"
        failed_state.mkdir(parents=True)
        (failed_state / "plan.json").write_text("{}\n")
        failed_commands = [
            {"stage": "configure", "argv": _stage_command("configure")},
            {"stage": "build", "argv": _stage_command("build", exit_code=9)},
            {"stage": "index", "argv": _stage_command("index")},
            {"stage": "bundle", "argv": _stage_command("bundle")},
            {"stage": "run", "argv": _stage_command("run")},
        ]
        failed_plan = {**plan, "build_dir": str(failed_build), "commands": failed_commands}
        failed = execute_integration_build(failed_plan)
        assert failed["status"] == "FAIL", failed
        assert [row["stage"] for row in failed["stages"]] == ["configure", "build"]
        assert failed["stages"][-1]["returncode"] == 9
        assert not (failed_build / "stage-index").exists()
        assert not (failed_build / "stage-run").exists()
        skipped_target = execute_integration_target(failed_plan, failed, ["must-not-run"])
        assert skipped_target["status"] == "NOT RUN", skipped_target
        assert not (failed_build / ".faultdebug-adopt/artifacts").exists()

        bad_target_plan = {**target_plan, "commands": target_plan_commands[:-1]}
        try:
            execute_integration_target(bad_target_plan, target_build_result)
        except AdoptionError:
            pass
        else:
            raise AssertionError("unexpected target stage sequence was accepted")

        malformed = {**plan, "commands": commands[:-1]}
        try:
            execute_integration_build(malformed)
        except AdoptionError:
            pass
        else:
            raise AssertionError("unexpected integration stage sequence was accepted")

    print("integration explicit-build contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

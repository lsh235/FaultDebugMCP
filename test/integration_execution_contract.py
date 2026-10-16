#!/usr/bin/env python3
"""Verify explicit integration build execution skips application launch."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from faultdebug.adoption import AdoptionError, execute_integration_build
from faultdebug.bundle import create_bundle


def _stage_command(name: str, *, exit_code: int = 0) -> list[str]:
    code = (
        "from pathlib import Path; "
        f"Path({('stage-' + name)!r}).write_text('ran'); "
        f"raise SystemExit({exit_code})"
    )
    return [sys.executable, "-c", code]


def main() -> int:
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

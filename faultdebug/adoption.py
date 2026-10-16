"""Read-only ELF readiness checks and opt-in, isolated CMake adoption.

Preparing a plan never configures, builds, loads, or launches the supplied
project. Build helpers bind a content-addressed source snapshot to an ELF note.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection

SCHEMA = 1
NOTE_NAME = "faultdebug"
NOTE_TYPE = 0x46444247
HOOKS = {"__cyg_profile_func_enter", "__cyg_profile_func_exit"}
TARGET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*$")


class AdoptionError(ValueError):
    """An adoption input or its captured evidence is unsafe/incomplete."""


def _sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _notes(elf: ELFFile) -> tuple[str | None, list[dict]]:
    build_id = None
    provenance = []
    # PT_NOTE also survives stripping of the section table.
    containers = [s for s in elf.iter_sections() if hasattr(s, "iter_notes")]
    containers += [s for s in elf.iter_segments() if s["p_type"] == "PT_NOTE"]
    seen = set()
    for container in containers:
        for note in container.iter_notes():
            raw = note["n_desc"]
            if note["n_type"] == "NT_GNU_BUILD_ID":
                build_id = raw.hex() if isinstance(raw, bytes) else str(raw).lower()
            if note["n_name"] != NOTE_NAME or note["n_type"] != NOTE_TYPE:
                continue
            if not isinstance(raw, bytes):
                continue
            value = json.loads(raw.rstrip(b"\0").decode("utf-8"))
            if not isinstance(value, dict):
                raise AdoptionError("FaultDebug provenance note is not an object")
            identity = json.dumps(value, sort_keys=True)
            if identity not in seen:
                provenance.append(value)
                seen.add(identity)
    return build_id, provenance


def collect_preflight(binary: Path | str) -> dict:
    """Inspect bytes only; never use ldd, execute, dlopen, or trust a symbol alone."""
    path = Path(binary).expanduser().absolute()
    report = {
        "schema": SCHEMA, "kind": "faultdebug-preflight", "binary": str(path),
        "status": "unresolved", "checks": {}, "next_steps": [],
        "runtime_capture": "NOT RUN",
        "limitations": [
            "Static ELF readiness does not prove a runtime trace or source matching.",
            "Hook imports do not prove every function or dependency is instrumented.",
            "The binary and its dynamic dependencies were not executed or loaded.",
        ],
    }
    checks = report["checks"]
    try:
        if not path.is_file():
            raise AdoptionError("binary is missing or is not a regular file")
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                report["status"] = "unsupported"
                checks["elf"] = {"status": "FAIL", "reason": "not an ELF binary"}
                return report
            stream.seek(0)
            elf = ELFFile(stream)
            checks["elf"] = {"status": "PASS", "type": elf["e_type"]}
            machine = elf["e_machine"]
            osabi = elf["e_ident"]["EI_OSABI"]
            interpreters = [segment.get_interp_name() for segment in elf.iter_segments()
                            if segment["p_type"] == "PT_INTERP"]
            executable = bool(elf["e_entry"]) and (elf["e_type"] == "ET_EXEC" or
                          (elf["e_type"] == "ET_DYN" and bool(interpreters)))
            supported = (machine == "EM_X86_64" and elf.elfclass == 64
                         and elf.little_endian and osabi in {"ELFOSABI_SYSV", "ELFOSABI_LINUX"}
                         and executable)
            checks["platform"] = {"status": "PASS" if supported else "FAIL",
                                  "machine": machine, "bits": elf.elfclass, "osabi": osabi,
                                  "entry": elf["e_entry"], "interpreters": interpreters,
                                  "supported": "Linux x86_64 executables and PIE"}
            build_id, notes = _notes(elf)
            needed = []
            dynamic = elf.get_section_by_name(".dynamic")
            if dynamic is not None:
                needed = [tag.needed for tag in dynamic.iter_tags() if tag.entry.d_tag == "DT_NEEDED"]
            imports = set()
            for section in elf.iter_sections():
                if isinstance(section, SymbolTableSection):
                    imports.update(symbol.name for symbol in section.iter_symbols()
                                   if symbol["st_shndx"] == "SHN_UNDEF" and symbol.name in HOOKS)
            runtime = [name for name in needed if re.fullmatch(r"libfaultdebug_runtime\.so(?:\.[0-9.]+)?", name)]
            sections = {section.name for section in elf.iter_sections()}
            debug = bool({".debug_info", ".zdebug_info"} & sections)
            checks["build_id"] = {"status": "PASS" if build_id else "FAIL", "value": build_id}
            checks["runtime_linkage"] = {"status": "PASS" if runtime else "FAIL", "needed": needed,
                                          "runtime": runtime, "resolution": "NOT RUN"}
            checks["hook_imports"] = {"status": "PASS" if HOOKS <= imports else "FAIL",
                                      "imports": sorted(imports), "call_coverage": "unresolved"}
            checks["debug_info"] = {"status": "PASS" if debug else "FAIL",
                                    "external_debug_files": "NOT RUN"}
            checks["provenance"] = {"status": "PRESENT" if notes else "MISSING", "notes": notes,
                                    "source_snapshot_verification": "NOT RUN"}
            if not supported:
                report["status"] = "unsupported"
            elif not build_id or not runtime or not HOOKS <= imports or not debug:
                report["status"] = "needs-rebuild"
                report["next_steps"].append("Prepare an opt-in isolated CMake build with fault-debug integrate.")
            else:
                report["status"] = "ready"
                report["next_steps"].append("Run a bounded instrumented smoke and verify the captured artifact.")
            if not notes:
                report["next_steps"].append("Capture immutable build-time source provenance before making source claims.")
    except (OSError, ELFError, AdoptionError, ValueError, KeyError, struct.error, UnicodeError) as exc:
        report["status"] = "unresolved"
        checks["input"] = {"status": "FAIL", "reason": str(exc)}
    return report


def format_preflight(report: dict) -> str:
    lines = [f"FaultDebug preflight: {report['status']}", f"Binary: {report['binary']}"]
    lines += [f"  {name}: {value['status']}" for name, value in report["checks"].items()]
    lines.append("Runtime capture: NOT RUN")
    lines += [f"Next: {step}" for step in report["next_steps"]]
    return "\n".join(lines)


def _package_command(module: str) -> list[str]:
    # Pin this tool's package location. Never inherit the adopted project's
    # PYTHONPATH or let its cwd shadow faultdebug. Retain the venv executable
    # symlink: resolving it would discard its site-packages.
    package_root = str(Path(__file__).absolute().parent.parent)
    bootstrap = (f"import sys; sys.path.insert(0, {package_root!r}); "
                 f"from {module} import main; raise SystemExit(main())")
    return [str(Path(sys.executable).absolute()), "-I", "-c", bootstrap]


def _cmake_string(value: str) -> str:
    # Bracket arguments do not expand $, backslashes or semicolons. Commands
    # pass scalar values quoted; intentional target lists are appended one by one.
    delimiter = "="
    while f"]{delimiter}]" in value:
        delimiter += "="
    return f"[{delimiter}[{value}]{delimiter}]"


def _contains(parent: Path, child: Path) -> bool:
    return parent == child or parent in child.parents


def prepare_integration(source_root: Path | str, build_dir: Path | str, target: str,
                        faultdebug_prefix: Path | str, *, profile: str = "recommended",
                        cmake_args: list[str] | None = None,
                        instrument_targets: list[str] | None = None) -> dict:
    source = Path(source_root).expanduser().resolve()
    build = Path(build_dir).expanduser().resolve()
    prefix = Path(faultdebug_prefix).expanduser().resolve()
    targets = list(dict.fromkeys([target, *(instrument_targets or [])]))
    if any(not TARGET_NAME.fullmatch(value) for value in targets):
        raise AdoptionError("targets must be ordinary CMake target names (no aliases, paths, or shell syntax)")
    if profile not in {"recommended", "minimal", "full", "legacy"}:
        raise AdoptionError("unsupported instrumentation profile")
    if not (source / "CMakeLists.txt").is_file():
        raise AdoptionError("source-root must contain CMakeLists.txt")
    # An existing project hook may be needed to define targets/toolchain policy.
    # Refuse its source-defined setter instead of silently replacing it.
    for path in source.rglob("*"):
        if not path.is_file() or (path.name != "CMakeLists.txt" and path.suffix != ".cmake"):
            continue
        if any(part in {".git", ".venv", ".tools"} or part.startswith("build") for part in path.relative_to(source).parts):
            continue
        cmake_source = "\n".join(line for line in path.read_text(errors="replace").splitlines()
                                 if not line.lstrip().startswith("#"))
        if re.search(r"(?:set|list)\s*\(\s*(?:APPEND\s+)?CMAKE_PROJECT_(?:INCLUDE(?:_BEFORE)?|TOP_LEVEL_INCLUDES)\b", cmake_source, re.I):
            raise AdoptionError(f"existing CMake project hook must be integrated explicitly: {path}")
    if _contains(source, build) or _contains(build, source):
        raise AdoptionError("build-dir and source-root must be separate, non-overlapping directories")
    if build.exists() and (not build.is_dir() or any(build.iterdir())):
        raise AdoptionError("build-dir must be absent or empty; existing builds and plans are never overwritten")
    modules = list(prefix.glob("lib*/cmake/faultdebug/FaultDebugAdopt.cmake"))
    modules += list(prefix.glob("lib/*/cmake/faultdebug/FaultDebugAdopt.cmake"))
    modules += list(prefix.glob("share/faultdebug/cmake/FaultDebugAdopt.cmake"))
    if not modules:
        raise AdoptionError("prefix lacks FaultDebugAdopt.cmake; install the current native faultdebug package first")
    cmake = shutil.which("cmake")
    if cmake is None:
        raise AdoptionError("cmake is required to prepare executable command plans")
    extras = list(cmake_args or [])
    reserved = ("CMAKE_PROJECT_INCLUDE", "CMAKE_PROJECT_TOP_LEVEL_INCLUDES", "FAULTDEBUG_ADOPT_",
                "FAULTDEBUG_INSTRUMENT_PROFILE", "CMAKE_EXPORT_COMPILE_COMMANDS")
    for arg in extras:
        if arg in {"-D", "-S", "-B", "--build", "--install", "--workflow", "--preset", "-P", "-C", "--fresh"} or arg.startswith(("-S", "-B", "-C", "-P", "--preset=", "--workflow=")):
            raise AdoptionError("cmake-arg cannot redirect the isolated source/build operation")
        if arg.startswith("-D") and any(arg[2:].startswith(key) for key in reserved):
            raise AdoptionError("cmake-arg cannot override adoption safety settings")
        if not (arg.startswith("-D") and "=" in arg[2:] or
                arg in {"-Wno-dev", "-Wdev", "-Werror=dev", "-Wno-error=dev", "--no-warn-unused-cli"} or
                arg.startswith("--log-level=")):
            raise AdoptionError("cmake-arg supports -DKEY=VALUE and logging/warning options only; source/build/generator changes are not accepted")
    if profile == "minimal" and not any(arg.startswith("-DFAULTDEBUG_INSTRUMENT_INCLUDE_REGEX=") for arg in extras):
        raise AdoptionError("minimal profile requires an explicit FAULTDEBUG_INSTRUMENT_INCLUDE_REGEX")
    state = build / ".faultdebug-adopt"
    command = _package_command("faultdebug.adoption")
    cli = _package_command("faultdebug.cli")
    entry = state / "entry.cmake"
    state_file = state / "state.json"
    commands = [
        {"stage": "configure", "argv": [str(Path(cmake).absolute()), "-S", str(source), "-B", str(build),
          "-G", "Ninja", *extras, f"-DCMAKE_PROJECT_INCLUDE={entry}", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
          f"-DFAULTDEBUG_INSTRUMENT_PROFILE={profile}"]},
        {"stage": "build", "argv": [str(Path(cmake).absolute()), "--build", str(build), "--target", "faultdebug_adopt_finalize"]},
        {"stage": "index", "argv": [*command, "evidence", "--state", str(state_file), "--stage", "index"]},
        {"stage": "bundle", "argv": [*command, "evidence", "--state", str(state_file), "--stage", "bundle"]},
        {"stage": "run", "argv": [*command, "launch", "--state", str(state_file), "--"]},
    ]
    script = state / "build-and-bundle.sh"
    plan = {"schema": SCHEMA, "kind": "faultdebug-integration-plan", "status": "prepared",
            "source_root": str(source), "build_dir": str(build), "target": target,
            "instrument_targets": targets, "faultdebug_prefix": str(prefix), "profile": profile,
            "commands": commands, "script": str(script), "plan": str(state / "plan.json"),
            "limitations": [
                "Preparation does not configure, build, or execute the project.",
                "Linux x86_64 with Clang 18, CMake >= 3.20 and Ninja is the supported native path.",
                "Explicitly select owned static/shared libraries with --instrument-target; dependency instrumentation is not automatic.",
                "Filtered profiles use directory-scoped source options: other targets sharing the same source file in that directory may inherit those flags. Use a full profile without exclusions for target-scoped settings.",
                "External sources, generated build-tree sources and system/toolchain headers are outside the captured source root.",
                "Do not edit sources while building: before/after content checks cannot rule out transient edits restored during compilation.",
                "The script configures, builds, indexes and bundles; launch is a separate explicit command and requires application arguments.",
                "Projects defining CMAKE_PROJECT_INCLUDE hooks require explicit integration and are rejected by this helper.",
            ]}
    build.mkdir(parents=True, exist_ok=True)
    state.mkdir()
    payload = {"schema": SCHEMA, "source_root": str(source), "build_dir": str(build),
               "target": target, "targets": targets, "state_dir": str(state),
               "cli_argv": cli}
    _json(state_file, payload)
    entry.write_text(
        "# Generated opt-in bridge. The original project is unchanged.\n"
        f"set(FAULTDEBUG_ADOPT_STATE {_cmake_string(str(state_file))})\n"
        f"set(FAULTDEBUG_ADOPT_PREFIX {_cmake_string(str(prefix))})\n"
        f"set(FAULTDEBUG_ADOPT_TARGETS {_cmake_string(';'.join(targets))})\n"
        f"set(FAULTDEBUG_ADOPT_MAIN_TARGET {_cmake_string(target)})\n"
        f"set(FAULTDEBUG_ADOPT_PYTHON {_cmake_string(command[0])})\n"
        f"set(FAULTDEBUG_ADOPT_BOOTSTRAP {_cmake_string(command[3])})\n"
        f"include({_cmake_string(str(modules[0]))})\n")
    # Serialize targets as a CMake list intentionally; the string encoder
    # escapes semicolons for scalar data, so use separate target append calls.
    text = entry.read_text().replace(
        f"set(FAULTDEBUG_ADOPT_TARGETS {_cmake_string(';'.join(targets))})",
        "set(FAULTDEBUG_ADOPT_TARGETS)\n" + "\n".join(
            f"list(APPEND FAULTDEBUG_ADOPT_TARGETS {_cmake_string(value)})" for value in targets))
    entry.write_text(text)
    script.write_text("#!/bin/sh\nset -eu\n" + "\n".join(shlex.join(row["argv"]) for row in commands if row["stage"] != "run") + "\n")
    script.chmod(0o700)
    _json(state / "plan.json", plan)
    return plan


def execute_integration_build(plan: dict) -> dict:
    """Run only the generated configure/build/index/bundle argument vectors.

    The application launch stage is deliberately excluded; users must request
    that separately after reviewing the generated plan and bundle.
    """
    if plan.get("kind") != "faultdebug-integration-plan" or plan.get("status") != "prepared":
        raise AdoptionError("only a freshly prepared integration plan can be built")
    build = Path(plan.get("build_dir", "")).resolve()
    state = build / ".faultdebug-adopt"
    log_path = state / "build.log"
    commands = plan.get("commands")
    expected = ["configure", "build", "index", "bundle", "run"]
    if not isinstance(commands, list) or [row.get("stage") for row in commands] != expected:
        raise AdoptionError("integration plan has an unexpected stage sequence")
    if not state.is_dir() or not (state / "plan.json").is_file():
        raise AdoptionError("integration plan state is missing")

    results = []
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            for row in commands[:-1]:
                stage = row["stage"]
                argv = row.get("argv")
                if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
                    raise AdoptionError(f"integration {stage} command is malformed")
                print(f"faultdebug: running isolated {stage}; log: {log_path}",
                      file=sys.stderr, flush=True)
                log.write("$ " + shlex.join(argv) + "\n")
                try:
                    completed = subprocess.run(argv, cwd=build, stdout=log,
                                               stderr=subprocess.STDOUT, check=False)
                except OSError as exc:
                    results.append({"stage": stage, "status": "FAIL", "error": str(exc)[:512]})
                    return {"status": "FAIL", "stages": results, "log": str(log_path)}
                log.flush()
                result = {"stage": stage, "status": "PASS" if completed.returncode == 0 else "FAIL",
                          "returncode": completed.returncode}
                results.append(result)
                if completed.returncode != 0:
                    return {"status": "FAIL", "stages": results, "log": str(log_path)}
    except OSError as exc:
        return {"status": "FAIL", "stages": results, "log": str(log_path),
                "error": str(exc)[:512]}

    try:
        current = json.loads((state / "current-bundle.json").read_text())
        from .bundle import load_bundle
        bundle = load_bundle(current["bundle"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "FAIL", "stages": results, "log": str(log_path),
                "error": f"build completed but bundle verification failed: {exc}"[:512]}
    print(f"faultdebug: isolated build complete; verified bundle: {bundle.root}",
          file=sys.stderr, flush=True)
    return {"status": "PASS", "stages": results, "log": str(log_path),
            "bundle": str(bundle.root), "bundle_file_count": len(bundle.files),
            "target_launch": "NOT RUN"}


def _state(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise AdoptionError("unsupported adoption state")
    return value


def _inventory(root: Path) -> list[tuple[str, str]]:
    excluded = {".git", ".venv", ".tools", "__pycache__", "dist", "output", "test-results",
                ".ssh", ".aws", ".codex", ".agents"}
    rows = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in excluded and d != "build" and not d.startswith("build-")
                         and not d.endswith(".egg-info") and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or name == ".env" or name.startswith(".env."):
                continue
            if not path.is_file():
                continue
            rows.append((path.relative_to(root).as_posix(), _sha(path)))
    return sorted(rows)


def _digest(rows: list[tuple[str, str]]) -> str:
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _write_changed(path: Path, text: str) -> None:
    if path.is_file() and path.read_text() == text:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


def _note_source(digest: str) -> str:
    descriptor = json.dumps({"schema": SCHEMA, "snapshot_sha256": digest}, sort_keys=True, separators=(",", ":")) + "\0"
    encoded = descriptor.encode()
    padded = (len(encoded) + 3) // 4 * 4
    numbers = ",".join(str(byte) for byte in encoded)
    return ("/* Generated before compilation; no function instrumentation. */\n"
            f"__attribute__((used, section(\".note.faultdebug\"), aligned(4)))\n"
            f"static const struct {{ unsigned int namesz, descsz, type; char name[12]; unsigned char desc[{padded}]; }}\n"
            f"faultdebug_source_note = {{ 11, {len(encoded)}, {NOTE_TYPE}, \"faultdebug\", {{{numbers}}} }};\n")


def capture_snapshot(state_path: Path) -> dict:
    state = _state(state_path)
    root = Path(state["source_root"])
    directory = Path(state["state_dir"])
    rows = _inventory(root)
    digest = _digest(rows)
    snapshot = directory / "snapshots" / digest
    if not snapshot.exists():
        snapshot.parent.mkdir(exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".capture-", dir=snapshot.parent))
        try:
            for relative, expected in rows:
                dest = temporary / "files" / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / relative, dest)
                if _sha(dest) != expected:
                    raise AdoptionError(f"source changed while capturing: {relative}")
            if _inventory(root) != rows:
                raise AdoptionError("source changed while capturing; keep sources stable and rebuild")
            _json(temporary / "source-manifest.json", {
                "schema": SCHEMA, "root": str(root), "snapshot_sha256": digest,
                "files": [{"path": relative, "sha256": expected, "snapshot": f"files/{relative}"}
                          for relative, expected in rows]})
            temporary.rename(snapshot)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    else:
        manifest = json.loads((snapshot / "source-manifest.json").read_text())
        if manifest.get("snapshot_sha256") != digest:
            raise AdoptionError("existing captured snapshot manifest changed")
        for relative, expected in rows:
            if _sha(snapshot / "files" / relative) != expected:
                raise AdoptionError("existing captured snapshot files changed")
    current = {"schema": SCHEMA, "snapshot_sha256": digest, "snapshot": str(snapshot),
               "source_manifest": str(snapshot / "source-manifest.json"),
               "compile_commands_sha256": _sha(Path(state["build_dir"]) / "compile_commands.json")}
    _write_changed(directory / "current-snapshot.json", json.dumps(current, sort_keys=True) + "\n")
    for suffix in ("c", "cpp"):
        _write_changed(directory / f"source-note.{suffix}", _note_source(digest))
    return current


def _current(state: dict, *, check_live: bool = False) -> dict:
    current = json.loads((Path(state["state_dir"]) / "current-snapshot.json").read_text())
    if check_live and current.get("snapshot_sha256") != _digest(_inventory(Path(state["source_root"]))):
        raise AdoptionError("source changed after its pre-build snapshot; rebuild with stable sources")
    manifest = json.loads(Path(current["source_manifest"]).read_text())
    manifest_rows = [(row["path"], row["sha256"]) for row in manifest["files"]]
    if _digest(manifest_rows) != current["snapshot_sha256"]:
        raise AdoptionError("captured source manifest changed")
    for row in manifest["files"]:
        if _sha(Path(current["snapshot"]) / row["snapshot"]) != row["sha256"]:
            raise AdoptionError("captured source snapshot changed")
    return current


def _binary(state: dict, target: str | None = None) -> Path:
    name = target or state["target"]
    path = Path(state["state_dir"]) / f"binary-{name}.txt"
    binary = Path(path.read_text().strip())
    if not binary.is_absolute() or not binary.is_file():
        raise AdoptionError("configured target binary is missing")
    return binary


def finalize_build(state_path: Path) -> dict:
    from .provenance import make_manifest
    state = _state(state_path)
    current = _current(state, check_live=True)
    directory = Path(state["state_dir"])
    compdb = Path(state["build_dir"]) / "compile_commands.json"
    compdb_sha = _sha(compdb)
    if compdb_sha != current["compile_commands_sha256"]:
        raise AdoptionError("compile commands changed during the build; reconfigure and rebuild")
    inputs = directory / "build-inputs"
    inputs.mkdir(exist_ok=True)
    captured_compdb = inputs / f"{compdb_sha}.json"
    if captured_compdb.exists() and _sha(captured_compdb) != compdb_sha:
        raise AdoptionError("captured compile commands changed")
    if not captured_compdb.exists():
        shutil.copyfile(compdb, captured_compdb)
    results = []
    main_binary = _binary(state)
    with main_binary.open("rb") as stream:
        main_build_id, main_notes = _notes(ELFFile(stream))
    if not main_build_id or not any(note.get("snapshot_sha256") == current["snapshot_sha256"] for note in main_notes):
        raise AdoptionError("linked executable does not contain the current captured source note")
    for target in state["targets"]:
        binary = _binary(state, target)
        kind = (directory / f"type-{target}.txt").read_text().strip()
        if kind == "STATIC_LIBRARY":
            build_id = None
        else:
            with binary.open("rb") as stream:
                build_id, notes = _notes(ELFFile(stream))
            if not build_id or not any(note.get("snapshot_sha256") == current["snapshot_sha256"] for note in notes):
                raise AdoptionError(f"{target}: linked binary does not contain the current captured source note")
        manifest_path = directory / f"{target}.faultdebug.manifest.json"
        if kind == "STATIC_LIBRARY":
            value = {"schema": SCHEMA, "target_type": kind, "build_id": None,
                     "linked_executable_build_id": main_build_id,
                     "artifacts": [{"path": str(binary), "sha256": _sha(binary)}],
                     "source_manifest": {"path": current["source_manifest"], "sha256": _sha(Path(current["source_manifest"]))},
                     "compile_commands": {"path": str(Path(state["build_dir"]) / "compile_commands.json"),
                                          "sha256": _sha(Path(state["build_dir"]) / "compile_commands.json")}}
            _json(manifest_path, value)
        else:
            value = make_manifest(manifest_path, build_id=build_id, artifacts=[binary],
                                  source_manifest=Path(current["source_manifest"]),
                                  compile_commands=Path(state["build_dir"]) / "compile_commands.json",
                                  toolchain={"adoption": SCHEMA, "source_snapshot_sha256": current["snapshot_sha256"],
                                             "target_type": kind, "linked_executable_build_id": main_build_id})
        results.append({"target": target, "binary": str(binary), "manifest": str(manifest_path),
                        "build_id": value["build_id"], "target_type": kind})
    _json(directory / "build-evidence.json", {"schema": SCHEMA, "snapshot": current, "targets": results,
                                            "compile_commands": {"path": str(captured_compdb), "sha256": compdb_sha}})
    return {"schema": SCHEMA, "status": "captured", "targets": results}


def _captured_arguments(row: dict, root: Path, captured_root: Path) -> tuple[list[str], str]:
    """Map source/include operands, preserving definitions and other flags.

    CMake's Ninja database may retain its dollar escaping in a shell command.
    Decode that spelling only for path operands, after proving it against the
    authoritative ``file`` field. No shell evaluates the command or its paths.
    """
    directory = Path(row.get("directory", ".")).resolve()
    original_file = Path(row["file"])
    if not original_file.is_absolute():
        original_file = directory / original_file
    original_file = original_file.resolve()
    arguments = list(row.get("arguments") or shlex.split(row.get("command", "")))
    if not arguments:
        raise AdoptionError("compile command has no compiler arguments")
    if any(arg.startswith("@") for arg in arguments):
        raise AdoptionError("response-file compile commands require explicit integration")
    separate = {"-I", "-isystem", "-iquote", "-idirafter", "-include", "-imacros",
                "-isysroot", "--sysroot", "-resource-dir"}
    consume = separate | {"-o", "-MF", "-MT", "-MQ", "-x", "-target", "--target",
                          "-Xclang", "-Xpreprocessor", "-D", "-U"}
    inputs = []
    ninja_dollars = False
    skip = False
    for position, arg in enumerate(arguments[1:], 1):
        if skip:
            skip = False
            continue
        if arg in consume:
            skip = True
            continue
        if arg.startswith("-"):
            continue
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = directory / candidate
        if candidate.resolve() == original_file:
            inputs.append(position)
            continue
        if "command" in row and "arguments" not in row and "\\$$" in arg:
            decoded = Path(arg.replace("\\$$", "$"))
            if not decoded.is_absolute():
                decoded = directory / decoded
            if decoded.resolve() == original_file:
                inputs.append(position)
                ninja_dollars = True
    if len(inputs) != 1:
        raise AdoptionError("cannot identify a single source operand matching the compilation database file")

    def map_path(value: str) -> str:
        if ninja_dollars:
            value = value.replace("\\$$", "$")
        path = Path(value)
        if not path.is_absolute():
            path = directory / path
        path = path.resolve()
        if _contains(root, path):
            captured = captured_root / path.relative_to(root)
            if not captured.exists():
                raise AdoptionError(f"compile input was excluded from captured source: {path}")
            return str(captured)
        return str(path)

    mapped = [arguments[0]]
    position = 1
    joined = sorted(separate - {"--sysroot", "-resource-dir", "-isysroot"}, key=len, reverse=True)
    while position < len(arguments):
        arg = arguments[position]
        if position == inputs[0]:
            mapped.append(str(captured_root / original_file.relative_to(root)))
        elif arg in separate:
            if position + 1 >= len(arguments):
                raise AdoptionError("compile command has an incomplete path option")
            mapped.extend([arg, map_path(arguments[position + 1])])
            position += 1
        elif arg.startswith("--sysroot=") or arg.startswith("-resource-dir="):
            option, value = arg.split("=", 1)
            mapped.append(option + "=" + map_path(value))
        else:
            option = next((prefix for prefix in joined if arg.startswith(prefix) and arg != prefix), None)
            mapped.append(option + map_path(arg[len(option):]) if option else arg)
        position += 1
    return mapped, map_path(str(directory))


def prepare_evidence(state_path: Path, stage: str) -> dict:
    from .bundle import create_bundle, load_bundle
    from .index import build_index
    state = _state(state_path)
    current = _current(state)
    directory = Path(state["state_dir"])
    captured = json.loads((directory / "build-evidence.json").read_text())
    if captured["snapshot"]["snapshot_sha256"] != current["snapshot_sha256"]:
        raise AdoptionError("build evidence refers to an older snapshot; rebuild")
    for target in captured["targets"]:
        manifest = json.loads(Path(target["manifest"]).read_text())
        if _sha(Path(target["binary"])) != manifest["artifacts"][0]["sha256"]:
            raise AdoptionError("built binary changed after provenance capture")
        if _sha(Path(current["source_manifest"])) != manifest["source_manifest"]["sha256"]:
            raise AdoptionError("captured source manifest changed after provenance capture")
    compdb_capture = captured["compile_commands"]
    if _sha(Path(compdb_capture["path"])) != compdb_capture["sha256"]:
        raise AdoptionError("captured compile commands changed after the build")
    index = directory / "index.json"
    if stage == "index":
        original = Path(state["source_root"])
        replacement = Path(current["snapshot"]) / "files"
        compdb = json.loads(Path(compdb_capture["path"]).read_text())
        rewritten = []
        resources = {}
        for row in compdb:
            path = Path(row["file"])
            if not path.is_absolute():
                path = Path(row["directory"]) / path
            if not _contains(original, path.resolve()):
                continue
            relative = path.resolve().relative_to(original)
            if not (replacement / relative).is_file():
                raise AdoptionError(f"compile source was excluded from snapshot: {relative}")
            item = dict(row)
            item["file"] = str(replacement / relative)
            item["arguments"], item["directory"] = _captured_arguments(row, original, replacement)
            item.pop("command", None)
            argv = item.get("arguments", [])
            # Wheel-provided libclang has no compiler resource headers. Use the
            # very compiler which produced this TU, rather than an unrelated
            # host clang or an include path guessed from this checkout.
            if argv and not any(arg.startswith("-resource-dir") for arg in argv):
                compiler = argv[0]
                if compiler not in resources:
                    try:
                        resource = subprocess.check_output([compiler, "-print-resource-dir"], text=True,
                                                           stderr=subprocess.PIPE).strip()
                    except (OSError, subprocess.CalledProcessError) as exc:
                        raise AdoptionError("could not query the selected Clang compiler resource directory") from exc
                    if not (Path(resource) / "include" / "stddef.h").is_file():
                        raise AdoptionError("Clang resource headers are unavailable for captured-source indexing")
                    resources[compiler] = resource
                item["arguments"].append(f"-resource-dir={resources[compiler]}")
            rewritten.append(item)
        compdb_path = directory / "captured-compile-commands.json"
        _json(compdb_path, rewritten)
        from .index import IndexErrorRuntime
        from clang.cindex import TranslationUnitLoadError
        try:
            value = build_index(compdb_path, index)
        except (IndexErrorRuntime, TranslationUnitLoadError) as exc:
            raise AdoptionError(f"captured-source parsing failed: {exc}") from exc
        severe = [row for row in value.get("coverage_failures", []) if row.get("severity", 0) >= 3]
        if severe:
            raise AdoptionError(f"captured-source index has {len(severe)} compiler errors; resolve compiler/header options")
        return {"schema": SCHEMA, "status": "indexed", "index": str(index), "functions": len(value["functions"])}
    if not index.is_file():
        raise AdoptionError("run the index stage before creating a bundle")
    binary_rows = [row for row in captured["targets"] if row["target_type"] != "STATIC_LIBRARY"]
    binary_hashes = [(row["target"], _sha(Path(row["binary"]))) for row in binary_rows]
    identity = {"source_snapshot_sha256": current["snapshot_sha256"], "index_sha256": _sha(index),
                "binary_sha256": binary_hashes, "compile_commands_sha256": compdb_capture["sha256"]}
    bundle_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = directory / "bundles" / bundle_id
    if output.exists():
        bundle = load_bundle(output)
        if bundle.manifest.get("index_sha256") != identity["index_sha256"]:
            raise AdoptionError("existing immutable bundle index changed")
        expected = sorted(_sha(Path(row["binary"])) for row in binary_rows)
        if sorted(row["sha256"] for row in bundle.manifest.get("binaries", [])) != expected:
            raise AdoptionError("existing immutable bundle binary list changed")
        _json(directory / "current-bundle.json", {"schema": SCHEMA, "bundle": str(bundle.root)})
        return {"schema": SCHEMA, "status": "bundled", "bundle": str(bundle.root), "files": len(bundle.files), "reused": True}
    output.parent.mkdir(exist_ok=True)
    bundle = create_bundle(Path(current["snapshot"]) / "files", output, index=index,
                           binaries=[Path(row["binary"]) for row in binary_rows])
    _json(directory / "current-bundle.json", {"schema": SCHEMA, "bundle": str(bundle.root)})
    return {"schema": SCHEMA, "status": "bundled", "bundle": str(bundle.root), "files": len(bundle.files)}


def launch_target(state_path: Path, args: list[str]) -> int:
    state = _state(state_path)
    current = _current(state)
    directory = Path(state["state_dir"])
    captured = json.loads((directory / "build-evidence.json").read_text())
    if current["snapshot_sha256"] != captured["snapshot"]["snapshot_sha256"]:
        raise AdoptionError("build evidence refers to an older snapshot; rebuild")
    for target in captured["targets"]:
        manifest = json.loads(Path(target["manifest"]).read_text())
        if _sha(Path(target["binary"])) != manifest["artifacts"][0]["sha256"]:
            raise AdoptionError("built target changed after provenance capture; refusing launch")
    main_target = next((row for row in captured["targets"] if row["target"] == state["target"]), None)
    if main_target is None or _binary(state).resolve() != Path(main_target["binary"]).resolve():
        raise AdoptionError("configured binary path changed after provenance capture; refusing launch")
    command = [*state["cli_argv"], "run", "--collect-success", "--artifact-dir",
               str(Path(state["state_dir"]) / "artifacts"), "--", main_target["binary"], *args]
    return subprocess.call(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("snapshot", "finalize"):
        child = actions.add_parser(action)
        child.add_argument("--state", type=Path, required=True)
    evidence = actions.add_parser("evidence")
    evidence.add_argument("--state", type=Path, required=True)
    evidence.add_argument("--stage", choices=("index", "bundle"), required=True)
    launch = actions.add_parser("launch")
    launch.add_argument("--state", type=Path, required=True)
    launch.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    try:
        if ns.action == "launch":
            return launch_target(ns.state, ns.args[1:] if ns.args[:1] == ["--"] else ns.args)
        if ns.action == "snapshot":
            result = capture_snapshot(ns.state)
        elif ns.action == "finalize":
            result = finalize_build(ns.state)
        else:
            result = prepare_evidence(ns.state, ns.stage)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (AdoptionError, OSError, ValueError, ELFError) as exc:
        print(f"faultdebug adoption: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

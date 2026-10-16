# Adopt an existing C/C++ project

FaultDebug now checks an existing Linux executable and prepares an isolated
CMake integration without editing the project's `CMakeLists.txt` or reusing
its current build. An ordinary prebuilt executable needs an instrumented
rebuild before it can produce function events.

The supported path is Linux x86_64, Python 3.12, Clang 18, CMake 3.20 or newer,
and Ninja. These commands assume the current Python package is installed in
your active environment and the current native package is installed at an
absolute prefix. See [Quick start](../README.md#quick-start) for prerequisites
and [the upstream comparison](existing-project-research-2026-10-13.md) for the
design evidence.

## 1. Check the executable without running it

```sh
python -m faultdebug.cli preflight --binary /absolute/project/build/server --json
```

The result separates ELF/platform checks, GNU Build ID, runtime linkage,
function-hook imports, debug information, and provenance notes. It never runs
the binary, calls `ldd`, or loads dynamic dependencies. A `ready` result is
static readiness only: `runtime_capture` remains `NOT RUN`, dependency
resolution is `NOT RUN`, and imported hooks do not establish full call
coverage. Missing debug information or hooks yields `needs-rebuild`; a shared
library, unsupported platform, or non-ELF file is `unsupported`; unreadable or
malformed inputs are `unresolved`. CLI exit is 0 for `ready` and 2 for all other states.

## 2. Install the current native integration

From the FaultDebug checkout, build and install into a user-owned prefix:

```sh
cmake -S . -B build-runtime -G Ninja \
  -DCMAKE_C_COMPILER=clang-18 -DCMAKE_CXX_COMPILER=clang++-18 \
  -DFAULTDEBUG_PYTHON_EXECUTABLE="$(command -v python)" \
  -DFAULTDEBUG_BUILD_TESTS=OFF -DFAULTDEBUG_ENABLE_PROVENANCE=OFF
cmake --build build-runtime --parallel 2
cmake --install build-runtime --prefix "$HOME/.local/faultdebug"
```

Use this current prefix rather than an older installed helper; adoption needs
`FaultDebugAdopt.cmake`, its selective integration helpers, and the exported
runtime package. The generated plan pins the Python interpreter/package and
native prefix it uses.

## 3. Prepare a separate instrumented build

```sh
python -m faultdebug.cli integrate \
  --source-root /absolute/project \
  --build-dir /absolute/project-faultdebug-build \
  --target server \
  --faultdebug-prefix "$HOME/.local/faultdebug" \
  --profile recommended \
  --cmake-arg=-DCMAKE_C_COMPILER=clang-18 \
  --cmake-arg=-DCMAKE_CXX_COMPILER=clang++-18 \
  --json
```

Preparation writes a JSON plan and shell script inside the new build directory.
It does not configure, compile, or launch the application. Source and build
directories must be separate and non-overlapping; the build directory must be
absent or empty. Existing outputs and plans are rejected. Pass CMake cache
settings as `--cmake-arg=-DKEY=VALUE` so a leading `-D` is parsed correctly.
Source/build overrides, script-mode options, and conflicting project-injection
hooks are rejected.

To have the CLI run the same isolated configure/build/index/bundle stages and
verify the resulting bundle in one call, add `--execute-build` to the command.
It stores combined command output in `.faultdebug-adopt/build.log` and returns
the bundle path. This opt-in never runs the application; launch remains a
separate reviewed step. Without the flag, behavior remains plan-only.

The main target must be a project-owned executable. Targets in nested
`add_subdirectory()` directories and custom executable output directories are
supported. Aliases, imported targets, generator-expression source selections,
and custom project-injection hooks require explicit integration instead.

`recommended` instruments the selected executable's sources and excludes
`vendor/` and `generated/`. It does not automatically instrument linked
libraries. Add each library you own and want to observe:

```sh
# Add this option to the integrate command for an application-owned library:
--instrument-target project_core
```

The profile uses CMake source properties. When multiple targets in the same
CMake directory share a translation unit, that source can inherit the selected
options in the isolated build. `full` without exclusions applies target-scoped
options; otherwise use explicit manual integration for this layout. Strict
isolation among targets sharing sources is outside the filtered-profile path.

Generated code outside the captured source root and compiler response files
are rejected by the evidence stage. Supply supported compilation inputs or
use the existing manual integration helpers. Keep sources stable during the
build. Inspect snapshots before sharing them; bundles contain captured source
and build settings.

## 4. Build, bundle, and explicitly run

Without `--execute-build`, run the `script` path returned by the plan:

```sh
sh /absolute/project-faultdebug-build/.faultdebug-adopt/build-and-bundle.sh
```

The script configures, builds, indexes, and bundles. Launch is a separate
explicit plan stage. The plan's `commands` are arrays of arguments, so execute
them as argument arrays; do not reconstruct them with `eval`. For example,
with a saved `plan.json`:

```sh
python - /absolute/project-faultdebug-build/.faultdebug-adopt/plan.json --config example.conf <<'PY'
import json, subprocess, sys
plan = json.load(open(sys.argv[1]))
command = next(row['argv'] for row in plan['commands'] if row['stage'] == 'run')
separator = [] if command[-1:] == ['--'] else ['--']
raise SystemExit(subprocess.call(command + separator + sys.argv[2:]))
PY
```

The generated run stage collects a normal exit with `--collect-success`.
Supported fatal signals also produce artifacts; the launcher preserves the
target's signal-derived exit status. Snapshots are taken before compilation,
the linked ELF note identifies the snapshot, and finalization pins the binary,
Build ID, source manifest, and compile database. The evidence index reads
captured source and compilation inputs, even if the live checkout is edited
afterward. Rebuilding refreshes the snapshot and binary identity; an older
bundle cannot verify source for a different captured binary. Changed captured
metadata or a replaced binary is rejected before evidence use or launch.

Artifacts are under `.faultdebug-adopt/artifacts/`; the verified bundle path is
in `.faultdebug-adopt/current-bundle.json`. Create the report with those paths:

```sh
python -m faultdebug.cli fault-report /absolute/path/fault-123.fault \
  --bundle /absolute/path/bundle --output /absolute/path/incident-report
```

Open `incident-report/report.html` and inspect capture completeness, dropped
events, source resolution, and collector status before relying on it. Bounded
rings can retain only part of a long application run.

## Validation

The offline mandatory gate is `test/existing_project_adoption.py`, also
registered as CTest `fd_python_existing_project_adoption`. It exits nonzero
when a mandatory check fails or cannot run. It exercises a pre-existing build,
nested target, custom output path, opt-in static library, excluded vendor
source, literal shell metacharacters, verified fatal source, post-build live
edits, rebuild identity changes, and metadata/launch tampering.

```sh
python test/existing_project_adoption.py --build-dir build \
  --output build/existing-project-adoption.json
```

The validation table below records the adoption implementation's prior local
run on 2026-10-13. It is historical evidence for that recorded workspace, not
the current alpha7 revision's release gate. Fresh alpha7 results are recorded
in [the alpha7 scope and verification](releases/v1.3.0-alpha.7.md).

External project checks require explicit local upstream sources, so the CTest
gate never downloads code:

```sh
python test/existing_project_adoption.py --build-dir build \
  --external-cjson-source /absolute/cJSON-1.7.18 \
  --external-libuv-source /absolute/libuv-1.48.0 \
  --output build/existing-project-external-adoption.json
```

The pinned evaluated revisions are cJSON
`acc76239bee01d8e9c858ae2cab296704e52d916` and libuv
`e9f29cb984231524e3931aa0ae2c5dae1a32884e`. The cJSON scope is its upstream
`cJSON_test` executable and static `cjson`; libuv uses its upstream `uv_a`
library with a disposable timer driver. The test records source-tree hashes,
compares normal output/exit status, leaves the original inputs unchanged, and
requires actual retained, source-verified `cJSON_*` / `uv_*` events.
The reusable harness records the supplied local source hash; it does not
authenticate an arbitrary source directory as that declared upstream revision.

Local validation on 2026-10-13 used Python 3.12 and Clang 18.1.3. The locally
extracted compiler lacks headers at its default resource path; the tests passed
an explicit matching `-resource-dir=/usr/lib/llvm-18/lib/clang/18`. A native
build alone did not establish that index setup. The initial restricted-socket
CTest run had three `EPERM` failures; the same complete suite was rerun with
local sockets available. The MCP stdio audit also timed out during sandbox
initialization and passed when rerun with unrestricted local transport.

| Gate | Result | Evidence |
| --- | --- | --- |
| Fresh native build and runtime smoke | PASS | `build-adoption-validation/evidence/build-final.log`; native/runtime CTests |
| Existing-project independent acceptance | PASS, 12/12 | `build-adoption-validation/evidence/adoption-complete.json` |
| Full current-source CTest | PASS, 25/25 | `build-adoption-validation/evidence/ctest-final.log` |
| cJSON upstream executable + static library | PASS | 3 retained, source-verified `cJSON_*` symbols; 3,978 events, 0 dropped, stable snapshot |
| libuv upstream static library + timer driver | PASS | Retained source-verified `uv_run`, `uv__run_timers`, `uv_stop`; 230 normal-run events and 207 fatal-run events, 0 dropped; SIGABRT capture exit 134 |
| Wheel installed outside the checkout | PASS | `build-adoption-validation/evidence/wheel-consumer.json`; installed console aliases, new build/index/bundle and fatal source from `/tmp` |
| Read-only MCP regression | PASS | `build-adoption-validation/evidence/mcp-definition-audit.json`; 25 tools, 76 documented parameters, 12 invalid calls rejected, evidence unchanged |
| Long-duration soak, production service rollout, other platforms/build systems | NOT RUN | Outside this bounded adoption change |
| Knowledge-graph coverage | NOT RUN | Graph tools unavailable; exact source/log fallback used |

The evidence paths refer to this local validation workspace and are not bundled
in the source distribution. Wheel validation shares Python dependencies from
the existing Python 3.12 environment; its package code, console commands,
generated commands, new build, and report use an installed prefix outside the
checkout. This is adoption acceptance, not a new stable-release certification.

Both external inputs came from fresh official archives pinned by commit:

| Project | Official source archive | SHA256 of downloaded archive |
| --- | --- | --- |
| cJSON 1.7.18 | [acc76239](https://codeload.github.com/DaveGamble/cJSON/tar.gz/acc76239bee01d8e9c858ae2cab296704e52d916) | `88be7eb146a320e255212cf1ec77e393846979ce1d2579917c5ae87c2d4ce3dd` |
| libuv 1.48.0 | [e9f29cb9](https://codeload.github.com/libuv/libuv/tar.gz/e9f29cb984231524e3931aa0ae2c5dae1a32884e) | `26d7f55a4d731cfe40e36b03d58000439f523a75dec0290a6e8b46f625925ab1` |

The original extracted source and ordinary build were hashed before/after the
integration and remained unchanged. cJSON's older CMake policies and libuv's
plain `target_link_libraries()` calls required compatibility fixes in the
FaultDebug bridge; upstream source files were preserved.

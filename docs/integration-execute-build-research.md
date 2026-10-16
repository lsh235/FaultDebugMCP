# Isolated integration execution: research and decision

Date: 2026-10-17 (Asia/Seoul). Target: v1.3.0-alpha.9.

## Gap

`faultdebug integrate` already validates an isolated build directory and emits
argument-vector commands plus a shell script for configure, build, indexing and
bundle creation. Users then need to run the generated script themselves and
locate the resulting bundle. That extra handoff makes the first adoption
workflow slower and encourages reconstructing a multi-stage command by hand.

The execution boundary matters: CMake configure/build processes the selected
project's CMake files and build rules. Existing behavior is plan-only, and
launching the application is a separately requested action.

## Options considered

1. Always execute after preparing a plan. Rejected because it would change the
   current non-executing default and run project build logic without an explicit
   opt-in.
2. Add an `adopt` alias or another wrapper command. Rejected because it would
   duplicate the existing target, prefix, profile and safety inputs.
3. Add `faultdebug integrate --execute-build`. Accepted: after the existing
   safety checks create a fresh isolated plan, the CLI runs only its
   `configure`, `build`, `index` and `bundle` argument vectors, saves combined
   output under `.faultdebug-adopt/build.log`, and verifies the resulting
   bundle. The planned `run` stage remains excluded; users still choose when
   and how to launch the application.

Commands are executed as argument arrays rather than reconstructed shell text.
The generated script remains available for users who want manual execution.
The CMake `find_package(CONFIG)` and prefix lookup behavior used by the
adoption bridge follows the official [CMake `find_package` documentation](https://cmake.org/cmake/help/latest/command/find_package.html)
and [`CMAKE_PREFIX_PATH` documentation](https://cmake.org/cmake/help/latest/variable/CMAKE_PREFIX_PATH.html).

## Decision and limits

Decision: **YES**, implement this as an explicit convenience path. Acceptance
requires that the default still only prepares a plan; execution runs exactly
the four build/evidence stages, stops at the first nonzero command, records the
stage and log path, verifies the emitted bundle, and never launches the target.
The isolated source/build checks and integration restrictions remain in force.

This flag is not a sandbox. CMake and compiler build rules execute with the
current user's permissions and can run project-defined build logic. The user
must explicitly opt in after selecting the source tree, target, profile and
separate empty build directory. Arbitrary build systems, project-owned CMake
hooks, generated/out-of-root source, full dependency instrumentation and stable
acceptance remain outside this feature.

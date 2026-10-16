# Meson adoption research

Date: 2026-10-17 (Asia/Seoul). Candidate reviewed for the alpha13 cycle.
Baseline: `v1.3.0-alpha.12` at `4fd13eff8d19cf72c1e9fb9d5a38dff773faead9`.

## Candidate

Extend `faultdebug integrate` from isolated CMake builds to Meson projects.
The repository already demonstrates the compiler wrappers with a Meson fixture,
but that fixture proves selective compile instrumentation only; it is not an
adoption, provenance, or capture workflow.

## Existing contract and evidence

`faultdebug.adoption.prepare_integration` currently accepts only projects with
`CMakeLists.txt` and creates a fresh Ninja build. Its generated
`FaultDebugAdopt.cmake` hook runs after project targets are declared, then
validates the explicitly selected executable and owned libraries, links the
runtime, adds the source-snapshot ELF note, and records exact target paths and
types. The later finalizer verifies the pre-build source snapshot, unchanged
compile database, binary Build-ID and matching source note before it permits
indexing, bundling, or launch.

Meson provides native machine files for choosing a non-default compiler and
introspection files for configured targets. Its documentation describes
`intro-targets.json` as IDE integration data and notes limitations for
pre-configuration target introspection, including conditional targets and
source-list accuracy. More importantly, those facilities do not provide the
target-mutation hook used by the current adoption bridge. A wrapper-only build
could add compiler flags, but would not yet establish target-specific runtime
linkage and the matching pre-build provenance note.

Primary references: [Meson native environments](https://mesonbuild.com/Native-environments.html),
[Meson IDE integration and target introspection](https://mesonbuild.com/IDE-integration.html).

## Options

1. Treat the existing Meson wrapper fixture as adoption support. Rejected:
   it has no source snapshot, selected-target identity, provenance note,
   verified bundle, or capture acceptance.
2. Add `--build-system meson` by reading target introspection and using the
   compiler wrappers. Proposed for review only if it can match CMake's
   evidence contract; current inspection found no equivalent target hook.
3. Defer Meson adoption until a separate build adapter can inject the source
   note and runtime into an explicitly selected target and prove exact output
   identity without modifying the project. Preferred.

## Review question

Should alpha13 implement Meson adoption now, or defer it until the target and
provenance lifecycle can meet the existing CMake contract?

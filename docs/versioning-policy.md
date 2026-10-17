# FaultDebug versioning policy

This policy classifies a change by its effect on the declared public contract,
not by its implementation size, perceived importance, or number of files. It
follows [Semantic Versioning 2.0.0](https://semver.org/) and the Python
pre-release spelling defined by [PEP 440 / PyPA version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/#pre-releases).

## Public contract

Review compatibility across every surface users can depend on:

- Python API and distribution metadata;
- CLI commands, arguments, defaults, exit codes, and output;
- MCP profiles, tool names, input schemas, output schemas, and semantics;
- CMake package/API and native ABI, including SONAME;
- FDAR/artifact formats, evidence-store schemas, and persisted data;
- supported runtimes, platforms, and documented install workflows.

An implementation detail becomes part of the compatibility decision when it is
documented, emitted in a schema, persisted, or consumed by a supported tool.
Unknown compatibility is not presumed safe: gather evidence, add an
opt-in/deprecation path, classify conservatively as major, or defer the change.

## Stable version increments

| Increment | Use when | FaultDebug examples |
| --- | --- | --- |
| **MAJOR** (`X.0.0`) | A released public contract becomes incompatible. | Removing/renaming a CLI command or MCP tool; changing a default profile; making an optional argument required; narrowing accepted inputs; changing a field's type, requiredness, or meaning; changing ABI, artifact/store format, or protocol without a compatible reader/migration; dropping a documented supported runtime. |
| **MINOR** (`X.Y.0`) | New public functionality is backward compatible and existing calls retain their documented behavior. | Adding a command/tool; adding an optional input whose omission preserves old behavior; adding an opt-in profile/capability; adding output fields only when supported clients are known to tolerate them or output is explicitly versioned. |
| **PATCH** (`X.Y.Z`) | A backward-compatible correction or maintenance change leaves the intended public contract intact. | Correcting an implementation defect to match documented behavior; safe internal performance/build fixes; documentation-only corrections. |

When a release contains multiple classes, use the highest applicable
increment. Do not call a change a patch just because it is small. A behavior
change that invalidates a documented or relied-on contract is not a patch; if it
is not safely additive, use a major increment or ship an explicit
migration/deprecation path first.

After stable `2.0.0`, the ordinary mapping is `3.0.0` for a major change,
`2.1.0` for a minor change, and `2.0.1` for a patch. Reset lower components
when a higher component increments.

## Pre-releases

Python and native/CMake package metadata can use different spellings for the
same candidate where the build system requires it. Python `2.0.0a3`
corresponds to the annotated Git tag `v2.0.0-alpha.3`; the CMake project stays
`2.0.0` unless its packaging contract explicitly gains a pre-release
representation. Validate generated metadata and archives.

`alpha.N`, `beta.N`, and `rc.N` advance iterations of the named target release;
they are not stable major/minor/patch increments. An additive candidate
developed before the first stable v2 release can be `2.0.0-alpha.3` because it
belongs to the still-unreleased v2.0.0 target. After v2.0.0 ships, an equivalent
backward-compatible feature is normally `2.1.0`, not another `2.0.0` alpha.
Pre-release tags never imply stable acceptance. Record both the intended
stable increment and the pre-release sequence.

## Required feature research and review

Before implementation, write a research note and a separate review decision.
The review must contain:

1. The user task and observed baseline evidence, with exact source paths or
   reproducible measurements.
2. At least three choices where meaningful: do nothing, the smallest useful
   change, and a broader or structurally different alternative. Compare user
   value, complexity, runtime/resource cost, failure modes, and evidence needed.
3. The exact contract delta for each affected surface, including omitted/default
   behavior, output/schema changes, persisted data, rollout, and migration.
4. A compatibility matrix for old and new producers/clients, including malformed
   and boundary inputs; state unknowns instead of inferring compatibility.
5. A proposed stable increment (**major/minor/patch**) and pre-release tag,
   with the policy rule that determines each.
6. Measurable acceptance checks for behavior and user outcome, plus explicit
   non-goals, resource/security bounds, and remaining release gates.
7. A decision (**YES**, **NO**, or **DEFER**) and bounded implementation scope.
   Significant compatibility, evidence-integrity, or recovery changes also
   require a read-only review by someone who did not author the change.

Implementation starts only after a YES decision. NO or DEFER is a valid
outcome: record why and continue research from the largest unresolved user need.
After implementation, verify the exact candidate commit, build/install path,
runtime behavior, and hosted checks before tagging. Keep stable release gates
and external adoption or score measurements separate from candidate tests.

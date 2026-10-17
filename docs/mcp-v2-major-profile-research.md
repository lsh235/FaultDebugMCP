# v2.0.0 major-version research: default MCP profile

Date: 2026-10-17 (Asia/Seoul). Target: `2.0.0`.

## Why the prior versions stayed in 1.x

The v1.3 alpha series mainly added optional tools and structured output while
preserving the 27-tool `full` profile, the 16-tool `focused` profile, and the
existing native/evidence formats. Those additions are compatible API growth,
so they support a minor-version line. An alpha counter records development
iterations; it does not by itself justify incrementing the major number.

FaultDebugMCP has a published `v1.0.0` tag and an established public API. Under
[Semantic Versioning](https://semver.org/spec/v2.0.0.html), a major increment is
required when a public API change is incompatible. This proposal changes which
MCP tools clients see when they start the server without a profile, and removes
one optional tool from the explicitly selected focused profile.

## Current contract and evidence

- `faultdebug mcp --root PATH` and `make_server(PATH)` currently default to
  `full`: 27 tools and 84 described parameters.
- `focused` currently exposes 16 tools and 45 parameters. It includes
  `get_call_relations`, which reads static-index caller/callee hypotheses and
  does not establish observed runtime execution.
- `CMakeLists.txt` publishes the package as 1.3.0 with
  `SameMajorVersion` package compatibility. Consumers that request CMake
  package major 1 will not match a 2.0 package candidate.
- The Glama example selects `focused`. The official
  [TDQS rubric](https://github.com/glama-ai/tool-definition-quality-score)
  places tool-count coherence in the server score and describes 3-15 tools as
  the typical well-scoped range; 16-25 is a heavier range. This supports testing
  a 15-tool catalog, but does not predict or prove a higher numeric score.
- The current Glama administrator pin, scanned catalog, score breakdown and
  scan time are not visible from this environment. Their status remains
  **NOT VERIFIED**.

## Proposed incompatible change

1. Make `focused` the default for the Python API, CLI and packaged MCP image.
   The default catalog becomes exactly 15 tools and 41 described parameters.
2. Remove `get_call_relations` from `focused`, because it is advanced static
   exploration rather than a first-line capture, incident, or verified-source
   step. Keep the tool, its schema and behavior in `full`.
3. Keep an explicit migration path: `fault-debug mcp --root PATH
   --tool-profile full` restores all 27 tools and the previous static
   call-relations capability; Python callers use
   `make_server(root, tool_profile="full")`.
4. Preserve shared-memory ABI v1, FDAR v1, semantic RPC schema v1, SQLite base
   schema v2, required MCP names and evidence semantics. The major change is
   the MCP catalog contract, not a native capture-format reset.
5. Publish the CMake package as 2.0.0 and keep its `SameMajorVersion` policy;
   CMake consumers that explicitly request version 1 must update to
   `find_package(faultdebug 2 CONFIG REQUIRED)` (or remove an unnecessary
   exact-major constraint). Runtime SONAME stays v1 because the ABI is stable.

This changes the default catalog for existing clients and changes the named
`focused` catalog, so it is intentionally incompatible and belongs in v2.0.
The tool is not removed from the server; existing users can select `full`.
Release notes and migration guidance must identify the change before a stable
v2.0.0 release.

## Bounded acceptance

- Default CLI, `make_server` and container image expose the exact 15-tool
  focused catalog; capabilities report the same profile and inventory.
- Explicit `full` exposes the exact 27-tool catalog, including unchanged
  `get_call_relations` structured output and behavior.
- A real stdio client sees the default 15 tools, rejects a call to the hidden
  static-relations tool, and succeeds when connected to `full`.
- Source and installed-wheel metadata audits agree; the wheel reports
  `2.0.0a1`, CMake package metadata reports `2.0.0`, and runtime SONAME remains
  ABI v1.
- Python/package CI, MCP container verification, native build/runtime smoke,
  and migration docs pass. A Glama score claim requires a separate external
  scan of the exact published revision.

## Exploration limits

The repository's `codebase-memory` skill was consulted, but graph tools are not
exposed in this session. The bounded review used direct source reads and
targeted searches for profile registration, CLI defaults, capability filtering,
MCP tests and release metadata; it does not claim full graph coverage. The
attached REA history is comparative material, not a FaultDebugMCP instruction
or a substitute for this repository's API evidence.

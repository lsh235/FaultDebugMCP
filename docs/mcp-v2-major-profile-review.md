# v2.0.0 major-version review: default MCP profile

Date: 2026-10-17 (Asia/Seoul)

## Decision

**YES — move the MCP default to the 15-tool `focused` catalog, and keep the
complete catalog behind `--tool-profile full`.** This is the first v2 API
change, not just another compatible output-schema addition.

The default change is observable by clients that use `tools/list` without
setting a profile: they will receive 15 tools instead of 27. Focused clients
also stop seeing `get_call_relations`; the same tool remains fully available in
`full`. These are concrete public contract changes and justify a major version
under SemVer. Existing clients have a direct migration option:

```sh
fault-debug mcp --root PATH --tool-profile full
```

Python API users can preserve the same catalog with
`make_server(root, tool_profile="full")`. CMake consumers with an explicit
version-1 requirement must update it to `find_package(faultdebug 2 CONFIG
REQUIRED)`; the shared-library SONAME remains v1.

The 15-tool size follows Glama's published TDQS tool-count guidance and keeps
advanced static-index exploration outside the first-line workflow. This is a
testable score-improvement hypothesis only. The current external Glama pin and
score are **NOT VERIFIED**, so no numeric improvement is promised.

## Trade-offs and constraints

- Focused users who need static caller/callee hypotheses must opt into `full`.
- Full keeps all 27 tools, 84 parameters, schemas and behavior.
- Native runtime SONAME and the ABI/artifact/evidence-store schemas do not
  change in this release candidate.
- The existing v1.3 alpha milestones remain a record of additive development;
  they are not being relabeled as v2.
- The new target is `2.0.0`; the first unstable candidate uses Python PEP 440
  `2.0.0a1` and Git tag `v2.0.0-alpha.1`. A prerelease tag is not stable 2.0.0.

## Acceptance

1. Exact profile inventories and capability parity pass in the direct manager,
   real stdio transport, Docker image and installed wheel.
2. Real stdio rejects `get_call_relations` in default focused mode and retains
   its existing schema and behavior under explicit `full` mode.
3. Build, package, CLI execution and hosted CI pass on the exact tagged commit.
4. Stable promotion remains **NO-GO** until the current-revision full
   provenance-enabled core/gRPC profile, Docker N=8/16/32 matrix, kind
   lifecycle, new 1800-second soak, external libuv corpus re-evaluation and
   independent final audit are all closed.
5. Report Glama score as **NOT VERIFIED** until Glama scans the exact pinned
   15-tool configuration and exposes its score and scan time.

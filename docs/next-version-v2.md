# FaultDebugMCP v2.0 release objective

Date: 2026-10-17 (Asia/Seoul)

## Objective

Target the first incompatible MCP catalog release as **v2.0.0**. The current
candidate changes the no-option MCP server from 27 tools to the 15-tool
`focused` profile, and removes `get_call_relations` only from that profile.
Users can restore the previous catalog with `--tool-profile full`; all 27 tools
and the static call-relations behavior remain available.

This is an explicit public API break, so it justifies the major number. The
first candidate is `2.0.0a1` / `v2.0.0-alpha.1`; the latest published
candidate is `2.0.0a2` / `v2.0.0-alpha.2`. Neither candidate is the stable
release. Candidate feature reviews must classify the intended stable increment
under [`versioning-policy.md`](versioning-policy.md); an alpha number advances
the current target and does not itself mean a stable minor or patch release.
The v1.3 alpha train records compatible additions and is superseded as the
active release target by this plan.

## Work sequence

Before each candidate implementation, record evidence, alternatives, contract
impact, stable version class, and bounded acceptance in separate research and
review notes as required by [`versioning-policy.md`](versioning-policy.md).

1. **M0 — contract break:** update the Python factory, CLI and container default;
   remove advanced static call relations only from focused; retain the full
   profile; test old/new client behavior over MCP stdio and installed package.
2. **M1 — packaging and migration:** align Python and CMake product versions,
   write EN/KO migration notes, audit wheel/sdist, container launch, and source
   consumers. Keep native runtime ABI v1 unless separate evidence shows a native
   breaking change is necessary.
3. **M2 — candidate publication:** publish each v2 prerelease tag only after
   exact-commit build, runtime, packaging and hosted CI checks. Keep the
   implementation in a reviewable draft PR.
4. **M3 — release acceptance:** complete the required current-revision gates
   below, then run an independent stable audit before promoting to `v2.0.0`.
5. **M4 — external usefulness:** ask Glama to pin and rescan the documented
   15-tool profile; separately validate the install-to-first-evidence workflow
   with an external C/C++ project. Do not use tool-count or CI results as
   adoption evidence.

## Stable release gates

These were still open at the v1.3 alpha34 checkpoint and must be freshly
verified against the final v2 candidate:

- full provenance-enabled core and gRPC release profile;
- Docker N=8/16/32 workload matrix and recovery/cost evidence;
- kind Pod/container lifecycle and identity checks;
- new 1800-second workload soak;
- external libuv corpus re-evaluation;
- independent final stable audit.

Each gate must record `PASS`, `FAIL` or `NOT RUN`, its exact revision and
environment. Any required `FAIL` or `NOT RUN` blocks a stable `v2.0.0` tag.
The Glama TDQS re-scan and external consumer workflow are separately reported;
neither is silently substituted with local tests.

## Version contract

- Python distribution: `2.0.0a3` for the current candidate; stable target
  `2.0.0`.
- Native CMake project package: `2.0.0`; runtime shared-library SONAME stays
  `1` because the C ABI is unchanged.
- `--tool-profile full`: exact previous 27-tool catalog, including
  `get_call_relations`.
- Default / `--tool-profile focused`: exact 15-tool catalog, 43 parameters;
  no `get_call_relations` entry.
- Shared-memory ABI v1, FDAR v1, semantic RPC schema v1 and evidence-store base
  schema v2 remain readable as before.
- `get_evidence_summary` accepts 1–32 unique capture names in one call and
  returns one count-only row per input plus aggregate reason-code counts. Its
  representation is `summary_schema: 2`; the semantic RPC schema remains v1.
- `get_rpc_trace` and `get_incident_report` accept optional `page_size=1..200`,
  default 200, and page only observed RPC events. This is intended as a stable
  minor addition after v2.0.0; the alpha3 candidate remains in the v2.0.0
  prerelease sequence.

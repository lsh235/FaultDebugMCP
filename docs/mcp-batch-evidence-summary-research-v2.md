# v2 MCP batch evidence-summary research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.2`.

## User problem

The focused MCP flow can summarize RPC evidence before fetching event
histories, but `get_evidence_summary` currently accepts one capture name.
For a workload containing 8, 16, or 32 captures, a client must make 8, 16, or
32 summary calls before it can compare counts and choose the captures worth
opening. `get_incident_report` accepts multiple captures, but returns observed
event rows and pagination metadata; it is a larger response intended for
reporting rather than a compact first-pass inventory.

## Source evidence and limits

- `faultdebug/mcp_server.py` loads one capture and calls
  `evidence_summary([report])`.
- `faultdebug/rpc.py:evidence_summary` already accepts multiple reports and
  computes aggregate observed RPC counts, process-relation counts, static
  candidate counts and unresolved diagnostics.
- `EvidenceSummaryOutput` currently encodes `artifacts` as the literal `1`
  and exposes raw unresolved rows. This shape cannot identify per-capture
  outliers or guarantee a compact response when a list is summarized.
- `get_incident_report(names)` remains the detailed, paged path. This candidate
  should not copy event histories or claim that aggregate counts prove a
  common cause.

The `codebase-memory` skill was consulted, but its graph tools are not exposed
in this session. This bounded research used direct source reads of the handler,
aggregate function, output model, MCP metadata tests and existing release
notes. It makes no graph-coverage or exhaustive call-graph claim.

## Candidate contract

For `v2.0.0-alpha.2`, change the focused tool to accept a required list of 1–32
distinct root-relative capture names. Keep one MCP tool, so the default
catalog remains 15 tools and its parameter count remains 41. Return one
count-only row per input name in the supplied order plus aggregate counts.
Per-capture rows identify local RPC status, observed RPC count, static
candidate count and unresolved reason counts. Cross-capture process-relation
counts and unresolved reasons remain at the aggregate level because they do
not belong to one capture.

The response should contain only stable reason-code counts, not unbounded
diagnostic payloads. Use a separate `summary_schema` marker for this output
shape; the existing `schema` field continues to identify the semantic RPC
evidence version. Detailed records remain available through `get_rpc_trace`
and `get_incident_report`.

`v2.0.0-alpha.1` clients currently send `name` and receive `artifacts: 1` plus
raw `unresolved` rows. Because v2 is still prerelease, alpha.2 can replace this
unstable shape, but the migration must be explicit. There is no stable v2
consumer contract yet.

## Efficiency hypothesis and risks

For N captures, this reduces summary round trips from N to 1 while keeping
payloads count-only and attributed to each input. It does not reduce the
number of detailed calls needed to inspect selected captures, and it does not
prove lower end-to-end diagnosis time without a representative user task.

The new list parameter and output rows could increase tool-definition
complexity; no Glama score improvement is predicted. A rescan of the exact
published profile would still be required. Limit N to 32, reject duplicate or
escaping paths before reading, preserve input order, and keep unknown/malformed
evidence visibly unresolved. No additional tool should be added to the
focused profile for this feature.

## Bounded acceptance

- Real stdio accepts 1, 8, 16 and 32 names in one `get_evidence_summary` call
  and returns exactly one compact row per input name in input order.
- Aggregates equal the sums of independently computed per-capture RPC and
  static-candidate counts; cross-capture relation results match
  `process_relations` on the same report set.
- Empty lists, more than 32 names, duplicates, escaping paths and malformed
  captures fail clearly without changing any input.
- The published output schema validates both text and structured results;
  diagnostic maps remain count-only and response size stays below 64 KiB for
  the 32-capture fixture.
- Default and full tool inventories remain 15 and 27. Build/install and hosted
  Python, container and Clang 18 CI pass on the exact candidate revision.
- Report the 1-versus-N call-count result as an interface-level efficiency
  measurement, not as user task-completion or adoption evidence.

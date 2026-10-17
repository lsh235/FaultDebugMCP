# Alpha34 research: typed service-flow output

Date: 2026-10-17 (Asia/Seoul)

## Question

Which next MCP contract change can improve the usefulness of the definitions
Glama scans without claiming a score change that has not been measured?

## Evidence

- The official TDQS definition includes `outputSchema` among the fields sent to
  the evaluator. Its contextual-completeness guidance says a declared output
  schema reduces what the prose description must explain. The official
  improvement checklist recommends documented output schemas.
- In the current default `full` profile, `get_service_flow` returns a plain
  `dict` and has no typed output schema. Its query contract has a stable common
  envelope (`schema`, `snapshot_id`, `session_id`, `section`, `counts`, and
  `limitations`) plus page fields and selected-section `items` for collection
  queries. The default profile exposes 27 tools; 17 currently publish output
  schemas.
- `get_service_flow` already shares its read-only projection between CLI and
  MCP. It rechecks frozen inputs on every page and rejects a stale snapshot.
  The selected collection rows are intentionally producer-shaped and may gain
  fields, so closing those rows in a schema would risk compatibility.
- Glama's live score and scan timestamp are not available in this session. A
  source change can be validated locally and by hosted CI, but any numeric
  TDQS improvement remains unverified until Glama re-scans the intended build.

## Candidate

Add an additive output contract to `get_service_flow` for the summary and
collection-page envelopes. Type the stable envelope, the seven stable count
keys, section names, and pagination fields. Keep collection rows open and
preserve extra root fields so new application/native evidence remains readable.
Do not change the query algorithm, JSON text payload, pagination, snapshot
fingerprint, evidence files, or tool membership.

This addresses a real untyped output in the default profile and gives MCP
clients a machine-readable distinction between summary and paged collection
responses. It may help TDQS contextual completeness; no numeric score effect is
assumed.

## Alternatives

- More prose alone would leave the missing structured response contract.
- Typing every full-profile-only tool in one release would enlarge the change
  and make schema drift harder to review. Continue one stable contract at a
  time.
- Removing tools to reduce the full catalog could damage its evidence coverage
  and is not supported by a Glama per-dimension breakdown.

## Validation targets

1. Real stdio `tools/list` exposes the schema in the full profile and continues
   to omit `get_service_flow` from the focused profile.
2. Summary and every collection section validate with the output schema; page
   union, `next_page`, empty pages, and stale-snapshot rejection remain intact.
3. MCP text JSON stays byte-semantically equal to the shared CLI projection;
   no input evidence file changes.
4. Sparse/unknown collection-row fields survive through `structuredContent`.
5. Build, package, local native/service-flow regressions, and hosted CI pass.
6. Record Glama score and scan time as NOT VERIFIED unless the live listing or
   authorized administrator test supplies those observations.

## Exploration limits

The installed codebase-memory skill was checked, but its graph MCP tools are
not exposed in this session. The candidate was traced by direct source and test
inspection; no complete graph-coverage claim is made.

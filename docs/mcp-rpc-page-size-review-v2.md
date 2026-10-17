# Configurable MCP RPC pages candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.3`.

## Decision

**YES — add bounded `page_size` inputs to `get_rpc_trace` and
`get_incident_report`.** These tools currently force 200 observed RPC rows per
page even though the existing service-flow query already supports a typed
caller-selected size. Letting clients request fewer rows improves control over
large MCP responses without adding another tool.

## Version classification

Under [`docs/versioning-policy.md`](versioning-policy.md), this feature is an
intended **MINOR** addition after a stable release: it adds optional inputs and
preserves the old request's default response. Because stable v2.0.0 has not
shipped and the feature is being developed inside that target, the candidate
tag remains `v2.0.0-alpha.3` / Python `2.0.0a3`; this alpha ordinal is not a
stable minor increment. The v2.0.0 target itself remains **MAJOR** against v1
because alpha1 changed the default MCP tool catalog and documented package
major. Stable v2 acceptance remains separate and NO-GO.

Compatibility reasoning: callers that omit `page_size` still receive at most
200 rows and the same fields/page arithmetic. Callers that explicitly pass the
new input opt into a smaller event slice. Generated input and output schemas
change, so review must cover real stdio metadata and typed responses. Consumer
compatibility uncertainty must be recorded rather than called safe.

| Consumer case | Expected behavior | Evidence required |
| --- | --- | --- |
| Existing client omits the new input | Same default 200-row pages and response values. | Compare full default response with explicit `page_size=200`; validate with the new output schema. |
| Updated client requests 1–200 rows | Receives at most the requested number of observed rows; totals and page numbering remain global/stable. | Test 1, an intermediate value, 200, concatenated pages, and exhausted page over real stdio. |
| Client pins the old exact tools/list schema | The published input/output schema differs and such a client may need regeneration even though its old request still works. | Call this out in release notes; do not claim exact schema snapshot equality. |
| Incident report has repeated non-paged context | Candidates, process relations, fields, and unresolved evidence remain present on each page. | Compare two pages from a fixture containing each evidence class. |

## Alternatives considered

- **NO CHANGE:** preserves every schema but keeps a fixed 200-row response for
  clients with smaller context or transport budgets.
- **YES, bounded rows on these two tools:** smallest user-visible change; reuses
  existing page numbering and the local service-flow size convention; retains
  default behavior. This is the selected scope.
- **Broader byte/cursor pagination:** could address more transport and dataset
  growth cases, but needs additional serialization, continuation, ordering, and
  cross-tool contracts. Current evidence does not justify that larger surface.
  The selected feature does not promise a byte ceiling.

Cost is limited but real: two additional focused parameters, input/output schema
updates, and pagination tests. Decoding and scanning remain unchanged, so this
does not claim lower total CPU or memory work. A small page can repeat unpaged
uncertainty and candidate metadata; acceptance checks event equivalence across
pages and persistence of the non-paged fields.

## Required limits

- Add optional `page_size` in the closed range 1–200; keep the default at 200
  so existing callers retain their current behavior.
- Return the effective size in each typed output. Keep `total` values scoped
  to the complete observed collection and preserve zero-based page semantics.
- Page only the observed RPC event rows, matching current behavior. Keep
  candidates, unresolved evidence, and other report fields separate and
  unchanged on each page.
- Do not claim that this bounds the full incident-report response: artifact
  summaries, candidates and diagnostics remain unpaged.
- Keep the tool inventories at 27 full / 15 focused and verify the focused
  parameter count is 43 (full profile: 86 parameters).
- Keep Glama score impact **NOT VERIFIED** until Glama scans the exact published
  candidate.

## Acceptance

Proceed only if real stdio tests demonstrate default compatibility, schema
bounds, page concatenation without duplicate or missing events, stable totals,
and structured/text output validation at sizes 1, intermediate, and 200. Stable
v2 remains blocked on its separate release gates and independent audit.

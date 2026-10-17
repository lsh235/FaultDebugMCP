# Incident-slice MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.31`, based on
`v1.3.0-alpha.30`.

## Baseline and source evidence

The focused profile exposes `get_incident_slice` as the main read path from a
persisted incident ID to its artifact, participant, observed, derived,
static-candidate, unresolved, hypothesis and source-reference evidence. The
handler returns a stable page envelope but currently advertises no
`outputSchema`. The SQL projection fixes incident, artifact, process and saved
source-reference columns; observed and diagnostic payload rows are retained as
producer JSON.

Success responses carry evidence-store `schema=2`, a stored incident row,
artifacts for the current page, participants, observed RPC/peer snapshots,
derived process relations, static candidates, unresolved rows, hypotheses,
source references, pagination totals and capture-limit indicators. The
`observed_event_total` field is added only when the page selects artifacts;
`event_total` and `event_truncated` are present on empty pages as well. An
unknown incident, invalid database or unavailable incident tables returns the
existing `{schema: 2, error: {code: INCIDENT_QUERY_ERROR, message}}` payload.

`get_unresolved` is a narrower gap-only view. `get_incident_report` analyzes
named capture files without requiring a stored incident, and
`get_source_evidence` verifies stored source references against a bundle. A
slice's `source_references` are stored claims, not verified citations. The
contract must keep those boundaries visible and must not turn payload rows
into typed root-cause verdicts.

Evidence payloads are JSON copied from producers, and database row layouts can
gain fields as the store evolves. Type the stable page envelope and known SQL
columns, keep SQL rows open to extensions, and leave payload collections
producer-defined. Preserve the conditional `observed_event_total` key and the
existing text JSON, including the page-level `event_truncated` and
`event_total` distinction. Read-only store access and the error payload stay
unchanged.

The local tool description currently enumerates most response fields. The
official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score)
recommends a documented output schema and cutting description text that merely
repeats schema fields. A bounded rewrite can preserve selection guidance and
evidence caveats while moving return-shape detail into the schema. This can
improve machine-readable usability; it cannot guarantee a Glama score change.

Codebase-memory graph tools are not exposed in this session. This bounded
research uses direct source reads of the focused-profile list, handler,
read-only evidence-store projection and existing real-stdio tests; it makes no
graph-coverage or exhaustive-impact claim.

## Bounded candidate

Publish a success/error union for `get_incident_slice` in both profiles.
Document the page envelope, schema version, known SQLite row columns,
conditional observed-event total and truncation limit. Accept unknown fields on
SQL rows and arbitrary JSON payload values in evidence collections. Keep the
description focused on when to call the tool, how it differs from its siblings,
the 200-artifact/1,000-observed-event limits, and the fact that stored source
references require a separate verification call.

Do not change the query, event ordering or cap, artifact pagination,
`observed_event_total` omission, error code, read-only behavior, evidence
classification, text output or tool inventory. The current 27/84 full and
15/44 focused catalogs remain fixed; typed output-schema counts would increase
from 14/13 to 15/14.

## Acceptance evidence

1. Full and focused stdio publish equivalent non-empty success/error schemas.
2. Validate populated and empty pages, a page beyond the artifact total,
   observed-event truncation at 1,000, a missing incident, unavailable-store
   error, variable payload types and unknown SQL-row extensions.
3. Preserve exact text JSON, conditional `observed_event_total`, error code,
   evidence bytes and read-only store state.
4. Build/install distributions and run the installed-wheel full/focused stdio
   audit; hosted CI passes on the final release-record commit before tagging.
5. Report Glama pin, rescan and numeric score only with separate external
   evidence; stable acceptance remains a distinct gate.

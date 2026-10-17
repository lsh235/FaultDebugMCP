# Incident report MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.27`.

## Decision

**YES: implement the bounded output-schema candidate researched in
`mcp-incident-report-output-research.md`.**

`get_incident_report` is an available, read-only first-line tool in both
profiles and returns a substantial cross-capture report. Its stable envelope
and its page boundary are currently visible only through JSON text and
prose. A documented output schema will give MCP clients a structured result
and will expose return-field semantics to TDQS. This is an actionable contract
improvement even if Glama reports no score change.

## Review of scope and risk

The proposal is appropriately narrow: it changes only the return annotation
and the corresponding tool metadata/tests/docs/version. It does not alter
capture decoding, report construction, evidence ordering, pagination, or the
text payload. Reusing the existing RPC-event model plus a report-local
`artifact_index` avoids a second description of normalized event fields.

Process relations, producer candidates, unresolved rows and field observations
have source-dependent keys or values. Keep those records permissive so older
captures and producer extensions remain visible. Typed structured output must
not add defaults to the text result, discard unknown evidence, or turn
diagnostic/candidate rows into verified relations. The return model must be
validated against actual stdio responses before release; a failure means
revise or remove the schema candidate, not weaken the evidence checks.

## Bounded acceptance

1. `get_incident_report` publishes a non-empty schema in full and focused
   `tools/list`; tool and parameter inventory, input schema, annotations and
   description contracts remain unchanged.
2. Real full/focused stdio calls cover empty/no-RPC, observed events, a
   cross-capture relation, unresolved/candidate rows, explicit field values,
   and page 0/page 1 of a 201-event report. `structuredContent` validates and
   agrees with the existing parsed text result.
3. A malformed path/capture still returns an MCP error. Evidence snapshots
   before and after are identical. The existing CLI report remains unchanged.
4. Wheel/sdist build and an installed-wheel MCP check pass outside the source
   checkout; hosted CI passes on the final implementation commit before the
   alpha tag and draft PR are published.
5. Release notes say `NOT RE-SCORED` until an official Glama scan is observed.

## Explicit non-claims

This review does not claim a TDQS increase, Glama deployment, a stable release,
or completion of the full release gate. It approves only this alpha candidate
and its verification work.

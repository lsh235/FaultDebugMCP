# Session-list output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.22`.

## Baseline and opportunity

`list_sessions` is the read-only SQLite entry point that returns session IDs
before `get_session`. The store query has one fixed six-field row projection:
nullable session ID, earliest captured process-start monotonic time, artifact
count, verified-artifact count, minimum identity-source label and aggregate
trust state. Its page envelope is fixed at schema version 2 with `sessions`,
`total`, `page` and `page_size`. The handler does not return arbitrary artifact
payloads, and query failures remain MCP tool errors.

This is a narrower machine-readable contract than `get_session`, whose result
contains evidence collections and variable payloads. A documented output schema
lets MCP clients consume session counts and trust state without guessing field
semantics or parsing text. TDQS explicitly recommends schemas with field
documentation and evaluates the schema contents; it does not guarantee a
numeric score increase.

Sources: [TDQS scoring inputs and output-schema guidance](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[tool handler and profile boundary](../faultdebug/mcp_server.py),
[session-list SQL projection](../faultdebug/evidence_store.py).

## Candidate and boundary

Add one typed success output model for `list_sessions`. Preserve schema version
2, all six selected row fields, the nullable unassigned session ID and nullable
first-start time. Leave `identity_source` as an open string because the store
aggregates application/runtime-provided labels, and keep `trust_state` limited
to the existing `verified` and `unresolved` values. Describe counts as stored
artifact counts, not process counts or fault verdicts.

Keep the output schema in the existing full profile only. `list_sessions` is
intentionally absent from the 15-tool focused workflow, whose server
instructions direct session-store users to the full profile. Do not change
profile membership or the existing MCP tool error behavior for missing stores.
Do not type `get_session` or its evidence rows in this increment.

## Bounded acceptance

1. Full-profile `tools/list` publishes a documented object schema that matches
   the SQL projection and page envelope; focused profile remains 15 tools/44
   parameters with no `list_sessions` exposure.
2. Real stdio validates populated and empty full-profile responses against the
   output schema and confirms the structured fields match top-level text JSON.
3. Missing-store and invalid-filter failures remain MCP tool errors; listing
   remains read-only, unassigned grouping and captured monotonic-time filtering
   retain their semantics, and evidence files do not change.
4. Keep the full catalog at 27 tools/84 parameters and current focused catalog
   at 15 tools/44 parameters; output-schema tools become seven full and six
   focused.
5. Build/install and run relevant store/MCP regressions plus hosted CI. Glama
   admin pin, deployment, re-scan and numeric score require separate evidence.

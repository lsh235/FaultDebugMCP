# Incident-list output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.21`.

## Baseline and opportunity

`list_incidents` is part of the 15-tool focused profile and is the entry point
for stored, agent-declared incident inspection. It returns a stable SQLite
projection and page metadata, but MCP currently exposes only its input schema.
The successful row shape has ten fixed fields selected by an explicit SQL
projection: incident and session identity, trigger process/signal, status,
phase, partial flag, first-seen monotonic time, trust state, and artifact
count. The query also has one stable structured-error payload with
`schema=2` and `error.code=INCIDENT_QUERY_ERROR`.

This is a better schema target than `get_incident_slice`: the list does not
forward arbitrary stored payloads, and its success/error variants can be
modeled as a small union. Glama's published TDQS checklist recommends output
schemas whose field documentation reduces the description burden. The schema
may make a fresh rubric evaluation more informative and enables direct client
consumption; it cannot promise a numeric score change.

Sources: [TDQS output-schema guidance](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[list projection and error mapping](../faultdebug/mcp_server.py),
[incident-list query](../faultdebug/evidence_store.py).

## Candidate and boundary

Publish success and query-error output models for `list_incidents` only. Match
the SQL projection exactly, including nullable values and SQLite's integer
representation of `partial`. Keep free-form status/phase strings free-form;
the store accepts declared application values rather than a closed enum.
Preserve text JSON, read-only querying, AND-combined filters and the meaning of
`first_seen_ns` as the incident's captured monotonic time.

FastMCP exposes a union return annotation as an object schema with a `result`
property whose `anyOf` selects success or error. Structured MCP clients receive
that same payload under `structuredContent.result`; the text block keeps the
existing top-level JSON object. Compare the nested structured value with the
text value to prove the two representations agree.

Do not model the incident slice, provenance rows or stored evidence payloads in
this increment; those contain larger schemas and extensible records.

## Bounded acceptance

1. Publish a documented success/error output-schema union in both full and
   focused profiles, with the exact ten-field incident record and pagination
   contract.
2. Validate actual populated/empty success responses and the missing-store or
   unavailable-table error response against the advertised schemas over real
   stdio; `structuredContent.result` must equal the existing top-level text JSON.
3. Keep 27 full/15 focused tools, 84/44 parameters, all five existing output
   schemas, titles, safety annotations and evidence immutability unchanged.
4. Preserve incident IDs, time filter semantics, read-only store access and
   error code. Do not turn the list into an incident declaration or root-cause
   verdict.
5. Build/install and run relevant store/MCP regressions plus hosted CI. Verify
   any Glama pin, deployment, re-scan and numeric score separately.

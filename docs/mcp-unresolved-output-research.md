# Unresolved-evidence MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate assessed for alpha32.

## Source evidence and profile

`get_unresolved` reads a declared incident's gap rows from the SQLite evidence
store. Its success envelope contains `schema=2`, the incident row, producer and
query-generated unresolved payloads, artifact-page metadata and total artifact
count. Missing incidents, invalid stores and unavailable incident tables keep
the payload-level `{schema: 2, error: {code: INCIDENT_QUERY_ERROR, message}}`
contract. Pagination follows linked artifacts, not individual gap rows.

Direct inspection of `FOCUSED_MCP_TOOL_NAMES` and `test/mcp_tool_metadata.py`
shows that `get_unresolved` is **not** exposed by the focused profile. Its
current description in that profile's neighboring tools is also intentionally
rewritten so it does not recommend an unavailable tool. A schema for this
full-only tool would increase the full output-schema count but would not change
the repository's documented focused Glama catalog. The actual administrator
pin is inaccessible in this session, so a different external profile cannot
be assumed.

The earlier [alpha28 evidence-summary review](mcp-evidence-summary-output-review.md)
also rejected a full-only schema for this score-focused task. That decision
remains applicable to `get_unresolved`; do not repeat a full-only change while
the Glama target profile is unknown.

## Decision

Do not implement this candidate in alpha32. Keep it available for a later
full-profile client-contract milestone. Continue research for a bounded feature
that improves the documented focused profile.

Codebase-memory graph tools are not exposed. This bounded assessment reads the
profile set, description overrides, handler and store projection directly; it
does not claim graph coverage or exhaustive repository impact.

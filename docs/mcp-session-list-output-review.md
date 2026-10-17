# Session-list output-schema feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.22` candidate.

## Decision

**YES — add a typed output schema to `list_sessions`.** The successful response
is a bounded projection produced by explicit SQL aggregation. A client can
reliably distinguish an assigned session from the unassigned group, process
start time from wall-clock time, total artifacts from verified artifacts, and
stored trust status. This reduces parsing work in the common SQLite inventory
step without changing the existing tool set.

Keep the schema full-profile only. The focused 15-tool profile intentionally
does not expose session-store inventory and says session tools require `full`.
Keep `identity_source` open because stored values may vary. Missing stores and
query failures remain MCP tool errors; do not turn them into a new JSON error
shape. The TDQS checklist says evaluators read documented output fields, but a
Glama rescan is required to observe any score change.

## Acceptance

1. Advertised fields match the six-field SQL row projection and schema-v2 page
   envelope; nullable values and meanings are documented.
2. Full-profile real stdio validates populated, unassigned and empty results;
   the structured result equals the existing text JSON. Missing-store failure
   remains an MCP error.
3. The 27/84 full and 15/44 focused catalogs remain intact; `list_sessions`
   remains absent from focused; safety hints and evidence immutability pass.
4. Store/MCP regressions, sdist/wheel build and installed CLI/MCP execution pass;
   hosted CI validates the final tagged commit.
5. Official Glama administrator pin, deployment, re-scan and numeric score are
   marked only from direct evidence. Stable acceptance remains **NO-GO**.

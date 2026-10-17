# Incident-list output-schema feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.21` candidate.

## Decision

**YES — publish a typed success/error output schema for `list_incidents`.**
This is the focused workflow's next stable machine-readable boundary after
verified source lookup. Its success fields are directly constrained by one SQL
projection, and its MCP error payload has one fixed code. A model can describe
incident identity, the distinction between session and incident ID, nullable
trigger details, captured monotonic time, trust state and artifact count.

Preserve `partial` as the current SQLite `0`/`1` representation and leave
application-defined status and phase strings open. This makes the schema
honest to the existing API instead of silently changing values. Leave the
larger incident slice and variable payloads untyped for a later review. TDQS
recommends documented output schemas but does not guarantee that a title/schema
change raises the official score; Glama deployment and re-scoring remain
external.

The MCP SDK represents a success/error union as `outputSchema.properties.result`
with `anyOf`; structured clients receive the selected object at
`structuredContent.result`. The ordinary text response remains the existing
top-level JSON object, so acceptance compares that text payload with the nested
structured value.

## Acceptance

1. Both MCP profiles publish non-empty success/error schemas for
   `list_incidents`; item fields and optional nulls match the SQL projection.
2. Real stdio validates populated/empty listing and query-error responses;
   `structuredContent.result` equals the existing top-level JSON text.
3. Read-only mode, ID/time/trust filters, error code, inventory, prior five
   output schemas, titles, boolean hints and evidence immutability are retained.
4. Relevant SQLite and MCP regressions, distribution build/install and all
   hosted CI jobs pass on the tagged code revision.
5. Glama administrator configuration, deployment, re-scan and score are
   reported only with independent evidence.

Stable release acceptance remains **NO-GO**.

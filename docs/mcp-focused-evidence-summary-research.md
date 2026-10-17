# Focused evidence-summary MCP research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.32`, based on
`v1.3.0-alpha.31`.

## Current profile and source behavior

`get_evidence_summary` is a full-profile read-only tool. It loads one named
capture and returns a six-field count inventory: RPC schema version, summary
status, capture count, observed RPC/process-relation counts, static-candidate
count and unresolved diagnostic rows. The unresolved rows are decoder or
process-pairing diagnostics; each contains a string `reason`, while other keys
vary by condition. A missing RPC extension is reported as unresolved, not as
successful communication. The tool returns no event histories. Invalid paths
or malformed captures remain MCP tool errors.

The repository's documented Glama container profile is `focused`, and the
actual administrator pin and listing score are inaccessible here. The focused
catalog currently omits this compact summary, although the full catalog
recommends it from `open_fault`. Adding it to focused would make the short
count-only triage step available before the more detailed `open_fault`,
`get_rpc_trace` or `get_fault_flow` results. Its one required capture name is
cheap to invoke; its documented output lets an agent decide whether a detailed
call is useful. It is semantically distinct from raw capture decoding and
history-returning tools.

The official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
passes `outputSchema` to evaluation and says documented fields can relieve
prose from repeating response structure. It explicitly says schema presence
alone is not a deterministic score signal. It also evaluates sibling
selection and server coherence, so adding a focused tool can help or hurt those
dimensions; no numeric effect is predicted. The
[Glama indexing methodology](https://glama.ai/mcp/methodology) discusses
re-indexing, but this session cannot access the user's administrator pin or
public score page.

Codebase-memory graph tools are not exposed. This bounded research directly
reads `FOCUSED_MCP_TOOL_NAMES`, its profile-specific descriptions, the summary
handler, `evidence_summary`, unresolved diagnostic producers and the real stdio
audit. It does not claim graph coverage or exhaustive repository impact.

## Reconsidered candidate

The full-only `get_evidence_summary` schema was previously rejected in alpha28.
This is a different proposal: expose the existing compact one-capture summary
in the focused profile and publish its typed schema at the same time. This
addresses the earlier visibility reason for the NO decision and changes only
one catalog entry.

The current focused profile has 15 tools and 44 parameters. The candidate
becomes 16 tools and 45 parameters; the full profile remains at 27/84. Current
structured-output counts are 15/14 (full/focused); the candidate would make
those 16/15. Existing input parameters, annotations and query behavior remain
unchanged. The focused `open_fault` description should name the summary as the
count-only alternative, and the focused server instructions should identify it
as the inexpensive triage step.

## Bounded candidate

Expose `get_evidence_summary` in the focused profile. Publish a direct-object
output schema with `schema=1`, `status` (`complete` or `limited`), one-capture
count, the two non-negative observed counts, static-candidate count and
unresolved diagnostic rows. Require the stable string `reason` on each
diagnostic and allow its additional fields. State that `complete` means no
unresolved diagnostic was emitted; it does not mean the application succeeded
or that every event was captured.

Shorten the full and focused descriptions only where output fields repeat the
schema. Preserve the distinction between summary counts and detailed RPC/fault
views, the missing-instrumentation boundary, MCP tool errors, and read-only/no-
execution behavior. Do not alter the summary algorithm, text JSON, error
behavior, input schema or full catalog.

## Acceptance evidence

1. Full and focused real stdio both expose equivalent summary schemas; focused
   membership becomes 16 tools/45 parameters while full remains 27/84.
2. Validate a complete count summary and a limited summary with no RPC
   extension; preserve diagnostic-specific fields and exact text/structured
   equality.
3. Invalid capture paths remain MCP tool errors, and source artifacts remain
   unchanged.
4. Build/install sdist and wheel; run installed full/focused stdio audits and
   CLI outside checkout; hosted CI passes on the final release-record commit.
5. Report a Glama score only with administrator-pin and official rescan
   evidence. Stable acceptance remains separate.

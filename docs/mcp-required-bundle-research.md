# MCP source tools: required bundle schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.15`.
Baseline: `v1.3.0-alpha.14`.

## Observed contract mismatch

`get_function_source` and `get_call_relations` both reject a call without a
verified source bundle. Their runtime descriptions say so, but the
`tools/list` JSON Schema currently advertises `bundle` as nullable and optional
because each Python parameter defaults to `None`. A client must make a call
that the schema permits only to receive an error that the implementation
predictably requires a bundle.

The other `bundle` inputs are genuinely optional: `open_fault`, `get_fault_flow`
and `resolve_addresses` can return useful capture-only or unresolved results
without source data. Their nullable schemas should remain unchanged.

The Glama TDQS rubric evaluates parameter semantics against the exported
schema, and weighs purpose clarity, usage guidance, behavior transparency and
parameter semantics separately. Making these two fields required expresses the
existing runtime contract in the protocol schema and removes the contradictory
"required despite nullable default" wording. This change is expected to
improve schema accuracy; only Glama's re-scan can confirm a score change.

Sources: [Glama indexing methodology](https://glama.ai/mcp/methodology),
[open TDQS rubric](https://github.com/glama-ai/tool-definition-quality-score).
The current listing score/API was not available to this research run (public
API returned HTTP 401), so no baseline or predicted numeric score is claimed.

## Options

1. Keep nullable optional fields and rely on prose to say they are mandatory.
   Rejected: clients still generate predictably invalid calls.
2. Make bundle required only for the two source-index tools and retain optional
   bundles for capture-only tools. Accepted: the schema reflects existing
   behavior without broadening the change or adding a tool.
3. Add a fallback that silently guesses a bundle. Rejected: multiple bundles
   can be present and guessing would weaken source identity verification.

## Proposed acceptance

- The real `tools/list` schema marks `bundle` required and non-null for exactly
  `get_function_source` and `get_call_relations`.
- The real stdio server rejects missing/invalid bundles and accepts verified
  bundles for both tools.
- Existing optional-bundle tools remain optional; all 26 tools retain their
  annotations and read-only behavior, and evidence files remain unchanged.
- Hosted CI verifies the protocol and existing native/package regression set.

# Verified source output-schema feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.20` candidate.

## Decision

**YES — publish one precise structured result schema for `get_function_source`.**
This is a first-line operation in the focused evidence-to-source workflow. Its
successful return fields are bounded and directly supported by the implementation;
MCP clients can consume paths, line ranges, identity and source text without
parsing the text content.

Scope stays on the success shape. Source verification remains required, and
missing IDs or invalid bundles continue to surface as tool errors. Leave
`get_call_relations` and address-resolution output untyped for now because their
row data can carry static-index extensions or variable resolution fields. The
official TDQS checklist recommends documented output schemas, but a human-score
increase is nondeterministic and remains unverified.

## Acceptance

1. `get_function_source` publishes a non-empty object `outputSchema` in both
   profiles with seven documented fields and a literal `resolved: true`.
2. Real stdio returns schema-valid `structuredContent` for a verified source
   lookup; structured and text responses agree on every field.
3. Missing function IDs and invalid bundles remain rejected, no current source
   worktree is substituted, and evidence files remain unchanged.
4. The existing four structured schemas, 27/15 tool inventories, 84/44
   parameter counts, descriptive titles and boolean annotations are preserved.
5. Package build/install and all hosted CI jobs pass on the final tagged
   revision. Glama pin, deployment, re-scan and score remain NOT VERIFIED absent
   independent evidence.

Stable release acceptance remains **NO-GO**.

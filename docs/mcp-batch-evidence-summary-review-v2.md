# v2 batch evidence-summary candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.2`.

## Decision

**YES — implement bounded multi-capture count summaries in the existing
`get_evidence_summary` tool.** It reduces first-pass MCP round trips from N to
one for a selected set of up to 32 captures while keeping the focused catalog
at 15 tools. The underlying aggregate function already accepts a report list;
the work is a missing MCP request/output contract, not a speculative new
evidence inference.

## Required limits

- Accept 1–32 unique root-relative capture names in input order.
- Preserve a separate summary-output schema marker. Keep raw semantic evidence
  schema identity distinct from the summary representation version.
- Return per-capture counts/status plus aggregate counts; group unresolved
  diagnostics by stable reason code so a large batch stays compact.
- Keep cross-capture relations aggregate-only. Do not assign one relation to
  a capture without evidence that supports that assignment.
- Keep observed events, static candidates and unresolved counts distinct.
  The count-only result must never become a root-cause or success verdict.
- Update alpha1-to-alpha2 migration notes. This changes only prerelease
  contracts; do not claim that an alpha1 input/output format was a stable v2
  API.

## Acceptance

Proceed only if the 1/8/16/32 stdio fixtures prove aggregate equivalence,
stable input ordering, path and size bounds, read-only behavior, output-schema
validation, and unchanged 15/27 tool inventories. Keep Glama score impact
**NOT VERIFIED** until Glama scans the exact published build. Stable v2 remains
blocked on its separate release gates and independent audit.

# Evidence summary MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.28`.

## Decision

**NO: do not implement this as the alpha28 score-focused change.**

Source inspection confirms `get_evidence_summary` is full-profile only and is
absent from `FOCUSED_MCP_TOOL_NAMES`. The repository's documented Glama
Dockerfile example selects the focused catalog, so this schema would add no
definition to that target. The external administrator profile is not verified;
without evidence that Glama is scoring the full catalog, changing this tool is
not a justified step toward the user's current score goal.

## Scope and risk

The proposed model itself is technically bounded, but its only direct catalog
effect would be one additional full-profile output schema. Keep the current
worktree free of this code change and continue research for a candidate that is
actually exposed by the focused profile.

The omitted field is viable for a later full-profile client-consistency
milestone. A new alpha28 candidate must first be mapped against the focused
tool set and must preserve dynamic evidence shapes.

No code was approved by this review. It makes no Glama score, external
deployment, stable-release or full-gate claim.

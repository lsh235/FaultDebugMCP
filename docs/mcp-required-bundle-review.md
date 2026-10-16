# MCP required-bundle schema: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.15` candidate.

## Decision

**YES — declare `bundle` as required for `get_function_source` and
`get_call_relations`.** Both functions already fail when it is omitted, and
their descriptions already say that it is mandatory. The current nullable
schema therefore invites invalid calls and lowers the precision of the
published tool contract.

## Scope and acceptance

1. Use the existing non-null `RequiredBundlePath` schema type for both tools;
   reorder `get_call_relations` parameters as needed to preserve Python's
   default-argument rules while retaining `direction="outbound"`.
2. Verify required/non-null fields from a real MCP `tools/list` exchange and
   verify that a missing bundle is rejected before the handler runs.
3. Exercise both tools with a valid verified bundle and preserve the optional
   bundle behavior of `open_fault`, `get_fault_flow`, and `resolve_addresses`.
4. Preserve all 26 tool names, read-only annotations, root confinement and
   evidence-file immutability.

This is a schema-accuracy improvement aligned with the
[research record](mcp-required-bundle-research.md). It does not promise a
numeric Glama score increase; the live score is independently evaluated.

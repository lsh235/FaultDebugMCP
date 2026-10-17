# RPC-trace output-schema review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.24`.

## Decision: YES

Add a typed output contract for `get_rpc_trace`.

This tool is already present in the focused profile and returns a versioned,
bounded envelope with normalized event scalar types and a finite diagnostic
taxonomy. A schema can make RPC identity, timing and uncertainty fields easier
for clients to consume while preserving the explicit distinction between
observed events, static candidates and unresolved diagnostics. That makes this
a useful next score-oriented increment without increasing tool count.

Keep extension-provided `static_candidates` open JSON, because their producer
contract is separate and the decoder intentionally does not reinterpret them.
Do not turn missing instrumentation into a failure or treat an observed shared
identifier as causation. The implementation must preserve all six diagnostic
reasons, pagination semantics and MCP errors for malformed/ambiguous input.

No score change is predicted. Alpha22's public Glama snapshot is stale, and the
administrator pin and rescan remain unauthenticated/unverified. The output
schema is only a local definition improvement until an official scan records a
new score.

Acceptance is the five bounded conditions in
[research](mcp-rpc-trace-output-research.md), especially every diagnostic
branch, absent instrumentation, paging, evidence immutability and full/focused
stdio validation.

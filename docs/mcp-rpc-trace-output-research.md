# RPC-trace output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.24`.

## Baseline and opportunity

`get_rpc_trace` is in both the full and 15-tool focused MCP profiles. It
normalizes an optional semantic-RPC extension into `observed` events and keeps
`static_candidates` and `unresolved` in separate top-level evidence classes.
The handler pages only observations at 200 rows; the total describes all
normalized observed events, while candidates and diagnostic rows remain
visible on each page. Missing RPC instrumentation is a valid unresolved result.
Malformed or ambiguous extensions remain MCP tool errors.

The response has schema version 1, a status of `complete`, `limited`, or
`unresolved`, and a nullable source label. Normalized observation keys have a
fixed finite set and validated scalar types. The decoder also emits six
versioned unresolved reason codes: absent extension, non-monotonic sequence,
sequence gap, partial/overflow runtime, incomplete stream, and empty event
stream. Static candidates remain caller/runtime-provided JSON and are never
merged into observed events.

Sources: [TDQS output-schema guidance](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[MCP handler and profile membership](../faultdebug/mcp_server.py),
[normalized event and diagnostic contract](../faultdebug/rpc.py).

## Candidate boundary

Add a documented typed success output for `get_rpc_trace` in both profiles.
Describe every normalized event field, each diagnostic variant, the fixed
page-size envelope, source labels and status meanings. Keep `static_candidates`
as open JSON because its source contracts are caller-defined. Preserve the
existing text result, evidence-class boundaries, order, pagination and MCP
error semantics. Do not infer causal RPC links or add runtime instrumentation.

## Bounded acceptance

1. Real `tools/list` publishes the output schema in full and focused profiles;
   tool and parameter inventories remain unchanged.
2. Real stdio validates populated, paged and absent-extension results. Each
   supported diagnostic reason validates as its own schema branch; static
   candidates remain separate from normalized observations.
3. Malformed, duplicate and unsupported-version extensions remain MCP errors.
   Text output remains unchanged, and structured output matches it subject only
   to documented nullable fields inserted by the SDK.
4. Full/focused catalog sizes, safety annotations and capture immutability stay
   unchanged; no static candidate becomes an observed event or causal edge.
5. Run the RPC decoder and MCP schema regressions, package build, installed
   wheel boundary check and hosted CI. Glama re-scan and score remain external
   evidence; no numeric score increase is forecast.

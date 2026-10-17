# Address resolution MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.28`.

## Baseline and source evidence

The alpha27 `focused` catalog includes `resolve_addresses`, but its real
`tools/list` definition has no `outputSchema`. The handler in
`faultdebug/mcp_server.py` returns one `items` row per requested absolute
address using `faultdebug.inspect.resolve_addresses`.

Every resolver row begins with `address`, `kind`, and `resolved`. Unresolved
rows may include a reason such as `missing_module`, `build_id_mismatch`,
`missing_symbol`, or `function_not_in_index`; resolved rows may include the
module, Build ID, load bias, relative address, symbol, and function ID. Matching
separate debug symbols, static index edges and offline source-location details
are optional. These are evidence states, not a fault-cause verdict.

The repository already publishes `FaultFlowResolution` in the fault-flow
output schema. It documents the same resolution fields, allows future
resolution metadata, and keeps static edges and source locations distinct.
The candidate can reuse that row model inside a small `{items: [...]}` result
contract. It must preserve unknown producer fields, per-address failures, and
the existing raw text response.

The codebase-memory graph tools are not exposed in this session. This bounded
review uses direct reads of `FOCUSED_MCP_TOOL_NAMES`, the MCP handler, the
address resolver and its existing output model. No graph-coverage or
exhaustive call-graph claim is made.

## Relevance to TDQS and users

The repository's Glama Dockerfile example selects the focused profile, so this
tool is in the target catalog documented here. The official
[TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
includes the full output schema in the tool definition and evaluates
contextual completeness against the documented return fields. A useful schema
can also let callers distinguish a verified function ID from an unresolved
address without parsing text, then pass only an actual ID to the required
bundle-backed `get_function_source` tool.

This is a justified definition improvement, not evidence of a numeric score
gain. Glama's external profile, pin, deployment and rescan remain unverified.

## Bounded candidate

Add `ResolveAddressesOutput` with a documented `items` array of
`FaultFlowResolution` rows and annotate the MCP handler with that model. Keep
the resolver algorithm, optional bundle/debug lookup, input parameters,
read-only annotations, errors, text JSON and tool inventory unchanged. An
empty address list continues to return an empty `items` array. Per-address
unresolved results continue to coexist with other rows in the same response.

If accepted, the output-schema count increases from 11 to 12 in the full
profile and 10 to 11 in focused. Tool and parameter counts remain 27/84 and
15/44.

## Acceptance evidence

Use real stdio in both profiles for an empty address list and an address with
no matching captured module, validate `structuredContent` against the
published schema, and compare every text field while allowing only the
documented optional null fields added by the typed model. Existing invalid
address, count-limit and debug-directory rejection tests must remain green.
Snapshot captures and bundles before and after. Build and install the wheel
outside the checkout and require hosted CI before tagging.

No official Glama rescan or stable-release acceptance is part of this
candidate.

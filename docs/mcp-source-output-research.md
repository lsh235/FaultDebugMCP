# Verified source output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.20`.

## Baseline and opportunity

The focused profile now has typed structured results for capabilities, store
health, artifact discovery and bundle discovery. The central verified source
lookup, `get_function_source`, still returns an untyped dictionary over MCP.
Its implementation has a narrow success contract: `resolved`, `function_id`,
verified `bundle` and `file` paths, one-based `start_line` / `end_line`, and the
source text. Missing IDs, invalid paths or failed bundle verification are MCP
tool errors rather than alternate success dictionaries.

The output model is safer to publish than schemas for more general evidence
queries: it has no arbitrary row extensions, pagination variants, or
status-dependent fields. The MCP SDK v1.30 already supports typed output
annotations, so this does not require another dependency migration. Glama's
published TDQS checklist recommends documented output schemas because the
evaluator can use their fields when judging contextual completeness. This is a
rubric-backed candidate, not evidence that this tool is a cause of the current
server score.

Sources: [TDQS output-schema guidance](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[official MCP Python SDK structured-output guide](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/docs/servers/structured-output.md),
[FaultDebugMCP implementation](../faultdebug/inspect.py).

## Candidate and scope boundary

Add a precise typed output model only for `get_function_source`. Keep the
existing text result and source-verification behavior. Do not add schemas to
`get_call_relations` or address-resolution rows in this increment: those pass
through static-index extension data and variable symbol outcomes, so a narrow
schema could reject or discard valid evidence fields.

## Bounded acceptance

1. Publish the exact seven-field success contract on `get_function_source` in
   both full and focused profiles.
2. Validate the actual `structuredContent` against the advertised JSON Schema
   over stdio and confirm its values match the existing text JSON for a verified
   source function.
3. Keep source and bundle verification mandatory. Invalid or missing function
   IDs remain tool errors; capture/store evidence and other tool definitions
   remain unchanged.
4. Retain 27 full tools/84 parameters and 15 focused tools/44 parameters, all
   current title/annotation contracts and the existing four schemas.
5. Build/install the package, run source/bundle/MCP regressions and hosted CI.
   State any Glama deployment or numeric score only with external evidence.

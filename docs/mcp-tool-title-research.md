# MCP display-title research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.19`.

## Baseline and opportunity

The real `tools/list` response currently has no top-level `Tool.title`. The
server stores short labels such as `Get capabilities` in
`ToolAnnotations.title`, but its registration wrapper does not pass the
separate `title` argument supported by FastMCP. Glama TDQS scores the top-level
title as part of the MCP tool definition and includes it in the evaluator's
prompt. TDQS also computes `titleIsMeaningful` when a title differs from the
programmatic name and is longer than that name. A changed title changes the
definition hash and makes the definition eligible for rescoring.

The MCP Python SDK v1.30.0 already supports this without a dependency or
protocol upgrade: `FastMCP.tool` accepts `title`, its internal registration
retains it, and the wire `Tool` extends `BaseMetadata` with the optional title.
The SDK documents the title as human-readable display text for end-user
contexts. This is a small presentation and definition-quality gap rather than a
runtime evidence feature.

Sources: [TDQS tool inputs and title signal](https://github.com/glama-ai/tool-definition-quality-score),
[TDQS score-improvement checklist](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[MCP SDK v1.30.0 FastMCP registration](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py),
[MCP SDK v1.30.0 wire Tool type](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/types.py).

## Candidate

Publish an informative top-level title for each of the 27 full-profile tools.
Keep all titles distinct, concise, and longer than their snake_case tool names;
make each title identify the resource and scope rather than mechanically
reformatting the name. Keep the existing `readOnlyHint`, `destructiveHint`,
`idempotentHint`, and `openWorldHint` values. Align the legacy annotation title
with the new display title so clients do not receive competing labels.

Titles are part of TDQS input and can make tool pickers easier to scan, but the
rubric grades six definition dimensions through an LLM. The title signal is a
deterministic context measurement, not a guaranteed score bonus. A Glama
administrator pin, deployment, fresh scan, and numeric result remain necessary
to verify any effect.

## Bounded acceptance

1. Use the existing `mcp==1.30.0` public FastMCP `title` argument; do not change
   the dependency or any tool name, input, output, profile, or evidence behavior.
2. Through real stdio, verify each full-profile tool has a distinct top-level
   title different from and longer than its programmatic name, and that the
   annotation title matches. Check all 15 focused tools retain the same property.
3. Keep 27 full and 15 focused tools, all current input/output schemas and
   boolean safety annotations. Preserve read-only behavior and evidence files.
4. Run the stdio metadata audit, relevant regressions, Python package build and
   install checks, plus hosted CI.
5. Do not predict or claim an official score change without Glama's fresh
   evaluation.

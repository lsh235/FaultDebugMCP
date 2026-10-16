# MCP structured-output research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.18`.

## Baseline and opportunity

Alpha17 publishes 15 focused MCP tools and gives each input parameter a
description. The tools return JSON-like dictionaries as text, but the pinned
`mcp==1.9.4` does not publish an `outputSchema` or structured result channel.
Glama's open TDQS specification includes `outputSchema` in the exact tool
definition it evaluates, records whether a schema is present, and says a schema
can carry return details that otherwise burden the prose description. This is
a concrete protocol contract gap, not evidence that it explains the current
numeric Glama score.

The official Python SDK v1.9.4 `Tool` type contains `inputSchema` but no
`outputSchema`, and its FastMCP `list_tools` only maps input schema and
annotations. The official v1.30.0 SDK still exposes FastMCP and maps
`info.output_schema` into the wire-level `outputSchema`; the return annotation
provides the schema and the SDK returns structured data. The official SDK
documentation describes this as an additive data channel alongside text
content. Staying below major version 2 avoids its announced API and protocol
migration.

Sources: [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score),
[Python SDK v1.9.4 tool types](https://github.com/modelcontextprotocol/python-sdk/blob/v1.9.4/src/mcp/types.py),
[Python SDK v1.30.0 FastMCP](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py),
[official structured-output guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/structured-output.md),
[SDK migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md).

## Candidate

Move the pinned v1 SDK from 1.9.4 to 1.30.0 and add typed output models for
four high-value focused tools: `get_capabilities`, `check_store`,
`discover_artifacts`, and `discover_bundles`. The models will specify the
stable outer contract and meaningful row fields, while keeping explicitly
variable evidence records permissive where the source format is extensible.
Avoid blanket `dict[str, Any]` annotations that only create an empty-looking
schema. Other tools remain on their current response contract until their
variable evidence shapes have a defensible model.

This improves machine consumption independently of Glama: MCP clients can use
`structuredContent` instead of parsing text. It also supplies non-empty output
schemas to the published definition for a bounded portion of the first-line
catalog. It does not promise any score change; Glama's score is still generated
from its external deployment and rubric scan.

## Risks and bounded acceptance

The SDK upgrade activates return validation for annotated results. A wrong
model could turn a successful inspection into a tool error, so each model must
be tested against representative success and error payloads over real stdio.
The existing `content` text remains parseable JSON and evidence stores/files
must remain unchanged.

Acceptance:

1. Pin `mcp==1.30.0` while keeping `<2` and confirm the existing FastMCP setup,
   CLI transports and annotations continue to work.
2. Publish non-empty `outputSchema` for the four named tools in both focused
   and full profiles; validate `structuredContent` against each schema through
   the real client/server pair.
3. Cover valid, empty, rejected and structured-error response variants;
   preserve existing text JSON behavior and evidence immutability.
4. Keep 27 full tools, 15 focused tools, all parameter descriptions and current
   annotations unchanged. Run package build/install and hosted CI.
5. Update Glama's documented source pin only. Mark admin configuration,
   deployment, official score and re-scan NOT VERIFIED unless direct evidence
   is available.

## Review decision

**YES, with the four-tool scope above.** The user asked to improve the actual
MCP definitions and clients benefit from typed structured results. The output
schema is protocol-standard, and the official v1 SDK now supports it without a
major-version migration. Proceed only if real stdio validates all response
variants; otherwise roll back the output-schema portion and continue research.

No score estimate or release-readiness claim is authorized by this candidate.

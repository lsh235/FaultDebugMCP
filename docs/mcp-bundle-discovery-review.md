# MCP verified-bundle discovery: feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.16` candidate.

## Decision

**YES — add a bounded read-only `discover_bundles` tool.** It is the missing
step between locating a capture and invoking the source tools whose verified
bundle requirement became explicit in alpha15. The tool must return candidates,
not claim to verify them; verification remains at the source-consuming call.

## Scope and acceptance

1. Search only beneath the configured root; reject or omit symlink escapes and
   return relative paths only.
2. Scan no more than 10,000 manifests and page up to 200 rows. Discovery must
   not parse manifests or hash bundle contents.
3. Report `verification=not_performed`, a root-relative directory path and the
   manifest file size. A filename match is a candidate, not a validity claim.
4. Keep source verification inside `get_function_source`,
   `get_call_relations`, and `get_source_evidence`; preserve evidence
   immutability and all existing tool contracts.
5. Add the tool to the additional-capability list and exercise its real stdio
   schema, pagination, malformed manifest candidate and symlink behavior.

This improves the MCP workflow and its tool-set cohesion. Glama's independent
score remains unverified until its listing is rebuilt and rescored. See the
[research record](mcp-bundle-discovery-research.md).

# MCP tool-surface profiles: research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.17`.
Baseline: alpha16 full profile, 27 tools and 84 described parameters.

## Score-relevant gap

Alpha16 improves the capture-to-source workflow, but the standard server still
publishes 27 tools. Glama's published TDQS model weights per-tool definition
quality at 70% and tool-set coherence at 30%. Its coherence rubric explicitly
scores tool-count appropriateness: 3–15 tools is the typical well-scoped range,
16–25 is described as heavy, and 50+ as an extreme mismatch. The official
scoring source also warns that changing tool count does not guarantee a higher
overall score; disambiguation, naming, completeness and each tool's TDQS still
matter.

The exact current FaultDebugMCP score and dimension breakdown remain unavailable
through the public retrieval path in this session. Therefore, 27 tools is a
rubric-backed improvement target, not a verified explanation of the current
numeric score.

Sources: [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score),
[Glama indexing methodology](https://glama.ai/mcp/methodology).

## Options

1. Add more prose to all tool descriptions. Rejected: every current input
   parameter already has a description, and the rubric rewards useful
   distinctions while penalizing bloat.
2. Remove advanced tools from the MCP server globally. Rejected: this would
   break existing full-surface clients and make unrelated workflows unavailable.
3. Add an explicit focused MCP profile while keeping `full` as the default.
   Accepted: the focused profile exposes 15 tools for the common capture,
   incident and verified-source investigation path. The complete 27-tool API
   remains available with the default profile. Glama's launch configuration can
   intentionally select the focused surface, and the listing then describes
   exactly what it exposes.

## Focused profile

The 15 tools are `get_capabilities`, `discover_artifacts`, `discover_bundles`,
`open_fault`, `get_thread_trace`, `get_fault_flow`, `get_rpc_trace`,
`get_incident_report`, `check_store`, `list_incidents`, `get_incident_slice`,
`get_source_evidence`, `resolve_addresses`, `get_function_source`, and
`get_call_relations`. This preserves the declared required tool set and covers
capture discovery, trace inspection, incident-backed evidence, and verified
source lookup. Tools for broader timeline, session, provenance and legacy-index
work remain available in `full`.

The selected profile must be reflected in `get_capabilities`; it must not claim
that filtered tools are available. Unknown profile values fail closed. No MCP
tool behavior or evidence semantics change.

## Proposed acceptance

- `full` remains the default and exposes the exact alpha16 27-tool inventory.
- `focused` exposes exactly the 15 documented names; every required capability
  tool is present and capability lists agree with the actual catalog.
- The real stdio protocol lists only the selected profile and rejects calls to
  filtered tools as unknown.
- The published Glama command selects `focused` and its source pin is the exact
  implementation commit.
- Hosted CI passes for the final implementation; the official Glama rescan is
  separately checked before claiming any score change.

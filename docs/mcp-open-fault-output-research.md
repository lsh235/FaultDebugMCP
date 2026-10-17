# Open-fault output schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.33`, based on the
alpha32 focused-catalog change.

## Current tool surface

The documented Glama build profile is `focused`. Its 16 tools all have titles,
descriptions, parameter documentation and read-only annotations, but the
`tools/list` audit reports an output schema for only 15. The sole untyped
focused result is `open_fault`, the first detailed capture view after artifact
discovery. `get_evidence_summary` offers counts only; `get_thread_trace`,
`get_rpc_trace` and `get_fault_flow` provide more specialized views.

`open_fault` returns the dictionary from `collect_file` and can add a verified
bundle marker. Native captures have stable top-level sections for the header,
threads, modules, crashes, completeness and snapshot consistency; the optional
RPC sidecar adds `rpc` and `rpc_events`. The launcher may add process, target,
session, context, collector and artifact metadata. JSON capture files can be
sparse and producer-defined, and future fields must remain visible. Thread
rows already have an open extension model in the MCP output contracts.

The official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
scores the `tools/list` definition, reads `outputSchema` in full, and says a
bare object schema earns no output-field credit. It also emphasizes that
descriptions should name alternatives and explain when to use them. This makes
the one missing focused schema a grounded candidate, but no numeric increase
can be predicted. The official [Glama indexing methodology](https://glama.ai/mcp/methodology)
requires an updated capture/re-scan before a score change can be confirmed.

Codebase-memory graph tools are not exposed in this session. This bounded
research directly inspected the focused catalog, `open_fault`, `collect_file`,
the native decoder's returned sections, launcher-added fields, thread output
models and real-stdio metadata tests. It does not claim graph coverage or
exhaustive impact analysis.

## Proposed change

Publish a documented typed output schema for `open_fault` without changing
capture decoding or JSON text content. Type only stable native fields and
well-established wrappers. Keep producer-defined row/root extensions open;
make legacy/sparse sections optional; keep context and other variable
producer payloads explicitly open instead of pretending they have a fixed
shape. Document that `complete` and a verified bundle marker describe
capture/read or source-integrity evidence, not application success or root
cause.

The full catalog remains 27 tools / 84 parameters and 16 output schemas. The
focused catalog remains 16 / 45 and increases from 15 to 16 output schemas.
The input schema, tool selection, artifact bytes, evidence semantics and
read-only behavior remain unchanged.

## Acceptance evidence

1. Both profiles publish the same `open_fault` output schema; the existing
   inventory counts remain 27/84 and 16/45.
2. Real stdio validates native-like, sparse legacy JSON, optional verified
   bundle metadata and unknown producer fields without losing the text result.
3. Malformed/escaping paths remain MCP errors, and captures/bundles remain
   byte-for-byte unchanged.
4. Source and installed-wheel metadata audits, package build and hosted CI pass.
5. Glama's new schema capture, scan time and score are verified separately;
   stable acceptance remains **NO-GO**.

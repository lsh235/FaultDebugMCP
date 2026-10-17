# Evidence summary MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.28`.

## Baseline and evidence

The alpha27 release exposes `get_evidence_summary` only in the full profile;
`FOCUSED_MCP_TOOL_NAMES` omits it. It has no `outputSchema`. The handler reads
one root-relative capture and calls `evidence_summary([report])`. The result has a compact,
stable envelope: `schema`, `status`, `artifacts`, `observed`,
`static_candidates`, and `unresolved`. `observed` contains the two counts
`rpc_events` and `process_relations`; this tool returns no event histories.

The report builder always receives a one-element list from the handler, so
`artifacts` is exactly 1. The schema version is the RPC contract version 1.
Status is `complete` when no diagnostic rows were produced and `limited`
otherwise. Absence of semantic RPC evidence is represented as a limitation,
not successful communication. `static_candidates` is a count, while
`unresolved` contains source-specific diagnostic rows with different keys.
Malformed capture paths and decoding failures continue to use MCP tool errors.
The handler is read-only and performs no target execution or store mutation.

The codebase-memory skill's graph tools are not exposed in this session. This
bounded candidate uses direct reads of `faultdebug/mcp_server.py`,
`faultdebug/rpc.py`, the existing RPC output model and stdio audit. It makes no
exhaustive call-graph or graph-coverage claim.

## TDQS and client value

The repository's Glama Dockerfile example selects the focused profile, while
the external administrator setting remains unverified. A schema for this
full-only tool would not affect that documented focused catalog, so its
priority for the current score request is weak.

The official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
includes `outputSchema` in the definition given to the evaluator and says
documented fields can relieve prose from explaining return structure. This
tool is a compact first-step inventory: structured counts let a client decide
whether to fetch the detailed `get_rpc_trace`, the multi-capture
`get_incident_report`, or the execution-oriented `get_fault_flow` without
parsing a text JSON block. A typed result also gives callers stable names for
the count fields while keeping diagnostic reasons visible.

The specification also says a schema's presence alone is not a quality gain;
the candidate should describe the actual field semantics and limitations. No
Glama score attribution or numeric prediction is justified without an
official rescan.

## Bounded candidate

The initial idea was to type `get_evidence_summary`. That would affect only the
full profile: full/focused counts would become 12/10 output schemas, while
tool/parameter counts remain 27/84 and 15/44. Since the documented Glama
configuration targets focused, this is not the selected alpha28 candidate.
Retain it as a later client-consistency improvement if the target configuration
switches to full.

If accepted, full/focused tool counts remain 27/15 and parameter counts
84/44. The output-schema counts increase from 11/10 to 12/11.

## Acceptance evidence

If reconsidered for the full profile, validate real stdio for an empty/no-RPC
capture, a 201-event capture, an unsupported RPC extension represented as a
diagnostic, and a malformed path/capture that remains an MCP error. Validate
`structuredContent` against the published schema and require exact equality
with the existing parsed text result. Snapshot evidence inputs before and
after, then build/install the wheel and require hosted CI.

No official Glama rescan or stable-release acceptance is part of this
candidate.

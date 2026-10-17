# Incident report MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.27`.

## Baseline

The alpha26 tag exposes 27 tools in the full profile and 15 in the focused
profile. `get_incident_report` is available in both profiles but publishes no
`outputSchema`; clients currently receive its JSON text result without the
typed `structuredContent` contract already available on `get_rpc_trace` and
`get_fault_flow`.

The real handler in `faultdebug/mcp_server.py` accepts root-relative capture
names and a zero-based page. It combines decoded RPC records from the captures,
adds `artifact_index` to each observed event, and pages only
`observed.rpc_events` in groups of 200. It also returns `page`, `page_size`,
and `total_rpc_events`. The report builder in `faultdebug/rpc.py` emits
`schema`, `status`, `artifacts`, `observed`, `static_candidates`, `unresolved`,
and four `fields` collections: `status`, `deadlines`, `retries`, and `streams`.
The report reads captures and does not write report files or modify evidence.

## Stable and variable response fields

The top-level envelope, status vocabulary (`complete`, `limited`,
`unresolved`), paging fields, `observed` groups and four `fields` groups are
stable code contracts. RPC observations reuse the normalized event fields
already published by `RpcTraceOutput`; each row additionally has the
report-local `artifact_index`.

The report intentionally combines records whose row shapes vary by source:

- `process_relations` combines semantic-RPC joins with explicit IPC relations;
- static candidates are copied from the producer without interpretation;
- unresolved rows come from RPC decoding, endpoint matching and timeline
  diagnostics; and
- status/deadline/retry/stream field rows contain only the value explicitly
  present on the corresponding event.

The output contract should type the envelope and normalized RPC events while
leaving these producer- and diagnostic-owned rows open JSON objects. A schema
must not require fields absent from older captures, narrow extension values,
or promote a candidate/diagnostic into an observed causal relation. Keep the
existing text JSON shape and evidence semantics unchanged.

## TDQS relevance and limits

The official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
states that the evaluator receives the `outputSchema` in full and that
documented return fields can relieve the description of explaining their
shape. It also explicitly says a bare object schema relieves the description
of nothing. This candidate can provide meaningful field-level return
semantics for one multi-capture report tool. It does not establish that the
current Glama score is low because of this tool, and no numeric gain can be
predicted without an official rescan.

## Bounded candidate

Add a typed result contract for `get_incident_report` in both MCP profiles:

1. Type the stable top-level envelope, status, page metadata, artifact rows,
   and the documented field-availability collections.
2. Reuse the normalized `RpcTraceEvent` fields and add `artifact_index` for
   report events.
3. Preserve static candidates, process relations, unresolved diagnostics and
   value-bearing field rows as open JSON records where producers define
   extensible shapes.
4. Preserve the legacy text content byte-shape at the JSON-value level,
   actual paged behavior, read-only annotations and error behavior.

Do not change tool count, input parameters, report derivation, CLI format,
store/capture contents or evidence classification. The expected profile
counts remain 27 tools/84 parameters and 15 tools/44 parameters; full and
focused output-schema counts increase by one each if implementation passes.

## Acceptance evidence

Validate real stdio in both profiles for empty/no-RPC evidence, observed RPC
events, explicit process relations, unresolved records, static candidates,
field projections, and at least two report pages. Check `structuredContent`
against the published schema and compare its defined values with the existing
text result. A malformed capture must continue to return a tool error. Snapshot
all evidence inputs before and after. Build and install the wheel outside the
checkout, verify the installed server publishes the same schema, then require
hosted CI before tagging and publishing an alpha release.

No Glama score or stable-release acceptance claim is part of this candidate.

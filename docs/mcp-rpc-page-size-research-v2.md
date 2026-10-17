# Configurable MCP RPC pages research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.3`.
Baseline: `v2.0.0-alpha.2`.

## User problem

`get_rpc_trace` and `get_incident_report` page observed RPC events in fixed
groups of 200. Their output schemas publish `page_size` as the literal `200`,
and the tools accept only a page number. A client with a smaller context or
transport budget cannot request a smaller slice; a client that needs a short
preview still receives the same page size.

## Source evidence

- `faultdebug/mcp_server.py:get_rpc_trace` slices `observed` at 200 and writes
  `page_size: 200` to every response.
- `faultdebug/mcp_server.py:get_incident_report` likewise slices only
  `observed.rpc_events` at 200. Artifact summaries, static candidates,
  unresolved rows and recorded application fields remain outside that page.
- `faultdebug/mcp_outputs.py:RpcTraceOutput` and `IncidentReportOutput` both
  declare `page_size` as `Literal[200]`.
- `get_service_flow` already demonstrates a typed `page_size` range of 1–200
  and returns the selected value. This establishes a local contract pattern.
- The official Python SDK derives tool input schemas from type hints and
  output schemas from return annotations, so a bounded optional argument and
  matching response type are visible to clients:
  [tools](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md),
  [structured output](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/structured-output.md).

The codebase-memory skill was consulted, but graph-query tools are unavailable
in this session. These findings are bounded to direct reads of the two handlers,
their output models, related tests, and the existing service-flow page contract;
they do not claim full graph coverage.

## Candidate contract

Add an optional `page_size` parameter from 1 through 200 to `get_rpc_trace` and
`get_incident_report`, with default 200. Preserve zero-based `page`, the
existing default response exactly, and every evidence field. The response's
`page_size` reports the actual requested value.

Only the observed event collection is paged, as today. Static candidates,
unresolved diagnostics, and incident-report artifact rows remain on every
response. This makes event pages tunable but does not promise a hard byte cap
for the entire result. `get_thread_trace` is out of scope because it pages
thread rows whose nested event histories are not currently split by event.

This adds two bounded optional parameters and no MCP tools. The focused catalog
stays at 15 tools; its parameter count changes from 41 to 43. The full catalog
stays at 27 tools and changes from 84 to 86 parameters. It is intended to give
clients control over event row count, not to guarantee a TDQS score change or
reduce total decoding work.

## Alternatives and cost

| Choice | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep 200 fixed rows | No API or implementation change. | Clients cannot request a smaller event slice even when their context/transport budget is tighter. |
| Add a bounded row count to these two existing page-based tools | Reuses their page number and the service-flow range convention; keeps old calls at 200; requires no new tool. | Adds two parameters and a schema change; does not cap unpaged fields or total decode/scan work. |
| Add a byte-budget or cursor system across all report tools | Could address broader transport cost and evolving datasets. | More complex serialization/continuation semantics; byte size varies by evidence; larger compatibility and pagination-order surface than this observed need supports. |

The smallest option is the current candidate. Its measurable benefit is caller
control over the number of observed event rows returned per call. It must not be
presented as a universal response-byte or total-work reduction.

## Bounded acceptance

- Real stdio publishes the optional 1–200 `page_size` input schema for both
  tools and keeps the default at 200.
- Values 1, an intermediate value, and 200 return that many rows at most;
  page metadata and total counts remain correct across page boundaries.
- Concatenating pages at a smaller size reproduces the same ordered observed
  event IDs as the default page size without omissions or duplicates.
- Empty/exhausted pages remain valid; zero, 201, booleans, floats, and strings
  are rejected by the input contract.
- Structured and text results validate against the updated output schemas.
- Full/focused inventories remain 27/15 tools, with 43 focused parameters.
- The full profile exposes 86 parameters; focused exposes 43.
- Report row-count bounds and representative payload sizes only; do not claim a
  universal byte ceiling or a Glama score change.

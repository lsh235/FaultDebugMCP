# Bounded raw thread history research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.4`.
Baseline: `v2.0.0-alpha.3` at `21f2563be3fb8d9ace6b58baffb31c5752a8394d`.

## User task

Inspect raw thread events through MCP while controlling the amount returned to
the client. This is a request/response-size control; it is not a request to
discard or rewrite captured evidence.

## Source evidence

- `faultdebug/mcp_server.py:get_thread_trace` accepts `name`, optional `tid`,
  and `page`; it always slices at most 200 thread rows. It does not slice the
  `events` list nested inside any selected row.
- `faultdebug/inspect.py:thread_trace` filters by OS `tid` and returns original
  thread records. A reused `tid` can match several generations.
- `faultdebug/mcp_outputs.py:ThreadTraceThread.events` is an ordered list of raw
  event rows. Its existing `event_count` and retention fields describe producer
  ring accounting and loss, not view truncation.
- `get_fault_flow(max_events=80)` already limits a derived pre-crash view and
  reports `omitted_from_view`. It is not a substitute for raw history: it builds
  a different projection and its limit is tied to the fault-flow model.
- The checked-in v1.1 C++ benchmark records a direct collector trace with
  100,290 event records across 33 thread rows and a 3,040-event maximum per
  thread. That report says `artifact_written: false`; it demonstrates a
  high-cardinality workload, not a previously measured MCP payload:
  [`test/external/cpp-call-benchmark-v1.1.md`](../test/external/cpp-call-benchmark-v1.1.md),
  [`report`](../test/external/cpp_call_benchmark_v1_1.json).
- The official Python MCP SDK derives tool input JSON Schema from function type
  hints and publishes structured output schemas from output types:
  [tool definitions](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/tools.md),
  [structured output](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/servers/structured-output.md).

The codebase-memory skill was consulted, but graph-query tools are unavailable
in this session. These observations are bounded to direct reads of the handler,
decoder, output models, tests, and benchmark report; they do not claim full
graph coverage.

## Candidate contract

Add two optional controls to `get_thread_trace`:

- `page_size`: strict integer 1–200, default 200, for outer thread rows;
- `max_events_per_thread`: strict integer 1–500, default null (no truncation).

When an event limit is supplied, keep the last N retained event rows in their
original sequence order. Add a reserved `faultdebug_view` extension to each
returned thread row with `events_omitted_from_view`; its integer is the number
removed from that response view, not the producer's `dropped_count`, and null
means the event list was unavailable. An empty or shorter-than-limit list
reports zero. Existing thread-row schemas allow additional properties, so old
clients can tolerate this opt-in annotation. If a producer already uses the
reserved `faultdebug_view` key, fail the bounded call rather than overwrite it.
Keep `event_count`, `dropped_count`, retention, other unknown row/event fields,
and the capture file unchanged. When both options are omitted, the text result
must remain unchanged.

This limits returned thread and event row counts only when callers opt in. A
maximum request can still contain 200 × 500 event rows, and the tool still
decodes the full capture before shaping the response. Do not claim a byte cap,
streaming, reduced decode cost, or reduced capture loss.

## Alternatives and cost

| Choice | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep current behavior | Full raw histories remain available with no API change. | A single thread row can contain thousands of events; outer page size 200 does not bound nested event rows. |
| Add optional outer page size and last-N event projection | Reuses existing page/tid/generation semantics; gives clients two explicit response controls; omission keeps legacy output. | Adds two parameters and an opt-in reserved row extension; consumers must distinguish view omission from capture loss. Decode and scan cost remain. A conflicting producer extension fails closed. |
| Add event cursors or a new per-thread event tool | Can retrieve arbitrary event ranges without dropping older rows from the response. | Needs a stable identity for each generation/slot and page consistency rules; legacy sparse JSON may not provide those identity fields. The current need is bounded inspection, not a cursor protocol. |
| Use `get_fault_flow(max_events)` | Already returns a bounded execution view. | It is a different derived pre-crash projection and cannot replace the raw thread/event history contract. |

The selected candidate addresses the narrower response-shaping task while
preserving complete raw access by default. A real MCP fixture with a large
nested event list must measure text/structured response reduction; the existing
benchmark is not substituted for that MCP measurement.

## Candidate version class

This is intended as a **MINOR-class** addition after a stable release: optional
inputs preserve old calls, and view-only omission metadata is present only when
the new event limit is requested. Because stable v2.0.0 has not shipped, the
candidate belongs to the current MAJOR prerelease train as Python `2.0.0a4` /
Git tag `v2.0.0-alpha.4`. See the
[versioning policy](versioning-policy.md).

## Bounded acceptance

- Real stdio publishes optional typed inputs with defaults and ranges 1–200 and
  1–500; invalid integer boundaries, booleans, floats and strings are rejected.
- Default calls and explicit `page_size=200, max_events_per_thread=null` retain
  the same text output and all raw event rows.
- Outer pages at sizes 1, an intermediate size, and 200 preserve total rows,
  order, generations and no omissions/duplicates across pages.
- Event limits 1, 80, and 500 return the last retained events in source order;
  `faultdebug_view.events_omitted_from_view` counts only rows excluded from
  this view and distinguishes missing/null lists from empty lists. Producer
  `event_count`, `dropped_count`, retention, and unknown row keys are unchanged.
- A producer-owned `faultdebug_view` survives default calls and makes an opt-in
  bounded call fail without altering the source capture.
- Empty, short, oversized, and sparse event arrays retain explicit semantics;
  unavailable event lists report an unknown omission count.
- The full and focused profiles remain 27/15 tools and grow from 86/43 to
  88/45 parameters. Structured/text responses validate and the source capture
  hash remains unchanged.
- A high-cardinality real stdio fixture reports event-row counts and serialized
  text/structured sizes before and after shaping; no universal byte ceiling is
  claimed.
- Stable v2 remains blocked by its separate release gates and independent
  audit; no Glama score change is inferred.

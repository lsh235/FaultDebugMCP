# Thread-trace MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.30`.

## Baseline and source evidence

The `focused` profile exposes `get_thread_trace`, but the tool does not yet
publish an `outputSchema`. `make_server` returns a fixed envelope with
`items`, `page`, `page_size`, and `total`; it paginates thread records rather
than individual events. A `tid` filter selects all matching thread generations
for the captured OS thread ID.

The decoder in `faultdebug/format.py` emits fixed thread fields (`slot`, `tid`,
`generation`, `flags`, `event_count`, `dropped_count`, and `events`) and adds a
`retention` object only when the native thread-history flags are present. Each
event carries `sequence`, `monotonic_ns`, `function`, `callsite`, `type`, and
`generation`. These are decoded raw ABI fields; they are not symbolized calls
or evidence that a recorded event is complete beyond the capture's explicit
loss state.

Three focused tools currently lack output schemas: `open_fault`,
`get_thread_trace`, and `get_incident_slice`. `open_fault` returns a full capture
with more nested artifact state, and `get_incident_slice` combines variable
store evidence rows. The bounded thread-trace envelope and native row shape
offer a smaller next candidate. Relation and retention rows should remain
permissive to avoid rejecting future decoder/index extensions.

The codebase-memory MCP tools are not exposed in this session. This bounded
research reads the focused-profile allowlist, MCP handler, native decoder and
real stdio metadata audit directly. It makes no graph-coverage or exhaustive
impact claim.

## Relevance to focused clients and TDQS

`get_thread_trace` is a first-line focused tool for raw thread history. A
structured schema can describe the pagination boundary, the distinction
between OS thread ID and generation, and retained event fields so clients can
consume the trace without inferring fields from the text response. The capture
already reports overflow and retired-history limits elsewhere; this schema
must preserve those values and avoid claiming a complete trace from the event
array alone.

The official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
evaluates the MCP output contract, but this repository cannot confirm the
external Glama profile, deployment or score without an official rescan.

## Bounded candidate

Publish a typed `get_thread_trace` result in both profiles. Type the fixed
envelope, thread record, event fields and conditional retention object. Keep
thread and event models open to additional producer fields. Preserve optional
retention omission/null behavior and the existing text JSON.

Do not change decoder output, event ordering, pagination, `tid` filtering,
capture validation, loss reporting or tool membership. Tool/parameter counts
remain 27/84 and 15/44; full/focused output schemas would increase from 13/12
to 14/13 if accepted.

## Acceptance evidence

Use real full/focused stdio calls to validate events, generation-aware thread
records, conditional retention, `tid` filtering across generations, an
unmatched ID, and an exhausted page. Compare all existing text fields with
`structuredContent`, prove unknown row extensions remain available, and verify
the capture bytes do not change. Build and install the wheel outside the
checkout, run the installed CLI and stdio audit, and require hosted CI on the
final release-record commit before tagging.

No Glama score change or stable-release acceptance is part of this candidate.

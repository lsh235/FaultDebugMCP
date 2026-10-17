# Bounded raw thread history candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.4`.
Baseline: `v2.0.0-alpha.3`.

## Decision

**YES — add opt-in bounds for outer thread pages and nested raw events.**
`get_thread_trace` currently pages at most 200 thread rows but returns every
retained event in each row. Existing project evidence shows that high-cardinality
threads are plausible: the v1.1 direct trace benchmark recorded 3,040 events in
one thread, although it did not save an artifact or measure an MCP response.
This is sufficient to justify a bounded synthetic MCP acceptance fixture, not a
claim about real-world MCP payloads.

## Version classification

Under [`versioning-policy.md`](versioning-policy.md), this is a **MINOR-class**
addition after a stable release. Both new inputs are optional, and omitting them
preserves the old text response. Changing `page_size` from literal 200 to the
1–200 range keeps 200 for old requests; updated clients opt into other values.
An opt-in `faultdebug_view.events_omitted_from_view` row extension keeps the
capture's original row shape otherwise intact. The old thread-row output schema
allows additional properties, so clients validating against that schema can
accept the annotation. If a capture already uses the reserved `faultdebug_view`
key, the opt-in call fails closed rather than shadowing producer evidence.
Exact tools/list snapshot clients still need to refresh metadata when upgrading.

The current stable v2.0.0 release has not shipped. This feature remains in the
existing MAJOR target as Python `2.0.0a4` / Git tag `v2.0.0-alpha.4`; alpha4 is
an iteration of the v2.0.0 target, not a stable minor release. Stable v2
acceptance remains separate and NO-GO.

## Contract and compatibility matrix

| Consumer case | Expected behavior | Check |
| --- | --- | --- |
| Existing call omits both options | 200 outer rows maximum, all retained nested events, unchanged text fields and raw row extensions. | Compare default output against explicit `page_size=200, max_events_per_thread=null`; compare rows and source digest. |
| Updated client supplies only `page_size` | Thread rows are bounded; each row still contains its complete raw event list. | Test 1, intermediate, and 200, including empty/exhausted pages and full page concatenation. |
| Updated client supplies `max_events_per_thread=N` | Each available event list returns the last N retained rows in original order; one omission count per returned item preserves exact alignment. | Test N=1, 80, and 500, short/empty/large histories, event order, and count metadata. |
| Capture lacks an event list or has a sparse/null list | Do not infer an omission count or capture loss. Preserve event-key presence; report null for unavailable lists and zero for empty lists in the aligned array. | Test absent, null, and empty `events` separately. |
| Raw thread row has a `faultdebug_view` extension | Preserve it in default output; fail an opted-in bounded call rather than overwrite producer evidence. | Assert both behaviors and unchanged source bytes. |
| Client validates against its old output schema | The old thread-row schema allows the opt-in `faultdebug_view` extension; exact tools/list snapshots still change and need refresh. | Validate default and opt-in structured/text results; document the metadata refresh. |

The handler must leave producer `event_count`, `dropped_count`, retention
accounting, event values, and the on-disk capture unchanged. The view marker is
not a synonym for capture loss. The selected tail is still a raw observation
slice, not a reconstructed fault-flow verdict.

## Alternatives and scope

- **NO CHANGE:** keeps complete raw histories and all current schemas; large
  nested lists can exceed a consumer's response/context budget.
- **YES, optional row and event bounds:** smallest stateless control surface
  that bounds both dimensions on this tool. Defaults preserve complete output;
  the omission count makes opt-in shaping visible. This is selected.
- **Event cursors or a new tool:** supports arbitrary ranges but requires stable
  generation identity and continuation rules, including for sparse legacy JSON.
  Current source evidence does not justify that larger protocol.
- **Use `get_fault_flow`:** provides `max_events`, but only for its derived
  pre-crash execution projection; it is not raw event history. Keep it as a
  complementary tool.

The change adds two input parameters and one opt-in row extension under the
existing open thread-row output schema.
The catalogs stay 27/15 tools and move to 88 full / 45 focused parameters. It
reduces returned event rows and serialized response size only when opted into;
it does not reduce full artifact decoding or establish a universal byte cap.

## Acceptance

Proceed only if real stdio tests verify the schema, defaults, strict integer
bounds, event order and counts, sparse inputs, page stitching, explicit
view-omission semantics, structured/text parity, response-size reduction for a
large nested fixture, and unchanged source bytes. Stable v2 remains blocked on
its independent release gates and audit. Glama TDQS impact remains
**NOT VERIFIED** until the exact candidate is externally rescanned.

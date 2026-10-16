# HTTP trace context adapter

`faultdebug.http_context` transports the W3C `traceparent` **version 00** field.
It keeps both 64-bit halves of the 128-bit trace ID. It is a small context
adapter, with no tracing SDK, sampler, automatic instrumentation, `tracestate`
processing, or support for later `traceparent` versions.

```python
from faultdebug.http_context import (
    extract_traceparent, new_traceparent, child_traceparent,
)

# headers may be a string-keyed mapping or http.client.HTTPMessage.
incoming = extract_traceparent(headers)
current = incoming if incoming is not None else new_traceparent()
outgoing = child_traceparent(current)
request_headers = {"traceparent": outgoing.to_header()}
```

`TraceParent(trace_id_hi, trace_id_lo, parent_id, trace_flags)` is immutable.
Its first three fields require integers in `0..2**64-1`; `trace_flags` requires
an integer in `0..255`. Booleans, strings, floats, negative numbers, overflow,
an all-zero trace ID, and a zero parent ID are rejected. Either individual
trace half may be zero. `parent_id` is the 64-bit sender span ID carried in the
HTTP field; it is not automatically a FaultDebugMCP native `rpc_id`.

`parse_traceparent(value)` accepts exactly the 55-character lowercase ASCII
version 00 wire form. It rejects surrounding whitespace, uppercase hex,
missing separators, extra fields, invalid hex, zero IDs, and unsupported
versions. `extract_traceparent(headers)` matches the field name without case,
returns `None` only when the field is absent, and rejects duplicate fields,
case-variant duplicates, comma-joined values, or an invalid present value.
An `HTTPMessage` is read with `get_all()` so repeated fields are not lost.
Invalid value types raise `TypeError`; malformed values, duplicates, invalid
integer ranges, and unsupported versions raise `ValueError`. Callers choose
their response to those errors; the adapter does not silently replace an
invalid incoming field with a new trace. This strict rejection policy is the
adapter's boundary contract, rather than a claim of a complete W3C SDK.

`new_traceparent()` uses cryptographic randomness to create a nonzero 128-bit
trace ID and nonzero 64-bit span ID, with flags `00`.
`parse_traceparent()` retains the raw incoming flags byte on `trace_flags` for
evidence. For outgoing version 00 fields, `to_header()` clears reserved bits
and emits only the sampled bit (`trace_flags & 0x01`), without changing the
stored input. Thus incoming `fe` serializes as `00`, and `ff` as `01`.
`child_traceparent(parent)` preserves the full trace ID and sampled bit,
clears reserved flag bits in the new context, and generates a nonzero span ID
distinct from the supplied `parent_id`. Its input object remains unchanged.
The sampled bit is a propagation hint. Flags `00` remain valid and do not
cause the adapter to drop context; no flag establishes that an event was
recorded. Reserved incoming bits remain inspectable as input evidence; they
are not forwarded in an outgoing v00 field.

HTTP context is untrusted correlation input. Possession of a matching trace
or span ID does not prove a call occurred, identify the caller, or establish
a native cross-process edge. The adapter does not create native RPC events.
Applications must supply their explicit mapping between HTTP context,
native RPC IDs, and instrumentation. The shop lab documents and checks that
mapping separately; receiving `traceparent` alone does not supply the lab's
shared RPC identity. The child helper stores only the outgoing field, so an
application that needs the prior parent ID must preserve it separately.

Contract checks:

```sh
python test/http_context_contract.py
```

The parser format and ID constraints follow the
[W3C Trace Context specification](https://www.w3.org/TR/trace-context/).

## Shopping fixture mapping

`test/shop/service.py` accepts no-header local requests and legacy low64
`X-Shop-Trace` requests. A present `traceparent` must be valid; a simultaneous
legacy trace must match the full trace (legacy high64 is zero). Duplicate
context or numeric mapping headers fail the fixture request with HTTP 400.
Legacy support is inbound: outbound calls now require peers that accept W3C
context; this alpha does not provide mixed-version outbound negotiation.

Each outbound call records a fresh client `span_id` and sends it as the
traceparent parent-id. The receiving service records a different server
`span_id`, with `parent_span_id` set to that client span. `X-Shop-Rpc` carries
the separate numeric RPC identity used by both native endpoints;
`X-Shop-Parent` carries the fixture's parent numeric RPC. These identifier
namespaces may contain equal numbers without becoming the same identity.
Application logs keep `trace_id_hi`, legacy low64 `trace_id`, `span_id`,
`parent_span_id` and `trace_flags`. Native numeric RPC records retain high64
and low64; their ABI does not gain W3C span fields. Every transport call gets
a fresh numeric RPC ID, but there is no general retry/attempt pairing here.
Headers and application logs are untrusted self-reports, with native
corroboration handled separately by the existing report contract.

`X-Shop-Timeout-Ms` carries a relative budget of 1..5000ms (default 5000 for
inbound requests). The receiver computes its own monotonic deadline.
Legacy absolute `X-Shop-Deadline` values are ignored and recorded as ignored;
they are never subtracted from a receiver's clock. This is a fresh local
processing budget, not a synchronized end-to-end deadline or transit-time
measurement. The HTTP caller separately enforces its socket timeout.

## Optional clock and generation provenance

`faultdebug.clock.local_clock_identity()` samples the calling process's Linux
boot UUID and time-namespace identity. A derived clock-domain ID requires
both; unavailable sources remain `None` with status `unknown` and limitations.
Namespace identity lifetime/reuse is not persistently verified. The metadata
is provenance, not clock synchronization, authenticity, or permission to infer
a global event order.

`ProcessIdentity.process_record(clock=metadata)` opts into attaching sampled
metadata. Launchers/collectors never automatically assign their own namespace
to a different PID. The shop logs its own local clock and canonical validated
`FAULTDEBUG_PROCESS_GENERATION`. This alpha does not add these clock fields to
the native ABI, record Pod/container lifecycle identity, or compare peer clocks.

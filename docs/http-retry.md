# HTTP attempts and local durable inventory retries

The alpha2 shop fixture adds bounded attempt metadata and an opt-in SQLite
inventory ledger. These are experimental application contracts. The existing
native RPC ABI, FDAR format, report schema and required MCP tools are unchanged.

## Explicit HTTP attempt metadata

`X-Shop-Operation` and `X-Shop-Attempt` must appear together, once each. The
operation is 1..128 printable ASCII characters excluding whitespace and commas.
The attempt is exactly `1`, `2`, or `3` after the HTTP parser's normal handling
of leading header whitespace. Duplicate, partial, comma-joined and malformed
values return HTTP 400 before native RPC recording. Legacy callers can omit
both; their attempt identity remains unknown.

`call(peer, path, body, parent, timeout=3, *, operation_id=None, attempt=1)`
performs **one** HTTP request. Callers explicitly issue another call to retry;
there is no automatic retry loop. With no operation ID, the fixture creates a
stable operation from the route and order/request identity. Callers controlling
retry semantics should supply the same operation ID and payload on each attempt.
Each call creates fresh client/server W3C spans and a fresh numeric RPC ID while
preserving the full 128-bit trace ID. Incoming event rows label attempt metadata
`peer_self_reported`, with evidence class `application_self_report`. These values
are unauthenticated application assertions: they neither enforce monotonic
attempt order nor establish native causal edges by themselves. Shared traces
alone are insufficient to join RPC endpoints.

The fixture allocates RPC IDs as
`(process_generation << 32) | (ordinal << 24) | counter`. Configure unique
`SHOP_ORDINAL` values in 1..255 among peers and increment process generation on
every restart. The 24-bit process-local counter fails before wrapping. Reusing
the same ordinal and generation for multiple process instances is unsupported.

`SHOP_HOST` and `SHOP_PORT` override the existing `0.0.0.0:8080` bind. The
`retry-client` role proxies `/reserve` and `/release` directly to inventory,
preserving the explicitly supplied operation and attempt. It is an isolated
acceptance fixture, not a complete checkout workflow.

## Durable local transaction scope

Set `SHOP_LEDGER_PATH` to a database file in an existing trusted local directory
to opt inventory into the reusable `faultdebug.retry_ledger.RetryLedger` API.
For another local application, create its business tables in the same database
and pass a callback that writes only through the supplied connection:

```python
from faultdebug.retry_ledger import RetryLedger

ledger = RetryLedger("application.sqlite3")

def reserve(connection):
    connection.execute("UPDATE inventory SET stock = stock - 1 WHERE sku = ?", ("FD-01",))
    return {"reserved": 1}

result = ledger.apply_once("reserve:order-42", {"sku": "FD-01", "quantity": 1}, reserve)
print(result.value, result.replayed)
```

The caller owns business validation such as stock availability. Callbacks must
not commit, close the connection, or perform effects outside that connection.
Payloads and results are bounded JSON objects; see the module docstring for exact
limits. The operation ID is local to this database, so namespace unrelated uses.

Without it, the original in-memory shop behavior remains available. The ledger
commits the business mutation and JSON result using the **same** SQLite
transaction. The default capacity is 10,000 operations, with no automatic
eviction; existing results remain replayable after capacity is reached. Busy or
capacity failures return HTTP 503. A receiver-local expired deadline returns
HTTP 504 and prevents committing a new mutation. Request timeout budgets remain
relative milliseconds, never another process's absolute monotonic timestamp.

The inventory operation key includes the action and logical operation ID. The
fingerprint includes action, order ID and quantity; scenario fault settings and
attempt number do not change the business payload. The same key and payload
returns its committed result with `replayed: true`, including after a process
restart with the same database. Reusing a key with different order or quantity
returns HTTP 409. A different key cannot change an existing order's quantity.
Reservation rows enforce one stock deduction per order.

Release persists a `released` tombstone. Repeating release cannot increment
stock again. A release arriving before the first reserve also persists
cancellation, preventing a delayed reserve from recreating that order. Replaying
an earlier successful reserve returns its **original** committed result, but does
not recreate a reservation released later. A fresh reserve operation for a
released order returns HTTP 409; use a new order identity for a new lifecycle.

`GET /state` exposes committed stock, active `reservations`,
`reservation_history`, `mutation_counts` and `ledger_operations`. Mutation counts
come from rows written in the business transaction, not from HTTP response
counts. A release tombstone is a release-state mutation even when no stock was
returned. This state endpoint is fixture instrumentation.

The `inventory_response_loss` scenario requires durable mode. After a successful
first reserve transaction commits, the fixture deliberately closes the HTTP
connection before sending a response. A retry of that operation returns the
stored result; replay does not trigger another disconnect or stock deduction.
This demonstrates a response-loss boundary. It does not simulate a power loss,
and does not make payments, network calls, filesystem writes or other databases
exactly once. Filesystem and hardware durability remain deployment assumptions.

## Verification

```sh
.venv/bin/python test/shop_http_context.py
.venv/bin/python test/shop_http_context.py \
  --boundary build-alpha2/test/shop/libshop_boundary.so \
  --runtime-dir build-alpha2
.venv/bin/python test/shop_http_retry.py --help
```

The HTTP context suite verifies malformed/partial attempt headers, fresh spans
and RPC IDs, counter bounds, concurrent duplicate operations, response loss,
database reopen, conflicting payloads, expiration before mutation, and release
tombstones. Its default mode labels the recorder as a fake; its native mode
checks collected RPC events in two process generations. Separate-process caller
and inventory restart acceptance is implemented in `test/shop_http_retry.py`.
The alpha tests do not replace the complete release, scale, lifecycle or soak
gates required before stable promotion.

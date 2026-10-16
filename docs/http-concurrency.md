# Bounded checkout concurrency and local TCP fault fixtures

The alpha3 package adds process-local keyed locking alongside the alpha2
[transactional retry ledger](http-retry.md). Keyed locks coordinate threads in
one Python process; the SQLite ledger separately coordinates local database
mutations across connections and process restarts. Neither provides a distributed
checkout transaction or exactly-once external payment/delivery.

`faultdebug.keyed_lock.KeyedLockPool(max_keys=1024).hold(key, timeout=...)` is a
context manager. It serializes holders of the same key while allowing other keys
to proceed. Active keys include waiters. Bounded capacity and waiting failures
are explicit; reference cleanup after release/error/timeout prevents retaining
an unbounded history of order IDs.

The shop uses one checkout key per order. The shared state/ID lock is held only
for short local updates, and is released during remote HTTP calls. An expired
receiver-local lock wait returns504 before downstream work; capacity failures
return503. A completed order replay with a different quantity returns409. The
fixture's `SHOP_CHECKOUT_LOCK_MODE=global` mode uses a separate checkout lock for
the serialized comparison; the default mode is `keyed`.

Application `checkout_begin`/`checkout_end` rows mark protected checkout intervals.
Peak overlap is computed within one process's ordered event log; it is not a
cross-host timestamp comparison. Same-order duplicates still serialize and
reuse a completed in-memory result. Completed checkout state is not durable
across checkout restarts. Inventory replay retains the narrower SQLite guarantee.

`test/shop/fault_proxy.py` supplies a local HTTP/TCP fixture with pass,
reset-before-forward, drop-after-complete-response, and before/after response
delay modes. It records its own observations separately from native/application
captures. An injected-mode setting does not prove a request reached a receiver,
committed a mutation or caused a native failure. Acceptance checks HTTP symptoms,
native endpoints and committed SQLite state independently.

This is a bounded local HTTP/1 fixture with finite bodies/workers/timeouts. It is
not a general HTTP gateway, TLS proxy, tracing provider or production chaos
controller. Chunked/streaming support and multi-host/container lifecycle
provenance remain outside this API.

Contract and native acceptance commands:

```sh
.venv/bin/python test/keyed_lock_contract.py
.venv/bin/python test/shop_checkout_contract.py
.venv/bin/python test/http_fault_proxy_contract.py
.venv/bin/python test/shop_concurrency.py \
  --boundary build-alpha3/test/shop/libshop_boundary.so --runtime-dir build-alpha3 \
  --output build-alpha3/shop-concurrency.json
```

Choose a fresh output path to retain evidence. See the
[alpha3 verification record](releases/v1.3.0-alpha.3.md) for measured workloads,
environment, exact completed checks and remaining release gates.

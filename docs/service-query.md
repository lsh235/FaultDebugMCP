# Read-only service evidence queries

Use `service-report` to write the full offline HTML/JSON/Markdown report. Use
`service-query` or MCP `get_service_flow` to inspect frozen evidence without
creating output files. Both query entry points share `query_service_flow`.

```sh
faultdebug service-query /path/to/frozen-evidence
faultdebug service-query /path/to/frozen-evidence --section calls --page-size 100
faultdebug service-query /path/to/frozen-evidence --section events --page 1 \
  --page-size 100 --snapshot-id <snapshot_id_from_first_query>
```

MCP arguments use an evidence directory relative to the server's `--root`:

```json
{"evidence":"incident-001","section":"calls","page":0,"page_size":100}
```

The default `summary` contains `counts`, `session_id`, `snapshot_id`, and
`limitations`, not full event arrays. Other sections are `services`, `calls`,
`causes`, `events`, `native_relations`, `unresolved`, and `evidence_files`.
Each returns `items`, `total`, `returned`, `page`, `page_size`, and `next_page`.
A null `next_page` ends traversal. Pages beyond the collection are empty;
negative pages and summary pages other than zero are errors.

Use the first response's `snapshot_id` for every later page. It fingerprints
sorted relative evidence paths, bytes, kinds, SHA-256 hashes, and query contract
version. Changing, adding or removing evidence rejects the old ID. Moving an
unchanged directory preserves it. Each request rereads and revalidates inputs:
this is not a cache, live atomic filesystem snapshot, or authenticity proof.
Keep input directories frozen while querying. Source bundle enrichment is not
part of this API; use existing verified source tools for source citations.

## Budgets and failures

| Resource | Limit |
| --- | --- |
| Native captures | 1–64 |
| Evidence files (captures and events.jsonl) | 256 |
| Scanned directory entries, including irrelevant files | 4096 |
| Each evidence file | 16 MiB |
| Combined evidence bytes | 64 MiB |
| Application JSONL lines, including malformed/unmatched lines | 100,000 |
| Page size | 1–200, default 100 |
| Serialized query result | 1 MiB |

Budget overruns are explicit errors, never silent truncation. Request a smaller
page if the response is too large. If a single row exceeds the response budget,
use the offline report or inspect the original evidence. A larger page size
does not bypass the input budget. Input files must be regular files; symlinks
inside evidence directories are rejected and FIFO reads cannot block the query.
Bundle validation for `service-report --bundle` is a separate operation outside
these native/application input budgets. The local supported platform remains
Ubuntu 24.04 x86_64 and Python 3.12; no new remote transport is introduced.

## Identity and interpretation

Application schema 1 retains `trace_id` as the low 64 bits; optional
`trace_id_hi` supplies the upper 64 bits and defaults to zero. Identity fields,
trace IDs, RPC IDs and timestamps must have the documented integer/string types;
booleans are not numeric IDs. The join key includes session, process ID, process
generation, both trace halves, and RPC ID. Reusing a PID, a role name or a low
trace ID cannot corroborate another process generation's evidence.

Duplicate/missing ends remain unresolved. A valid native/application status
match does not validate the application's explanation. Native observations,
application self-reports and unresolved evidence remain distinct. Durations use
same-process begin/end timestamps only; reversed timestamps produce an explicit
gap instead of a negative duration. The report does not establish a global clock
or causal ordering across processes, and does not implement general retry/attempt
matching or W3C header propagation.

## Verification

```sh
python test/service_identity_contract.py
python test/service_query_contract.py
python test/service_report_test.py
python test/mcp_tool_metadata.py --output build/mcp-definition-audit.json
```

The query tests include real MCP stdio calls, CLI parity, before/after file hashes,
page union, content changes, root errors, budget failures, and FIFO/symlink cases.
The identity tests use independently declared expected trace/process/status
values. These synthetic evidence checks do not replace native capture, Clang 18,
gRPC, Docker, external corpus, or release-soak acceptance.

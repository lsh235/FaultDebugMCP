# Alpha34 review: typed service-flow output

Decision: **YES**, implement the bounded output-contract change.

The full-profile cross-service query is a useful, stable user path and currently
has no output schema despite having a common versioned summary/page envelope.
Typing that envelope improves the client contract and addresses one explicit
TDQS input. Keep section rows open because their shape contains captured native
relations and application self-reports with extensible fields. The schema must
not turn self-reported causes into verified facts or make the snapshot ID sound
atomic.

Acceptance requires both summary and page responses to validate through real
stdio MCP, all seven sections to preserve row data, CLI/MCP output parity, stale
snapshot and invalid-path errors to remain unchanged, and evidence files to be
unchanged. The schema is additive; no score increase or stable-release
acceptance is inferred from it. Glama rescanning and per-dimension score remain
external, unverified gates.

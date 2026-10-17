# Fault-flow output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.25`.

## Baseline and opportunity

`get_fault_flow` is in the full and 15-tool focused profiles. It builds the
read-only execution view used to connect captured thread events, crash context,
observed nesting, gaps, address-resolution evidence and verified source
excerpts. The response has a stable version-1 envelope, but `tools/list`
currently publishes no output schema for it. The concise description names the
main sections; a client still has to infer their nested event, edge, crash and
source shapes.

The implementation in `faultdebug/fault_report.py` defines the report envelope
and the event/crash/edge/source fields. Some nested values are intentionally
producer- or resolution-dependent: target metadata, snapshot details, address
resolution evidence, diagnostic evidence and the exact gap row. Those can stay
open objects while the stable surrounding fields receive documented types.
Capture status, per-thread truncation, post-crash omission and gap reasons must
remain distinct; view limits are not evidence loss, and verified source text
must remain distinct from unresolved symbol candidates.

The [official TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
passes output schemas to its evaluator and says contextual completeness depends
on what the schema documents, not on schema presence alone. Contextual
completeness is only one weighted dimension, so a typed result may improve
definition quality but cannot guarantee a public score increase.

Sources: [focused MCP registration and current tool description](../faultdebug/mcp_server.py),
[report construction and stable envelope](../faultdebug/fault_report.py),
[existing report behavior tests](../test/fault_report_test.py), and
[TDQS rubric](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score).

## Candidate boundary

Add a documented typed output for `get_fault_flow` in both profiles. Type the
version/language envelope, completeness state, threads and event nodes,
crashes, graph edges, source excerpts, gaps, diagnostics and optional verified
bundle marker. Keep target and snapshot metadata, resolver evidence and
diagnostic evidence open where producers already vary. Make future/legacy
capture fields optional where the existing artifact reader permits them.

Preserve the existing text JSON, report generation, bounds, source lookup,
language selection, safety annotation, tool count and parameter count. The
schema must not classify nesting as root cause, turn unresolved symbols into
verified source, or conflate omitted display events with captured loss.

## Bounded acceptance

1. Real `tools/list` exposes the documented output schema for `get_fault_flow`
   in full and focused profiles; the 27/15 tool catalogs and 84/44 parameter
   counts do not change.
2. Real stdio validates an empty trace, a populated thread/crash report, loss
   and truncation diagnostics, and the no-bundle path. Tests verify stable text
   fields remain equivalent to structured content, allowing only explicitly
   documented null defaults.
3. A model-level fixture validates a verified source entry and resolution
   evidence, while existing fault-report tests continue to enforce provenance,
   thread-generation, edge and gap behavior.
4. Capture/bundle inputs remain byte-for-byte unchanged; invalid paths and
   bundles retain their current MCP error behavior; full/focused registration
   and annotations remain unchanged.
5. Run report and MCP regressions, Python distribution build, installed-wheel
   MCP execution outside the checkout, and hosted CI. Glama pin/deployment and
   a fresh official TDQS score remain external evidence.

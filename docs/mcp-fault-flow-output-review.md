# Fault-flow output-schema review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.25`.

## Decision: YES

Publish a typed output contract for `get_fault_flow` in the full and focused
MCP profiles.

This is the central single-capture fault investigation result and is already
in the focused catalog. Its report has a documented stable envelope and
well-defined thread, event, crash, edge and source rows, but no machine-readable
output contract. Typing those fields gives clients the evidence boundary as
data, including whether the capture is limited, which events were omitted from
the view, what gaps were recorded, and whether source text was verified.

The schema must leave genuinely variable target/snapshot/resolution evidence
open and keep optional legacy fields tolerant. That protects existing capture
compatibility while documenting the stable report. The implementation changes
no trace collection, report algorithm, causal interpretation or tool inventory.

The TDQS rubric evaluates the substance of an output schema under contextual
completeness, while schema presence alone earns nothing. This is a focused
quality increment for a complex workflow result, not a forecast of a numeric
Glama score change. Only a fresh official evaluation can establish that result.

Acceptance follows the five bounded conditions in
[research](mcp-fault-flow-output-research.md), especially real full/focused
stdio, loss/truncation boundaries, source-verification shape and installed
package execution.

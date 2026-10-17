# Source-evidence output-schema review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.23`.

## Decision: YES

Proceed with a typed structured result for `get_source_evidence`.

The tool is already exposed in Glama's recommended focused profile and returns
a stable, useful success envelope with auditable citation fields. A typed
contract can improve machine consumption and definition completeness in the
profile the administrator configuration actually selects. This is a better
score-oriented target than adding another schema to a full-only tool. It must
retain the compatibility-only flat fields for a single citation, represent
partial and unresolved evidence accurately, and distinguish its payload error
from MCP tool errors.

The review rejects any score forecast. Glama's public snapshot is stale and
there is no authenticated access to its build settings or scan control. The
implementation should update the repository's recommended focused pin only;
it must not claim or imply that the external Glama service has been deployed or
re-scored.

Acceptance is the five bounded conditions in
[research](mcp-source-evidence-output-research.md), especially real stdio in
both profiles, one/multiple/zero citations, unresolved rows, source immutability,
unchanged tool inventory, installed-package execution and hosted CI.

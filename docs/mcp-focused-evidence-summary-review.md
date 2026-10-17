# Focused evidence-summary MCP candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.32`.

## Decision

**YES: add `get_evidence_summary` to the focused profile and publish its typed output schema.**

The earlier full-only output-schema proposal was correctly deferred because it
could not affect the documented focused catalog. This proposal first exposes
the existing low-cost count summary there, so agents can decide whether a raw
capture, RPC history or fault-flow result is needed. It then makes those counts
and limits machine-readable.

## Scope and risk

Add the existing one-capture tool to focused, increasing that profile from
15/44 to 16/45 tools/parameters. Keep the full profile at 27/84. Publish the
fixed six-field response envelope; leave unresolved diagnostics open while
requiring their stable `reason`. Clarify that `status=complete` means no
unresolved diagnostic was emitted, not application success or capture
completeness. Update focused server instructions and `open_fault` guidance so
the count-only tool is easy to distinguish from detailed evidence views.

The extra catalog entry can affect TDQS sibling selection and coherence in
either direction. Its input is one required capture name and its output is a
bounded count summary, but only Glama's evaluation can determine the score.
Do not claim an increase from local schema tests.

Do not change decoding, counts, text response, capture handling, tool
annotations, full-profile catalog or evidence state. Expected output-schema
counts become 16 full and 15 focused.

## Bounded acceptance

1. Both profiles publish the same typed output schema and validate complete
   and limited results over real stdio.
2. The focused list exposes the new tool with its existing title/annotations;
   descriptions refer to alternatives that are available in the profile.
3. Missing RPC data remains unresolved; invalid paths remain MCP tool errors;
   evidence files stay unchanged.
4. Fresh wheel/sdist, installed-wheel full/focused stdio and CLI smoke pass;
   hosted CI passes before tagging.
5. External Glama pin, rescan and numeric score remain separately verified.
   Stable acceptance remains **NO-GO**.

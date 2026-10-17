# Open-fault output schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.33`.

## Decision

**YES: type the stable open-fault response sections and publish an extensible
output schema in both MCP profiles.**

`open_fault` is the only tool without an output schema in Glama's documented
focused catalog. It is the normal first detailed read after discovery and is
distinct from the count-only summary and specialized event/RPC/fault-flow
views. A typed, useful schema can let clients inspect the raw capture without
making up field shapes. The raw capture already contains stable native
sections, and existing output models demonstrate how to type known rows while
retaining future fields.

## Scope and risk

Declare optional native header/module/crash/capture-integrity fields and reuse
the open thread/event row model. Keep producer-defined top-level and row
extensions, RPC extension payloads, session/context metadata and launcher
wrappers open where their producer contracts vary. Preserve sparse JSON
captures and the optional verified bundle marker. The schema must not turn
missing fields into fabricated values, collapse unknown extensions, change
decoder output, or imply that a capture is complete, a target succeeded, or a
root cause was established.

Keep the input contract, tool inventory, annotations, text JSON, capture bytes
and evidence handling unchanged. The focused catalog stays 16/45 and rises
from 15 to 16 structured outputs; full stays 27/84 and rises from 16 to 17.
The candidate can improve documented-field coverage, but TDQS also grades
purpose, usage guidance, behavior, semantics and concision. Coherence and the
numeric score remain subject to Glama's independent evaluation.

## Bounded acceptance

1. Full and focused real stdio expose equal schemas and validate complete,
   sparse and bundle-enriched results.
2. Unknown producer keys remain present in structured output and text; known
   capture fields have useful descriptions and correct optionality.
3. Invalid paths still fail as tool errors; no artifact or bundle changes.
4. Build/install audits and all hosted jobs pass before alpha tagging.
5. Report no score change without Glama scan evidence; stable remains
   **NO-GO**.

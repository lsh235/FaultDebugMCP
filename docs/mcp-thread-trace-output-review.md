# Thread-trace MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.30`.

## Decision

**YES: implement the bounded `get_thread_trace` output schema.**

The tool is part of the focused first-line catalog and returns a compact fixed
page envelope over decoded thread records. Structured rows can expose the
native event sequence, monotonic timestamp, function/callsite addresses and
generation without conflating these raw records with symbolized calls or a
reconstructed fault flow.

## Scope and risk

Type only the stable page envelope and documented thread/event fields. Keep
thread and event models open to producer extensions because JSON artifacts may
carry additional fields. Model `retention` as optional and preserve the existing
null-versus-omitted distinction between structured and text results. Do not
claim that an event list proves completeness; event loss and retired history
remain separate capture fields.

The handler, decoder, `tid` matching across generations, event order,
pagination, required inputs, MCP errors, text JSON, capture evidence and tool
membership must remain unchanged. Add fixture fields that prove extension
survival and two generations sharing one OS thread ID.

## Bounded acceptance

1. Both profiles publish the same schema while retaining 27/84 full and 15/44
   focused tools/parameters.
2. Real stdio validates non-empty rows with and without `retention`, events,
   extension keys, same-OS-ID generations, `tid` filtering, unmatched ID and
   exhausted page. All existing text fields remain equal.
3. Invalid capture paths and negative pages remain tool errors; artifact bytes
   remain unchanged.
4. Wheel/sdist and installed-wheel full/focused stdio audit pass; hosted CI
   passes on the final release-record commit before tagging.
5. No numeric Glama change is claimed without an official rescan.

This review approves only the alpha30 candidate. Stable acceptance, external
deployment and the full release gate remain separate decisions.

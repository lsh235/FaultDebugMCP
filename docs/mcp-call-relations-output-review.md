# Static call-relations MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.29`.

## Decision

**YES: implement the bounded `get_call_relations` output schema.**

This tool is present in the focused catalog and supports the verified-source
workflow after `resolve_addresses` or an indexed function ID. A typed envelope
will expose direction, function identity, static evidence class, bundle path
and the relation collection through structured MCP content. Describing the
static-only evidence boundary is especially useful because these rows are
hypotheses, not runtime call observations.

## Scope and risk

Type only the stable top-level envelope and known relation keys. Keep relation
rows open to unknown fields and values because bundle index hashes are verified
but `index_rows` does not validate a closed edge schema. Do not impose a
discriminated union or narrow unknown edge kinds. Add a fixture extension field
and prove the structured output preserves it.

The handler, compiler index, bundle hash verification, required inputs,
read-only behavior, errors, text JSON and evidence meaning must remain
unchanged. Missing function IDs and invalid bundles remain MCP tool errors.

## Bounded acceptance

1. Both profiles publish the same output schema while retaining 27/84 full
   and 15/44 focused tools/parameters.
2. Real stdio validates outbound direct and unresolved rows, inbound caller
   rows, and an empty relation result in both profiles. The extension field
   survives, and every existing text value is preserved.
3. Missing functions and malformed bundles remain tool errors; evidence and
   bundle files remain unchanged.
4. Wheel/sdist and an installed-wheel stdio audit pass; hosted CI passes on
   the final release-record commit before tagging.
5. No numeric Glama change is claimed without a rescan.

This review approves only the alpha29 candidate. It does not approve stable
release, external deployment or completion of the full release gate.

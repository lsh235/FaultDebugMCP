# Incident-slice MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.31`.

## Decision

**YES: publish a typed success/error output schema for `get_incident_slice`.**

This is the focused workflow's central stored-incident evidence view. Its
stable response envelope and SQL-backed identity rows can become directly
consumable as structured MCP output, while variable producer payloads remain
open. The schema can make its pagination, event cap and error branch explicit
without changing the evidence query.

## Scope and risk

Model the fixed `schema=2` success/error envelope, the incident/artifact/process
and source-reference database rows, observation/derivation sections,
pagination, event count and truncation fields. `observed_event_total` is
conditional on a page selecting artifacts; preserve that omission instead of
normalizing text JSON. Keep SQL-backed rows open to store extensions and use
producer-defined JSON values for event, relation and diagnostic collections.

Retain the existing `INCIDENT_QUERY_ERROR` payload union. A stored source
reference remains unverified until `get_source_evidence` checks it against a
bundle. Do not change read-only behavior, page selection, evidence categories,
text output or the 1,000 observed-event cap. Shorten the handler description
only where the new schema makes a repeated field inventory redundant; preserve
the when-to-use guidance, sibling distinctions, evidence boundary and
completeness warning required for correct selection.

## Bounded acceptance

1. Both profiles publish equivalent success/error schemas while retaining
   27/84 full and 15/44 focused tools/parameters; schema counts become 15/14.
2. Real stdio validates populated and empty results, pages beyond the artifact
   total, event truncation, missing incident and invalid/unavailable store
   branches. It preserves variable JSON values and SQL-row extensions.
3. Text JSON remains unchanged, including omission of `observed_event_total`
   for an empty selected page. Error codes and evidence bytes remain unchanged.
4. Fresh sdist/wheel, installed-wheel full/focused stdio audit and hosted CI
   pass on the final release-record commit before tagging.
5. Glama administrator pin and rescan remain separately verified; no score
   increase is inferred from local schema checks. Stable acceptance stays
   **NO-GO**.

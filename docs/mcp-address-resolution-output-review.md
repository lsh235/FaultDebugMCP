# Address resolution MCP output-schema candidate review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.28`.

## Decision

**YES: implement the bounded `resolve_addresses` output schema.**

Unlike the previously rejected full-only candidate, `resolve_addresses` is
present in the focused 15-tool profile. The proposed schema therefore updates
the tool definition in the documented Glama configuration while giving MCP
clients a typed way to consume address-to-function resolution results.

The reusable `FaultFlowResolution` model already describes both successful
and unresolved resolution fields, keeps source/static data separate, and
allows additional resolution metadata. Wrapping it in an `items` result avoids
copying the report's resolution contract into another schema.

## Scope and risk

Limit the implementation to the output model/return annotation, real stdio
contract tests, alpha28 version and release documentation, and the repository
Glama pin example. The resolver itself does not change. Keep input validation,
Build-ID checks, local-only lookup, error behavior, text result, annotations
and tool/parameter inventory intact.

The main risk is return-model validation rejecting an existing conditional
resolution row. Every resolver result is built from a base row containing
`address`, `kind`, and `resolved`; the reused model permits source-specific
extra fields. Real stdio tests must validate empty and unresolved rows in both
profiles and retain optional fields without rewriting text JSON.

## Bounded acceptance

1. Both profiles publish the same non-empty `outputSchema`; catalog counts
   remain 27/84 full and 15/44 focused.
2. Real full/focused stdio validates empty and unresolved-address responses
   and compares the structured values with existing text fields.
3. Existing invalid inputs and path checks still return tool errors; evidence
   inputs remain unchanged.
4. Wheel/sdist and an installed-wheel check outside the checkout pass; hosted
   CI passes on the release-record commit before tag publication.
5. The release record makes no numeric-score claim without an official
   Glama rescan.

This review approves only this alpha28 candidate. It does not approve stable
release, external deployment, or completion of the full release gate.

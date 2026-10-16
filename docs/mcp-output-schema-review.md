# MCP structured-output feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.18` candidate.

## Decision

**YES — upgrade within MCP SDK v1 and publish typed outputs for four first-line
inspection tools.** `get_capabilities`, `check_store`, `discover_artifacts`,
and `discover_bundles` have bounded, versioned outer result contracts. The
structured channel makes these results directly consumable by client code while
the existing text content stays available. Other tools retain their current
responses until their varying evidence shapes can be modeled without pretending
that arbitrary JSON is a precise schema.

The SDK update is scoped to `mcp==1.30.0` and Pydantic `>=2.11,<2.14`; the MCP
major version remains below 2. All 27 `full` tools and 15 `focused` tools remain
registered with their existing annotations and input schemas. Four schemas are
present in both profiles.

This is a protocol contract improvement and a rubric-backed Glama opportunity,
not a score prediction. Glama's administrator pin, deployment, re-scan and
official numeric score are independent and remain unverified from this
checkout.

## Acceptance

1. Real stdio `tools/list` publishes non-empty object schemas for exactly the
   four selected tools; all other tool definitions remain available and valid.
2. Real stdio calls produce `structuredContent` that validates against its
   published JSON Schema for successful, empty, invalid-path and rejected-row
   cases. The established text JSON remains parseable.
3. The default `full` profile remains 27 tools/84 described parameters;
   `focused` remains 15/44, with profile capabilities and read-only annotations
   unchanged.
4. The audit proves captures, bundles, databases and legacy indexes remain
   unchanged. Python package build/install, relevant regressions and hosted CI
   pass.
5. Update only the documented Glama source pin. Do not claim that the external
   administrator configuration changed, that Glama deployed/re-scored, or
   that the numeric score improved without direct evidence.

The implementation review found and corrected response-shape gaps during the
real protocol check: the alpha17 profile fields belong in the capabilities
schema, and artifact discovery adds pagination fields after its lower-level
scanner returns. The final audit must run again after both corrections.

See the [research record](mcp-output-schema-research.md). Stable release
acceptance remains **NO-GO**.

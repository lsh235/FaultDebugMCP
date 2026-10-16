# MCP focused-profile feature review

Date: 2026-10-17 (Asia/Seoul). Review target: `v1.3.0-alpha.17` candidate.

## Decision

**YES — add a named `focused` MCP tool profile for a bounded first-line
investigation surface.** Keep `full` as the CLI and library default so existing
clients retain all 27 tools. The profile is an honest product variant, not a
claim that the official score will rise: Glama must rebuild and score the
focused listing independently.

The reason to prioritize this over additional description text is the official
coherence rubric's explicit tool-count dimension. The current catalog has 27
tools; the selected profile has 15, at the upper end of the specification's
typical well-scoped range. The exact score breakdown is not available, so this
addresses a visible rubric dimension without predicting the resulting score.

## Scope and acceptance

1. Add `--tool-profile full|focused`, default `full`, and a matching keyword-only
   `make_server` option. Reject unknown values.
2. Keep all 27 tools registered under `full`. Under `focused`, register only the
   15 names in `docs/mcp-profile-research.md` using the public FastMCP decorator
   path; avoid deleting tools through private manager internals.
3. Filter the capability contract's required/additional/versioned lists to the
   registered tools and identify the active profile. All declared required
   tools must remain present.
4. Exercise both profiles through the direct tool manager and real stdio MCP;
   verify tool counts/names, filtered-call rejection, annotations, capability
   parity and evidence immutability.
5. Update Glama's documented launch command and pin it to the implementation
   SHA. Do not claim external settings changed, a rescan occurred, or the score
   increased without direct evidence.

See the [research record](mcp-profile-research.md). Stable release acceptance
remains NO-GO.

# Focused-profile description review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.26`.

## Decision: YES

Provide profile-aware descriptions for the eight focused tools that currently
name alternatives omitted from the focused catalog.

The concrete defect is selection guidance that cannot be followed in the
selected profile. A focused caller can read that `get_rpc_trace` defers
cross-capture comparison to `get_process_relations`, or that `discover_artifacts`
has an indexed alternative in `query_artifact_index`, but neither named tool is
available there. The focused `check_store` description also named `list_sessions`,
which is not exposed in that profile. Similar cases affect store provenance,
single-capture summaries and unresolved incident queries. The full profile does
expose those alternatives, so a global rewrite would discard useful distinctions
for its callers.

The TDQS rubric explicitly evaluates tool descriptions against the sibling
names in the same server profile. A focused-only description map is a bounded
way to make each instruction actionable while preserving the richer full
catalog guidance. It adds no tools and does not increase the 15-tool focused
catalog. The expected effect is improved definition quality under the rubric;
there is no current Glama per-tool breakdown, so no numeric score gain can be
predicted or claimed.

Approve the candidate with the four acceptance conditions in
[research](mcp-focused-description-research.md), especially real stdio checks
that all named focused alternatives are exposed and all full-profile
descriptions remain unchanged.

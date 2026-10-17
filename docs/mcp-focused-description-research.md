# Focused-profile description research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.26`.

## Baseline and opportunity

The Glama build example selects FaultDebug's 15-tool `focused` profile. The
full profile contains 27 tools. A real full/focused stdio audit on alpha25
reported 100% parameter-description coverage, descriptive titles and 10/9
typed output schemas. The profile already keeps the focused tool count inside
TDQS's stated 3–15 coherence range, so adding more tools is not the target.

Comparing every focused `tools/list` description against the actual focused
catalog found eight descriptions that name alternatives unavailable in that
profile:

| Focused tool | Unavailable tool named in its description |
| --- | --- |
| `check_store` | `get_provenance` |
| `open_fault` | `get_evidence_summary` |
| `get_rpc_trace` | `get_process_relations` |
| `get_incident_report` | `get_evidence_summary` |
| `list_incidents` | `get_unresolved` |
| `get_incident_slice` | `get_unresolved` |
| `discover_artifacts` | `query_artifact_index` |
| `get_call_relations` | `get_process_relations` |

The five referenced tools remain available in the full profile, so removing
those distinctions globally would make full-profile guidance weaker. The
focused definitions should instead name available alternatives or state the
scope boundary without directing callers to hidden tools.

The [official TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
scores the `tools/list` definition using each tool's description, input/output
schemas, annotations and sibling tool names. It says sibling names inform
competitive selection, and its Usage Guidelines dimension rewards explicit
when/when-not guidance and named alternatives. A reference to a tool omitted
from the selected profile can therefore undermine a usage instruction. This is
a rubric-based quality issue, not a measured Glama score defect: no current
per-tool breakdown was available, and no score improvement is inferred.

Sources: [focused catalog and descriptions](../faultdebug/mcp_server.py),
[alpha25 real stdio inventory](../docs/releases/v1.3.0-alpha.25.md), and the
[TDQS rubric](https://github.com/glama-ai/tool-definition-quality-score#the-six-dimensions).

## Candidate boundary

Add a focused-only description map for the eight affected tools. Keep the
existing full-profile docstrings intact. Each focused description should:

- distinguish its job from tools the focused caller can actually select;
- retain relevant limits, evidence distinctions, errors and read-only behavior;
- avoid mentioning hidden tool names as if the caller could invoke them;
- remain concise and consistent with the current title, input and output
  schemas.

Do not change tool names, membership, parameters, annotations, runtime behavior,
report semantics or evidence. Do not add a tool. The full profile must retain
its existing descriptions and cross-tool alternatives.

## Bounded acceptance

1. Real full-profile `tools/list` keeps the 27-tool catalog and the current
   descriptions for the affected tools, including alternatives that exist in
   that profile.
2. Real focused `tools/list` keeps 15 tools/44 parameters and exposes no
   description that names an unavailable sibling tool; affected descriptions
   name suitable focused alternatives where one exists.
3. Existing titles, annotations, input schemas, output schemas, invalid-call
   behavior and read-only evidence checks remain unchanged.
4. Run the real stdio audit in both profiles, Python package checks and hosted
   CI. An official Glama score remains unverified until the selected Glama build
   is updated and rescanned.

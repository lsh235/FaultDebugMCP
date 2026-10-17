# Static call-relations MCP output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.29`.

## Baseline and source evidence

The alpha28 focused profile includes `get_call_relations`, but the tool has no
`outputSchema`. It requires a verified bundle and returns the stable envelope
`function_id`, `direction`, `relations`, `evidence`, and `bundle` from
`faultdebug.inspect.verified_call_relations`.

The generated bundle index in `faultdebug/index.py` writes two outbound edge
forms: direct calls with `callee_id` and `kind=direct`, and unresolved calls
with `spelling` and `kind=indirect_or_virtual`. Inbound results wrap a matching
edge as `{caller_id, edge}`. The output is static index evidence, never
observed runtime nesting or a verified call execution.

Bundles can contain version-1 indexes whose row extensions are hash-verified
but not schema-normalized by `SourceBundle.index_rows`. Therefore the proposed
schema should type the stable envelope and describe common relation keys while
keeping each relation row open to unknown JSON fields/values. A strict
discriminated edge union risks turning a previously readable index extension
into an MCP error. The existing text JSON, required bundle verification and
evidence classification must remain unchanged.

The codebase-memory graph tools are not exposed in this session. This bounded
candidate uses direct source reads of `FOCUSED_MCP_TOOL_NAMES`, the handler,
`verified_call_relations`, `SourceBundle.index_rows`, and the index writer. It
makes no graph-coverage or exhaustive call-graph claim.

## Relevance to focused clients and TDQS

The repository's Glama Dockerfile example selects the focused profile. The
official [TDQS specification](https://github.com/glama-ai/tool-definition-quality-score)
includes the full output schema in tool evaluation and judges return-shape
completeness against the documented fields. This candidate can document that
the output is a static hypothesis set, its direction and the distinction
between direct and unresolved rows. Those distinctions help agents avoid
mistaking a call candidate for runtime evidence and let them pass only the
verified `function_id`/bundle path to source inspection.

This does not establish the external Glama profile or a numeric score change.
Only a Glama rescan of the deployed MCP definition can verify score impact.

## Bounded candidate

Publish a typed `CallRelationsOutput` in both MCP profiles. Type the stable
function ID, `inbound|outbound` direction, `static_index` evidence label and
verified bundle path. Use an open relation-row model that documents common
`caller_id`, `callee_id`, `spelling`, `kind`, and nested `edge` fields but
accepts unknown JSON values/keys from hash-verified version-1 indexes.

Do not change static index generation, bundle verification, direction
semantics, required inputs, error behavior, runtime evidence, text output or
tool inventory. Tool/parameter counts remain 27/84 and 15/44; full/focused
output-schema counts would increase from 12/11 to 13/12 if accepted.

## Acceptance evidence

Use real full/focused stdio calls against a verified bundle containing direct
and unresolved outbound rows and a matching inbound row. Validate
`structuredContent`, compare all text fields, and prove an extra index field
survives the open relation model. Test an empty relation set, a missing
function ID and an invalid bundle as well. Evidence snapshots must remain
unchanged. Build/install the wheel outside the checkout and require hosted CI
before tagging.

No official Glama rescan or stable-release acceptance is part of this
candidate.

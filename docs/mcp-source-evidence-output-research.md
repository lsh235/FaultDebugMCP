# Source-evidence output-schema research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.23`.

## Baseline and opportunity

`get_source_evidence` is part of the 15-tool focused profile recommended by the
repository's Glama build example. It verifies incident source references against
an immutable bundle and returns verified citations plus unresolved references.
Unlike the full-only `get_provenance` query, a schema for this tool would be
visible in the focused profile used for Glama inspection.

The success contract has a fixed schema-v2 envelope: `incident_id`, verified
`bundle`, paged `citations`, `unresolved`, citation `total`, `page`, `page_size`
and `resolved`. Citation rows include nullable artifact/function IDs, source
path and line range, actual file hash, manifest hash, and a true verification
flag. Unresolved rows include a nullable function ID and stable reason code plus
the explanatory message. For compatibility, exactly one citation also adds
five flat convenience fields (`file`, line bounds, SHA256 and function ID) to
the top-level text response. Store or bundle failures are returned as
`error.code=SOURCE_EVIDENCE_ERROR`; invalid MCP parameters remain protocol-level
tool errors. The handler never returns source text.

The filter semantics matter: omitted `function_ids` uses the incident's saved
references, while supplied IDs add requests not already represented. Missing
IDs, hash mismatches and line-range failures remain unresolved evidence rather
than fabricated citations. `resolved` is true only when this page contains at
least one citation and no unresolved row. Pagination applies to citations;
unresolved rows remain visible on each page. These details must be stated in
field descriptions so clients do not treat a citation as root-cause proof.

Sources: [TDQS output-schema guidance](https://github.com/glama-ai/tool-definition-quality-score#improving-your-score),
[MCP handler and focused-profile membership](../faultdebug/mcp_server.py),
[bundle verification and result projection](../faultdebug/evidence_store.py).

## Candidate boundary

Publish a documented typed success/error output contract for
`get_source_evidence` in both profiles, without changing its text JSON, its
single-citation convenience fields, verification rules, pagination, error
behavior or focused tool membership. Model citation and unresolved rows with
their exact nullable fields. Keep source contents out of this tool's result;
`get_function_source` remains the separate verified source-text operation.

## Bounded acceptance

1. Real `tools/list` exposes a documented output schema for `get_source_evidence`
   in both full and focused profiles; no other tool/profile membership changes.
2. Real stdio validates success with zero, one and multiple citations, unresolved
   verification failures, and the one-citation flat fields against the schema.
3. Success `structuredContent` is equivalent to the schema-valid structured
   result, while the text response preserves its existing field names and
   convenience-field behavior. MCP errors for invalid arguments remain errors;
   store/bundle failures retain the current `SOURCE_EVIDENCE_ERROR` payload.
4. Verified citations still require a verified bundle manifest, source file,
   matching optional source hash and in-range line interval. The read-only store
   and bundle remain byte-for-byte unchanged.
5. Full/focused tool and parameter inventories stay fixed; the focused profile
   gains one typed output contract. Run source-evidence regressions, MCP schema
   audit, installed distribution checks and hosted CI.

This is a definition-quality improvement for the live focused profile, not a
claim that TDQS will increase. Only a fresh independent Glama scan can establish
the public score.

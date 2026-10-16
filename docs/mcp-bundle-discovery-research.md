# MCP verified-bundle discovery: research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v1.3.0-alpha.16`.
Baseline: `v1.3.0-alpha.15`.

## User workflow gap

Alpha15 made the bundle argument machine-required for source lookup and static
call-relation tools. An MCP consumer can find captures with `discover_artifacts`
and can query existing stores with `check_store`/`list_sessions`, but there is
no tool to locate source bundle directories beneath the configured `--root`.
Agents that do not already know the path must guess or ask the user, then risk
repeating calls with invalid paths.

## Options

1. Tell clients to search the filesystem themselves. Rejected: it bypasses the
   server's root allowlist and requires a separate filesystem tool.
2. Return every bundle manifest from `open_fault` or `discover_artifacts`.
   Rejected: it mixes different evidence classes and creates work for callers
   that only need capture discovery.
3. Add one read-only `discover_bundles` tool. Accepted: it lists root-relative
   `bundle.json` candidate directories with bounded pagination and manifest file
   size. It does not read or hash manifests; source tools still parse and verify
   every supplied bundle before exposing source or index data.

The tool must not disclose absolute source paths from manifests, traverse
symlinks outside `--root`, read manifest contents, write or repair files, or
imply that a candidate is verified. Bound candidate scans to 10,000 manifests
and page results by 200. A filename match is only a candidate; malformed
manifests remain visible as candidates and the existing source reader reports
verification errors without this discovery tool exposing raw contents.

Glama's public methodology evaluates tool-set coherence as well as each tool's
definition. A discovery step that joins existing capture discovery to the
verified source tools closes an actual workflow gap. The current score remains
unavailable (public score API returned HTTP 401), so no numeric increase is
predicted or claimed.

Sources: [Glama indexing methodology](https://glama.ai/mcp/methodology),
[open TDQS specification](https://github.com/glama-ai/tool-definition-quality-score).

## Proposed acceptance

- A `bundle.json` filename match appears with a root-relative directory path,
  file size and `verification=not_performed`, without parsing it.
- Malformed and oversized files are candidates only; discovery never exposes
  their contents or claims that a manifest is valid.
- Symlinked manifests are rejected and symlink escapes are never returned.
- Pagination and the 10,000-candidate bound are deterministic; no evidence
  files change.
- The real MCP server exposes the new additional tool while all existing tool
  names and read-only annotations remain intact.

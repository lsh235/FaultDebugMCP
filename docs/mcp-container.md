# Run the read-only MCP inspector in Docker

This image packages the Python MCP inspector. It does not compile or trace
programs. Build and capture artifacts with the native workflow, then mount only
the artifact directory into this container as read-only.

## Build

From the repository root:

```sh
docker build -f Dockerfile.mcp -t faultdebug-mcp:local .
```

The image uses Python 3.12 and installs the pinned application dependencies from
`pyproject.toml`. It does not include the C runtime, Clang, or CMake toolchain.

## Configure an MCP client

Replace `/absolute/path/to/artifacts` with the host directory containing the
`.fault` files, source bundles, or existing evidence store. The bind mount is
read-only, and the MCP process runs as an unprivileged container user.

```json
{
  "mcpServers": {
    "faultdebug": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--mount", "type=bind,src=/absolute/path/to/artifacts,dst=/artifacts,readonly",
        "faultdebug-mcp:local"
      ]
    }
  }
}
```

The MCP server uses stdio. It reads only files under `/artifacts`; it does not
mount the Docker socket, upload evidence, or contact a remote service. A bundle
or evidence database must be inside the mounted directory to be available.
Host file permissions still apply: the container user (UID 65532) must be able
to read the mounted files. If your artifact directory is private to your user,
run the container with `--user "$(id -u):$(id -g)"` before `--mount`, and ensure
the image's `/artifacts` path is not needed for writes.

## Security and scope

The MCP tools are read-only and validate relative paths against the configured
root. The native capture launcher and report-generating CLI are separate
workflows and can write output. Treat fault captures and source bundles as
sensitive; do not expose them to untrusted MCP clients.

## Tool definitions and Glama

The MCP `tools/list` response contains descriptions and per-parameter JSON Schema
metadata for all 25 tools. Each tool declares `readOnlyHint=true`,
`destructiveHint=false`, `idempotentHint=true`, and `openWorldHint=false`.
Capture and bundle paths are relative to the configured root; absolute paths,
parent traversal and escaping symlinks are rejected. Address resolution may read
recorded local ELF paths and run a local symbolizer with remote lookup disabled.

Choose tools by evidence source and question:

| Question | Tools |
| --- | --- |
| What can this server read, and where are the captures? | `get_capabilities`, `check_store`, `discover_artifacts` |
| What did one process record? | `open_fault`, `get_thread_trace`, `get_fault_flow`, `get_rpc_trace`, `get_evidence_summary` |
| How do captures group or relate across processes? | `collect_faults`, `get_timeline`, `get_process_relations`, `get_incident_report`, `get_session_manifest`, `get_process_participants` |
| What is already persisted in SQLite? | `list_sessions`, `get_session`, `get_provenance`, `query_artifact_index` (legacy index) |
| What evidence belongs to a declared incident? | `list_incidents`, `get_incident_slice`, `get_unresolved` |
| Which addresses/source/call candidates can be verified? | `resolve_addresses`, `get_function_source`, `get_call_relations`, `get_source_evidence` |

`get_session(session_id=null)` selects only unassigned artifacts; it does not
list all sessions. `get_thread_trace` pages thread records, `get_rpc_trace` pages
RPC observations, and store incident/session tools page artifacts. Returned
counts and truncation flags describe the corresponding collection. The pinned
MCP SDK does not advertise output schemas; tool descriptions document the
returned keys and distinguish MCP errors from structured `error.code` payloads.

Run the protocol and read-only audit from the repository root:

```sh
.venv/bin/python test/mcp_tool_metadata.py --output build/mcp-definition-audit.json
```

This starts a real stdio server, inspects all schema metadata, exercises reads
and rejected inputs, verifies nullable session selection, and checks that
captures/stores/indexes remain byte-for-byte unchanged. CI publishes the inspected
definitions as the `mcp-definition-audit` artifact. This is a deterministic
contract check, not an estimated TDQS score.

[Glama's TDQS rubric](https://github.com/glama-ai/tool-definition-quality-score)
evaluates the definitions collected from a running server. The repository's
`glama.json` identifies its maintainer. The existing
[Glama listing](https://glama.ai/mcp/servers/lsh235/FalutDebugMCP) currently retains
the original repository spelling; the canonical GitHub repository is
`lsh235/FaultDebugMCP`.

[Glama's indexing methodology](https://glama.ai/mcp/methodology) describes
re-scanning after commits/rebuilds. After publishing a change, confirm the listing's
scan timestamp and tool inventory before reporting its new score. If its build
configuration still points to old source, the maintainer can select the current
repository/build spec in Glama administration. Use `Dockerfile.mcp` for the local
build, or equivalent build steps `python -m pip install .` and command
`fault-debug mcp --root /artifacts` with an existing readable artifact directory.
Container release configuration is described in
[Glama's release guide](https://glama.ai/blog/2026-03-15-how-to-make-a-release).

The target is complete, concise definitions across every tool; a 5.0 official
score is only confirmed after Glama's independent rubric/coherence evaluation.

## 한국어 안내

이 이미지는 Python MCP 조회기만 포함하며 C/C++ 프로그램을 빌드하거나
추적하지 않습니다. native 도구로 생성한 artifact 디렉터리만 `/artifacts`에
읽기 전용으로 마운트하세요. MCP 프로세스는 stdio로 통신하고 Docker socket을
마운트하지 않습니다. 호스트 파일 권한에 따라 UID 65532가 파일을 읽지 못할
수 있습니다. 이 경우 설정의 `docker run` 인수에 `--user "$(id -u):$(id -g)"`를
추가하고 접근 가능한 artifact 디렉터리를 지정하세요.

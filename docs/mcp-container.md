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
metadata for all 27 tools in the default `full` profile. The optional `focused`
profile exposes a bounded 15-tool capture/incident/source workflow. Every tool
in either profile declares `readOnlyHint=true`,
`destructiveHint=false`, `idempotentHint=true`, and `openWorldHint=false`.
Capture and bundle paths are relative to the configured root; absolute paths,
parent traversal and escaping symlinks are rejected. Address resolution may read
recorded local ELF paths and run a local symbolizer with remote lookup disabled.

The pinned MCP Python SDK `mcp==1.30.0` publishes non-empty `outputSchema`
contracts for `get_capabilities`, `check_store`, `discover_artifacts`, and
`discover_bundles`.
Successful calls provide `structuredContent` alongside the existing JSON text;
the real stdio audit validates both profiles against the published schemas.
Optional status-specific fields can appear as `null` in `structuredContent`,
while the text response retains its original keys.

Choose tools by evidence source and question:

| Question | Tools |
| --- | --- |
| What can this server read, and where are the captures or source bundles? | `get_capabilities`, `check_store`, `discover_artifacts`, `discover_bundles` |
| What did one process record? | `open_fault`, `get_thread_trace`, `get_fault_flow`, `get_rpc_trace`, `get_evidence_summary` |
| How do captures group or relate across processes? | `collect_faults`, `get_timeline`, `get_process_relations`, `get_incident_report`, `get_session_manifest`, `get_process_participants` |
| What is already persisted in SQLite? | `list_sessions`, `get_session`, `get_provenance`, `query_artifact_index` (legacy index) |
| What evidence belongs to a declared incident? | `list_incidents`, `get_incident_slice`, `get_unresolved` |
| Which addresses/source/call candidates can be verified? | `resolve_addresses`, `get_function_source`, `get_call_relations`, `get_source_evidence` |

`get_session(session_id=null)` selects only unassigned artifacts; it does not
list all sessions. `get_thread_trace` pages thread records, `get_rpc_trace` pages
RPC observations, and store incident/session tools page artifacts. Returned
counts and truncation flags describe the corresponding collection. The full
profile publishes ten typed output schemas and the focused profile publishes
nine, including verified source citations, normalized RPC observations with
separate uncertainty diagnostics, and a typed fault-flow view with explicit
gaps and verified-source markers. Other
return details remain in descriptions, including the distinction between MCP
tool errors and structured `error.code` payloads.

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
[Glama listing](https://glama.ai/mcp/servers/lsh235/FaultDebugMCP) uses the
canonical repository spelling [`lsh235/FaultDebugMCP`](https://github.com/lsh235/FaultDebugMCP).

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

## Glama administrator build settings

Glama generates its own Dockerfile from the administrator build spec. Updating
`Dockerfile.mcp` in GitHub does not change those administrator settings.
Open the listing's [Dockerfile administration page](https://glama.ai/mcp/servers/lsh235/FaultDebugMCP/admin/dockerfile)
and set these fields:

```json
{
  "baseImage": "debian:trixie-slim",
  "buildSteps": [
    "uv sync --python 3.12",
    "mkdir -p /app/artifacts"
  ],
  "cmdArguments": [
    "mcp-proxy", "--", ".venv/bin/fault-debug",
    "mcp", "--root", "/app/artifacts", "--tool-profile", "focused"
  ],
  "nodeVersion": "24",
  "pinnedCommit": "e277d336800f016f30a714a2b9e3169acbfa41f3",
  "placeholderArguments": {},
  "pythonVersion": "3.12"
}
```

This full implementation SHA selects the alpha25 `focused` 15-tool first-line
workflow, nine structured response contracts, and descriptive titles; omit
the profile argument for the complete 27-tool catalog, which exposes ten typed
contracts. It includes normalized RPC diagnostics and a typed fault-flow view
in both profiles. This repository example
does not update the external Glama setting. The
previously documented
`255395c86809cce886ce58cdc5736b2a4c0f8aaa` revision predates it and exposed 25
tools with 76 described parameters. Alpha15 exposed 26 tools and 83 described
parameters, with `bundle` required for the two source tools. Alpha16 added the
read-only `discover_bundles` tool; the full-profile audit exposes 27 tools and
84 parameters. Alpha17 keeps that behavior while its focused profile publishes
15 tools. Alpha18 adds four output schemas and structured results in both
profiles. Alpha19 adds descriptive top-level titles to all 27 tool definitions.
Alpha20 adds a typed source result for `get_function_source`. Alpha21 adds a
typed incident-list result, alpha22 adds a typed session-list result to the
full profile, alpha23 adds typed verified source evidence to both profiles,
alpha24 types `get_rpc_trace`, and alpha25 types `get_fault_flow` in both profiles.
Check the
generated Dockerfile's `git checkout` before deploying. A null pin alone
does not prove that the generated checkout contains your latest changes.

Python 3.12 matches `requires-python = ">=3.12,<3.13"` in `pyproject.toml`.
Specifying it in both the runtime selection and `uv sync` avoids relying on
automatic interpreter selection. `uv sync` installs the project's
`fault-debug` entry point. Keep the Glama-provided `mcp-proxy` wrapper: it exposes
the application's stdio transport through HTTP for Glama's inspection.

Use the literal `/app/artifacts` directory without a placeholder substitution.
It starts empty so the inspector can list tools; actual fault analysis requires
readable captures, bundles or stores provisioned there. An empty inspection
directory does not contain sample captures or expose the checkout as evidence.

Click **Deploy** to test the image. After a successful test, select **Make
Release** or **Create Release**, then **Create & Publish Release**, as described
in [Glama's release guide](https://glama.ai/blog/2026-03-15-how-to-make-a-release).
Check that inspection sees 15 focused tools, including `discover_bundles`,
before checking the new TDQS scan. A successful image build is separate from an
official score.

The old pinned revision was validated locally with Glama's generated Dockerfile
template and `mcp-proxy@6.7.16`: image build, HTTP MCP initialization, its
25-tool listing, 76 parameter descriptions and `get_capabilities` passed. The
alpha15 source revision separately passed the repository's 26-tool/83-parameter
stdio audit; alpha16's full-profile audit, alpha17's profile audit, alpha18's
structured-result audit, alpha19's title audit and alpha20's source-schema audit
are in their release notes. No local result confirms a remote Glama deployment or
TDQS score. After changing the
administrator pin, Deploy and release the listing,
then verify its scan timestamp, required-bundle schemas and official score.

### A build fails immediately with HTTP 502

If the error is `DockerBuildError` with nginx `502 Bad Gateway`, an empty
`extra.logs` array, and a duration of less than a second, the available evidence
points to Glama's Docker build service or its gateway. There is no build-step
output establishing a failure in `uv sync` or in the application. Correct any
independent spec problems, save the settings and retry **Deploy** once.

If the same immediate 502 remains, contact `support@glama.ai` with the listing
URL, failed build ID, timestamp, duration and the error log. Glama's release guide
provides this support contact. Repository changes cannot repair a remote Docker
API gateway. If a later attempt instead includes package-installation or startup
logs, diagnose that new failure from its first concrete error.

## 한국어 안내

이 이미지는 Python MCP 조회기만 포함하며 C/C++ 프로그램을 빌드하거나
추적하지 않습니다. native 도구로 생성한 artifact 디렉터리만 `/artifacts`에
읽기 전용으로 마운트하세요. MCP 프로세스는 stdio로 통신하고 Docker socket을
마운트하지 않습니다. 호스트 파일 권한에 따라 UID 65532가 파일을 읽지 못할
수 있습니다. 이 경우 설정의 `docker run` 인수에 `--user "$(id -u):$(id -g)"`를
추가하고 접근 가능한 artifact 디렉터리를 지정하세요.

Glama 관리자 빌드는 위의 **Glama administrator build settings** 설정을
사용하세요. Python은 `3.12`, 빌드 단계는 `uv sync --python 3.12`와
`mkdir -p /app/artifacts`, 실행 경로는 `/app/artifacts`입니다. 빌드 시작 직후
`502 Bad Gateway`와 빈 `logs`가 반복되면 빌드 ID와 로그를 Glama 지원팀에
전달하세요. 컨테이너 빌드 성공과 TDQS 재평가 완료는 별도로 확인해야 합니다.

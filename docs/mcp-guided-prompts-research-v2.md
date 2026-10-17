# MCP guided investigation prompts: research

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.5`.
Baseline: `v2.0.0-alpha.4`, commit `cc1fbf64dbccd2c5213667258cb947ced8a1110c`.

## User task and observed gap

Continue the versioned feature cycle with an addition that improves the first
investigation path and reduces repeated setup instructions without inflating the
tool catalog or changing evidence. The current server exposes 15 tools in its
default `focused` profile and 27 with `--tool-profile full`; it exposes no MCP
prompts. The user-facing workflows are present in tool descriptions and server
instructions, but clients that support prompts cannot offer them as selectable,
reusable investigation recipes.

Observed source baseline:

- `faultdebug/mcp_server.py::make_server` creates a FastMCP server and registers
  tools through `register_tool`; it has no `app.prompt` registration.
- The focused catalog already contains the common capture workflow
  (`discover_artifacts`, `get_evidence_summary`, `open_fault`, `get_fault_flow`,
  `get_rpc_trace`) and stored-incident workflow (`check_store`,
  `get_incident_slice`, `get_source_evidence`). These names are
  declared in `FOCUSED_MCP_TOOL_NAMES` and exercised by
  `test/mcp_tool_metadata.py`.
- `pyproject.toml` pins MCP Python SDK `1.30.0`; that release exposes the
  `FastMCP.prompt` decorator with inferred prompt arguments in the pinned source.
- `docs/versioning-policy.md` classifies a new optional public capability as
  MINOR when existing calls retain their behavior. Since v2.0.0 is still an
  unreleased major target, compatible additions stay in its alpha sequence.

The [MCP Prompts specification](https://modelcontextprotocol.io/specification/2025-11-25/server/prompts)
defines prompts as templates that clients can list and retrieve. It describes
them as user-controlled and typically selected by the user in the client UI;
the protocol does not require a client to expose a particular UI. The pinned
[Python SDK v1.30.0 FastMCP source](https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/server/fastmcp/server.py)
includes `FastMCP.prompt(name, title, description, icons)` and converts
function parameters into prompt arguments.

## Alternatives

| Option | User value | Cost and runtime | Failure modes and evidence |
| --- | --- | --- | --- |
| 1. Do nothing | Existing users can still describe the task in chat and follow tool documentation. | No code, runtime, or maintenance cost. | First-time users must compose the correct tool sequence and remember evidence limits; no new client workflow is available. |
| 2. Add more workflow prose to tool/server descriptions | Repeats the current guidance for clients that only display tools. | Low code cost, but adds tokens to every client listing and repeats adjacent schemas. | May make tool definitions less concise and does not create a selectable workflow. Must be re-audited against TDQS; no score gain can be inferred. |
| 3. Add two user-selected MCP prompts (preferred for review) | Offers a capture-triage recipe and a stored-incident recipe using existing focused tools; makes evidence limits part of the workflow. | Small additive protocol surface; no capture decoding, filesystem access, process launch, network access, or additional tool execution on the server. | A host may not display prompts. Prompt text can steer a model but cannot guarantee completion; test protocol contents and tool-name parity, not downstream model behavior. Escape user arguments as data and never interpret them as paths or instructions. |
| 4. Add a new workflow/orchestrator tool | Could bundle several reads into one tool call. | Larger handler, new schema/output, duplicated query logic and potentially large responses. | Risks hiding stepwise evidence and encouraging broad reads; needs byte budgets, partial-failure semantics, output compatibility review and new score audit. Not justified while current tools already expose bounded steps. |

Option 3 is worth implementing only as a thin, optional client feature. It does
not claim to improve the Glama tool-definition score: Glama's published TDQS
inputs cover tool definitions and server coherence, and no live Glama
re-evaluation or prompt-specific score has been observed. See the
[official TDQS implementation](https://github.com/glama-ai/tool-definition-quality-score)
for its scoring inputs. The external score remains **NOT VERIFIED**.

## Proposed prompt behavior

Register exactly two prompts, available under both `focused` and `full` profiles:

1. `triage_capture(capture_name)` guides a client to verify the named capture
   under `--root`, use `get_evidence_summary` for a low-volume first pass, then
   select `open_fault`, `get_fault_flow`, or `get_rpc_trace` only as indicated
   by the observed counts. It asks the model to keep observations, derived
   interpretations, unresolved evidence and hypotheses distinct.
2. `investigate_incident(incident_id, db)` guides a client to check the store,
   read the named incident slice, inspect its returned unresolved rows, and
   request source evidence only when a verified bundle is available. `db`
   defaults to `evidence.sqlite3`, matching the existing store tools. The prompt
   must work in `focused`, where `get_unresolved` is not exposed.

Prompt handlers return one user-role text message. They perform no reads or
tool calls. Arguments are bounded, JSON-quoted, and labeled untrusted data so
newlines or instruction-like filenames cannot become extra template structure.
The prompt must not generate shell commands, assert a root cause, or imply that
shared IDs/timestamps prove causality. Existing tool path and store validation
remains authoritative when a client later invokes a tool.

## Contract and compatibility assessment

| Surface | Alpha4 behavior | Proposed behavior | Compatibility evidence / unknowns |
| --- | --- | --- | --- |
| Python API | `make_server(root, tool_profile=...)` registers tools only. | Same signature and behavior; server additionally registers two prompts. | Existing callers and return values remain unchanged. SDK is already pinned; verify the pinned decorator through hosted real-protocol tests. |
| CLI | Existing command-line args and exit behavior. | Unchanged. | No CLI parsing or output changes. |
| MCP tools | 15 focused / 27 full; schemas and semantics unchanged. | Identical tool names, schemas, annotations and call behavior. | Must compare real `tools/list` inventories before and after. Glama tool score is not established by prompt registration. |
| MCP prompts | No prompts are listed. | Two additive prompt names, descriptions and arguments; each `prompts/get` returns one user message. | Existing prompt-unaware clients should continue using the identical tool catalog; exact behavior of each host UI is outside repository control. |
| Native ABI, CMake, FDAR, store | Unchanged. | Unchanged. | No native or persisted format changes. |
| Filesystem and evidence | Tool calls enforce `--root`; prompt registration does not access evidence. | Prompt retrieval remains pure template generation. | Test before/after hashes and malformed/special argument cases. No prompt argument may cause server-side reads. |

Compatibility cases to verify:

| Client/request | Expected behavior |
| --- | --- |
| Existing client only lists/calls tools | Same 15/27 tool catalogs and behavior; prompts may be ignored. |
| Prompt-capable client lists prompts | Exactly the two documented entries are returned in either profile. |
| Valid prompt arguments | One user-role text message with the selected workflow and escaped argument values. |
| Missing required `capture_name` or `incident_id` | MCP invalid-params error; no handler side effect. |
| Empty/overlong arguments, embedded newlines, quotes, or instruction-like text | Reject invalid bounds or preserve the full value only as escaped data; never reinterpret it as workflow instructions. |
| Unknown prompt name | Standard MCP invalid-params error. |
| Tool call with a prompt-supplied invalid path/store | Existing tool-level root/path checks reject it; prompt retrieval itself does not validate or read that path. |

## Version proposal and acceptance

Stable class: **MINOR** after a stable v2 release, because two optional MCP
prompts are new public functionality and existing tools/clients retain their
contract. The current target is still unreleased, so the prerelease sequence is
Python `2.0.0a5` / tag `v2.0.0-alpha.5`. This is a stable-minor-class feature;
it is not evidence that v2.0.0 has passed its major-release gates.

Measurable candidate checks:

- Real stdio `prompts/list` returns the two names, argument requiredness and
  concise descriptions under both server profiles.
- Real stdio `prompts/get` returns one user message per prompt; content contains
  only the documented tool sequence and evidence boundaries.
- Missing/unknown/empty/overlong inputs fail as protocol errors. Special text is
  JSON-quoted and remains a single argument value.
- Prompt listing/retrieval does not change files; tool inventories, schemas,
  annotations and all existing invalid-call checks remain unchanged.
- Both recipes reference only tools available in both profiles.
- Hosted exact-commit CI validates package install and stdio behavior.
- Report Glama scan, pin, deployment and numeric score as **NOT VERIFIED** until
  independently observed. Do not use prompt support as score evidence.

Non-goals: automatic invocation, LLM task-completion claims, tool chaining by
the server, new capture/store operations, native/ABI changes, new Glama score
claims, stable v2 acceptance, and host-specific prompt UI guarantees. Existing
full v2 release gates remain open.

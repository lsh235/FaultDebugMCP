# MCP guided investigation prompts: feature review

Date: 2026-10-17 (Asia/Seoul). Candidate: `v2.0.0-alpha.5`.
Research: [guided prompt research](mcp-guided-prompts-research-v2.md).

## Decision

**YES — add two optional MCP prompts for capture triage and stored-incident
investigation.** The two workflows compose tools already present in both
profiles; the server will return instructions only after a client requests a
prompt. This gives prompt-capable clients a selectable path without adding MCP
tools, changing evidence output, or executing a filesystem operation from a
prompt handler.

This is a narrow workflow capability, not a Glama score optimization. The
prompt-aware user interface is host-dependent, and the prompt cannot ensure
that a model completes the investigation. We will verify the actual MCP
`prompts/list` and `prompts/get` exchange and retain the tool inventory audit;
we will not infer downstream user task completion or TDQS improvement.

## Version decision

Classify the addition as **MINOR** under the repository policy: new optional
public protocol capability, with existing Python, CLI, MCP tool, ABI and stored
artifact contracts unchanged. Since v2.0.0 is still the unreleased major target,
use Python `2.0.0a5` and `v2.0.0-alpha.5`. The alpha tag does not close any v2
stable release gate.

## Bounded implementation

1. Register exactly `triage_capture(capture_name)` and
   `investigate_incident(incident_id, db="evidence.sqlite3")` in
   `faultdebug/mcp_server.py` for both profiles.
2. Bound prompt arguments; encode them as JSON string data; do not read files,
   access stores, launch processes, call tools, or perform network operations
   while generating a prompt.
3. Guide callers through only tools available in both profiles and maintain
   the existing observed/derived/unresolved/hypothesis and verified-bundle
   boundaries. Do not mention `get_unresolved` in the shared recipe because it
   is not exposed in the focused profile; inspect the unresolved section
   returned by `get_incident_slice`.
4. Add real stdio protocol assertions for prompt listing/retrieval and invalid
   input while requiring unchanged 15/27 tool inventories and existing tool
   contract checks.
5. Update capabilities-independent documentation and the release record; do
   not add prompt names to `get_capabilities`, which currently describes the
   tool capability contract.

## Acceptance

- Both profiles return exactly the same two prompts and the same tools as
  alpha4.
- Each prompt advertises the expected argument names and requiredness, returns
  a single user-role text message, and includes the intended existing tool
  sequence without forbidden causality/root-cause claims.
- Empty, overlong, missing and unknown prompt inputs fail with MCP protocol
  errors; newlines, quotes and instruction-like values cannot create extra
  prompt structure.
- Prompt retrieval leaves a filesystem fixture unchanged and performs no tool
  call. Existing read-only, root-confinement, schema, invalid-call and evidence
  immutability checks pass.
- Exact candidate commit passes hosted Python/package, MCP container and Clang
  18 CI before it is tagged. External Glama rescan and stable-release gates
  remain separate.

## Review boundary

The prompt strings are advisory and clients control whether to present or use
them. The acceptance establishes the server protocol contract only; it does
not establish a model's follow-through, a host UI's behavior, external adoption,
Glama score change, or stable-release readiness. If implementation needs to
change tool semantics, read/write behavior, prompt capabilities by profile, or
persisted data, stop and re-review the scope and version class before coding.

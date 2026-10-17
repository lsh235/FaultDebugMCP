"""Read-only MCP facade over captured artifacts."""
from pathlib import Path
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field
from .service_query import ServiceSection, query_service_flow
from .format import collect_file
from .bundle import BundleError, discover_bundle_paths, load_bundle
from .inspect import (resolve_addresses as resolve_address_records, thread_trace,
                      verified_call_relations, verified_function_source)
from .aggregate import ArtifactIndex, build_timeline, collect_artifacts
from .rpc import evidence_summary, incident_report, process_relations, rpc_trace
from .session import process_participants, session_manifest
from .discovery import inspect_spool
from .evidence_store import EvidenceStore, EvidenceStoreError
from .capabilities import get_capabilities as capability_contract
from .mcp_outputs import (ArtifactDiscoveryOutput, BundleDiscoveryOutput,
                          CallRelationsOutput,
                          CapabilitiesOutput, FaultFlowOutput, FunctionSourceOutput,
                          IncidentListOutput, IncidentSliceOutput, SessionListOutput, SourceEvidenceOutput,
                          IncidentReportOutput, ResolveAddressesOutput, RpcTraceOutput,
                          ThreadTraceOutput,
                          StoreCheckOutput)

# Field metadata is exported in tools/list; docstring Args alone is not a schema.
CaptureName = Annotated[str, Field(min_length=1, description="Root-relative .fault or decoded .json capture path, e.g. fault-1234.fault; no absolute paths, '..', or escaping symlinks.")]
CaptureNames = Annotated[list[CaptureName], Field(max_length=1000, description="Capture paths beneath --root, up to 1,000; obtain paths from discover_artifacts. All captures are decoded before the result page is selected.")]
BundlePath = Annotated[str | None, Field(description="Verified bundle directory beneath --root, e.g. bundles/build-001. Omit/null for capture-only evidence; source citations require a bundle.")]
DebugDirectory = Annotated[str | None, Field(description="Optional existing root-relative local GNU build-id debug root containing .build-id/xx/rest.debug; no absolute paths, parent traversal, symlink escape, or network lookup.")]
RequiredBundlePath = Annotated[str, Field(min_length=1, description="Existing verified source/binary bundle directory beneath --root, e.g. bundles/build-001; paths and manifest hashes must verify.")]
StorePath = Annotated[str, Field(min_length=1, description="Existing root-relative .sqlite, .db, or .sqlite3 evidence store. Created/ingested with the CLI beforehand; MCP never creates or migrates it.")]
Page = Annotated[int, Field(ge=0, description="Zero-based page, default 0; increment to retrieve the next slice of up to 200 records. See the tool description for the paged collection.")]
StartNs = Annotated[int | None, Field(ge=0, description="Inclusive lower bound in captured monotonic nanoseconds, not Unix time. Null means no lower bound; combine with end_ns within the same clock domain.")]
EndNs = Annotated[int | None, Field(ge=0, description="Inclusive upper bound in captured monotonic nanoseconds. Null means no upper bound; normally >= start_ns when both are supplied.")]
TrustState = Annotated[Literal["verified", "unresolved"] | None, Field(description="Exact stored artifact trust filter; null includes both states. Trust is provenance verification, not confidence in a root-cause hypothesis.")]
ProvenanceTrust = Annotated[Literal["verified", "unresolved", "quarantined"] | None, Field(description="Exact stored trust filter; null includes all valid-artifact provenance. Quarantined artifacts are excluded by this query even when requested.")]
SessionId = Annotated[str | None, Field(description="Exact runtime session ID returned by list_sessions; null selects all sessions for listing/provenance tools, but only unassigned artifacts for get_session.")]
IncidentId = Annotated[str, Field(min_length=1, max_length=256, description="Exact agent-declared incident ID returned by list_incidents, not a filename or runtime session ID.")]
FunctionId = Annotated[str, Field(min_length=1, description="Exact compiler/index function ID from resolve_addresses or bundle index; a symbol name or instruction address is not interchangeable.")]
TraceId = Annotated[str | None, Field(description="Exact context.trace_id recorded in the capture; null disables this filter. With correlation_id supplied, both filters must match (AND).")]
CorrelationId = Annotated[str | None, Field(description="Exact context.correlation_id recorded in the capture; null disables this filter. Shared identifiers group evidence but do not prove causal links.")]

FOCUSED_MCP_TOOL_NAMES = frozenset({
    "get_capabilities", "discover_artifacts", "discover_bundles", "open_fault",
    "get_thread_trace", "get_fault_flow", "get_rpc_trace", "get_incident_report",
    "check_store", "list_incidents", "get_incident_slice", "get_source_evidence",
    "resolve_addresses", "get_function_source", "get_call_relations",
})

# Keep the full catalog's sibling guidance intact, while making every named
# alternative in the focused catalog actionable within that smaller profile.
FOCUSED_MCP_TOOL_DESCRIPTIONS = {
    "check_store": """Inspect one SQLite evidence store's health and migration compatibility without repair.

Use before list_incidents, especially for a missing or corrupt DB. Returns status, read_only, schema compatibility and diagnostics; STORE_PATH_INVALID is an error payload. An absent store is reported without creation. This profile does not expose provenance-record inspection; use the evidence CLI for a detailed trust audit. No migration or credential lookup occurs; use the evidence CLI separately if diagnostics require repair.""",
    "open_fault": """Decode one capture's process, thread, crash and integrity records for initial triage.

Use after discover_artifacts; get_fault_flow produces a bounded execution view, while get_rpc_trace inspects recorded RPC boundaries. Returns the decoded capture and, if supplied, a verified bundle marker (not source lines). Names are relative to --root. Invalid paths, malformed captures or failed bundle verification produce MCP tool errors; partial captures retain their loss flags.""",
    "get_rpc_trace": """Decode one capture's semantic RPC observations, static candidates and unresolved limits.

Use to inspect recorded request/response boundaries; get_thread_trace is for function events and get_fault_flow for reconstructed nesting. Use get_incident_report for ad hoc cross-capture analysis. Returns observed (paged), total, page, page_size, static_candidates and unresolved. Only observed RPC rows are paged; uncertainty is retained on every page. Missing RPC instrumentation yields unresolved evidence rather than invented edges. Malformed captures, ambiguous RPC extensions or invalid paths produce MCP tool errors.""",
    "get_incident_report": """Project a combined RPC incident report directly from named captures, without a stored incident ID.

Use for ad hoc multi-capture analysis; get_incident_slice reads an agent-declared incident already in SQLite, and open_fault is for one capture. Returns observed RPC events/process relations, static_candidates, unresolved and field availability. page slices only observed.rpc_events in batches of 200; total_rpc_events counts the full set. Inferences never become root-cause proof. Invalid captures/paths produce MCP tool errors; report files are not written.""",
    "list_incidents": """List agent-declared incident summaries already persisted in a SQLite evidence store.

Use to obtain incident IDs before get_incident_slice; get_incident_report instead derives an ad hoc report from capture filenames. Returns incidents, total, page and page_size; time bounds filter incident first_seen_ns, not process-start times. Filters combine with AND and empty matches return an empty list. Failures return error.code=INCIDENT_QUERY_ERROR. The query neither declares incidents nor infers root cause; inspect unresolved evidence in get_incident_slice. No migration occurs.""",
    "get_incident_slice": """Read artifact, process, RPC and source-reference evidence for one stored declared incident.

Use an ID from list_incidents; get_incident_report uses filenames instead. Returns incident, artifacts (paged), participants, observed, derived, static_candidates, unresolved, hypotheses and source_references. Each page includes evidence for up to 200 artifacts, capped at 1,000 observed events; inspect event_truncated/event_total before concluding completeness. Source references are not verified citations; use get_source_evidence to verify them against a bundle. Unknown IDs/store failures return error.code=INCIDENT_QUERY_ERROR without modifying the store.""",
    "discover_artifacts": """Recursively discover and validate captures beneath the configured artifact root.

Use first when filenames are unknown; open_fault decodes a selected capture and get_fault_flow builds a bounded per-thread execution view. Returns artifacts (paged), total/count, valid and invalid counts; malformed files remain FAIL rows rather than disappearing. Scans at most 10,000 matches. include_json adds fault-*.json only with the default fault-*.fault pattern; use *.json for a custom JSON glob. Invalid roots/patterns or exceeding the scan limit produce MCP tool errors; no index is created.""",
    "get_call_relations": """Read inbound callers or outbound call candidates for one function in a verified static index.

Use for source call hypotheses; get_fault_flow reconstructs recorded nesting and get_rpc_trace shows observed RPC boundaries. Returns function_id, direction, relations, evidence=static_index and bundle. Outbound includes unresolved edges; inbound includes indexed callers with matching callee IDs. A verified bundle is required. No runtime execution is proven, and capture/function Build-ID matching requires resolve_addresses. Missing IDs, unverified bundles or invalid directions produce MCP tool errors.""",
}

# MCP's top-level Tool.title is distinct from the legacy annotation title. Keep
# the display title useful on its own and long enough to be meaningfully
# different from the programmatic snake_case name.
MCP_TOOL_DISPLAY_TITLES = {
    "get_service_flow": "Inspect cross-service calls, causes, and evidence gaps",
    "get_capabilities": "Review supported evidence formats and tool limits",
    "check_store": "Check evidence-store integrity and compatibility",
    "open_fault": "Open one fault capture with its recorded context",
    "get_thread_trace": "Inspect ordered events from one captured thread",
    "get_fault_flow": "Trace captured fault events across their thread",
    "get_rpc_trace": "Inspect captured RPC observations and relationships",
    "collect_faults": "Decode fault captures into bounded evidence records",
    "get_timeline": "Page events across selected fault captures",
    "get_process_relations": "Compare process relationships across captures",
    "get_evidence_summary": "Summarize observed evidence and unresolved questions",
    "get_incident_report": "Build an evidence-bounded report for one incident",
    "get_session_manifest": "Inspect declared identities in a capture session",
    "get_process_participants": "List recorded processes in a declared session",
    "list_sessions": "List evidence sessions with their capture counts",
    "get_session": "Retrieve captures assigned to one evidence session",
    "get_provenance": "Check recorded artifact and build provenance",
    "list_incidents": "List agent-declared incidents in the evidence store",
    "get_incident_slice": "Read one bounded page of incident evidence",
    "get_unresolved": "List questions not resolved by recorded evidence",
    "get_source_evidence": "Verify source claims against a required bundle",
    "discover_artifacts": "Find and validate captures under the evidence root",
    "discover_bundles": "Find candidate source bundles without verifying them",
    "query_artifact_index": "Search the read-only index of captured artifacts",
    "resolve_addresses": "Resolve captured addresses against verified symbols",
    "get_function_source": "Read source lines for a verified function",
    "get_call_relations": "Inspect verified callers and callees for a function",
}


def _relative(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("paths must be relative to the allowlisted root without parent traversal")
    path = (root / relative).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        raise ValueError("path is outside the allowlisted root")
    return path


def _debug_directories(root: Path, name: str | None) -> list[Path] | None:
    if name is None:
        return None
    path = _relative(root, name)
    if (path != root.resolve() and root.resolve() not in path.parents) or not path.is_dir():
        raise ValueError("debug directory must be an existing directory beneath the allowlisted root")
    return [path]


def _read_only(title: str) -> ToolAnnotations:
    return ToolAnnotations(title=title, readOnlyHint=True, destructiveHint=False,
                           idempotentHint=True, openWorldHint=False)

def _load(root: Path, name: str) -> dict:
    path = _relative(root, name)
    if root.resolve() not in path.parents or path.suffix not in (".fault", ".json"):
        raise ValueError("artifact is outside the allowlisted root")
    if not path.is_file(): raise ValueError(f"artifact not found: {name}")
    return collect_file(path)

def _safe_artifact(root: Path, name: str) -> Path:
    path = _relative(root, name)
    if root.resolve() not in path.parents or path.suffix not in (".fault", ".json") or not path.is_file():
        raise ValueError("artifact is outside the allowlisted root or missing")
    return path


def _safe_store(root: Path, name: str) -> Path:
    path = _relative(root, name)
    if root.resolve() not in path.parents or path.suffix not in (".sqlite", ".db", ".sqlite3") or not path.is_file():
        raise ValueError("evidence store is outside the allowlisted root or missing")
    return path


def _bundle(root: Path, name: str):
    path = _relative(root, name)
    if root.resolve() not in path.parents and path != root.resolve():
        raise ValueError("bundle is outside the allowlisted root")
    try: return load_bundle(path)
    except BundleError as exc: raise ValueError(str(exc)) from exc

def make_server(root: Path, *, tool_profile: str = "full"):
    if type(tool_profile) is not str or tool_profile not in {"full", "focused"}:
        raise ValueError("tool_profile must be 'full' or 'focused'")
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("official mcp Python SDK is required") from exc
    if tool_profile == "focused":
        instructions = (
            "Focused evidence inspection: discover_artifacts locates captures; use open_fault/get_fault_flow and "
            "discover_bundles before verified source tools. Stored incidents use check_store, list_incidents and "
            "get_incident_slice. Session/timeline/index tools need full profile. Paths stay under --root. Keep observed, "
            "derived, static_candidates, unresolved and hypotheses distinct; source needs a verified bundle, and "
            "shared IDs/time order do not prove causality. No writes or network lookup."
        )
    else:
        instructions = (
            "Inspect existing local captures; no recording, ingestion, repair, or report-file writes. "
            "Start with get_capabilities/discover_artifacts; discover_bundles locates source bundles. "
            "Use open_fault/get_fault_flow for captures. "
            "For existing SQLite evidence, check_store then list_sessions/list_incidents and fetch a slice. "
            "Paths are relative to --root. Keep observed, derived, static_candidates, unresolved and hypotheses "
            "distinct. Source citations need a verified bundle; shared IDs/time order do not prove causality."
        )
    app = FastMCP("faultdebug", instructions=instructions)
    registered_tool_names: set[str] = set()

    def register_tool(*, name=None, description=None, annotations=None):
        def decorator(function):
            if tool_profile == "full" or function.__name__ in FOCUSED_MCP_TOOL_NAMES:
                tool_name = name or function.__name__
                try:
                    title = MCP_TOOL_DISPLAY_TITLES[tool_name]
                except KeyError as exc:
                    raise ValueError(f"missing MCP display title for {tool_name}") from exc
                titled_annotations = (
                    annotations.model_copy(update={"title": title})
                    if annotations is not None else None
                )
                tool_description = description
                if tool_profile == "focused":
                    tool_description = FOCUSED_MCP_TOOL_DESCRIPTIONS.get(tool_name, description)
                app.tool(name=name, title=title, description=tool_description,
                         annotations=titled_annotations)(function)
                registered_tool_names.add(tool_name)
            return function
        return decorator
    @register_tool(annotations=_read_only("Get service flow"))
    def get_service_flow(
        evidence: Annotated[str, Field(min_length=1, description="Root-relative frozen evidence directory containing native .fault captures and optional events.jsonl files. No symlinks; 64 MiB total input budget.")],
        section: Annotated[ServiceSection, Field(description="Summary returns counts; select one evidence collection to retrieve a page without mixing native observations and application explanations.")] = "summary",
        page: Page = 0,
        page_size: Annotated[int, Field(ge=1, le=200, description="Records per page, 1–200, default 100. Reduce if the 1 MiB response byte budget is exceeded.")] = 100,
        snapshot_id: Annotated[str | None, Field(description="SHA-256 fingerprint from a previous query. Supply on subsequent pages to reject changed inputs; null starts a new snapshot check.")] = None,
    ) -> dict:
        """Inspect cross-service evidence as a summary or one bounded collection page.

        Start with summary, then request calls, causes, events, services,
        native_relations, unresolved or evidence_files. Reuse snapshot_id for
        subsequent pages. Returns counts and limitations; collection pages add
        items, total, returned and next_page. Every call rereads bounded frozen
        inputs; this is not a retained live snapshot. Application reasons remain
        self-reported. No cross-process global clock or causal order is inferred.
        Invalid paths, budgets, corrupt inputs or a stale snapshot produce tool
        errors. Reads only; source enrichment uses existing verified bundle tools.
        """
        path = _relative(root, evidence)
        return query_service_flow(path, section=section, page=page,
                                  page_size=page_size, snapshot_id=snapshot_id)
    @register_tool(annotations=_read_only("Get capabilities"))
    def get_capabilities() -> CapabilitiesOutput:
        """Describe supported capture/store versions, evidence classes, platform and query limits.

        Use first to plan an inspection; discover_artifacts locates files and check_store
        checks a specific database. Returns the bounded contract, active MCP profile,
        exposed tool names and filtered capability groups. Reads no captures and needs
        no credentials; it does not prove that a particular file or bundle is valid."""
        contract = capability_contract()
        for key in ("required_tools", "additional_tools", "v09_tools"):
            contract[key] = [name for name in contract[key] if name in registered_tool_names]
        contract["mcp_tool_profile"] = tool_profile
        contract["exposed_tools"] = sorted(registered_tool_names)
        return contract
    @register_tool(annotations=_read_only("Check store"))
    def check_store(db: StorePath = "evidence.sqlite3") -> StoreCheckOutput:
        """Inspect one SQLite evidence store's health and migration compatibility without repair.

        Use before list_sessions or list_incidents, especially for a missing/corrupt DB;
        get_provenance instead retrieves artifact trust records. Returns status, read_only,
        schema compatibility and diagnostics; STORE_PATH_INVALID is an error payload.
        An absent store is reported without creation. No migration or credential lookup
        occurs; use the evidence CLI separately if the returned diagnostics require repair."""
        try:
            path = _relative(root, db)
        except ValueError as exc:
            return {"schema": 2, "status": "error", "read_only": True,
                    "error": {"code": "STORE_PATH_INVALID", "message": str(exc)}}
        if root.resolve() not in path.parents or path.suffix not in (".sqlite", ".db", ".sqlite3"):
            return {"schema": 2, "status": "error", "read_only": True,
                    "error": {"code": "STORE_PATH_INVALID", "message": "evidence store is outside the allowlisted root"}}
        return EvidenceStore.inspect_health(path)
    @register_tool(annotations=_read_only("Open fault"))
    def open_fault(name: CaptureName, bundle: BundlePath = None) -> dict:
        """Decode one capture's process, thread, crash and integrity records for initial triage.

        Use after discover_artifacts; get_fault_flow instead produces a bounded execution
        view and get_evidence_summary gives a compact RPC evidence inventory. Returns the
        decoded capture and, if supplied, a verified bundle marker (not source lines).
        Names are relative to --root. Invalid paths, malformed captures or failed bundle
        verification produce MCP tool errors; partial captures retain their loss flags."""
        report = _load(root, name)
        if bundle: report["bundle"] = {"path": str(_bundle(root, bundle).root), "verified": True}
        return report
    @register_tool(annotations=_read_only("Get thread trace"))
    def get_thread_trace(name: CaptureName, tid: Annotated[int | None, Field(ge=0, description="Captured OS thread ID; null includes all thread generations. A reused ID can match more than one thread record.")] = None, page: Page = 0) -> ThreadTraceOutput:
        """Read captured thread records and their retained function events from one artifact.

        Use for raw thread histories, not semantic RPCs (get_rpc_trace) or reconstructed
        nesting (get_fault_flow). Returns items, total, page and page_size; pagination
        slices thread records, not individual events. tid filters the OS thread ID and
        may match multiple generations. Invalid captures/paths produce MCP tool errors;
        an unmatched tid or an exhausted page yields empty items. No live process is queried."""
        rows = thread_trace(_load(root, name), tid)
        return {"items": rows[page * 200:(page + 1) * 200], "page": page, "page_size": 200, "total": len(rows)}
    @register_tool(annotations=_read_only("Get fault flow"))
    def get_fault_flow(name: CaptureName, bundle: BundlePath = None, max_events: Annotated[int, Field(ge=1, le=500, description="Maximum last retained pre-crash function events per thread (1–500); truncates the view, not the underlying capture.")] = 80, debug_directory: DebugDirectory = None) -> FaultFlowOutput:
        """Build a bounded per-thread fault-flow model with recorded nesting, fault context and gaps.

        Use for an execution-view explanation; get_thread_trace instead returns raw
        thread records, and get_incident_report joins RPC evidence across captures.
        Returns capture, threads, crashes, edges, sources and gaps without writing
        HTML/Markdown. max_events limits the last retained pre-crash events per thread;
        view omission differs from capture loss. Without a verified bundle, source
        citations remain unavailable. An optional root-relative debug_directory may
        supply matching separate ELF symbols from a GNU .build-id cache. Invalid paths
        produce MCP tool errors; network debug lookup is disabled."""
        from .fault_report import build_fault_report
        return build_fault_report(_load(root, name), bundle=_bundle(root, bundle) if bundle else None,
                                  max_events=max_events,
                                  debug_directories=_debug_directories(root, debug_directory))
    @register_tool(annotations=_read_only("Get rpc trace"))
    def get_rpc_trace(name: CaptureName, page: Page = 0) -> RpcTraceOutput:
        """Decode one capture's semantic RPC observations, static candidates and unresolved limits.

        Use to inspect recorded request/response boundaries; get_thread_trace is for
        function events and get_process_relations matches endpoints across captures.
        Returns observed (paged), total, page, page_size, static_candidates and unresolved.
        Only observed RPC rows are paged; uncertainty is retained on every page. Missing
        RPC instrumentation yields unresolved evidence rather than invented edges.
        Malformed captures, ambiguous RPC extensions or invalid paths produce MCP tool errors."""
        decoded = rpc_trace(_load(root, name))
        page = max(0, page)
        decoded["total"] = len(decoded["observed"])
        start = page * 200
        decoded["observed"] = decoded["observed"][start:start + 200]
        decoded["page"] = page
        decoded["page_size"] = 200
        return decoded
    @register_tool(annotations=_read_only("Collect faults"))
    def collect_faults(names: CaptureNames, trace_id: TraceId = None, correlation_id: CorrelationId = None, page: Page = 0) -> dict:
        """Collect process/crash metadata from named captures, grouped by exact context identifiers.

        Use for a filtered artifact inventory; get_incident_report adds RPC evidence and
        query_artifact_index searches metadata already indexed in SQLite. Both optional
        ID filters must match when supplied. Returns artifacts (paged), count, groups
        and filters; count/groups cover all matches, not just the page. Grouping by shared
        IDs does not prove causal links. Missing or invalid captures fail the call with
        an MCP tool error; no database ingestion occurs."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        paths = [_safe_artifact(root, name) for name in names]
        result = collect_artifacts(paths, trace_id=trace_id, correlation_id=correlation_id)
        start = max(0, page) * 200
        result["artifacts"] = result["artifacts"][start:start + 200]; result["page"] = max(0, page); result["page_size"] = 200
        return result
    @register_tool(annotations=_read_only("Get timeline"))
    def get_timeline(names: CaptureNames) -> dict:
        """Order captured process-start, crash and explicit IPC events, preserving ambiguous links.

        Use to inspect recorded timing and unique IPC send/receive pairs;
        get_process_relations also handles semantic RPC endpoint relationships.
        Returns events, relations, diagnostics and complete/limited status. All supplied
        captures are included; timestamps are monotonic, so compare only compatible clock
        domains. Temporal order alone is not causality. Missing/malformed captures produce
        MCP tool errors; absent IPC pairs stay in diagnostics. No live tracing occurs."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        reports = [collect_file(_safe_artifact(root, name)) for name in names]
        return build_timeline(reports)
    @register_tool(annotations=_read_only("Get process relations"))
    def get_process_relations(names: CaptureNames, page: Page = 0) -> dict:
        """Match explicit IPC/RPC endpoint evidence across named captures into process relationships.

        Use for cross-process links; get_session_manifest groups participants and
        get_timeline orders captured timing. Returns observed (paged), total, page,
        page_size, static_candidates and unresolved; only observed relations are paged.
        A shared PID, session ID or nearby timestamp never creates a causal edge.
        Missing endpoint evidence remains unresolved; invalid captures/paths produce
        MCP tool errors. Reads captures directly without consulting an evidence store."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        result = process_relations([collect_file(_safe_artifact(root, name)) for name in names])
        page = max(0, page)
        result["total"] = len(result["observed"])
        start = page * 200
        result["observed"] = result["observed"][start:start + 200]
        result["page"] = page
        result["page_size"] = 200
        return result
    @register_tool(annotations=_read_only("Get evidence summary"))
    def get_evidence_summary(name: CaptureName) -> dict:
        """Summarize RPC evidence counts and limits for one capture without returning full histories.

        Use for a compact triage inventory before get_rpc_trace or get_fault_flow;
        get_incident_report instead combines multiple captures. Returns status,
        artifact/observed/static-candidate counts and unresolved rows; evidence classes
        remain separate. Empty/missing RPC evidence is reported explicitly, not interpreted
        as successful communication. Invalid capture paths or decode failures produce
        MCP tool errors. No target execution or evidence ingestion occurs."""
        return evidence_summary([_load(root, name)])
    @register_tool(annotations=_read_only("Get incident report"))
    def get_incident_report(names: CaptureNames, page: Page = 0) -> IncidentReportOutput:
        """Project a combined RPC incident report directly from named captures, without a stored incident ID.

        Use for ad hoc multi-capture analysis; get_incident_slice fetches an agent-declared
        incident already in SQLite, and get_evidence_summary is a single-capture inventory.
        Returns observed RPC events/process relations, static_candidates, unresolved and
        field availability. page slices only observed.rpc_events in batches of 200;
        total_rpc_events counts the full set. Inferences never become root-cause proof.
        Invalid captures/paths produce MCP tool errors; report files are not written."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        result = incident_report([collect_file(_safe_artifact(root, name)) for name in names])
        page = max(0, page)
        events = result["observed"]["rpc_events"]
        result["observed"]["rpc_events"] = events[page * 200:(page + 1) * 200]
        result["page"] = page
        result["page_size"] = 200
        result["total_rpc_events"] = len(events)
        return result
    @register_tool(annotations=_read_only("Get session manifest"))
    def get_session_manifest(names: CaptureNames, page: Page = 0) -> dict:
        """Build a runtime-session manifest with participants and separate cross-process evidence classes.

        Use to understand capture membership without an evidence store; list_sessions
        queries stored session summaries and get_process_participants omits the detailed
        RPC projection. Returns session, participants (paged), total_participants,
        observed, derived, static_candidates and unresolved. Only participants are paged;
        shared/inferred session identity does not establish causality. Conflicting or
        missing identity remains unresolved; invalid captures produce MCP tool errors."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        reports = [collect_file(_safe_artifact(root, name)) for name in names]
        result = session_manifest(reports, artifact_refs=names)
        page = max(0, page)
        participants = result["participants"]
        result["participants"] = participants[page * 200:(page + 1) * 200]
        result["page"] = page
        result["page_size"] = 200
        result["total_participants"] = len(participants)
        return result
    @register_tool(annotations=_read_only("Get process participants"))
    def get_process_participants(names: CaptureNames, page: Page = 0) -> dict:
        """List captured process identities, generations and collector status from named artifacts.

        Use for a participant inventory; get_session_manifest additionally includes RPC
        and derived relation projections. Returns session, status, participants (paged),
        total_participants and unresolved identity limits. OS PIDs may be reused; prefer
        declared runtime process IDs/generations when available. This reads captures,
        not SQLite or live processes. Missing/malformed captures or invalid paths
        produce MCP tool errors; an exhausted participant page returns an empty list."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        reports = [collect_file(_safe_artifact(root, name)) for name in names]
        result = process_participants(reports, artifact_refs=names)
        page = max(0, page)
        participants = result["participants"]
        result["participants"] = participants[page * 200:(page + 1) * 200]
        result["page"] = page
        result["page_size"] = 200
        result["total_participants"] = len(participants)
        return result
    @register_tool(annotations=_read_only("List sessions"))
    def list_sessions(db: StorePath = "evidence.sqlite3", start_ns: StartNs = None,
                      end_ns: EndNs = None, trust_state: TrustState = None,
                      page: Page = 0) -> SessionListOutput:
        """List runtime session summaries from an existing SQLite evidence store.

        Use after check_store to obtain session IDs before get_session; get_session_manifest
        instead constructs a manifest directly from named captures. Returns sessions,
        total, page and page_size, including an unassigned group when present.
        Time filters apply to captured process start times, not wall-clock time; trust
        filters require matching stored provenance. Empty matches yield an empty list.
        Invalid/missing stores or query failures produce MCP tool errors; no migration occurs."""
        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.list_sessions(start_ns=start_ns, end_ns=end_ns,
                                       trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @register_tool(annotations=_read_only("Get session"))
    def get_session(session_id: SessionId, db: StorePath = "evidence.sqlite3",
                    start_ns: StartNs = None, end_ns: EndNs = None,
                    trust_state: TrustState = None, page: Page = 0) -> dict:
        """Read one stored runtime session's artifacts, participants, evidence classes and provenance.

        Use an ID from list_sessions; null selects only artifacts without a session ID,
        not all sessions. get_incident_slice instead narrows to one declared incident.
        Returns session, artifacts (paged), total_artifacts, observed, derived,
        static_candidates, unresolved, hypotheses and provenance. Pagination applies
        to artifacts; evidence rows for selected artifacts are returned together.
        Time filters use captured process starts. An unknown ID gives empty artifacts;
        invalid stores/queries produce MCP tool errors without migration."""

        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.get_session(session_id, start_ns=start_ns, end_ns=end_ns,
                                     trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @register_tool(annotations=_read_only("Get provenance"))
    def get_provenance(db: StorePath = "evidence.sqlite3", session_id: SessionId = None,
                       artifact_id: Annotated[int | None, Field(ge=1, description="Exact numeric artifact row ID from get_session/get_incident_slice; null includes all matching artifact rows.")] = None, trust_state: ProvenanceTrust = None,
                       page: Page = 0) -> dict:
        """Read stored artifact hashes, build identities, trust reasons and verification declarations.

        Use to audit evidence origin before interpreting get_session/get_incident_slice;
        check_store checks database health instead. Returns provenance, total, page and
        page_size. Optional session/artifact/trust filters combine with AND; null session
        means all valid artifacts, unlike get_session. Quarantined artifacts are excluded.
        This reports stored verification, not a fresh re-hash or root-cause confidence.
        Invalid stores/query failures produce MCP tool errors; nothing is reindexed."""
        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.get_provenance(session_id=session_id, artifact_id=artifact_id,
                                        trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @register_tool(annotations=_read_only("List incidents"))
    def list_incidents(db: StorePath = "evidence.sqlite3", session_id: SessionId = None,
                       start_ns: StartNs = None, end_ns: EndNs = None,
                       trust_state: TrustState = None, page: Page = 0) -> IncidentListOutput:
        """List agent-declared incident summaries already persisted in a SQLite evidence store.

        Use to obtain incident IDs before get_incident_slice or get_unresolved;
        get_incident_report instead derives an ad hoc report from capture filenames.
        Returns incidents, total, page and page_size; time bounds filter incident
        first_seen_ns, not process-start times. Filters combine with AND and empty
        matches return an empty list. Failures return error.code=INCIDENT_QUERY_ERROR.
        The query neither declares incidents nor infers root cause; no migration occurs."""
        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.list_incidents(session_id=session_id, start_ns=start_ns,
                                            end_ns=end_ns, trust_state=trust_state, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @register_tool(annotations=_read_only("Get incident slice"))
    def get_incident_slice(incident_id: IncidentId, db: StorePath = "evidence.sqlite3",
                           trust_state: TrustState = None, page: Page = 0) -> IncidentSliceOutput:
        """Read artifact, process, RPC and source-reference evidence for one stored declared incident.

        Use an ID from list_incidents; get_incident_report analyzes capture filenames,
        while get_unresolved reads only gaps. Each call reads at most 200 linked artifacts;
        observed RPC payloads are capped at 1,000, so check event_truncated/event_total
        before treating them as complete. Stored source references are claims until
        get_source_evidence verifies them against a bundle. The query is read-only and
        does not migrate or repair the store; failures return INCIDENT_QUERY_ERROR."""

        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.get_incident_slice(incident_id, trust_state=trust_state, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @register_tool(annotations=_read_only("Get unresolved"))
    def get_unresolved(incident_id: IncidentId, db: StorePath = "evidence.sqlite3", page: Page = 0) -> dict:
        """Read only unresolved evidence and capture-limit rows for one stored incident.

        Use to explain missing proof after get_incident_slice; get_source_evidence
        instead verifies source references against a bundle. Returns incident, unresolved,
        page, page_size and total_artifacts. Pagination follows incident artifacts,
        not individual gap rows; one page may have no gaps while later pages do.
        Includes event_limit_reached when the incident projection truncates observations.
        Unknown IDs or invalid stores return error.code=INCIDENT_QUERY_ERROR;
        this does not repair missing evidence."""
        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.get_unresolved(incident_id, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @register_tool(annotations=_read_only("Get source evidence"))
    def get_source_evidence(incident_id: IncidentId, bundle: RequiredBundlePath,
                            db: StorePath = "evidence.sqlite3",
                            function_ids: Annotated[list[FunctionId] | None, Field(max_length=100, description="Up to 100 exact index IDs to request in addition to incident references. Null/empty uses stored references; IDs outside the bundle stay unresolved.")] = None, page: Page = 0) -> SourceEvidenceOutput:
        """Verify one stored incident's source references against a supplied immutable bundle.

        Use after get_incident_slice to obtain citation paths/line ranges/hashes; get_function_source
        looks up one indexed function without a stored incident. Returns citations,
        unresolved verification failures, resolved and pagination metadata. Null or empty
        function_ids uses declared references; an explicit list additionally requests
        those bundle functions. At most 100 IDs are accepted. Bundle paths/hashes must
        verify; missing/mismatched inputs return error.code=SOURCE_EVIDENCE_ERROR or
        unresolved rows. Current-worktree source is never substituted."""
        try:
            loaded = _bundle(root, bundle)
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.get_source_evidence(incident_id, loaded.root,
                                                 function_ids=function_ids, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "SOURCE_EVIDENCE_ERROR", "message": str(exc)}}
    @register_tool(annotations=_read_only("Discover artifacts"))
    def discover_artifacts(pattern: Annotated[str, Field(min_length=1, description="Root-relative recursive filename glob, e.g. fault-*.fault or *.json. No absolute paths or parent traversal; at most 10,000 matches.")] = "fault-*.fault", include_json: Annotated[bool, Field(description="With default fault-*.fault, also discover fault-*.json; with a custom pattern this does not add another glob.")] = False, page: Page = 0) -> ArtifactDiscoveryOutput:
        """Recursively discover and validate captures beneath the configured artifact root.

        Use first when filenames are unknown; query_artifact_index searches an existing
        SQLite index and open_fault decodes a selected capture. Returns artifacts (paged),
        total/count, valid and invalid counts; malformed files remain FAIL rows rather
        than disappearing. Scans at most 10,000 matches. include_json adds fault-*.json
        only with the default fault-*.fault pattern; use *.json for a custom JSON glob.
        Invalid roots/patterns or exceeding the scan limit produce MCP tool errors;
        no index is created."""
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("pattern must stay beneath the allowlisted root")
        result = inspect_spool(root, pattern=pattern, include_json=include_json, limit=10000)
        page = max(0, page)
        result["total"] = len(result["artifacts"])
        start = page * 200
        result["artifacts"] = result["artifacts"][start:start + 200]
        result["page"] = page
        result["page_size"] = 200
        return result
    @register_tool(annotations=_read_only("Discover bundles"))
    def discover_bundles(page: Page = 0) -> BundleDiscoveryOutput:
        """Find root-relative directories containing a bundle.json manifest candidate.

        Use before get_function_source, get_call_relations or get_source_evidence
        when the verified bundle path is unknown; discover_artifacts finds captures
        only. Returns candidate paths (paged), total and rejected symlink/non-file
        manifests. Discovery reads no manifest contents or hashes, so every result
        has verification=not_performed and may be malformed or tampered. The consuming
        source tool verifies the selected bundle before exposing data. Scans at most
        10,000 manifests; invalid roots or exceeding the limit produce MCP errors.
        Reads directory entries only and writes nothing."""
        try:
            return discover_bundle_paths(root, page=page)
        except BundleError as exc:
            raise ValueError(str(exc)) from exc
    @register_tool(annotations=_read_only("Query artifact index"))
    def query_artifact_index(name: Annotated[str, Field(min_length=1, description="Existing root-relative .sqlite or .db legacy artifact index created by artifact-index CLI; not a schema-v2 evidence store.")], trace_id: TraceId = None, correlation_id: CorrelationId = None, page: Page = 0) -> dict:
        """Query capture payloads from an existing legacy SQLite artifact metadata index.

        Use to filter previously indexed captures by exact trace/correlation IDs;
        discover_artifacts scans files and list_sessions queries a schema-v2 evidence
        store instead. Returns artifacts, count, page and page_size; count is the page
        length (no full total). Both ID filters combine with AND. Reads the DB in SQLite
        read-only/query-only mode; no CREATE TABLE or migration occurs. Missing files,
        wrong schemas or query failures produce MCP tool errors."""
        path = _relative(root, name)
        if root.resolve() not in path.parents or path.suffix not in (".sqlite", ".db") or not path.is_file(): raise ValueError("index is outside the allowlisted root or missing")
        index = ArtifactIndex(path, readonly=True)
        try:
            rows = index.query(trace_id=trace_id, correlation_id=correlation_id, limit=200, offset=max(page, 0) * 200)
            return {"schema": 1, "count": len(rows), "page": max(page, 0), "page_size": 200, "artifacts": rows}
        finally: index.close()
    @register_tool(annotations=_read_only("Resolve addresses"))
    def resolve_addresses(name: CaptureName, addresses: Annotated[list[Annotated[int, Field(ge=0, le=18446744073709551615)]], Field(max_length=1000, description="Up to 1,000 absolute runtime instruction addresses as JSON integers, e.g. [4198400]; preserve uint64 precision, do not pass hex strings or offsets.")], bundle: BundlePath = None, debug_directory: DebugDirectory = None) -> ResolveAddressesOutput:
        """Resolve captured instruction addresses against module Build IDs and available ELF symbols.

        Use to obtain verified symbol/function IDs before get_function_source;
        get_fault_flow instead resolves a bounded execution view. Returns items with
        per-address resolved status and explicit failure reasons; one unresolved item
        does not fail the others. Addresses are absolute runtime integers, not module
        offsets or hex strings. May read recorded local ELF paths and run local
        llvm-symbolizer with network lookup disabled; no target code is executed.
        An optional root-relative debug_directory supplies Build-ID-verified sidecar
        symbols from .build-id/xx/rest.debug. Invalid paths produce MCP tool errors;
        no network lookup or file modification occurs."""
        if len(addresses) > 1000: raise ValueError("maximum 1000 addresses")
        loaded = _bundle(root, bundle) if bundle else None
        return {"items": resolve_address_records(_load(root, name), addresses, bundle=loaded,
                                                 debug_directories=_debug_directories(root, debug_directory))}
    @register_tool(annotations=_read_only("Get function source"))
    def get_function_source(name: CaptureName, function_id: FunctionId,
                            bundle: RequiredBundlePath) -> FunctionSourceOutput:
        """Read exact source lines for one indexed function from a verified immutable bundle.

        Use a function ID from resolve_addresses or the bundle index; get_source_evidence
        verifies references for a stored incident, while get_call_relations returns
        static neighbors. Returns resolved, function_id, file, start_line, end_line and
        source text. A verified bundle is required. Capture decoding and bundle hashes are checked, but
        this lookup does not itself match the capture's Build ID to that function.
        Missing source/IDs or invalid inputs produce MCP tool errors."""
        _load(root, name)
        loaded = _bundle(root, bundle)
        return verified_function_source(function_id, loaded)
    @register_tool(annotations=_read_only("Get call relations"))
    def get_call_relations(name: CaptureName, function_id: FunctionId,
                           bundle: RequiredBundlePath,
                           direction: Annotated[Literal["outbound", "inbound"], Field(description="outbound: indexed callees/unresolved edges of this function; inbound: indexed callers whose edge targets this exact function ID.")] = "outbound") -> CallRelationsOutput:
        """Read inbound callers or outbound call candidates for one function in a verified static index.

        Use for source call hypotheses; get_fault_flow reconstructs recorded nesting and
        get_process_relations joins runtime IPC/RPC evidence. Returns function_id,
        direction, relations, evidence=static_index and bundle. Outbound includes unresolved
        edges; inbound includes indexed callers with matching callee IDs. A verified
        bundle is required. No runtime execution is proven, and
        capture/function Build-ID matching requires resolve_addresses. Missing IDs,
        unverified bundles or invalid directions produce MCP tool errors."""
        _load(root, name)
        loaded = _bundle(root, bundle)
        return verified_call_relations(function_id, direction, loaded)
    required_tools = set(capability_contract()["required_tools"])
    if not required_tools <= registered_tool_names:
        raise RuntimeError("MCP profile omitted one or more required capability tools")
    return app

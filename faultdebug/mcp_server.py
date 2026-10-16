"""Read-only MCP facade over captured artifacts."""
from inspect import cleandoc
from pathlib import Path
from typing import Annotated, Literal

from mcp.types import ToolAnnotations
from pydantic import Field
from .format import collect_file
from .bundle import BundleError, load_bundle
from .inspect import (resolve_addresses as resolve_address_records, thread_trace,
                      verified_call_relations, verified_function_source)
from .aggregate import ArtifactIndex, build_timeline, collect_artifacts
from .rpc import evidence_summary, incident_report, process_relations, rpc_trace
from .session import process_participants, session_manifest
from .discovery import inspect_spool
from .evidence_store import EvidenceStore, EvidenceStoreError
from .capabilities import get_capabilities as capability_contract

# Field metadata is exported in tools/list; docstring Args alone is not a schema.
CaptureName = Annotated[str, Field(min_length=1, description="Root-relative .fault or decoded .json capture path, e.g. fault-1234.fault; no absolute paths, '..', or escaping symlinks.")]
CaptureNames = Annotated[list[CaptureName], Field(max_length=1000, description="Capture paths beneath --root, up to 1,000; obtain paths from discover_artifacts. All captures are decoded before the result page is selected.")]
BundlePath = Annotated[str | None, Field(description="Verified bundle directory beneath --root, e.g. bundles/build-001. Omit/null for capture-only evidence; source citations require a bundle.")]
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


def _relative(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("paths must be relative to the allowlisted root without parent traversal")
    path = (root / relative).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        raise ValueError("path is outside the allowlisted root")
    return path


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

def make_server(root: Path):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("official mcp Python SDK is required") from exc
    app = FastMCP("faultdebug", instructions=(
        "Inspect existing local captures; no recording, ingestion, repair, or report-file writes. "
        "Start with get_capabilities and discover_artifacts; use open_fault/get_fault_flow for captures. "
        "For existing SQLite evidence, check_store then list_sessions/list_incidents and fetch a slice. "
        "Paths are relative to --root. Keep observed, derived, static_candidates, unresolved and hypotheses "
        "distinct. Source citations need a verified bundle; shared IDs/time order do not prove causality."
    ))

    def _tool(title: str):
        def register(fn):
            if fn.__doc__:
                fn.__doc__ = " ".join(cleandoc(fn.__doc__).split())
            app.add_tool(fn, annotations=_read_only(title))
            return fn
        return register

    @_tool("Get capabilities")
    def get_capabilities() -> dict:
        """Read supported capture/store versions, evidence classes, and query limits before
            choosing an inspection workflow. Use discover_artifacts to locate captures
            or check_store to inspect a database. This returns the server's bounded
            read-only contract; it does not validate a particular capture or bundle."""
        return capability_contract()
    @_tool("Check store")
    def check_store(db: StorePath = "evidence.sqlite3") -> dict:
        """Check the health and migration compatibility of one SQLite evidence store before
            querying it. Use get_provenance for stored trust records. An absent database
            is reported without creation; this tool never migrates or repairs it, and an
            invalid path returns STORE_PATH_INVALID."""
        try:
            path = _relative(root, db)
        except ValueError as exc:
            return {"schema": 2, "status": "error", "read_only": True,
                    "error": {"code": "STORE_PATH_INVALID", "message": str(exc)}}
        if root.resolve() not in path.parents or path.suffix not in (".sqlite", ".db", ".sqlite3"):
            return {"schema": 2, "status": "error", "read_only": True,
                    "error": {"code": "STORE_PATH_INVALID", "message": "evidence store is outside the allowlisted root"}}
        return EvidenceStore.inspect_health(path)
    @_tool("Open fault")
    def open_fault(name: CaptureName, bundle: BundlePath = None) -> dict:
        """Decode one capture's process, thread, crash, and integrity records for initial triage.
            Use after discover_artifacts; choose get_fault_flow for a bounded execution
            view or get_evidence_summary for a compact RPC inventory. Partial-capture
            loss flags remain visible; a supplied bundle is verified, but source lines
            are not returned."""
        report = _load(root, name)
        if bundle: report["bundle"] = {"path": str(_bundle(root, bundle).root), "verified": True}
        return report
    @_tool("Get thread trace")
    def get_thread_trace(name: CaptureName, tid: Annotated[int | None, Field(ge=0, description="Captured OS thread ID; null includes all thread generations. A reused ID can match more than one thread record.")] = None, page: Page = 0) -> dict:
        """Read raw thread records and retained function events from one capture. Use get_rpc_trace
            for semantic RPC observations or get_fault_flow for reconstructed nesting.
            Pagination slices thread records, not events; a reused OS thread ID can
            match multiple generations."""
        rows = thread_trace(_load(root, name), tid)
        return {"items": rows[page * 200:(page + 1) * 200], "page": page, "page_size": 200, "total": len(rows)}
    @_tool("Get fault flow")
    def get_fault_flow(name: CaptureName, bundle: BundlePath = None, max_events: Annotated[int, Field(ge=1, le=500, description="Maximum last retained pre-crash function events per thread (1–500); truncates the view, not the underlying capture.")] = 80) -> dict:
        """Build a bounded execution-flow view from one capture's recorded nesting, crash context,
            and gaps. Use get_thread_trace for raw records or get_incident_report to
            join RPC evidence across captures. max_events truncates this view, not the
            capture; source citations require a verified bundle."""
        from .fault_report import build_fault_report
        return build_fault_report(_load(root, name), bundle=_bundle(root, bundle) if bundle else None,
                                  max_events=max_events)
    @_tool("Get rpc trace")
    def get_rpc_trace(name: CaptureName, page: Page = 0) -> dict:
        """Read semantic RPC observations, static candidates, and unresolved limits from one
            capture. Use get_thread_trace for function events or get_process_relations
            to match endpoints across captures. Only observed RPC rows are paged;
            missing instrumentation stays unresolved rather than becoming an inferred
            edge."""
        decoded = rpc_trace(_load(root, name))
        page = max(0, page)
        decoded["total"] = len(decoded["observed"])
        start = page * 200
        decoded["observed"] = decoded["observed"][start:start + 200]
        decoded["page"] = page
        decoded["page_size"] = 200
        return decoded
    @_tool("Collect faults")
    def collect_faults(names: CaptureNames, trace_id: TraceId = None, correlation_id: CorrelationId = None, page: Page = 0) -> dict:
        """Filter named captures by exact trace/correlation IDs and group matching process and
            crash metadata. Use get_incident_report to include RPC evidence or
            query_artifact_index to search an existing SQLite metadata index. Supplied
            ID filters combine with AND; shared IDs group records but do not prove
            causality."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        paths = [_safe_artifact(root, name) for name in names]
        result = collect_artifacts(paths, trace_id=trace_id, correlation_id=correlation_id)
        start = max(0, page) * 200
        result["artifacts"] = result["artifacts"][start:start + 200]; result["page"] = max(0, page); result["page_size"] = 200
        return result
    @_tool("Get timeline")
    def get_timeline(names: CaptureNames) -> dict:
        """Order captured process-start, crash, and explicit IPC events across files while
            retaining ambiguous links. Use get_process_relations to match RPC endpoints
            across processes. Timestamps are monotonic and comparable only within
            compatible clock domains; temporal proximity never establishes causality."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        reports = [collect_file(_safe_artifact(root, name)) for name in names]
        return build_timeline(reports)
    @_tool("Get process relations")
    def get_process_relations(names: CaptureNames, page: Page = 0) -> dict:
        """Match explicit IPC/RPC endpoint evidence across captures into process relationships. Use
            get_timeline for event order or get_session_manifest for participants plus
            broader evidence classes. Shared PIDs, session IDs, or nearby timestamps
            never create an edge; missing endpoint evidence stays unresolved."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        result = process_relations([collect_file(_safe_artifact(root, name)) for name in names])
        page = max(0, page)
        result["total"] = len(result["observed"])
        start = page * 200
        result["observed"] = result["observed"][start:start + 200]
        result["page"] = page
        result["page_size"] = 200
        return result
    @_tool("Get evidence summary")
    def get_evidence_summary(name: CaptureName) -> dict:
        """Summarize RPC evidence counts and gaps for one capture without returning full histories.
            Use before get_rpc_trace or get_fault_flow; choose get_incident_report to
            combine captures. Empty RPC evidence remains unknown and is not treated as
            successful communication."""
        return evidence_summary([_load(root, name)])
    @_tool("Get incident report")
    def get_incident_report(names: CaptureNames, page: Page = 0) -> dict:
        """Build an ad hoc multi-capture RPC incident report from capture names without a stored
            incident ID. Use get_incident_slice for an incident already declared in
            SQLite or get_evidence_summary for one capture. Only observed RPC events are
            paged; inferred relations are not root-cause proof."""
        if len(names) > 1000: raise ValueError("maximum 1000 artifacts")
        result = incident_report([collect_file(_safe_artifact(root, name)) for name in names])
        page = max(0, page)
        events = result["observed"]["rpc_events"]
        result["observed"]["rpc_events"] = events[page * 200:(page + 1) * 200]
        result["page"] = page
        result["page_size"] = 200
        result["total_rpc_events"] = len(events)
        return result
    @_tool("Get session manifest")
    def get_session_manifest(names: CaptureNames, page: Page = 0) -> dict:
        """Build a session manifest directly from captures, with participants and separate
            observed, derived, static, and unresolved relations. Use list_sessions for
            stored summaries or get_process_participants for an identity-only inventory.
            Shared or inferred session identity does not establish causality."""
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
    @_tool("Get process participants")
    def get_process_participants(names: CaptureNames, page: Page = 0) -> dict:
        """List process identities, generations, and collector status from named captures. Use
            get_session_manifest when RPC and relation projections are needed, or
            list_sessions for stored summaries. PIDs may be reused, so prefer declared
            runtime IDs and generations; this reads captures, not SQLite or live
            processes."""
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
    @_tool("List sessions")
    def list_sessions(db: StorePath = "evidence.sqlite3", start_ns: StartNs = None,
                      end_ns: EndNs = None, trust_state: TrustState = None,
                      page: Page = 0) -> dict:
        """List session summaries from an existing SQLite evidence store. Use after check_store;
            use get_session to read one session or get_session_manifest to build a
            manifest from captures. Time bounds apply to captured process starts, trust
            filters require stored provenance, and no migration occurs."""
        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.list_sessions(start_ns=start_ns, end_ns=end_ns,
                                       trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @_tool("Get session")
    def get_session(session_id: SessionId, db: StorePath = "evidence.sqlite3",
                    start_ns: StartNs = None, end_ns: EndNs = None,
                    trust_state: TrustState = None, page: Page = 0) -> dict:
        """Read artifacts, participants, evidence classes, and provenance for one stored session.
            Obtain IDs from list_sessions; null selects only unassigned artifacts. Use
            get_incident_slice for a declared incident. Pagination slices artifacts,
            while evidence for selected artifacts is returned together."""

        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.get_session(session_id, start_ns=start_ns, end_ns=end_ns,
                                     trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @_tool("Get provenance")
    def get_provenance(db: StorePath = "evidence.sqlite3", session_id: SessionId = None,
                       artifact_id: Annotated[int | None, Field(ge=1, description="Exact numeric artifact row ID from get_session/get_incident_slice; null includes all matching artifact rows.")] = None, trust_state: ProvenanceTrust = None,
                       page: Page = 0) -> dict:
        """Read stored artifact hashes, build identities, trust reasons, and verification
            declarations. Use to audit origin before interpreting a session or incident;
            check_store inspects database health instead. This reports stored
            verification, not a fresh re-hash or root-cause confidence, and does not
            reindex."""
        store = EvidenceStore(_safe_store(root, db), readonly=True)
        try:
            return store.get_provenance(session_id=session_id, artifact_id=artifact_id,
                                        trust_state=trust_state, page=page)
        except (EvidenceStoreError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            store.close()
    @_tool("List incidents")
    def list_incidents(db: StorePath = "evidence.sqlite3", session_id: SessionId = None,
                       start_ns: StartNs = None, end_ns: EndNs = None,
                       trust_state: TrustState = None, page: Page = 0) -> dict:
        """List agent-declared incident summaries already persisted in SQLite. Use returned IDs
            with get_incident_slice or get_unresolved; choose get_incident_report for an
            ad hoc view of capture files. Time bounds filter incident first_seen_ns.
            This query neither declares incidents nor infers root cause."""
        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.list_incidents(session_id=session_id, start_ns=start_ns,
                                            end_ns=end_ns, trust_state=trust_state, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @_tool("Get incident slice")
    def get_incident_slice(incident_id: IncidentId, db: StorePath = "evidence.sqlite3",
                           trust_state: TrustState = None, page: Page = 0) -> dict:
        """Read one declared incident's stored artifact, process, RPC, and source-reference
            evidence. Use an incident ID from list_incidents; get_incident_report builds
            an ad hoc view from capture names instead. Event output may be capped at
            1,000; check event_truncated/event_total before claiming completeness.
            Source references are not verified citations."""

        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.get_incident_slice(incident_id, trust_state=trust_state, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @_tool("Get unresolved")
    def get_unresolved(incident_id: IncidentId, db: StorePath = "evidence.sqlite3", page: Page = 0) -> dict:
        """Read only unresolved evidence and capture-limit rows for one stored incident. Use after
            get_incident_slice to explain remaining gaps; use get_source_evidence to
            verify source references against a bundle. Pagination follows incident
            artifacts, so inspect later pages; this tool does not repair missing
            evidence."""
        try:
            store = EvidenceStore(_safe_store(root, db), readonly=True)
            try:
                return store.get_unresolved(incident_id, page=page)
            finally:
                store.close()
        except (EvidenceStoreError, ValueError) as exc:
            return {"schema": 2, "error": {"code": "INCIDENT_QUERY_ERROR", "message": str(exc)}}
    @_tool("Get source evidence")
    def get_source_evidence(incident_id: IncidentId, bundle: RequiredBundlePath,
                            db: StorePath = "evidence.sqlite3",
                            function_ids: Annotated[list[FunctionId] | None, Field(max_length=100, description="Up to 100 exact index IDs to request in addition to incident references. Null/empty uses stored references; IDs outside the bundle stay unresolved.")] = None, page: Page = 0) -> dict:
        """Verify stored incident source references against a supplied immutable bundle and return
            citation paths, line ranges, and hashes. Use after get_incident_slice;
            choose get_function_source for one indexed function without an incident.
            Null/empty function_ids uses declared references; current-worktree files are
            never substituted."""
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
    @_tool("Discover artifacts")
    def discover_artifacts(pattern: Annotated[str, Field(min_length=1, description="Root-relative recursive filename glob, e.g. fault-*.fault or *.json. No absolute paths or parent traversal; at most 10,000 matches.")] = "fault-*.fault", include_json: Annotated[bool, Field(description="With default fault-*.fault, also discover fault-*.json; with a custom pattern this does not add another glob.")] = False, page: Page = 0) -> dict:
        """Find and validate capture files recursively beneath the configured artifact root. Use
            first when filenames are unknown; choose query_artifact_index for an
            existing index or open_fault to decode one capture. Malformed files remain
            invalid result rows, and scans are capped at 10,000 matches."""
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
    @_tool("Query artifact index")
    def query_artifact_index(name: Annotated[str, Field(min_length=1, description="Existing root-relative .sqlite or .db legacy artifact index created by artifact-index CLI; not a schema-v2 evidence store.")], trace_id: TraceId = None, correlation_id: CorrelationId = None, page: Page = 0) -> dict:
        """Search an existing legacy SQLite capture-metadata index by exact trace/correlation IDs.
            Use discover_artifacts to scan files or list_sessions to query a schema-v2
            evidence store. Filters combine with AND; count reports this page's rows,
            and the database is opened read-only."""
        path = _relative(root, name)
        if root.resolve() not in path.parents or path.suffix not in (".sqlite", ".db") or not path.is_file(): raise ValueError("index is outside the allowlisted root or missing")
        index = ArtifactIndex(path, readonly=True)
        try:
            rows = index.query(trace_id=trace_id, correlation_id=correlation_id, limit=200, offset=max(page, 0) * 200)
            return {"schema": 1, "count": len(rows), "page": max(page, 0), "page_size": 200, "artifacts": rows}
        finally: index.close()
    @_tool("Resolve addresses")
    def resolve_addresses(name: CaptureName, addresses: Annotated[list[Annotated[int, Field(ge=0, le=18446744073709551615)]], Field(max_length=1000, description="Up to 1,000 absolute runtime instruction addresses as JSON integers, e.g. [4198400]; preserve uint64 precision, do not pass hex strings or offsets.")], bundle: BundlePath = None) -> dict:
        """Resolve absolute captured instruction addresses using module Build IDs and available ELF
            symbols. Use returned function IDs with get_function_source; choose
            get_fault_flow for a bounded view of a capture. Addresses are JSON integers,
            not hex strings or offsets; unresolved items retain individual reasons, and
            local symbolization performs no network lookup or target execution."""
        if len(addresses) > 1000: raise ValueError("maximum 1000 addresses")
        loaded = _bundle(root, bundle) if bundle else None
        return {"items": resolve_address_records(_load(root, name), addresses, bundle=loaded)}
    @_tool("Get function source")
    def get_function_source(name: CaptureName, function_id: FunctionId, bundle: Annotated[str | None, Field(description="Verified root-relative source bundle directory; MUST be supplied for this lookup despite the nullable default. Missing bundle fails the call.")] = None) -> dict:
        """Read exact source lines for one function from a verified immutable bundle. Use a
            function ID from resolve_addresses or the bundle index; choose
            get_source_evidence for stored incident references or get_call_relations for
            static neighbors. A bundle is required; this lookup does not match the
            capture Build ID to the function."""
        _load(root, name)
        loaded = _bundle(root, bundle) if bundle else None
        if loaded is None: raise ValueError("bundle is required for verified source lookup")
        return verified_function_source(function_id, loaded)
    @_tool("Get call relations")
    def get_call_relations(name: CaptureName, function_id: FunctionId, direction: Annotated[Literal["outbound", "inbound"], Field(description="outbound: indexed callees/unresolved edges of this function; inbound: indexed callers whose edge targets this exact function ID.")] = "outbound", bundle: Annotated[str | None, Field(description="Verified root-relative source bundle directory; MUST be supplied for this lookup despite the nullable default. Missing bundle fails the call.")] = None) -> dict:
        """Read inbound callers or outbound call hypotheses for one function from a verified static
            index. Use get_fault_flow for recorded runtime nesting or
            get_process_relations for IPC/RPC links. A verified bundle is required;
            outbound results can include unresolved edges, and no runtime execution or
            capture/function Build-ID match is proven."""
        _load(root, name)
        loaded = _bundle(root, bundle) if bundle else None
        if loaded is None: raise ValueError("bundle is required for verified call relations")
        return verified_call_relations(function_id, direction, loaded)
    return app

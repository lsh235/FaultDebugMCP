"""Typed response contracts for the stable first-line MCP inspection tools."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OutputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ArtifactVersions(OutputModel):
    fdar: Annotated[int, Field(description="Supported FDAR capture format version.")]
    shared_memory_abi: Annotated[int, Field(description="Supported native recorder shared-memory ABI version.")]
    semantic_rpc: Annotated[int, Field(description="Supported semantic RPC record version.")]
    session_manifest: Annotated[int, Field(description="Supported runtime session manifest version.")]
    incident_query: Annotated[int, Field(description="Supported incident query-store version.")]


class HttpContextContract(OutputModel):
    schema_: Annotated[int, Field(alias="schema", description="HTTP context contract schema version.")]
    traceparent_versions: list[str]
    trace_id_bits: int
    numeric_rpc_mapping: str
    span_identity_is_native_causality: bool
    tracestate: bool
    clock_provenance: str
    cross_clock_deadlines: bool
    retry_attempt_mapping: str
    retry_identity_is_native_causality: bool


class RetryLedgerContract(OutputModel):
    schema_: Annotated[int, Field(alias="schema", description="Retry ledger contract schema version.")]
    storage: str
    atomic_scope: str
    external_side_effects_exactly_once: bool
    automatic_retries: bool


class KeyedLockContract(OutputModel):
    scope: str
    bounded_active_keys: bool
    distributed_lock: bool


class StoreVersions(OutputModel):
    base_schema: int
    incident_tables: str


class CapabilityLimits(OutputModel):
    artifacts_per_query: int
    page_size: int
    max_source_function_ids: int
    max_incident_observed_events: int
    max_rpc_events: int
    max_artifact_id_length: int
    fault_flow_events_per_thread: int
    service_flow_total_input_bytes: int
    service_flow_file_bytes: int
    service_flow_files: int
    service_flow_captures: int
    service_flow_scan_entries: int
    service_flow_application_lines: int
    service_flow_page_size: int
    service_flow_response_bytes: int


class PlatformToolchain(OutputModel):
    platform: str
    runtime: str
    python: str
    clang: str
    build: list[str]
    mcp_transport: str


class CapabilitySecurity(OutputModel):
    local_artifacts_only: bool
    remote_transport: bool
    encryption: bool
    source_lookup: str


class CapabilitiesOutput(OutputModel):
    """Versioned product, evidence, platform and safety contract."""

    schema_: Annotated[int, Field(alias="schema", description="Capabilities response schema version.")]
    contract_version: Annotated[str, Field(description="Semantic version of the capabilities contract.")]
    artifact_versions: ArtifactVersions
    http_context: HttpContextContract
    retry_ledger: RetryLedgerContract
    keyed_lock: KeyedLockContract
    store_versions: StoreVersions
    required_tools: Annotated[list[str], Field(description="Required MCP tools actually exposed by the selected profile.")]
    additional_tools: Annotated[list[str], Field(description="Optional MCP tools actually exposed by the selected profile.")]
    v09_tools: Annotated[list[str], Field(description="Versioned incident tools actually exposed by the selected profile.")]
    mcp_tool_profile: Annotated[Literal["full", "focused"], Field(description="Active MCP catalog profile.")]
    exposed_tools: Annotated[list[str], Field(description="Exact MCP tool names registered for the active profile.")]
    limits: CapabilityLimits
    evidence_classes: list[str]
    supported_signals: list[str]
    platform_toolchain: PlatformToolchain
    security: CapabilitySecurity


class StoreError(OutputModel):
    code: Literal["STORE_PATH_INVALID", "STORE_MISSING", "STORE_UNREADABLE"]
    message: str


class StoreBaseSchema(OutputModel):
    compatible: bool
    required: list[str]
    missing: list[str]


class StoreIncidentTables(OutputModel):
    status: Literal["available", "needs_writable_upgrade"]
    required: list[str]
    missing: list[str]


class StoreMigration(OutputModel):
    required: bool
    legacy_artifact_index: bool
    action: str | None


class StoreCheckOutput(OutputModel):
    schema_: Annotated[Literal[2], Field(alias="schema", description="SQLite evidence-store schema version.")]
    status: Literal["healthy", "compatible_additive_upgrade", "migration_required", "error"]
    read_only: Literal[True]
    path: str | None = None
    user_version: int | None = None
    base_schema: StoreBaseSchema | None = None
    incident_tables: StoreIncidentTables | None = None
    migration: StoreMigration | None = None
    integrity: str | None = None
    error: StoreError | None = None


class ArtifactCaptureValid(OutputModel):
    path: str
    status: Literal["PASS"]
    sha256: str
    pid: int | None
    collector: dict[str, Any]
    context: dict[str, Any]


class ArtifactCaptureInvalid(OutputModel):
    path: str
    status: Literal["FAIL"]
    error: str


ArtifactCapture = Annotated[
    ArtifactCaptureValid | ArtifactCaptureInvalid,
    Field(discriminator="status"),
]


class ArtifactDiscoveryOutput(OutputModel):
    schema_: Annotated[Literal[1], Field(alias="schema", description="Artifact discovery response schema version.")]
    root: str
    count: int
    valid: int
    invalid: int
    artifacts: list[ArtifactCapture]
    total: int
    page: int
    page_size: Literal[200]


class BundleCandidate(OutputModel):
    path: str
    status: Literal["candidate", "rejected"]
    manifest_bytes: int | None
    verification: Literal["not_performed"]
    reason: Literal[
        "symlink_manifest", "not_regular_manifest", "outside_root", "unavailable_manifest"
    ] | None = None


class BundleDiscoveryOutput(OutputModel):
    schema_: Annotated[Literal[1], Field(alias="schema", description="Bundle discovery response schema version.")]
    status: Literal["PASS"]
    bundles: list[BundleCandidate]
    total: int
    candidate_count: int
    rejected_count: int
    page: int
    page_size: int
    next_page: int | None
    verification: Literal["not_performed"]


class FunctionSourceOutput(OutputModel):
    """Source lines read from a verified immutable bundle index."""

    resolved: Annotated[Literal[True], Field(description="True only when the indexed function and verified source lines were found.")]
    function_id: Annotated[str, Field(description="Exact function identifier from the verified bundle index.")]
    bundle: Annotated[str, Field(description="Root path of the verified immutable source bundle.")]
    file: Annotated[str, Field(description="Verified source file path containing the indexed function.")]
    start_line: Annotated[int, Field(description="One-based first source line returned.")]
    end_line: Annotated[int, Field(description="One-based last source line returned, inclusive.")]
    source: Annotated[str, Field(description="Exact returned source text for the indexed function range.")]


class IncidentListItem(OutputModel):
    """One persisted declared incident row from the read-only store query."""

    incident_id: Annotated[str, Field(description="Agent-declared incident identifier used by incident evidence tools.")]
    session_id: Annotated[str | None, Field(description="Declared runtime session identifier; null means none was recorded.")]
    trigger_process_id: Annotated[str | None, Field(description="Declared triggering process identifier, when recorded.")]
    trigger_signal: Annotated[int | None, Field(description="Recorded trigger signal number, when supplied.")]
    status: Annotated[str | None, Field(description="Application-declared incident status; not inferred by the store.")]
    phase: Annotated[str | None, Field(description="Application-declared incident phase; not inferred by the store.")]
    partial: Annotated[Literal[0, 1] | None, Field(description="SQLite integer flag: 1 means declared partial, 0 means declared complete, null means not supplied.")]
    first_seen_ns: Annotated[int | None, Field(description="Earliest captured monotonic timestamp for this incident, not wall-clock time.")]
    trust_state: Annotated[Literal["verified", "unresolved"], Field(description="Stored artifact provenance state used for the incident projection.")]
    artifact_count: Annotated[int, Field(description="Number of distinct valid artifact rows linked to the incident.")]


class IncidentListSuccess(OutputModel):
    """Paginated list of stored declared incident summaries."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="Evidence-store schema version.")]
    incidents: Annotated[list[IncidentListItem], Field(description="Incident summaries in this page, ordered by recorded first-seen time and ID.")]
    total: Annotated[int, Field(description="Number of matching incident IDs across all pages.")]
    page: Annotated[int, Field(description="Zero-based page returned.")]
    page_size: Annotated[int, Field(description="Maximum incident summaries per page.")]


class IncidentListErrorDetail(OutputModel):
    code: Literal["INCIDENT_QUERY_ERROR"]
    message: str


class IncidentListError(OutputModel):
    """Structured query failure returned by list_incidents."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="Evidence-store schema version.")]
    error: Annotated[IncidentListErrorDetail, Field(description="Read-only incident query error; no store mutation was performed.")]


IncidentListOutput = Annotated[
    IncidentListSuccess | IncidentListError,
    Field(description="Either a paginated incident list or the stable INCIDENT_QUERY_ERROR response."),
]


class IncidentSliceRow(OutputModel):
    """SQLite-backed row with forward-compatible columns."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class IncidentSliceIncident(IncidentSliceRow):
    incident_id: Annotated[str, Field(description="Agent-declared incident ID used to group stored evidence.")]
    session_id: Annotated[str | None, Field(description="Declared session ID, when recorded.")] = None
    trigger_process_id: Annotated[str | None, Field(description="Declared triggering process ID, when recorded.")] = None
    trigger_signal: Annotated[int | None, Field(description="Declared signal number, when recorded.")] = None
    status: Annotated[str | None, Field(description="Producer-declared incident status; not inferred by the store.")] = None
    phase: Annotated[str | None, Field(description="Producer-declared incident phase; not inferred by the store.")] = None
    partial: Annotated[int | None, Field(description="Stored SQLite partial flag; copied, not reinterpreted.")] = None
    first_seen_ns: Annotated[int | None, Field(description="Earliest stored captured monotonic timestamp; not wall-clock time.")] = None
    trust_state: Annotated[str, Field(description="Stored provenance summary for the incident; not a root-cause confidence score.")]
    payload: Annotated[str, Field(description="Original incident metadata serialized as JSON text in the evidence store.")]


class IncidentSliceArtifact(IncidentSliceRow):
    artifact_id: Annotated[int, Field(ge=1, description="Persistent evidence-store artifact row ID.")]
    path: Annotated[str, Field(description="Stored artifact path at ingestion time.")]
    sha256: Annotated[str, Field(description="SHA-256 recorded at ingestion; this query does not re-hash the artifact.")]
    size: Annotated[int, Field(ge=0, description="Artifact byte size recorded at ingestion.")]
    ingested_ns: Annotated[int, Field(description="Evidence-store ingestion timestamp in nanoseconds.")]
    session_id: Annotated[str | None, Field(description="Declared session ID, when present.")] = None
    identity_source: Annotated[str, Field(description="Source label used by the store when assigning session identity.")]
    status: Annotated[str, Field(description="Stored artifact validity state; this projection selects valid artifacts.")]
    trust_state: Annotated[str, Field(description="Stored provenance state, not a fresh verification result.")]
    collector_ok: Annotated[int | None, Field(description="Collector success flag recorded at ingestion, when supplied.")] = None
    collector_status: Annotated[str | None, Field(description="Collector status copied from the capture, when supplied.")] = None
    collector_phase: Annotated[str | None, Field(description="Collector phase copied from the capture, when supplied.")] = None
    collector_partial: Annotated[int | None, Field(description="Collector partial flag recorded at ingestion, when supplied.")] = None
    process_start_ns: Annotated[int | None, Field(description="Captured process-start monotonic timestamp, when supplied.")] = None
    target_returncode: Annotated[int | None, Field(description="Recorded target return code, when supplied.")] = None
    target_signal: Annotated[int | None, Field(description="Recorded target signal, when supplied.")] = None
    incident_evidence_class: Annotated[str | None, Field(description="Producer-declared evidence class attached to this incident-artifact link.")] = None


class IncidentSliceParticipant(IncidentSliceRow):
    process_row_id: Annotated[int, Field(description="Persistent process-participant row ID.")]
    artifact_id: Annotated[int, Field(description="Artifact row ID owning this participant.")]
    participant_id: Annotated[str, Field(description="Session-manifest participant identity; not inferred from a PID.")]
    session_id: Annotated[str | None, Field(description="Declared session ID, when present.")] = None
    runtime_process_id: Annotated[str | None, Field(description="Declared runtime process identity, when present.")] = None
    process_generation: Annotated[int | None, Field(description="Declared process generation, when present.")] = None
    parent_process_id: Annotated[str | None, Field(description="Declared parent process identity, when present.")] = None
    role: Annotated[str | None, Field(description="Producer-declared participant role, when present.")] = None
    pid: Annotated[int | None, Field(description="Recorded operating-system process ID; not a persistent identity.")] = None
    parent_pid: Annotated[int | None, Field(description="Recorded parent process ID; not a persistent identity.")] = None
    executable: Annotated[str | None, Field(description="Recorded executable path, when present.")] = None
    start_monotonic_ns: Annotated[int | None, Field(description="Recorded process-start monotonic timestamp, when present.")] = None
    trust_state: Annotated[str, Field(description="Stored provenance state for the owning artifact.")]
    process_id: Annotated[str | None, Field(description="Compatibility alias copied from runtime_process_id.")] = None


class IncidentSliceSourceReference(IncidentSliceRow):
    source_reference_id: Annotated[int, Field(description="Persistent saved-source-reference row ID.")]
    incident_id: Annotated[str | None, Field(description="Associated declared incident ID, when stored.")] = None
    artifact_id: Annotated[int, Field(description="Artifact row ID associated with this reference.")]
    function_id: Annotated[str | None, Field(description="Producer-declared function ID, when supplied.")] = None
    bundle_path: Annotated[str | None, Field(description="Stored bundle path claim; it has not been verified by this query.")] = None
    file: Annotated[str | None, Field(description="Producer-declared source file path, when supplied.")] = None
    line_start: Annotated[int | None, Field(description="Producer-declared one-based start line, when supplied.")] = None
    line_end: Annotated[int | None, Field(description="Producer-declared inclusive end line, when supplied.")] = None
    sha256: Annotated[str | None, Field(description="Producer-declared file hash, when supplied; not re-checked here.")] = None
    payload: Annotated[str, Field(description="Original source-reference metadata serialized as JSON text.")]


class IncidentSliceObserved(OutputModel):
    rpc_events: Annotated[list[Any], Field(description="Stored observed RPC payloads for artifacts on this page; producer fields are preserved as supplied.")]
    peer_snapshots: Annotated[list[Any], Field(description="Stored peer-snapshot payloads for artifacts on this page; producer fields are preserved as supplied.")]


class IncidentSliceDerived(OutputModel):
    process_relations: Annotated[list[Any], Field(description="Stored derived process-relation payloads; they remain separate from direct observations.")]


class IncidentSliceSuccess(OutputModel):
    """One page of stored incident evidence with producer payloads kept open."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="Evidence-store schema version.")]
    incident: Annotated[IncidentSliceIncident, Field(description="Stored agent-declared incident row; status and phase are producer supplied.")]
    artifacts: Annotated[list[IncidentSliceArtifact], Field(description="Valid artifact rows selected for this page, with stored ingestion and provenance metadata.")]
    participants: Annotated[list[IncidentSliceParticipant], Field(description="Stored process-participant rows associated with artifacts on this page.")]
    observed: Annotated[IncidentSliceObserved, Field(description="Observed RPC and peer-snapshot payloads; their fields are producer-defined.")]
    derived: Annotated[IncidentSliceDerived, Field(description="Derived relation payloads, kept distinct from observed evidence.")]
    static_candidates: Annotated[list[Any], Field(description="Stored static candidate payloads; they do not prove runtime execution.")]
    unresolved: Annotated[list[Any], Field(description="Stored evidence gaps and query-limit rows; reasons vary by producer and limit.")]
    hypotheses: Annotated[list[Any], Field(description="Stored producer hypotheses; these are not verified conclusions.")]
    source_references: Annotated[list[IncidentSliceSourceReference], Field(description="Stored source-reference claims; use get_source_evidence to verify them against an immutable bundle.")]
    page: Annotated[int, Field(ge=0, description="Zero-based page of incident artifacts.")]
    page_size: Annotated[Literal[200], Field(description="Maximum number of incident artifacts on one page.")]
    total_artifacts: Annotated[int, Field(ge=0, description="Total valid artifacts linked to this incident before pagination.")]
    event_total: Annotated[int, Field(ge=0, description="Observed RPC event count for selected artifacts before the response cap.")]
    observed_event_total: Annotated[int | None, Field(ge=0, description="Observed RPC event count; omitted by text JSON when this page selects no artifacts.")] = None
    event_truncated: Annotated[bool, Field(description="True when observed RPC rows were capped at 1,000; false does not prove capture completeness.")]


class IncidentSliceErrorDetail(OutputModel):
    code: Annotated[Literal["INCIDENT_QUERY_ERROR"], Field(description="Stable payload-level code for missing incidents, invalid stores or unavailable incident tables.")]
    message: Annotated[str, Field(description="Store or query detail; no evidence rows were returned.")]


class IncidentSliceError(OutputModel):
    """Existing structured query failure returned by get_incident_slice."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="Evidence-store schema version.")]
    error: Annotated[IncidentSliceErrorDetail, Field(description="Read-only incident-slice query error; no store mutation was performed.")]


IncidentSliceOutput = Annotated[
    IncidentSliceSuccess | IncidentSliceError,
    Field(description="Either one page of stored incident evidence or the stable INCIDENT_QUERY_ERROR response."),
]


class SessionListItem(OutputModel):
    """One aggregated runtime-session row from the read-only store query."""

    session_id: Annotated[str | None, Field(description="Runtime session ID; null denotes the unassigned artifact group, not all sessions.")]
    first_start_ns: Annotated[int | None, Field(description="Earliest captured process-start monotonic timestamp in this group; null means none was recorded.")]
    artifact_count: Annotated[int, Field(ge=1, description="Number of valid artifacts in this session or unassigned group.")]
    verified_count: Annotated[int, Field(ge=0, description="Number of valid artifacts with verified provenance; it does not count processes.")]
    identity_source: Annotated[str, Field(description="Lexicographically first stored session-identity source label among matching artifacts; open string.")]
    trust_state: Annotated[Literal["verified", "unresolved"], Field(description="Aggregate provenance state; verified only when all listed artifacts are verified.")]


class SessionListOutput(OutputModel):
    """Paginated session summaries from the existing schema-v2 evidence store."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="SQLite evidence-store schema version.")]
    sessions: Annotated[list[SessionListItem], Field(description="Matching session summaries, including a null-session group for unassigned artifacts.")]
    total: Annotated[int, Field(ge=0, description="Number of matching session groups across all pages.")]
    page: Annotated[int, Field(ge=0, description="Zero-based page returned.")]
    page_size: Annotated[int, Field(ge=1, description="Maximum session summaries in this page.")]


class SourceEvidenceCitation(OutputModel):
    """One source citation checked against the supplied immutable bundle."""

    incident_id: Annotated[str, Field(description="Exact persisted incident ID whose source reference was checked.")]
    artifact_id: Annotated[int | None, Field(description="Stored artifact row ID for this reference; null means the function ID was requested directly.")]
    function_id: Annotated[str | None, Field(description="Exact indexed function ID, or null for a file-and-line reference.")]
    bundle: Annotated[str, Field(description="Resolved root path of the immutable bundle whose manifest and source were verified.")]
    file: Annotated[str, Field(description="Bundle-relative source file path; this is a verified citation, not source text.")]
    line_start: Annotated[int, Field(ge=1, description="One-based first line of the verified citation range.")]
    line_end: Annotated[int, Field(ge=1, description="One-based inclusive last line of the verified citation range.")]
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$", description="SHA-256 of the source file bytes verified for this citation.")]
    manifest_sha256: Annotated[str | None, Field(description="SHA-256 recorded for this file in the verified bundle manifest, when present.")]
    verified: Annotated[Literal[True], Field(description="True only after bundle membership, source hash and line bounds pass verification.")]


class SourceEvidenceUnresolved(OutputModel):
    """A declared/requested source reference that could not be verified."""

    function_id: Annotated[str | None, Field(description="Requested or recorded function ID; null means no ID was supplied.")]
    reason: Annotated[Literal["source_citation_unresolved"], Field(description="Stable reason category; inspect message for the specific verification failure.")]
    message: Annotated[str, Field(description="Why source lookup or citation verification failed; not proof that the source is defective.")]


class SourceEvidenceSuccess(OutputModel):
    """Verified source citations and unresolved references for an incident."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="SQLite evidence-store schema version.")]
    incident_id: Annotated[str, Field(description="Exact incident whose saved or explicitly requested function references were checked.")]
    bundle: Annotated[str, Field(description="Resolved immutable bundle root used for verification.")]
    citations: Annotated[list[SourceEvidenceCitation], Field(description="Verified citation rows on this page; source text remains a separate get_function_source result.")]
    unresolved: Annotated[list[SourceEvidenceUnresolved], Field(description="Saved or requested references not verified; these can remain visible on every page.")]
    total: Annotated[int, Field(ge=0, description="Number of verified citations across all pages, excluding unresolved references.")]
    page: Annotated[int, Field(ge=0, description="Zero-based citation page returned.")]
    page_size: Annotated[int, Field(ge=1, description="Maximum verified citations per page.")]
    resolved: Annotated[bool, Field(description="True only when this page has at least one verified citation and no unresolved references.")]
    file: Annotated[str | None, Field(description="Compatibility convenience field copied from the sole citation when exactly one is returned; otherwise null.")] = None
    line_start: Annotated[int | None, Field(description="One-based first line copied from the sole citation when exactly one is returned; otherwise null.")] = None
    line_end: Annotated[int | None, Field(description="One-based inclusive last line copied from the sole citation when exactly one is returned; otherwise null.")] = None
    sha256: Annotated[str | None, Field(description="Source hash copied from the sole citation when exactly one is returned; otherwise null.")] = None
    function_id: Annotated[str | None, Field(description="Function ID copied from the sole citation when exactly one is returned; otherwise null.")] = None


class SourceEvidenceErrorDetail(OutputModel):
    code: Annotated[Literal["SOURCE_EVIDENCE_ERROR"], Field(description="Stable payload-level code for store or bundle failures.")]
    message: Annotated[str, Field(description="Failure detail; the tool did not return verified citations.")]


class SourceEvidenceError(OutputModel):
    """Store or bundle failure represented by the existing tool payload."""

    schema_: Annotated[Literal[2], Field(alias="schema", description="SQLite evidence-store schema version.")]
    error: Annotated[SourceEvidenceErrorDetail, Field(description="Source-evidence query or bundle error; no source text was returned.")]


SourceEvidenceOutput = Annotated[
    SourceEvidenceSuccess | SourceEvidenceError,
    Field(description="Either verified incident source citations or the stable SOURCE_EVIDENCE_ERROR payload."),
]


class RpcTraceEvent(OutputModel):
    """One normalized semantic-RPC observation; missing source fields stay absent or null."""

    event_index: Annotated[int, Field(ge=0, description="Zero-based index in the decoded RPC extension before time/sequence ordering.")]
    sequence: Annotated[int | None, Field(ge=0, description="Native publication sequence when recorded; it is not a causal proof.")] = None
    monotonic_ns: Annotated[int | None, Field(ge=0, description="Recorded timestamp in the capture's monotonic clock domain, when available.")] = None
    start_monotonic_ns: Annotated[int | None, Field(ge=0, description="Recorded start timestamp in the capture's monotonic clock domain.")] = None
    end_monotonic_ns: Annotated[int | None, Field(ge=0, description="Recorded end timestamp in the capture's monotonic clock domain.")] = None
    trace_id_hi: Annotated[int | None, Field(ge=0, description="High 64 bits of the application-recorded W3C trace ID, when present.")] = None
    trace_id_lo: Annotated[int | None, Field(ge=0, description="Low 64 bits of the application-recorded W3C trace ID, when present.")] = None
    direction: Annotated[int | None, Field(ge=0, description="Application-defined numeric direction value; the decoder does not assign semantics.")] = None
    tid: Annotated[int | None, Field(ge=0, description="Recorded OS thread ID, not a cross-process identity.")] = None
    process_generation: Annotated[int | None, Field(ge=0, description="Recorded process-generation value, when present.")] = None
    thread_generation: Annotated[int | None, Field(ge=0, description="Recorded thread-generation value, when present.")] = None
    rpc_id: Annotated[str | int | None, Field(description="Recorded numeric/string RPC identity; shared values alone do not establish causality.")] = None
    kind: Annotated[str | int | None, Field(description="Application/runtime RPC event-kind value retained as recorded.")] = None
    method_id: Annotated[int | None, Field(ge=0, description="Recorded numeric method identity; no method name or payload is decoded.")] = None
    phase: Annotated[Literal["begin", "send", "receive", "recv", "status", "end", "cancel"] | None, Field(description="Normalized lifecycle phase when recorded or mapped from flags.")] = None
    role: Annotated[str | int | bool | None, Field(description="Application-defined caller/peer role value retained as a string, number or boolean.")] = None
    status: Annotated[str | int | bool | None, Field(description="Recorded application or RPC status value; it is not interpreted as a root-cause verdict.")] = None
    deadline_ns: Annotated[int | None, Field(ge=0, description="Recorded deadline in the associated monotonic domain, when supplied.")] = None
    retry_count: Annotated[int | None, Field(ge=0, description="Recorded retry count; it does not prove an operation was applied once.")] = None
    attempt: Annotated[int | None, Field(ge=0, description="Recorded attempt number, when supplied by the producer.")] = None
    stream: Annotated[str | int | bool | None, Field(description="Application-defined stream kind/value retained as a string, number or boolean.")] = None
    streaming: Annotated[bool | None, Field(description="Recorded streaming indicator, when supplied.")] = None
    pid: Annotated[int | None, Field(ge=0, description="Recorded process ID; PID reuse and namespaces still apply.")] = None
    peer_pid: Annotated[int | None, Field(ge=0, description="Recorded peer process ID; it is not independently verified by this decoder.")] = None
    flags: Annotated[int | None, Field(ge=0, description="Producer-defined event flags retained as a number.")] = None
    generation: Annotated[int | None, Field(ge=0, description="Producer-defined generation value retained as recorded.")] = None
    publication: Annotated[int | None, Field(ge=0, description="Producer publication marker retained as recorded.")] = None
    source: Annotated[str | None, Field(description="Original event source label when the extension supplied one.")] = None


class IncidentReportRpcEvent(RpcTraceEvent):
    """One normalized RPC observation annotated with its report-local artifact index."""

    artifact_index: Annotated[int, Field(ge=0, description="Zero-based position of the capture in this incident-report request; not a persistent artifact ID.")]


class IncidentReportArtifact(OutputModel):
    """Small capture context row retained by the multi-capture report."""

    index: Annotated[int, Field(ge=0, description="Zero-based position in the supplied capture-name list.")]
    pid: Annotated[Any, Field(description="Process ID value copied from the capture when present; this report-local row is not a persistent identity.")]
    target: Annotated[dict[str, Any], Field(description="Recorded target return-code/signal fields copied from the capture; absent source fields stay absent.")]
    collector: Annotated[dict[str, Any], Field(description="Recorded collector status fields copied from the capture; these are not independently verified.")]


class IncidentReportObserved(OutputModel):
    """Observed multi-capture event rows and explicit endpoint relations."""

    rpc_events: Annotated[list[IncidentReportRpcEvent], Field(description="Normalized semantic-RPC observations for the current page; artifact_index identifies their capture in this request.")]
    process_relations: Annotated[list[dict[str, Any]], Field(description="Observed explicit cross-process relations; relation keys depend on their RPC or IPC source evidence.")]


class IncidentReportFields(OutputModel):
    """Application fields copied only when present on decoded RPC events."""

    status: Annotated[list[dict[str, Any]], Field(description="Recorded status values; they are not interpreted as root-cause verdicts.")]
    deadlines: Annotated[list[dict[str, Any]], Field(description="Recorded deadline values; clock-domain compatibility is not inferred here.")]
    retries: Annotated[list[dict[str, Any]], Field(description="Recorded retry-count or attempt values; they do not prove exactly-once effects.")]
    streams: Annotated[list[dict[str, Any]], Field(description="Recorded stream or streaming values; no stream mode is inferred from event phase.")]


class IncidentReportOutput(OutputModel):
    """Read-only, paginated report built directly from named capture files."""

    schema_: Annotated[Literal[1], Field(alias="schema", description="Incident-report response schema version.")]
    status: Annotated[Literal["complete", "limited", "unresolved"], Field(description="Evidence availability label; limited and unresolved reports are not successful-RPC or root-cause verdicts.")]
    artifacts: Annotated[list[IncidentReportArtifact], Field(description="Request-local capture summary rows in the same order as the supplied capture names.")]
    observed: Annotated[IncidentReportObserved, Field(description="Observed evidence classes; RPC events are paged while process relations are not.")]
    static_candidates: Annotated[list[Any], Field(description="Producer-supplied or static candidates retained separately from observed evidence.")]
    unresolved: Annotated[list[dict[str, Any]], Field(description="Open diagnostic rows from RPC decoding, relation matching, and timeline analysis; keys vary by reason.")]
    fields: Annotated[IncidentReportFields, Field(description="Explicit status, deadline, retry and stream fields copied from decoded events; no missing value is inferred.")]
    page: Annotated[int, Field(ge=0, description="Zero-based page of observed RPC events returned.")]
    page_size: Annotated[Literal[200], Field(description="Maximum observed RPC events per page.")]
    total_rpc_events: Annotated[int, Field(ge=0, description="Total normalized RPC observations across all pages.")]


class EvidenceSummaryObserved(OutputModel):
    rpc_events: Annotated[int, Field(ge=0, description="Number of normalized observed RPC events; candidates and unresolved rows are excluded.")]
    process_relations: Annotated[int, Field(ge=0, description="Number of observed cross-process relations; static candidates are excluded.")]


class EvidenceSummaryDiagnostic(OutputModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    reason: Annotated[str, Field(description="Stable reason code for an unresolved RPC or process-relation diagnostic.")]


class EvidenceSummaryOutput(OutputModel):
    """Compact counts for one capture; no RPC event histories are returned."""

    schema_: Annotated[Literal[1], Field(alias="schema", description="Semantic RPC summary contract version.")]
    status: Annotated[Literal["complete", "limited"], Field(description="Complete means this summary produced no unresolved diagnostic; it does not assert application success or full capture coverage.")]
    artifacts: Annotated[Literal[1], Field(description="One named capture is summarized by each tool call.")]
    observed: Annotated[EvidenceSummaryObserved, Field(description="Counts of directly observed RPC events and process relations only.")]
    static_candidates: Annotated[int, Field(ge=0, description="Number of static RPC candidates; these are not observed execution.")]
    unresolved: Annotated[list[EvidenceSummaryDiagnostic], Field(description="Unresolved decoder and process-pairing diagnostics; additional diagnostic fields vary by reason.")]


class ServiceFlowCounts(OutputModel):
    """Stable collection counts; future collection counters remain open."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    services: Annotated[int, Field(ge=0, description="Native process/service summary rows.")]
    calls: Annotated[int, Field(ge=0, description="RPC calls matched to application call labels and explicit endpoint evidence.")]
    causes: Annotated[int, Field(ge=0, description="Application self-reported cause events; they are not root-cause verdicts.")]
    events: Annotated[int, Field(ge=0, description="Validated application event rows.")]
    native_relations: Annotated[int, Field(ge=0, description="Observed native endpoint relations, separate from application labels.")]
    unresolved: Annotated[int, Field(ge=0, description="Unresolved evidence and correlation-limit rows.")]
    evidence_files: Annotated[int, Field(ge=0, description="Frozen native capture and application-log files included in the fingerprint.")]


class ServiceFlowOutputModel(OutputModel):
    """Open root envelope for the frozen cross-service query projection."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    schema_: Annotated[Literal[1], Field(alias="schema", description="Service-flow query response schema version.")]
    snapshot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$", description="SHA-256 content fingerprint that must be reused across pages; it is not an atomic filesystem snapshot.")]
    session_id: Annotated[str, Field(min_length=1, description="Explicit runtime session ID shared by the included captures.")]
    counts: Annotated[ServiceFlowCounts, Field(description="Total row counts for all supported collections, independent of the selected page.")]
    limitations: Annotated[list[str], Field(description="Fixed interpretation limits; application explanations remain self-reports and do not establish cross-process causality.")]


class ServiceFlowSummaryOutput(ServiceFlowOutputModel):
    """Count-only service-flow response for section=summary."""

    section: Annotated[Literal["summary"], Field(description="Summary mode returns counts and limitations without a collection page.")]


class ServiceFlowPageOutput(ServiceFlowOutputModel):
    """One bounded page from the selected service-flow collection."""

    section: Annotated[Literal["services", "calls", "causes", "events", "native_relations", "unresolved", "evidence_files"], Field(description="The collection selected for this page.")]
    page: Annotated[int, Field(ge=0, description="Zero-based page returned.")]
    page_size: Annotated[int, Field(ge=1, le=200, description="Maximum rows requested for one page, from 1 through 200.")]
    total: Annotated[int, Field(ge=0, description="Total rows in the selected collection before pagination.")]
    returned: Annotated[int, Field(ge=0, description="Rows present in this page; an exhausted page returns zero.")]
    next_page: Annotated[int | None, Field(ge=0, description="Next zero-based page, or null when the selected collection is exhausted.")]
    items: Annotated[list[dict[str, Any]], Field(description="Selected collection rows. Row fields vary by evidence source and remain open to producer extensions.")]


ServiceFlowOutput = Annotated[
    ServiceFlowSummaryOutput | ServiceFlowPageOutput,
    Field(discriminator="section"),
]


class RpcExtensionAbsent(OutputModel):
    reason: Annotated[Literal["semantic_rpc_extension_absent"], Field(description="The capture does not contain a semantic-RPC extension.")]
    evidence: Annotated[Literal["artifact"], Field(description="The absent extension was checked on the captured artifact.")]


class RpcSequenceNotMonotonic(OutputModel):
    reason: Annotated[Literal["rpc_sequence_not_monotonic"], Field(description="The decoded event order reverses a pair of recorded publication sequence values.")]
    before: Annotated[int, Field(description="Earlier decoded row's sequence value.")]
    after: Annotated[int, Field(description="Later decoded row's sequence value; it is less than or equal to before.")]


class RpcSequenceGap(OutputModel):
    reason: Annotated[Literal["rpc_sequence_gap"], Field(description="The publication sequence skips one or more values.")]
    before: Annotated[int, Field(description="Earlier decoded row's sequence value.")]
    after: Annotated[int, Field(description="Later decoded row's sequence value; one or more values are missing.")]


class RpcTracePartial(OutputModel):
    reason: Annotated[Literal["runtime_trace_partial_or_overflow"], Field(description="The capture header marks partial data or recorder overflow.")]
    status: Annotated[int, Field(description="Recorded native capture-status bit field; not an RPC status code.")]


class RpcStreamIncomplete(OutputModel):
    reason: Annotated[Literal["semantic_rpc_stream_incomplete"], Field(description="The RPC extension or sidecar header marks the stream incomplete.")]
    flags: Annotated[int, Field(description="Recorded RPC sidecar flags used by the completeness check.")]
    dropped_count: Annotated[Any, Field(description="Raw producer drop-count value retained without reinterpretation.")]


class RpcEventsEmpty(OutputModel):
    reason: Annotated[Literal["semantic_rpc_events_empty"], Field(description="The extension is present but provides no normalized semantic events.")]
    evidence: Annotated[str, Field(description="Extension key that declared an empty semantic-RPC stream.")]


RpcTraceDiagnostic = Annotated[
    RpcExtensionAbsent | RpcSequenceNotMonotonic | RpcSequenceGap |
    RpcTracePartial | RpcStreamIncomplete | RpcEventsEmpty,
    Field(discriminator="reason", description="One explicit reason the RPC evidence is incomplete or absent."),
]


class RpcTraceOutput(OutputModel):
    """Versioned semantic-RPC observations with candidates and diagnostics kept distinct."""

    schema_: Annotated[Literal[1], Field(alias="schema", description="Semantic-RPC decoder response schema version.")]
    status: Annotated[Literal["complete", "limited", "unresolved"], Field(description="Evidence completeness label; unresolved/limited are not converted into successful RPC claims.")]
    source: Annotated[Literal["rpc_trace", "rpc", "semantic_rpc", "rpc_events", "semantic_rpc_events", "threads.semantic_events"] | None, Field(description="Extension key from which events were decoded; null means the artifact has no RPC extension.")]
    observed: Annotated[list[RpcTraceEvent], Field(description="Normalized observed events in the current page only.")]
    static_candidates: Annotated[list[Any], Field(description="Producer-supplied candidates, retained separately and never promoted to observed RPC events.")]
    unresolved: Annotated[list[RpcTraceDiagnostic], Field(description="Explicit sequence, completeness, or extension diagnostics; shared IDs do not resolve them.")]
    total: Annotated[int, Field(ge=0, description="Total normalized observed events across all pages, not just this page.")]
    page: Annotated[int, Field(ge=0, description="Zero-based page of observed events returned.")]
    page_size: Annotated[Literal[200], Field(description="Maximum observed RPC events per page.")]


class FaultFlowSnapshot(OutputModel):
    """Snapshot-read consistency; future producer metadata is preserved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    stable: Annotated[Any, Field(description="Raw producer stability value; only the literal boolean true is considered stable by the report builder.")] = None
    unstable_records: Annotated[Any, Field(description="Raw producer unstable-record details; the report preserves their shape.")] = None


class FaultFlowCapture(OutputModel):
    complete: Annotated[Any, Field(description="Raw capture completeness marker; only the literal boolean true is considered complete by the report builder.")]
    status: Annotated[int, Field(ge=0, description="Native capture status bit field retained from the artifact header.")]
    evidence_status: Annotated[Literal["capture_complete", "limited"], Field(description="Summary label: limited means one or more explicit gaps were retained.")]
    snapshot_consistency: Annotated[FaultFlowSnapshot, Field(description="Snapshot-read state; this is separate from capture loss and report-view omission.")]


class FaultFlowResolution(OutputModel):
    """Address lookup result with known fields typed and extension evidence retained."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    address: Annotated[int, Field(ge=0, description="Captured function or program-counter address checked against the artifact and optional bundle.")]
    kind: Annotated[str | None, Field(description="Address category supplied to the resolver.")] = None
    resolved: Annotated[bool, Field(description="True only when the resolver found one matching module/symbol and any requested source verification succeeded.")]
    reason: Annotated[str | None, Field(description="Unresolved reason code; absent on resolved addresses.")] = None
    module: Annotated[str | None, Field(description="Captured module path, when one address range matched.")] = None
    build_id: Annotated[str | None, Field(description="Captured or verified module Build ID, when available.")] = None
    actual_build_id: Annotated[str | None, Field(description="Build ID read from the candidate binary when it mismatched the captured identity.")] = None
    load_bias: Annotated[int | None, Field(ge=0, description="Recorded module load bias used to calculate the relative address.")] = None
    relative_address: Annotated[int | None, Field(ge=0, description="Address relative to the captured module load bias.")] = None
    symbol: Annotated[str | None, Field(description="Unique symbol name when resolved.")] = None
    function_id: Annotated[str | None, Field(description="Verified source-index function ID when a unique function row matched.")] = None
    candidates: Annotated[list[str | int | None] | None, Field(description="Symbol or function-index candidate IDs that remain ambiguous.")] = None
    debug_file: Annotated[str | None, Field(description="Separate debug-file path used after its Build ID matched.")] = None
    debug_file_build_id: Annotated[str | None, Field(description="Build ID verified for the separate debug file.")] = None
    static_edges: Annotated[list[Any] | None, Field(description="Static index edges kept as static evidence, never as observed runtime nesting.")] = None
    static_unresolved_edges: Annotated[list[Any] | None, Field(description="Unresolved static-index edges retained from the verified function row.")] = None
    source: Annotated[dict[str, Any] | None, Field(description="Offline symbolizer location metadata; it is not verified source text.")] = None


class ResolveAddressesOutput(OutputModel):
    """Per-address Build-ID-aware symbol and function resolution results."""

    items: Annotated[list[FaultFlowResolution], Field(description="One resolution row per requested address; unresolved rows remain visible and do not discard other items.")]


class StaticCallRelation(OutputModel):
    """Common keys of version-1 static call-index relation rows; extensions remain open."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    caller_id: Annotated[Any | None, Field(description="Function ID of the indexed caller in inbound results; absent for outbound edge rows.")] = None
    callee_id: Annotated[Any | None, Field(description="Indexed target function ID on a direct outbound edge, when resolved by the indexer.")] = None
    spelling: Annotated[Any | None, Field(description="Recorded call expression spelling when the static index could not resolve a direct callee.")] = None
    kind: Annotated[Any | None, Field(description="Static index edge category, such as direct or indirect_or_virtual; never a runtime event kind.")] = None
    edge: Annotated[Any | None, Field(description="Original edge nested under an inbound caller row; its contents remain producer-defined.")] = None


class CallRelationsOutput(OutputModel):
    """Read-only source-index call candidates for one verified function ID."""

    function_id: Annotated[str, Field(description="Exact function ID selected from the verified bundle index.")]
    direction: Annotated[Literal["inbound", "outbound"], Field(description="Whether this result lists indexed callers or indexed outgoing candidates.")]
    relations: Annotated[list[StaticCallRelation], Field(description="Static index rows only; outbound rows may be unresolved, and inbound rows wrap their matching edge.")]
    evidence: Annotated[Literal["static_index"], Field(description="Evidence class for these rows; this does not prove a runtime call occurred.")]
    bundle: Annotated[str, Field(description="Resolved root path of the verified immutable bundle containing the index.")]


class ThreadTraceRetention(OutputModel):
    """Conditional native thread-history accounting; unknown producer fields remain open."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    scope: Annotated[str, Field(description="Retention scope for the thread slot.")]
    event_count_scope: Annotated[str, Field(description="Generation scope of the retained event count.")]
    dropped_count_scope: Annotated[str, Field(description="Lifetime scope of the dropped event count.")]
    retired_generations: Annotated[int, Field(ge=0, description="Number of retired thread generations represented by the slot.")]
    retired_event_count: Annotated[int | None, Field(ge=0, description="Retired-generation event count, when the recorder knows it.")]


class ThreadTraceEvent(OutputModel):
    """One raw event; older JSON captures may omit fields available in the native ABI."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    sequence: Annotated[int | None, Field(ge=0, description="Per-thread publication sequence when recorded in the event ring.")] = None
    monotonic_ns: Annotated[int | None, Field(ge=0, description="Event timestamp in the process monotonic clock domain, when recorded.")] = None
    function: Annotated[int | None, Field(ge=0, description="Recorded function address; this field is not a resolved symbol.")] = None
    callsite: Annotated[int | None, Field(ge=0, description="Recorded callsite address when present in the source capture.")] = None
    type: Annotated[int | None, Field(ge=0, description="Raw native event type value when present; interpretation follows the capture ABI.")] = None
    generation: Annotated[int | None, Field(ge=0, description="Thread generation that owns this event record, when recorded.")] = None


class ThreadTraceThread(OutputModel):
    """Thread row that preserves sparse JSON captures and optional generation accounting."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    slot: Annotated[int | None, Field(ge=0, description="Native shared-memory thread slot, when present in the capture.")] = None
    tid: Annotated[int | None, Field(ge=0, description="Captured operating-system thread ID; it may be reused across generations.")] = None
    generation: Annotated[int | None, Field(ge=0, description="Current generation recorded in this thread slot, when present.")] = None
    flags: Annotated[int | None, Field(ge=0, description="Raw thread-slot flags describing generation and retained history, when present.")] = None
    event_count: Annotated[int | None, Field(ge=0, description="Native ring publication count, when present; it can exceed retained events after wraparound.")] = None
    dropped_count: Annotated[int | None, Field(ge=0, description="Slot-lifetime dropped-event count, when present; distinct from the retained array.")] = None
    events: Annotated[list[ThreadTraceEvent] | None, Field(description="Retained raw events in publication-sequence order when present; this list alone does not establish capture completeness.")] = None
    retention: Annotated[ThreadTraceRetention | None, Field(description="Present when the recorder advertises generation-aware history accounting.")] = None


class ThreadTraceOutput(OutputModel):
    """Paged raw thread histories from one immutable capture."""

    items: Annotated[list[ThreadTraceThread], Field(description="Thread records on this page; pagination slices threads, not their events.")]
    page: Annotated[int, Field(ge=0, description="Zero-based thread page.")]
    page_size: Annotated[Literal[200], Field(description="Maximum thread records per page.")]
    total: Annotated[int, Field(ge=0, description="Number of matching thread records before pagination.")]


class OpenFaultHeader(OutputModel):
    """Known native capture-header counters; unknown compatibility fields stay open."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    total_size: Annotated[int | None, Field(ge=0, description="Captured shared-memory size in bytes, when present.")] = None
    status: Annotated[int | None, Field(ge=0, description="Native capture-status bit field; it is not an application or RPC status code.")] = None
    event_capacity: Annotated[int | None, Field(ge=0, description="Native event-ring capacity when captured.")] = None
    thread_capacity: Annotated[int | None, Field(ge=0, description="Native thread-slot capacity when captured.")] = None
    module_capacity: Annotated[int | None, Field(ge=0, description="Native module-slot capacity when captured.")] = None
    crash_capacity: Annotated[int | None, Field(ge=0, description="Native crash-slot capacity when captured.")] = None
    creator_pid: Annotated[int | None, Field(ge=0, description="Process ID that created the native mapping; it is not a persistent identity.")] = None
    start_ns: Annotated[int | None, Field(ge=0, description="Recorded process start in its monotonic clock domain.")] = None
    ready_ns: Annotated[int | None, Field(ge=0, description="Recorded collector-ready time in the same monotonic clock domain.")] = None
    crash_ns: Annotated[int | None, Field(ge=0, description="Recorded crash time in the same monotonic clock domain.")] = None
    threads_offset: Annotated[int | None, Field(ge=0, description="Native thread-region byte offset.")] = None
    modules_offset: Annotated[int | None, Field(ge=0, description="Native module-region byte offset.")] = None
    crashes_offset: Annotated[int | None, Field(ge=0, description="Native crash-region byte offset.")] = None


class OpenFaultModule(OutputModel):
    """Known loaded-module fields; additional producer fields are preserved."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    slot: Annotated[int | None, Field(ge=0, description="Native module-table slot when present.")] = None
    load_bias: Annotated[int | None, Field(ge=0, description="Recorded runtime load bias.")] = None
    text_start: Annotated[int | None, Field(ge=0, description="Recorded start of the module text range.")] = None
    text_end: Annotated[int | None, Field(ge=0, description="Recorded end of the module text range.")] = None
    build_id: Annotated[str | None, Field(description="Recorded GNU Build ID; a later source lookup still verifies the candidate binary.")] = None
    path: Annotated[str | None, Field(description="Recorded module path; it is not proof that the current file matches the capture.")] = None


class OpenFaultCrash(OutputModel):
    """Raw native crash fields without a fault-cause interpretation."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    slot: Annotated[int | None, Field(description="Crash-record slot when present.")] = None
    flags: Annotated[int | None, Field(description="Raw crash validity and state flags.")] = None
    signal: Annotated[int | None, Field(description="Recorded signal number when present.")] = None
    si_code: Annotated[int | None, Field(description="Recorded signal subcode when present.")] = None
    fault_address: Annotated[int | None, Field(description="Recorded fault address; zero is preserved when marked valid.")] = None
    pc: Annotated[int | None, Field(description="Recorded program counter; it is not resolved to a symbol here.")] = None
    tid: Annotated[int | None, Field(description="Captured OS thread ID; it may be reused across thread generations.")] = None
    monotonic_ns: Annotated[int | None, Field(description="Crash timestamp in the recorded process clock domain.")] = None
    thread_generation: Annotated[int | None, Field(description="Thread generation matched to this crash row when captured.")] = None


class OpenFaultSnapshotConsistency(OutputModel):
    """Snapshot-read state; this does not establish global atomicity."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    stable: Annotated[bool | None, Field(description="True when no record changed during the decoder's bounded copy.")] = None
    unstable_records: Annotated[list[Any] | None, Field(description="Open diagnostic rows for records omitted or changed during the read.")] = None


class OpenFaultBundleMarker(OutputModel):
    """Optional source-bundle integrity result attached by open_fault."""

    path: Annotated[str, Field(description="Resolved root path of the verified immutable bundle.")]
    verified: Annotated[Literal[True], Field(description="True only after the bundle manifest and files pass verification.")]


class OpenFaultOutput(OutputModel):
    """Raw capture sections with known native fields typed and producer extensions open."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    header: Annotated[OpenFaultHeader | None, Field(description="Native format header when available; legacy and sparse JSON may omit it.")] = None
    threads: Annotated[list[ThreadTraceThread] | None, Field(description="Raw captured thread rows; pagination and event reconstruction are provided by dedicated tools.")] = None
    modules: Annotated[list[OpenFaultModule] | None, Field(description="Captured loaded-module rows; recorded paths and IDs are not independently verified here.")] = None
    crashes: Annotated[list[OpenFaultCrash] | None, Field(description="Raw crash rows; these fields do not by themselves establish a root cause.")] = None
    complete: Annotated[bool | None, Field(description="Capture-completeness marker when recorded; true does not imply application success.")] = None
    snapshot_consistency: Annotated[OpenFaultSnapshotConsistency | None, Field(description="Decoder snapshot-read consistency, separate from root cause and application outcome.")] = None
    rpc: Annotated[dict[str, Any] | None, Field(description="Optional producer-defined semantic-RPC sidecar and its header, events and completeness metadata.")] = None
    rpc_events: Annotated[list[Any] | None, Field(description="Optional raw RPC-event alias; use get_rpc_trace for normalized observations and explicit diagnostics.")] = None
    process: Annotated[dict[str, Any] | None, Field(description="Optional launcher process identity metadata; PID alone is not a persistent identity.")] = None
    target: Annotated[dict[str, Any] | None, Field(description="Optional recorded target exit information; it is not a root-cause verdict.")] = None
    collector: Annotated[dict[str, Any] | None, Field(description="Optional collector status and loss information.")] = None
    session: Annotated[dict[str, Any] | None, Field(description="Optional declared session identity metadata.")] = None
    context: Annotated[dict[str, Any] | None, Field(description="Optional producer context metadata; missing fields are not inferred.")] = None
    artifact: Annotated[str | None, Field(description="Optional artifact path recorded by the launcher.")] = None
    bundle: Annotated[OpenFaultBundleMarker | None, Field(description="Present only when the optional source bundle was verified.")] = None


class FaultFlowEvent(OutputModel):
    id: Annotated[str, Field(description="Stable report-local event identifier; not a capture-global identity.")]
    kind: Annotated[Literal["enter", "exit", "marker"], Field(description="Decoded native record kind; marker includes unknown/unsupported event types.")]
    sequence: Annotated[int, Field(ge=0, description="Per-thread publication sequence from the captured event ring.")]
    monotonic_ns: Annotated[int | None, Field(ge=0, description="Captured event time in the process monotonic clock domain, when recorded.")]
    function: Annotated[int, Field(ge=0, description="Recorded function address; symbol names are reported separately as resolution evidence.")]
    callsite: Annotated[int, Field(ge=0, description="Recorded callsite address, when present in the capture.")]
    depth: Annotated[int, Field(ge=0, description="Retained nesting depth at this event; gaps can clear the reconstruction stack.")]
    gaps_before: Annotated[list[str], Field(description="Explicit record-order/generation gaps before this node; an empty list does not establish root cause.")]
    resolution: Annotated[FaultFlowResolution, Field(description="Address-to-module/symbol lookup result, with unresolved candidates kept explicit.")]
    label: Annotated[str, Field(description="Display label from a resolved symbol or the captured address.")]
    source_verified: Annotated[bool, Field(description="True only when the event resolved to source verified in the supplied immutable bundle.")]


class FaultFlowCrash(OutputModel):
    id: Annotated[str, Field(description="Report-local crash identifier.")]
    kind: Annotated[Literal["crash"], Field(description="Fixed crash-node category.")]
    flags: Annotated[int, Field(ge=0, description="Recorded crash-field validity bits; null optional values mean their fields were not captured.")]
    signal: Annotated[int | None, Field(description="Captured signal number when the validity bit is set.")]
    signal_name: Annotated[str, Field(description="Signal name derived from the captured signal, or an explicit unrecorded label.")]
    si_code: Annotated[int | None, Field(description="Captured signal subcode when its validity bit is set.")]
    pc: Annotated[int | None, Field(ge=0, description="Program counter only when the capture marks it valid.")]
    fault_address: Annotated[int | None, Field(ge=0, description="Fault address only when the capture marks it valid; zero is preserved.")]
    tid: Annotated[int, Field(ge=0, description="Captured OS thread ID; PID/TID reuse can still occur.")]
    generation: Annotated[int, Field(ge=0, description="Thread generation matched to the crash record.")]
    monotonic_ns: Annotated[int, Field(ge=0, description="Crash timestamp in the captured monotonic clock domain.")]
    thread: Annotated[str | None, Field(description="Unique matching report thread ID; null means the matching generation was absent or ambiguous.")]
    last_event: Annotated[str | None, Field(description="Last retained event before the crash time, when one was matched.")]
    resolution: Annotated[FaultFlowResolution, Field(description="Crash-PC resolution evidence; it is not a fault-cause verdict.")]
    label: Annotated[str, Field(description="Display label from a resolved symbol, signal, or captured program counter.")]
    source_verified: Annotated[bool, Field(description="True only when crash source text was verified against the supplied immutable bundle.")]


class FaultFlowThreadGap(OutputModel):
    """One explicit gap row; optional fields vary by the reported gap reason."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    reason: Annotated[str | None, Field(description="Gap category when this row summarizes a capture, thread or crash condition.")] = None
    thread: Annotated[str | None, Field(description="Report-local thread ID when the gap is thread-specific.")] = None
    sequence: Annotated[int | None, Field(ge=0, description="Event sequence when the gap is tied to a retained event.")] = None
    reasons: Annotated[list[str] | None, Field(description="Event-level reasons that cleared or limited reconstructed nesting.")] = None
    status: Annotated[int | None, Field(ge=0, description="Native status bit field when the capture header caused this gap.")] = None
    unstable_records: Annotated[int | None, Field(ge=0, description="Count of unstable snapshot records when summarized by this gap.")] = None
    count: Annotated[int | None, Field(ge=0, description="Dropped records or retired generations, according to the reason.")] = None
    retired_event_count: Annotated[int | None, Field(ge=0, description="Retired-event count when recorded; null means unavailable.")] = None
    crash: Annotated[str | None, Field(description="Report-local crash ID when the gap concerns a crash node.")] = None


class FaultFlowUnmatchedEntry(OutputModel):
    function: Annotated[int, Field(ge=0, description="Function address left on the retained nesting stack.")]
    event_id: Annotated[str, Field(description="Report-local enter-event ID for this unmatched stack entry.")]


class FaultFlowGraphEdge(OutputModel):
    source: Annotated[str, Field(alias="from", description="Report-local source node ID.")]
    target: Annotated[str, Field(alias="to", description="Report-local target node ID.")]
    kind: Annotated[Literal["observed_nesting", "record_order", "crash_context"], Field(description="Evidence relation; observed nesting and record order are not root-cause conclusions.")]


class FaultFlowDiagnostic(OutputModel):
    code: Annotated[Literal["FD-MISSING-SYMBOL", "FD-PROVENANCE-MISMATCH", "FD-INCOMPLETE-TRACE"], Field(description="Stable diagnostic family for missing symbols, provenance mismatch, or incomplete trace evidence.")]
    severity: Annotated[Literal["error", "warning"], Field(description="Report severity assigned to this evidence-bound diagnostic.")]
    message: Annotated[str, Field(description="Actionable summary; the diagnostic does not infer application root cause.")]
    evidence: Annotated[dict[str, Any], Field(description="Address/trace evidence supporting the diagnostic; shape depends on its code.")]


class FaultFlowSource(OutputModel):
    resolved: Annotated[Literal[True], Field(description="True only for source read from the verified immutable bundle.")]
    function_id: Annotated[str, Field(description="Exact function identifier matched in the verified source index.")]
    bundle: Annotated[str, Field(description="Verified immutable bundle root.")]
    file: Annotated[str, Field(description="Verified source file path in the bundle.")]
    start_line: Annotated[int, Field(ge=1, description="First one-based line of returned verified source.")]
    end_line: Annotated[int, Field(ge=0, description="Last one-based line in the source index range; zero is retained for an empty source file.")]
    display_end_line: Annotated[int, Field(ge=0, description="Last line actually included in this bounded report excerpt; zero is retained for an empty source file.")]
    source: Annotated[str, Field(description="Source text read only after immutable-bundle verification.")]


class FaultFlowBundle(OutputModel):
    path: Annotated[str, Field(description="Resolved immutable bundle root used for verified source lookup.")]
    verified: Annotated[Literal[True], Field(description="The bundle passed the report's existing verification checks.")]


class FaultFlowThread(OutputModel):
    id: Annotated[str, Field(description="Report-local thread ID, assigned in capture order.")]
    slot: Annotated[int | None, Field(ge=0, description="Native thread-ring slot when recorded.")]
    tid: Annotated[int, Field(ge=0, description="Captured operating-system thread ID; reused IDs can have separate generations.")]
    generation: Annotated[int, Field(ge=0, description="Captured thread generation that disambiguates TID reuse.")]
    dropped_count: Annotated[int, Field(ge=0, description="Recorder drop count for this thread slot's lifetime.")]
    retained_events: Annotated[int, Field(ge=0, description="Number of validated events retained in the capture before report view limits.")]
    omitted_from_view: Annotated[int, Field(ge=0, description="Older pre-crash events omitted by max_events; these remain in the capture and do not imply loss.")]
    post_crash_events: Annotated[int, Field(ge=0, description="Captured events after the matching crash timestamp and therefore excluded from this thread view.")]
    events: Annotated[list[FaultFlowEvent], Field(description="Bounded execution nodes; nesting edges are reconstructed only across retained contiguous evidence.")]
    gaps: Annotated[list[FaultFlowThreadGap], Field(description="Thread-specific capture and reconstruction gaps.")]
    unmatched_entries: Annotated[list[FaultFlowUnmatchedEntry], Field(description="Enter events still on the retained nesting stack when processing ended.")]


class FaultFlowOutput(OutputModel):
    """Versioned execution view with capture gaps, resolution and verified source kept distinct."""

    schema_version: Annotated[Literal[1], Field(description="Version of the fault-flow report contract.")]
    kind: Annotated[Literal["faultdebug-fault-flow"], Field(description="Fixed report discriminator.")]
    language: Annotated[Literal["en", "ko"], Field(description="Language selected for this report invocation.")]
    capture: Annotated[FaultFlowCapture, Field(description="Capture completeness and snapshot-read state; this is independent from display truncation.")]
    target: Annotated[Any, Field(description="Original target exit and process metadata recorded in the capture; passed through without reinterpretation.")]
    threads: Annotated[list[FaultFlowThread], Field(description="Per-thread retained execution view; omitted_from_view counts display-bounded events only.")]
    crashes: Annotated[list[FaultFlowCrash], Field(description="Crash records linked to a unique matching thread generation when possible.")]
    edges: Annotated[list[FaultFlowGraphEdge], Field(description="Observed nesting, contiguous record order and crash-context edges; none is a root-cause verdict.")]
    sources: Annotated[dict[str, FaultFlowSource], Field(description="Verified source excerpts keyed by function ID; empty when no supplied bundle resolved one.")]
    gaps: Annotated[list[FaultFlowThreadGap], Field(description="Capture, thread and crash gaps retained as explicit evidence; extra reason-specific fields remain preserved.")]
    diagnostics: Annotated[list[FaultFlowDiagnostic], Field(description="Stable diagnostic summaries with their supporting evidence payloads.")]
    limitations: Annotated[list[str], Field(description="Fixed interpretation limits for this reconstructed execution view.")]
    bundle: Annotated[FaultFlowBundle | None, Field(description="Verified bundle marker, or null when no bundle was supplied.")]

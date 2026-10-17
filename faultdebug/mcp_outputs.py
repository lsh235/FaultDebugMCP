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

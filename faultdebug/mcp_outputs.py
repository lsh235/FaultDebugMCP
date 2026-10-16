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

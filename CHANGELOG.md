# Changelog

## [Unreleased]

## [1.3.0-alpha.22] - 2026-10-17

- Publish a documented structured result for full-profile `list_sessions`,
  distinguishing assigned/unassigned groups, monotonic start time, artifact
  counts, identity source and aggregate trust state.
- Keep profile membership, read-only store semantics and MCP query errors
  unchanged; official Glama deployment, re-scan and score remain unverified.

## [1.3.0-alpha.21] - 2026-10-17

- Publish validated structured success and query-error outputs for read-only
  incident listing while preserving incident IDs, filters and evidence state.
- Keep larger extensible incident slices untyped; official Glama deployment,
  re-scan and score remain unverified.

## [1.3.0-alpha.20] - 2026-10-17

- Publish a validated seven-field structured result schema for verified source
  lookup while retaining the text response and mandatory immutable-bundle check.
- Keep variable static-index relation rows untyped; official Glama deployment,
  re-scan and score remain unverified.

## [1.3.0-alpha.19] - 2026-10-17

- Publish distinct, task-specific top-level MCP display titles for all 27
  tools, aligned with the existing annotation titles and safety hints.
- Validate title visibility over real stdio in full and focused profiles;
  Glama's external pin, deployment, re-scan and score remain unverified.

## [1.3.0-alpha.18] - 2026-10-17

- Upgrade the MCP Python SDK within major version 1 and publish validated,
  structured outputs for capabilities, store health, artifact discovery, and
  bundle discovery while preserving the existing text response channel.
- Audit both full and focused tool profiles over real stdio; Glama's external
  pin, deployment, rescan and numeric score remain unverified.

## [1.3.0-alpha.1] - 2026-10-17

Identity-transport development milestone; Python package `1.3.0a1` and native
project `1.3.0`. This is the first part of the v1.3 plan, not stable acceptance.

- Add a strict, dependency-free version-00 W3C traceparent adapter preserving all
  128 trace bits and the sampled flag, rejecting ambiguous/duplicate context explicitly.
- Use it in the real HTTP shopping lab with explicit numeric RPC correlation and
  separate client/server span IDs. Headers and app logs remain application evidence.
- Record optional local Linux boot/time-namespace clock provenance; keep unknown
  sources unknown and validate process-generation values without lossy coercion.
- Compute receiver deadlines from bounded relative timeout budgets.
- Validate HTTP boundaries with both an explicit fake recorder and native captures,
  alongside installed CLI/MCP and existing report/query contracts.


## [1.2.0-rc.2] - 2026-10-17

Evidence-foundation candidate based on `cb02d7ab9265c22e3e6c1e05f1460fb336c2001a`.
The Python package is `1.2.0rc2`; native ABI/FDAR v1 and store schema v2 are unchanged.
This RC records the shared service query and strict identity/input contracts.
It is not stable v1.2 or completion of the v1.3 roadmap; current-revision full
core/gRPC release acceptance and an independent final audit remain pending.

- Match application corroboration by full 128-bit trace and process generation.
- Bound evidence reads and expose deterministic paginated CLI/MCP snapshots.
- Keep missing/ambiguous end events and invalid durations unresolved.


- Documented all MCP tool selection boundaries, return/error contracts and
  parameter semantics in the live stdio definitions; added read-only annotations,
  schema validation constraints and a protocol/immutable-evidence CI audit.
- Fixed legacy artifact-index inspection to use SQLite read-only/query-only mode
  without initializing tables, and reject absolute/parent-traversal MCP paths.
- Added Glama maintainer metadata and registry re-evaluation instructions.

- Added an N-process Docker shopping fault laboratory (8..32 application
  processes), real HTTP orders, replay protection, compensation, concurrent
  workloads and five controlled failure scenarios including native SIGILL.
- Added `service-report` documents and standalone interactive service-flow
  reports from checksummed captures and separately corroborated application
  events; native crash reports retain Build-ID verified source evidence.
- Scoped RPC joins by session, trace and explicit process identity/generation
  for equal PIDs in container namespaces. Native direction takes precedence
  over phase; end events use their actual end time rather than start=0.

- Added `fault-debug fault-report` to generate Markdown, JSON, and standalone
  interactive HTML from a checksummed fault artifact. The report shows captured
  fault PCs, per-thread instrumented nesting and record order, explicit gaps,
  verified source excerpts, and separate static candidates.
- Added Korean/English report labels, search, thread selection, themes and
  printable documents, plus read-only MCP `get_fault_flow`.
- Fixed missing crash thread-generation metadata. Registration publishes the
  TID after generation initialization; in-progress slots are explicit unstable
  evidence. Signal lookup is bounded and does not access dynamic TLS.
- Added evidence-bound report, checksum, rendering-safety and MCP allowlist
  regression checks to CI. The artifact ABI and release version are unchanged.
- Constrained Pydantic to `<2.14` for the pinned MCP 1.9.4 SDK, whose private
  typing-helper import otherwise fails in a fresh installation.

## [1.2.0-rc.1] - 2026-10-03

This pre-release candidate uses Python package version `1.2.0rc1` and native
project version `1.2.0`. Local and GitHub-hosted core and gRPC release profiles
pass. The independent acceptance review remains `NOT RUN`; this candidate does
not indicate final v1.2.0 release acceptance.

- Corrected decoded event ordering when a per-thread ring wraps, and added
  bounded collector, snapshot-consistency, and long-soak telemetry contracts.
- Expanded paired workload measurements with per-run output and loss evidence.
- Added provenance-enabled core/gRPC release profiles, installed-wheel
  consumer checks, and scheduled/manual GitHub Actions reporting.
- Kept the 1800-second soak's dropped-event and unstable-snapshot counts
  explicit; its trace is incomplete and must not be read as lossless evidence.

## [1.1.0] - 2026-10-01

Added local setup diagnostics and reproducible paired performance measurements.

- Added `fault-debug doctor` checks for the Python environment, pinned runtime
  dependencies, Clang 18 selection, build tools, compiler wrappers, and runtime
  library availability.
- Added `fault-debug benchmark` with alternating baseline/instrumented runs,
  binary hashes, p50/p95/p99 wall time, optional operation throughput, CPU and
  peak RSS, and artifact size/loss fields when artifact output is configured.
- Benchmark JSON uses a versioned schema and reports unavailable measurements
  as `NOT RUN`; results remain scoped to the supplied workload and host.

## [1.0.0] - 2026-10-01

Added stable capability and store-health contracts.

- Added bounded CLI `capabilities` and MCP `get_capabilities` responses with
  required inspection tools, artifact/store versions, limits, evidence classes,
  supported signals, platform/toolchain, and security boundaries.
- Added read-only CLI `evidence-health` and MCP `check_store` checks for SQLite
  integrity, v0.8/v0.9 compatibility, additive incident tables, and migration
  state.
- Documented upgrade, support, local-only security, and compatibility rules.

## [0.9.0] - 2026-10-01

Added incident-centric read-only evidence queries over the v0.8 store.

- Connected declared agent incident IDs and peer snapshots to bounded
  incident/artifact/process/event projections without inferring causality from
  session membership.
- Added CLI incident, unresolved, and verified source citation queries plus
  MCP `list_incidents`, `get_incident_slice`, `get_unresolved`, and
  `get_source_evidence`.
- Added verified bundle file/line/SHA-256 citations and structured query
  errors. The v0.8 base schema remains v2 with additive incident tables.

## [0.8.0] - 2026-10-01

Added a restartable SQLite schema-v2 evidence store for local artifacts.

- Ingest verifies FDAR checksums and validates session/process identity plus
  supplied Build ID, binary, source, and index provenance expectations.
- Corrupt or mismatched inputs are quarantined separately; readable artifacts
  without complete trust inputs remain `unresolved` rather than `verified`.
- Added deterministic session, time-window, trust, and provenance queries,
  restart/reindex behavior, and migration from the v0.6 metadata index.
- Added read-only MCP `list_sessions`, `get_session`, and `get_provenance`
  tools and matching CLI commands.

## [0.7.0] - 2026-10-01

Added a versioned read-only session manifest for local multi-artifact analysis.

- Added `fault-debug session-manifest` and `process-participants` plus MCP
  `get_session_manifest` and `get_process_participants`.
- Session manifests preserve observed RPC events, derived process relations,
  static candidates, and unresolved evidence as separate classes.
- Added optional `session` declarations with explicit session and participant
  IDs while retaining legacy trace/correlation grouping for older artifacts.

## [0.6.0] - 2026-10-01

Added a read-only incident report over captured local artifacts.

- Added `fault-debug incident-report` and MCP `get_incident_report`.
- Reports retain observed RPC events, explicit process relations, static
  candidates, and unresolved evidence as separate classes.
- Explicit status, deadline, retry, and stream fields are summarized only when
  supplied by an artifact; no values are inferred from timing or process exit.
- Documented the v0.6 unary gRPC fixture's numeric RPC IDs, propagated trace
  IDs, status events, deadline/response-delay controls, and CompletionQueue
  workers. Streaming and retry scenarios remain explicitly `NOT RUN`.

## [0.5.0] - 2026-10-01

Added selective build instrumentation and local artifact/provenance lookup.

- Added CMake include/exclude source regexes and matching compiler-wrapper
  controls for Make/autotools translation units, including an explicit
  `FAULTDEBUG_LINK_DRIVER` for object-only C++ links.
- Added bounded `artifact-discover`/`discover` CLI discovery and the
  `discover_artifacts` MCP tool for validating local fault spools.
- Added verified bundle binary hash and bundle-root path checks, normalized
  Build IDs, and CLI lookup of source by function ID from a verified bundle.

## [0.4.0] - 2026-10-01

Added an optional, bounded semantic RPC sidecar and evidence-preserving
analysis surface.

- Reserved a versioned numeric RPC sidecar after the unchanged ABI v1 mapping;
  it carries opaque IDs, method IDs, timing, direction, status, generation,
  and loss flags without payloads, metadata, credentials, or method strings.
- Added strict Python sidecar decoding and optional `rpc_events` artifact
  output. ABI v1 artifacts without a sidecar remain readable and report an
  unresolved semantic RPC stream.
- Added read-only MCP tools `get_rpc_trace`, `get_process_relations`, and
  `get_evidence_summary`. Results keep observed events, static candidates, and
  unresolved evidence in separate fields.
- This release does not install a gRPC interceptor or infer causal order from
  function names, parent PIDs, or shared trace IDs.

## [0.3.0] - 2026-10-01

Added the first gRPC asynchronous proxy integration fixture and its evidence
gate.

- Added an optional CMake target, `fd_grpc_async_proxy`, that generates the
  protobuf and gRPC C++ sources with `protoc` and `grpc_cpp_plugin`.
- Added an asynchronous CompletionQueue upstream server, asynchronous proxy
  forwarding, and a client fixture under `test/programs/grpc_proxy/`.
- Added a real post-response null dereference scenario that produces a
  FaultDebug SIGSEGV artifact while the client still receives the response.
- Added independent FDAR, signal-origin, module, sequence, boundary-marker,
  symbolization, and verified-bundle source checks in `test/grpc_proxy_test.py`.
- Added a clean `max-calls=1` shutdown check that requires no fault artifact.
- Added process-group cleanup for timeout paths and explicit handling for
  closed gRPC completion queues and upstream forwarding failures.
- Kept gRPC and generated protobuf internals outside blanket function
  instrumentation; only application-owned proxy boundary markers are recorded
  so the bounded ring remains useful.
- Missing gRPC/protobuf packages leave the optional fixture `SKIPPED` while the
  existing C/C++ fixture suite remains buildable.

The gRPC fixture demonstrates function-boundary evidence and source recovery.
RPC IDs, metadata propagation, gRPC status events, and semantic cross-process
correlation remain planned for a later ABI/MCP extension.

## [0.2.0rc2] - 2026-09-29

- Added a scheduled/manual GitHub Actions workflow for the pinned fmt 11.1.4
  external evaluation, including Clang 18, the compiler wrapper, an
  instrumented driver, and the independent evaluator.
- Added explicit `NOT RUN` handling when apt, external network, toolchain, or
  Python dependencies are unavailable.
- Added `test/external_fmt_v020.py` for raw baseline/instrumented timing and RSS
  capture plus SIGILL, SIGSEGV, SIGBUS, SIGFPE, and SIGABRT artifact checks.
  The workflow runs this matrix when external build paths are supplied and
  records `NOT RUN` when those inputs are unavailable; timing has no pass/fail
  threshold.

## [0.1.0] - 2026-09-29

Initial public release.

- Added the C11 instrumentation runtime with fixed shared-memory ABI, per-thread event rings, startup readiness, module identity, alternate-stack fatal-signal capture, and bounded recorder memory.
- Added the Python launcher and post-exit collector with memfd transport, committed-record validation, checksums, partial-termination reporting, and versioned `.fault` artifacts.
- Added compilation-database indexing with direct and unresolved static relations.
- Added immutable source and binary bundles with Build ID and hash verification.
- Added CLI commands for running, inspecting, collecting, indexing, and creating bundles.
- Added read-only MCP tools for fault opening, thread traces, address resolution, source lookup, call relations, and multi-process metadata collection.
- Added process identity and optional trace/correlation context metadata with backward-compatible artifact reads.

Known limits are documented in [ROADMAP.md](ROADMAP.md).

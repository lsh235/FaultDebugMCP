#!/usr/bin/env python3
"""Audit real tools/list schemas and read-only behavior; do not estimate TDQS."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from faultdebug.aggregate import ArtifactIndex
from faultdebug.artifact import write_artifact
from faultdebug.bundle import create_bundle
from faultdebug.evidence_store import EvidenceStore

FOCUSED_TOOLS = {
    'get_capabilities', 'discover_artifacts', 'discover_bundles', 'open_fault',
    'get_thread_trace', 'get_fault_flow', 'get_rpc_trace', 'get_incident_report',
    'check_store', 'list_incidents', 'get_incident_slice', 'get_source_evidence',
    'resolve_addresses', 'get_function_source', 'get_call_relations',
}
OUTPUT_SCHEMA_TOOLS = {
    'get_capabilities', 'check_store', 'discover_artifacts', 'discover_bundles',
    'get_function_source', 'list_incidents', 'list_sessions', 'get_source_evidence',
    'get_rpc_trace', 'get_fault_flow', 'get_incident_report', 'resolve_addresses',
    'get_call_relations', 'get_thread_trace',
}
FOCUSED_OUTPUT_SCHEMA_TOOLS = OUTPUT_SCHEMA_TOOLS - {'list_sessions'}
PROFILE_DESCRIPTION_EXPECTATIONS = {
    'check_store': ('get_provenance', ('list_incidents',)),
    'open_fault': ('get_evidence_summary', ('discover_artifacts', 'get_fault_flow', 'get_rpc_trace')),
    'get_rpc_trace': ('get_process_relations', ('get_thread_trace', 'get_fault_flow', 'get_incident_report')),
    'get_incident_report': ('get_evidence_summary', ('get_incident_slice', 'open_fault')),
    'list_incidents': ('get_unresolved', ('get_incident_slice', 'get_incident_report')),
    'get_incident_slice': ('get_unresolved', ('list_incidents', 'get_incident_report', 'get_source_evidence')),
    'discover_artifacts': ('query_artifact_index', ('open_fault', 'get_fault_flow')),
    'get_call_relations': ('get_process_relations', ('get_fault_flow', 'get_rpc_trace')),
}


def payload(result):
    assert not result.isError, result
    return json.loads(next(block.text for block in result.content if block.type == 'text'))


def structured_payload(result):
    assert not result.isError, f"MCP call returned error: {result.content}"
    structured = getattr(result, 'structuredContent', None)
    assert isinstance(structured, dict), f"missing structuredContent: {result}"
    return structured


def validate_structured_payload(result, output_schema):
    structured = structured_payload(result)
    jsonschema.validate(structured, output_schema)
    return structured


def assert_source_evidence_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == {'result'}
    structured_result = structured['result']
    convenience = {'file', 'line_start', 'line_end', 'sha256', 'function_id'}
    omitted = set(structured_result) - set(text_result)
    assert omitted <= convenience
    assert all(structured_result[key] is None for key in omitted)
    assert {key: structured_result[key] for key in text_result} == text_result
    return structured


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def rpc_artifact(root, stem, extension=None, header=None, pid=100):
    report = {'process': {'pid': pid}, 'threads': [], 'crashes': []}
    if extension is not None:
        report['rpc_trace'] = extension
    if header is not None:
        report['header'] = header
    return write_artifact(report, root, pid, artifact_stem=stem)


def flow_artifact(root, stem, *, status=0, complete=True, dropped=0):
    report = {
        'complete': complete,
        'header': {'status': status},
        'snapshot_consistency': {'stable': True, 'unstable_records': []},
        'target': {'returncode': -11, 'signal': 11},
        'modules': [],
        'threads': [{
            'slot': 0, 'tid': 100, 'generation': 1, 'flags': 0,
            'event_count': 2, 'dropped_count': dropped,
            'events': [
                {'sequence': 0, 'monotonic_ns': 10, 'function': 4096,
                 'callsite': 0, 'type': 1, 'generation': 1},
                {'sequence': 1, 'monotonic_ns': 20, 'function': 4096,
                 'callsite': 0, 'type': 1, 'generation': 1},
            ],
        }],
        'crashes': [{
            'flags': 15, 'tid': 100, 'thread_generation': 1,
            'pc': 8192, 'fault_address': 0, 'signal': 11,
            'si_code': 1, 'monotonic_ns': 25,
        }],
    }
    return write_artifact(report, root, 100, artifact_stem=stem)


def assert_rpc_trace_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result)
    for key, value in text_result.items():
        if key != 'observed':
            assert structured[key] == value, key
            continue
        assert len(structured['observed']) == len(value)
        for structured_event, text_event in zip(structured['observed'], value):
            omitted = set(structured_event) - set(text_event)
            assert omitted <= set(output_schema['$defs']['RpcTraceEvent']['properties']) - set(text_event)
            assert all(structured_event[field] is None for field in omitted)
            assert {field: structured_event[field] for field in text_event} == text_event
    return structured


def assert_fault_flow_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result)
    assert structured['schema_version'] == text_result['schema_version'] == 1
    assert structured['kind'] == text_result['kind'] == 'faultdebug-fault-flow'
    assert structured['capture']['evidence_status'] == text_result['capture']['evidence_status']
    assert len(structured['threads']) == len(text_result['threads'])
    assert len(structured['crashes']) == len(text_result['crashes'])
    return structured


def assert_incident_report_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result)
    for key, value in text_result.items():
        if key != 'observed':
            assert structured[key] == value, key
            continue
        assert set(structured['observed']) == set(value)
        assert structured['observed']['process_relations'] == value['process_relations']
        assert len(structured['observed']['rpc_events']) == len(value['rpc_events'])
        allowed_optional = set(output_schema['$defs']['IncidentReportRpcEvent']['properties'])
        for structured_event, text_event in zip(
                structured['observed']['rpc_events'], value['rpc_events']):
            omitted = set(structured_event) - set(text_event)
            assert omitted <= allowed_optional - set(text_event), omitted
            assert all(structured_event[field] is None for field in omitted)
            assert {field: structured_event[field] for field in text_event} == text_event
    return structured


def assert_resolve_addresses_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result) == {'items'}
    assert len(structured['items']) == len(text_result['items'])
    allowed_optional = set(output_schema['$defs']['FaultFlowResolution']['properties'])
    for structured_item, text_item in zip(structured['items'], text_result['items']):
        omitted = set(structured_item) - set(text_item)
        assert omitted <= allowed_optional - set(text_item), omitted
        assert all(structured_item[field] is None for field in omitted)
        assert {field: structured_item[field] for field in text_item} == text_item
    return structured


def assert_call_relations_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result)
    for key, value in text_result.items():
        if key != 'relations':
            assert structured[key] == value, key
            continue
        assert len(structured['relations']) == len(value)
        allowed_optional = set(output_schema['$defs']['StaticCallRelation']['properties'])
        for structured_row, text_row in zip(structured['relations'], value):
            omitted = set(structured_row) - set(text_row)
            assert omitted <= allowed_optional - set(text_row), omitted
            assert all(structured_row[field] is None for field in omitted)
            assert {field: structured_row[field] for field in text_row} == text_row
    return structured


def assert_open_row(structured_row, text_row, allowed_optional, *, skip=()):
    omitted = set(structured_row) - set(text_row)
    assert omitted <= set(allowed_optional) - set(text_row), omitted
    assert all(structured_row[field] is None for field in omitted)
    for field, value in text_row.items():
        if field not in skip:
            assert structured_row[field] == value, field


def assert_thread_trace_contract(result, output_schema, text_result):
    structured = validate_structured_payload(result, output_schema)
    assert set(structured) == set(text_result)
    for field in ('page', 'page_size', 'total'):
        assert structured[field] == text_result[field], field
    thread_fields = output_schema['$defs']['ThreadTraceThread']['properties']
    event_fields = output_schema['$defs']['ThreadTraceEvent']['properties']
    assert len(structured['items']) == len(text_result['items'])
    for structured_thread, text_thread in zip(structured['items'], text_result['items']):
        assert_open_row(structured_thread, text_thread,
                        set(thread_fields) - set(output_schema['$defs']['ThreadTraceThread'].get('required', [])),
                        skip={'events', 'retention'})
        assert len(structured_thread['events']) == len(text_thread['events'])
        for structured_event, text_event in zip(
                structured_thread['events'], text_thread['events']):
            assert_open_row(
                structured_event, text_event,
                set(event_fields) - set(output_schema['$defs']['ThreadTraceEvent'].get('required', [])))
        if 'retention' in text_thread:
            assert_open_row(structured_thread['retention'], text_thread['retention'],
                            set(output_schema['$defs']['ThreadTraceRetention']['properties']))
        else:
            assert structured_thread['retention'] is None
        assert set(structured_thread) <= set(thread_fields) | set(text_thread)
    return structured


def assert_profile_descriptions(full_tools, focused_tools):
    hidden_names = set(full_tools) - set(focused_tools)
    for name, tool in focused_tools.items():
        for hidden_name in hidden_names:
            assert re.search(r'(?<![A-Za-z0-9_])' + re.escape(hidden_name) +
                             r'(?![A-Za-z0-9_])', tool.description) is None, (
                                 name, hidden_name, tool.description)
    for name, (full_alternative, focused_alternatives) in PROFILE_DESCRIPTION_EXPECTATIONS.items():
        assert full_alternative in full_tools[name].description, (
            name, full_alternative, full_tools[name].description)
        assert full_alternative not in focused_tools[name].description, (
            name, full_alternative, focused_tools[name].description)
        for alternative in focused_alternatives:
            assert alternative in focused_tools, (name, alternative)
            assert alternative in focused_tools[name].description, (
                name, alternative, focused_tools[name].description)


async def audit(root):
    capture = write_artifact({'process': {'pid': 7}, 'threads': [], 'crashes': []}, root, 7)
    thread_history = write_artifact({
        'process': {'pid': 77},
        'threads': [
            {'slot': 0, 'tid': 77, 'generation': 1, 'flags': 0,
             'event_count': 1, 'dropped_count': 0,
             'events': [{'sequence': 0, 'monotonic_ns': 10, 'function': 4096,
                         'callsite': 0, 'type': 1, 'generation': 1,
                         'producer_extension': 'event-v1'}],
             'producer_extension': {'source': 'index-fixture'}},
            {'slot': 1, 'tid': 77, 'generation': 2, 'flags': 3,
             'event_count': 2, 'dropped_count': 0,
             'events': [{'sequence': 1, 'monotonic_ns': 20, 'function': 8192,
                         'callsite': 4096, 'type': 2, 'generation': 2}],
             'retention': {'scope': 'current_thread_generation',
                           'event_count_scope': 'current_generation',
                           'dropped_count_scope': 'slot_lifetime',
                           'retired_generations': 1, 'retired_event_count': None,
                           'producer_extension': 'retention-v1'}},
        ],
        'crashes': [],
    }, root, 77, artifact_stem='thread-history')
    sparse_thread_history = root / 'fault-sparse-thread.json'
    sparse_thread_history.write_text(json.dumps({
        'threads': [{'tid': 78, 'generation': 3,
                     'events': [{'sequence': 4, 'type': 9}]}],
    }))
    flow_good = flow_artifact(root, 'flow-good')
    flow_limited = flow_artifact(root, 'flow-limited', status=1 << 9,
                                 complete=False, dropped=3)
    rpc_events = [
        {'sequence': index, 'monotonic_ns': index * 10, 'rpc_id': 7,
         'kind': 'client', 'phase': 'status'}
        for index in range(1, 202)
    ]
    rpc_events[0].update({'pid': 100, 'trace_id_hi': 1, 'trace_id_lo': 2,
                          'method_id': 42, 'retry_count': 0, 'role': True,
                          'status': True, 'stream': True})
    rpc_events[-1].update({'status': 0, 'streaming': False})
    rpc_good = rpc_artifact(root, 'rpc-good', {'schema': 1, 'events': rpc_events})
    incident_sender = rpc_artifact(root, 'incident-sender', {
        'schema': 1,
        'events': [{'rpc_id': 'alpha27-rpc', 'phase': 'send', 'pid': 410,
                    'method_id': 42, 'status': 'OK', 'deadline_ns': 1000,
                    'retry_count': 1, 'stream': 'unary'}],
        'static_candidates': [{'kind': 'candidate', 'rpc_id': 'alpha27-rpc'}],
    }, pid=410)
    incident_receiver = rpc_artifact(root, 'incident-receiver', {
        'schema': 1,
        'events': [{'rpc_id': 'alpha27-rpc', 'phase': 'receive', 'pid': 411,
                    'method_id': 42, 'status': 'OK', 'streaming': False}],
    }, pid=411)
    rpc_gap = rpc_artifact(root, 'rpc-gap', {'schema': 1, 'events': [
        {'sequence': 1, 'monotonic_ns': 10}, {'sequence': 3, 'monotonic_ns': 30}]})
    rpc_reversal = rpc_artifact(root, 'rpc-reversal', {'schema': 1, 'events': [
        {'sequence': 2, 'monotonic_ns': 10}, {'sequence': 1, 'monotonic_ns': 20}]})
    rpc_partial = rpc_artifact(root, 'rpc-partial', {'schema': 1, 'events': rpc_events[:1]},
                               header={'status': (1 << 3) | (1 << 9)})
    rpc_incomplete = rpc_artifact(root, 'rpc-incomplete', {
        'schema': 1, 'events': rpc_events[:1], 'complete': False,
        'header': {'flags': 1, 'dropped_count': 2}})
    rpc_empty = rpc_artifact(root, 'rpc-empty', {'schema': 1, 'events': []})
    rpc_bad_version = rpc_artifact(root, 'rpc-bad-version', {'schema': 99, 'events': []})
    rpc_duplicate = write_artifact({
        'process': {'pid': 101}, 'threads': [], 'crashes': [],
        'rpc_trace': {'schema': 1, 'events': []}, 'rpc': {'schema': 1, 'events': []}},
        root, 101, artifact_stem='rpc-duplicate')
    (root / 'debug').mkdir()
    nested = root / 'nested'
    nested.mkdir()
    (nested / 'fault-nested.json').write_text(json.dumps({'process': {'pid': 8}}))
    (nested / 'fault-malformed.json').write_text('{malformed capture\n')
    declared = root / 'declared.json'
    declared.write_text(json.dumps({
        'session': {'schema': 1, 'session_id': 'session-a', 'participant_id': 'proc-a'},
        'process': {'pid': 9, 'start_monotonic_ns': 100,
                    'identity': {'schema': 1, 'session_id': 'session-a',
                                 'process_id': 'proc-a', 'process_generation': 1}},
        'collector': {'incident_id': 'incident-a', 'trigger_process_id': 'proc-a',
                      'trigger_signal': 11, 'status': 'captured', 'phase': 'test',
                      'partial': True},
    }))
    source_root = root / 'source'
    source_root.mkdir()
    (source_root / 'main.c').write_text(
        'int main(void) {\n  return 0;\n}\nvoid helper(void) {\n}\n')
    source_index = root / 'index.json'
    source_index.write_text(json.dumps({'functions': [
        {'id': 'fn-main', 'name': 'main', 'file': 'main.c', 'line': 1,
         'source_range': {'start': 1, 'end': 3},
         'edges': [{'callee_id': 'fn-helper', 'kind': 'direct',
                    'confidence': 'index-fixture'}],
         'unresolved_edges': [{'spelling': 'callback', 'kind': 'indirect_or_virtual',
                               'confidence': 'index-fixture'}]},
        {'id': 'fn-helper', 'name': 'helper', 'file': 'main.c', 'line': 4,
         'source_range': {'start': 4, 'end': 5}, 'edges': [], 'unresolved_edges': []},
    ]}))
    bundle_directory = root / 'bundles with spaces' / 'build-001'
    create_bundle(source_root, bundle_directory, index=source_index)
    source_bundle_path = 'bundles with spaces/build-001'
    malformed_bundle = root / 'malformed-bundle'
    malformed_bundle.mkdir()
    (malformed_bundle / 'bundle.json').write_text('{malformed\n')
    symlink_bundle = root / 'symlink-bundle'
    symlink_bundle.mkdir()
    (symlink_bundle / 'bundle.json').symlink_to(Path(__file__).resolve())
    with EvidenceStore(root / 'evidence.sqlite3') as store:
        for artifact in (capture, declared):
            ingested = store.ingest(artifact)
            assert ingested['status'] == 'ingested', ingested
    index = ArtifactIndex(root / 'index.sqlite')
    index.add([capture])
    index.close()
    sqlite3.connect(root / 'empty.sqlite').close()
    before = snapshot(root)
    params = StdioServerParameters(command=sys.executable,
                                   args=['-m', 'faultdebug.cli', 'mcp', '--root', str(root)],
                                   cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.instructions and len(initialized.instructions) <= 512
            listed = await session.list_tools()
            tools = {tool.name: tool for tool in listed.tools}
            assert len(tools) == 27, sorted(tools)
            assert FOCUSED_TOOLS <= set(tools), sorted(tools)
            for name, tool in tools.items():
                assert tool.title and tool.title != name and len(tool.title) > len(name), (name, tool.title)
                assert tool.annotations and tool.annotations.title == tool.title, name
            assert len({tool.title for tool in tools.values()}) == len(tools)
            assert {name for name, tool in tools.items() if tool.outputSchema} == OUTPUT_SCHEMA_TOOLS
            for name in OUTPUT_SCHEMA_TOOLS:
                assert tools[name].outputSchema, name
                if name == 'list_incidents':
                    incident_output_schema = tools[name].outputSchema
                    assert incident_output_schema.get('type') == 'object'
                    assert incident_output_schema.get('required') == ['result']
                    assert len(incident_output_schema['properties']['result'].get('anyOf', [])) == 2
                else:
                    assert tools[name].outputSchema.get('type') == 'object', (name, tools[name].outputSchema)
            assert 'schema' in tools['get_capabilities'].outputSchema['properties']
            assert 'artifacts' in tools['discover_artifacts'].outputSchema['properties']
            assert 'bundles' in tools['discover_bundles'].outputSchema['properties']
            assert 'error' in tools['check_store'].outputSchema['properties']
            source_schema = tools['get_function_source'].outputSchema
            assert source_schema.get('properties', {}).keys() == {
                'resolved', 'function_id', 'bundle', 'file', 'start_line', 'end_line', 'source'}
            assert set(source_schema.get('required', [])) == {
                'resolved', 'function_id', 'bundle', 'file', 'start_line', 'end_line', 'source'}
            assert source_schema['properties']['resolved']['const'] is True
            incident_schema = tools['list_incidents'].outputSchema
            assert set(incident_schema['properties']) == {'result'}
            incident_defs = incident_schema.get('$defs', {})
            assert set(incident_defs['IncidentListItem']['properties']) == {
                'incident_id', 'session_id', 'trigger_process_id', 'trigger_signal', 'status',
                'phase', 'partial', 'first_seen_ns', 'trust_state', 'artifact_count'}
            assert set(incident_defs['IncidentListSuccess']['properties']) == {
                'schema', 'incidents', 'total', 'page', 'page_size'}
            assert set(incident_defs['IncidentListError']['properties']) == {'schema', 'error'}
            session_schema = tools['list_sessions'].outputSchema
            assert set(session_schema['properties']) == {
                'schema', 'sessions', 'total', 'page', 'page_size'}
            session_defs = session_schema.get('$defs', {})
            assert set(session_defs['SessionListItem']['properties']) == {
                'session_id', 'first_start_ns', 'artifact_count', 'verified_count',
                'identity_source', 'trust_state'}
            assert set(session_schema.get('required', [])) == {
                'schema', 'sessions', 'total', 'page', 'page_size'}
            source_evidence_schema = tools['get_source_evidence'].outputSchema
            assert set(source_evidence_schema.get('properties', {})) == {'result'}
            assert len(source_evidence_schema['properties']['result'].get('anyOf', [])) == 2
            source_evidence_defs = source_evidence_schema.get('$defs', {})
            assert set(source_evidence_defs['SourceEvidenceSuccess']['properties']) == {
                'schema', 'incident_id', 'bundle', 'citations', 'unresolved', 'total',
                'page', 'page_size', 'resolved', 'file', 'line_start', 'line_end',
                'sha256', 'function_id'}
            assert set(source_evidence_defs['SourceEvidenceCitation']['properties']) == {
                'incident_id', 'artifact_id', 'function_id', 'bundle', 'file', 'line_start',
                'line_end', 'sha256', 'manifest_sha256', 'verified'}
            assert set(source_evidence_defs['SourceEvidenceUnresolved']['properties']) == {
                'function_id', 'reason', 'message'}
            assert set(source_evidence_defs['SourceEvidenceError']['properties']) == {'schema', 'error'}
            rpc_schema = tools['get_rpc_trace'].outputSchema
            assert set(rpc_schema['properties']) == {
                'schema', 'status', 'source', 'observed', 'static_candidates',
                'unresolved', 'total', 'page', 'page_size'}
            rpc_defs = rpc_schema.get('$defs', {})
            assert set(rpc_defs['RpcTraceEvent']['properties']) == {
                'event_index', 'sequence', 'monotonic_ns', 'start_monotonic_ns',
                'end_monotonic_ns', 'trace_id_hi', 'trace_id_lo', 'direction', 'tid',
                'process_generation', 'thread_generation', 'rpc_id', 'kind', 'method_id',
                'phase', 'role', 'status', 'deadline_ns', 'retry_count', 'attempt',
                'stream', 'streaming', 'pid', 'peer_pid', 'flags', 'generation',
                'publication', 'source'}
            assert len(rpc_schema['properties']['unresolved']['items']['discriminator']['mapping']) == 6
            fault_flow_schema = tools['get_fault_flow'].outputSchema
            assert set(fault_flow_schema['properties']) == {
                'schema_version', 'kind', 'language', 'capture', 'target', 'threads',
                'crashes', 'edges', 'sources', 'gaps', 'diagnostics', 'limitations', 'bundle'}
            assert set(fault_flow_schema['$defs']['FaultFlowEvent']['properties']) == {
                'id', 'kind', 'sequence', 'monotonic_ns', 'function', 'callsite',
                'depth', 'gaps_before', 'resolution', 'label', 'source_verified'}
            assert set(fault_flow_schema['$defs']['FaultFlowSource']['properties']) == {
                'resolved', 'function_id', 'bundle', 'file', 'start_line', 'end_line',
                'display_end_line', 'source'}
            incident_report_schema = tools['get_incident_report'].outputSchema
            assert set(incident_report_schema['properties']) == {
                'schema', 'status', 'artifacts', 'observed', 'static_candidates',
                'unresolved', 'fields', 'page', 'page_size', 'total_rpc_events'}
            incident_report_defs = incident_report_schema['$defs']
            assert set(incident_report_defs['IncidentReportObserved']['properties']) == {
                'rpc_events', 'process_relations'}
            assert set(incident_report_defs['IncidentReportFields']['properties']) == {
                'status', 'deadlines', 'retries', 'streams'}
            assert 'artifact_index' in incident_report_defs[
                'IncidentReportRpcEvent']['properties']
            resolve_addresses_schema = tools['resolve_addresses'].outputSchema
            assert set(resolve_addresses_schema['properties']) == {'items'}
            assert resolve_addresses_schema['$defs']['FaultFlowResolution'] == \
                fault_flow_schema['$defs']['FaultFlowResolution']
            call_relations_schema = tools['get_call_relations'].outputSchema
            assert set(call_relations_schema['properties']) == {
                'function_id', 'direction', 'relations', 'evidence', 'bundle'}
            assert set(call_relations_schema['properties']['direction']['enum']) == {
                'inbound', 'outbound'}
            assert call_relations_schema['properties']['evidence']['const'] == 'static_index'
            assert set(call_relations_schema['$defs']['StaticCallRelation']['properties']) == {
                'caller_id', 'callee_id', 'spelling', 'kind', 'edge'}
            assert call_relations_schema['$defs']['StaticCallRelation'][
                'additionalProperties'] is True
            thread_trace_schema = tools['get_thread_trace'].outputSchema
            assert set(thread_trace_schema['properties']) == {
                'items', 'page', 'page_size', 'total'}
            assert thread_trace_schema['properties']['page_size']['const'] == 200
            for model in ('ThreadTraceThread', 'ThreadTraceEvent', 'ThreadTraceRetention'):
                assert thread_trace_schema['$defs'][model]['additionalProperties'] is True
            parameters = 0
            for name, tool in tools.items():
                assert tool.description and 30 <= len(tool.description) <= 1600, name
                assert tool.annotations, name
                hints = tool.annotations
                assert (hints.readOnlyHint is True and hints.destructiveHint is False
                        and hints.idempotentHint is True and hints.openWorldHint is False), name
                for parameter, schema in tool.inputSchema.get('properties', {}).items():
                    assert schema.get('description', '').strip(), (name, parameter)
                    parameters += 1
                page = tool.inputSchema.get('properties', {}).get('page')
                if page:
                    assert page.get('minimum') == 0, name
            direction = tools['get_call_relations'].inputSchema['properties']['direction']
            assert set(direction['enum']) == {'inbound', 'outbound'}
            capabilities_result = await session.call_tool('get_capabilities', {})
            full_capabilities = payload(capabilities_result)
            assert validate_structured_payload(
                capabilities_result, tools['get_capabilities'].outputSchema) == full_capabilities
            assert full_capabilities['mcp_tool_profile'] == 'full'
            assert set(full_capabilities['exposed_tools']) == set(tools)
            assert set(full_capabilities['required_tools']) <= set(tools)
            for tool_name in ('get_function_source', 'get_call_relations'):
                schema = tools[tool_name].inputSchema
                assert 'bundle' in schema['required'], (tool_name, schema)
                assert schema['properties']['bundle'].get('type') == 'string', (tool_name, schema)
            for tool_name in ('open_fault', 'get_fault_flow', 'resolve_addresses'):
                schema = tools[tool_name].inputSchema
                assert 'bundle' not in schema.get('required', []), (tool_name, schema)
            bundles_result = await session.call_tool('discover_bundles', {})
            discovered_bundles = payload(bundles_result)
            structured_bundles = validate_structured_payload(
                bundles_result, tools['discover_bundles'].outputSchema)
            assert structured_bundles['total'] == discovered_bundles['total']
            assert [(row['path'], row['status']) for row in structured_bundles['bundles']] == [
                (row['path'], row['status']) for row in discovered_bundles['bundles']]
            assert any(row['status'] == 'rejected' and row['reason'] == 'symlink_manifest'
                       for row in structured_bundles['bundles'])
            assert discovered_bundles['verification'] == 'not_performed', discovered_bundles
            assert discovered_bundles['total'] == 3, discovered_bundles
            assert discovered_bundles['candidate_count'] == 2, discovered_bundles
            assert discovered_bundles['rejected_count'] == 1, discovered_bundles
            bundle_rows = {row['path']: row for row in discovered_bundles['bundles']}
            assert bundle_rows[source_bundle_path]['status'] == 'candidate', bundle_rows
            assert bundle_rows[source_bundle_path]['manifest_bytes'] == (bundle_directory / 'bundle.json').stat().st_size
            assert bundle_rows['malformed-bundle']['status'] == 'candidate', bundle_rows
            assert bundle_rows['symlink-bundle']['status'] == 'rejected', bundle_rows
            source_bundle_path = bundle_rows[source_bundle_path]['path']
            source_result = await session.call_tool('get_function_source', {
                'name': capture.name, 'function_id': 'fn-main', 'bundle': source_bundle_path})
            source = payload(source_result)
            assert validate_structured_payload(
                source_result, source_schema) == source
            assert source['resolved'] is True and 'int main' in source['source'], source
            relations_result = await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-main', 'bundle': source_bundle_path})
            relations = payload(relations_result)
            assert_call_relations_contract(relations_result, call_relations_schema, relations)
            assert relations['evidence'] == 'static_index' and relations['direction'] == 'outbound', relations
            assert [row['kind'] for row in relations['relations']] == [
                'direct', 'indirect_or_virtual']
            assert relations['relations'][0]['callee_id'] == 'fn-helper'
            assert relations['relations'][0]['confidence'] == 'index-fixture'
            assert relations['relations'][1]['spelling'] == 'callback'
            assert relations['relations'][1]['confidence'] == 'index-fixture'
            inbound_result = await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-helper',
                'bundle': source_bundle_path, 'direction': 'inbound'})
            inbound_relations = payload(inbound_result)
            assert_call_relations_contract(
                inbound_result, call_relations_schema, inbound_relations)
            assert inbound_relations['relations'] == [{
                'caller_id': 'fn-main',
                'edge': {'callee_id': 'fn-helper', 'kind': 'direct',
                         'confidence': 'index-fixture'}}]
            empty_relations_result = await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-helper',
                'bundle': source_bundle_path, 'direction': 'outbound'})
            empty_relations = payload(empty_relations_result)
            assert_call_relations_contract(
                empty_relations_result, call_relations_schema, empty_relations)
            assert empty_relations['relations'] == []
            caps = payload(await session.call_tool('get_capabilities', {}))
            assert caps['platform_toolchain']['mcp_transport'] == 'stdio'
            opened = payload(await session.call_tool('open_fault', {'name': capture.name}))
            assert opened['process']['pid'] == 7
            thread_trace_result = await session.call_tool('get_thread_trace', {
                'name': thread_history.name})
            thread_trace_text = payload(thread_trace_result)
            thread_trace = assert_thread_trace_contract(
                thread_trace_result, thread_trace_schema, thread_trace_text)
            assert thread_trace_text['total'] == 2 and thread_trace_text['page_size'] == 200
            assert [row['generation'] for row in thread_trace['items']] == [1, 2]
            assert thread_trace['items'][0]['retention'] is None
            assert thread_trace['items'][0]['producer_extension'] == {'source': 'index-fixture'}
            assert thread_trace['items'][0]['events'][0]['producer_extension'] == 'event-v1'
            assert thread_trace['items'][1]['retention']['producer_extension'] == 'retention-v1'
            sparse_result = await session.call_tool('get_thread_trace', {
                'name': sparse_thread_history.name})
            sparse_text = payload(sparse_result)
            sparse_structured = assert_thread_trace_contract(
                sparse_result, thread_trace_schema, sparse_text)
            assert set(sparse_text['items'][0]) == {'tid', 'generation', 'events'}
            assert set(sparse_text['items'][0]['events'][0]) == {'sequence', 'type'}
            assert sparse_structured['items'][0]['slot'] is None
            assert sparse_structured['items'][0]['events'][0]['callsite'] is None
            filtered_thread_trace_result = await session.call_tool('get_thread_trace', {
                'name': thread_history.name, 'tid': 77})
            filtered_thread_trace = payload(filtered_thread_trace_result)
            assert_thread_trace_contract(
                filtered_thread_trace_result, thread_trace_schema, filtered_thread_trace)
            assert [row['generation'] for row in filtered_thread_trace['items']] == [1, 2]
            missing_thread_trace_result = await session.call_tool('get_thread_trace', {
                'name': thread_history.name, 'tid': 78})
            missing_thread_trace = payload(missing_thread_trace_result)
            assert_thread_trace_contract(
                missing_thread_trace_result, thread_trace_schema, missing_thread_trace)
            assert missing_thread_trace['items'] == [] and missing_thread_trace['total'] == 0
            exhausted_thread_trace_result = await session.call_tool('get_thread_trace', {
                'name': thread_history.name, 'page': 1})
            exhausted_thread_trace = payload(exhausted_thread_trace_result)
            assert_thread_trace_contract(
                exhausted_thread_trace_result, thread_trace_schema, exhausted_thread_trace)
            assert exhausted_thread_trace['items'] == []
            assert exhausted_thread_trace['total'] == 2 and exhausted_thread_trace['page'] == 1
            empty_resolutions_result = await session.call_tool('resolve_addresses', {
                'name': capture.name, 'addresses': [], 'debug_directory': 'debug'})
            empty_resolutions = payload(empty_resolutions_result)
            assert_resolve_addresses_contract(
                empty_resolutions_result, resolve_addresses_schema, empty_resolutions)
            assert empty_resolutions['items'] == []
            unresolved_addresses_result = await session.call_tool('resolve_addresses', {
                'name': capture.name, 'addresses': [1]})
            unresolved_addresses = payload(unresolved_addresses_result)
            assert_resolve_addresses_contract(
                unresolved_addresses_result, resolve_addresses_schema, unresolved_addresses)
            assert unresolved_addresses['items'][0]['address'] == 1
            assert unresolved_addresses['items'][0]['resolved'] is False
            assert unresolved_addresses['items'][0]['reason'] == 'missing_module'
            artifact_result = await session.call_tool('discover_artifacts', {'include_json': True})
            found = payload(artifact_result)
            assert validate_structured_payload(
                artifact_result, tools['discover_artifacts'].outputSchema) == found
            assert found['invalid'] >= 1
            assert 'nested/fault-nested.json' in {row['path'] for row in found['artifacts']}
            empty_discovery_result = await session.call_tool('discover_artifacts', {
                'pattern': 'no-matches-*.fault'})
            empty_discovery = payload(empty_discovery_result)
            assert validate_structured_payload(
                empty_discovery_result, tools['discover_artifacts'].outputSchema) == empty_discovery
            assert empty_discovery['total'] == empty_discovery['count'] == 0
            indexed = payload(await session.call_tool('query_artifact_index', {'name': 'index.sqlite'}))
            assert indexed['count'] == 1
            sessions_result = await session.call_tool('list_sessions', {})
            sessions = payload(sessions_result)
            assert validate_structured_payload(sessions_result, session_schema) == sessions
            assert sessions['total'] == 2
            sessions_by_id = {row['session_id']: row for row in sessions['sessions']}
            assert sessions_by_id['session-a']['first_start_ns'] == 100
            assert sessions_by_id['session-a']['artifact_count'] == 1
            assert sessions_by_id[None]['first_start_ns'] is None
            assert sessions_by_id[None]['identity_source'] == 'absent'
            empty_sessions_result = await session.call_tool('list_sessions', {'start_ns': 101})
            empty_sessions = payload(empty_sessions_result)
            assert validate_structured_payload(empty_sessions_result, session_schema) == empty_sessions
            assert empty_sessions['sessions'] == [] and empty_sessions['total'] == 0
            missing_sessions_result = await session.call_tool(
                'list_sessions', {'db': 'absent.sqlite'})
            assert missing_sessions_result.isError is True
            unassigned = payload(await session.call_tool('get_session', {'session_id': None}))
            assert unassigned['total_artifacts'] == 1
            assert unassigned['session']['session_id'] is None
            assert payload(await session.call_tool('get_session', {'session_id': 'absent'}))['artifacts'] == []
            incidents_result = await session.call_tool('list_incidents', {})
            incidents = payload(incidents_result)
            incident_structured = validate_structured_payload(incidents_result, incident_schema)
            assert incident_structured == {'result': incidents}
            assert incidents['total'] == 1 and incidents['incidents'][0]['incident_id'] == 'incident-a'
            assert incidents['incidents'][0]['partial'] == 1
            source_single_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path,
                'function_ids': ['fn-main']})
            source_single = payload(source_single_result)
            assert_source_evidence_contract(
                source_single_result, source_evidence_schema, source_single)
            assert source_single['total'] == 1 and source_single['resolved'] is True
            assert source_single['file'] == source_single['citations'][0]['file']
            assert source_single['sha256'] == source_single['citations'][0]['sha256']
            assert source_single['citations'][0]['verified'] is True
            source_many_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path,
                'function_ids': ['fn-main', 'fn-helper']})
            source_many = payload(source_many_result)
            assert_source_evidence_contract(
                source_many_result, source_evidence_schema, source_many)
            assert source_many['total'] == 2 and len(source_many['citations']) == 2
            assert 'file' not in source_many and 'line_start' not in source_many
            source_none_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path, 'function_ids': []})
            source_none = payload(source_none_result)
            assert_source_evidence_contract(
                source_none_result, source_evidence_schema, source_none)
            assert source_none['citations'] == [] and source_none['resolved'] is False
            source_unresolved_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path,
                'function_ids': ['missing-function']})
            source_unresolved = payload(source_unresolved_result)
            assert_source_evidence_contract(
                source_unresolved_result, source_evidence_schema, source_unresolved)
            assert not source_unresolved['citations'] and len(source_unresolved['unresolved']) == 1
            assert source_unresolved['unresolved'][0]['reason'] == 'source_citation_unresolved'
            assert source_unresolved['resolved'] is False
            source_error_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path, 'db': 'absent.sqlite'})
            source_error = payload(source_error_result)
            assert_source_evidence_contract(
                source_error_result, source_evidence_schema, source_error)
            assert source_error['error']['code'] == 'SOURCE_EVIDENCE_ERROR'
            source_bundle_error_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': 'malformed-bundle'})
            source_bundle_error = payload(source_bundle_error_result)
            assert_source_evidence_contract(
                source_bundle_error_result, source_evidence_schema, source_bundle_error)
            assert source_bundle_error['error']['code'] == 'SOURCE_EVIDENCE_ERROR'
            fault_flow_result = await session.call_tool(
                'get_fault_flow', {'name': flow_good.name})
            fault_flow_text = payload(fault_flow_result)
            fault_flow_structured = assert_fault_flow_contract(
                fault_flow_result, fault_flow_schema, fault_flow_text)
            assert fault_flow_text['capture']['evidence_status'] == 'capture_complete'
            assert len(fault_flow_text['threads'][0]['events']) == 2
            assert fault_flow_text['crashes'][0]['last_event'] == 'thread-0-event-1'
            assert {edge['kind'] for edge in fault_flow_text['edges']} == {
                'observed_nesting', 'record_order', 'crash_context'}
            assert fault_flow_structured['threads'][0]['events'][0]['kind'] == 'enter'
            assert fault_flow_structured['crashes'][0]['resolution']['reason'] == 'missing_module'
            fault_flow_truncated_result = await session.call_tool(
                'get_fault_flow', {'name': flow_good.name, 'max_events': 1})
            fault_flow_truncated = payload(fault_flow_truncated_result)
            assert_fault_flow_contract(
                fault_flow_truncated_result, fault_flow_schema, fault_flow_truncated)
            assert fault_flow_truncated['threads'][0]['omitted_from_view'] == 1
            assert fault_flow_truncated['capture']['evidence_status'] == 'capture_complete'
            fault_flow_limited_result = await session.call_tool(
                'get_fault_flow', {'name': flow_limited.name})
            fault_flow_limited = payload(fault_flow_limited_result)
            assert_fault_flow_contract(
                fault_flow_limited_result, fault_flow_schema, fault_flow_limited)
            assert fault_flow_limited['capture']['evidence_status'] == 'limited'
            assert any(gap.get('reason') == 'dropped_records'
                       for gap in fault_flow_limited['gaps'])
            fault_flow_empty_result = await session.call_tool(
                'get_fault_flow', {'name': capture.name})
            fault_flow_empty = payload(fault_flow_empty_result)
            assert_fault_flow_contract(
                fault_flow_empty_result, fault_flow_schema, fault_flow_empty)
            assert not fault_flow_empty['threads'] and not fault_flow_empty['crashes']
            fault_flow_bad_bundle = await session.call_tool(
                'get_fault_flow', {'name': flow_good.name, 'bundle': '../escape'})
            assert fault_flow_bad_bundle.isError
            rpc_result = await session.call_tool('get_rpc_trace', {'name': rpc_good.name})
            rpc_text = payload(rpc_result)
            assert_rpc_trace_contract(rpc_result, rpc_schema, rpc_text)
            assert rpc_text['schema'] == 1 and rpc_text['status'] == 'complete'
            assert rpc_text['source'] == 'rpc_trace' and rpc_text['total'] == 201
            assert rpc_text['page'] == 0 and rpc_text['page_size'] == 200
            assert len(rpc_text['observed']) == 200
            assert rpc_text['observed'][0]['trace_id_hi'] == 1
            assert rpc_text['observed'][0]['retry_count'] == 0
            rpc_page_result = await session.call_tool(
                'get_rpc_trace', {'name': rpc_good.name, 'page': 1})
            rpc_page = payload(rpc_page_result)
            assert_rpc_trace_contract(rpc_page_result, rpc_schema, rpc_page)
            assert rpc_page['page'] == 1 and rpc_page['total'] == 201
            assert len(rpc_page['observed']) == 1
            incident_page0_result = await session.call_tool(
                'get_incident_report', {'names': [rpc_good.name]})
            incident_page0 = payload(incident_page0_result)
            incident_page0_structured = assert_incident_report_contract(
                incident_page0_result, incident_report_schema, incident_page0)
            assert incident_page0['page'] == 0 and incident_page0['page_size'] == 200
            assert incident_page0['total_rpc_events'] == 201
            assert len(incident_page0['observed']['rpc_events']) == 200
            assert incident_page0_structured['fields'] == incident_page0['fields']
            assert incident_page0['fields']['retries'][0]['retry_count'] == 0
            incident_page1_result = await session.call_tool(
                'get_incident_report', {'names': [rpc_good.name], 'page': 1})
            incident_page1 = payload(incident_page1_result)
            assert_incident_report_contract(
                incident_page1_result, incident_report_schema, incident_page1)
            assert incident_page1['page'] == 1 and incident_page1['total_rpc_events'] == 201
            assert len(incident_page1['observed']['rpc_events']) == 1
            incident_join_result = await session.call_tool('get_incident_report', {
                'names': [incident_sender.name, incident_receiver.name]})
            incident_join = payload(incident_join_result)
            assert_incident_report_contract(
                incident_join_result, incident_report_schema, incident_join)
            assert len(incident_join['observed']['rpc_events']) == 2
            assert len(incident_join['observed']['process_relations']) == 1
            assert incident_join['observed']['process_relations'][0]['kind'] == 'rpc'
            assert incident_join['static_candidates'] == [
                {'kind': 'candidate', 'rpc_id': 'alpha27-rpc'}]
            assert incident_join['fields']['deadlines'] == [{
                'artifact_index': 0, 'rpc_id': 'alpha27-rpc', 'deadline_ns': 1000}]
            assert incident_join['fields']['retries'] == [{
                'artifact_index': 0, 'rpc_id': 'alpha27-rpc', 'retry_count': 1}]
            assert incident_join['fields']['streams'] == [
                {'artifact_index': 0, 'rpc_id': 'alpha27-rpc', 'stream': 'unary'},
                {'artifact_index': 1, 'rpc_id': 'alpha27-rpc', 'streaming': False}]
            incident_empty_result = await session.call_tool(
                'get_incident_report', {'names': [capture.name]})
            incident_empty = payload(incident_empty_result)
            assert_incident_report_contract(
                incident_empty_result, incident_report_schema, incident_empty)
            assert incident_empty['status'] == 'unresolved'
            assert incident_empty['observed']['rpc_events'] == []
            assert incident_empty['unresolved']
            rpc_absent_result = await session.call_tool('get_rpc_trace', {'name': capture.name})
            rpc_absent = payload(rpc_absent_result)
            assert_rpc_trace_contract(rpc_absent_result, rpc_schema, rpc_absent)
            assert rpc_absent['status'] == 'unresolved' and rpc_absent['source'] is None
            assert rpc_absent['unresolved'][0]['reason'] == 'semantic_rpc_extension_absent'
            diagnostic_cases = [
                (rpc_gap, 'rpc_sequence_gap'),
                (rpc_reversal, 'rpc_sequence_not_monotonic'),
                (rpc_partial, 'runtime_trace_partial_or_overflow'),
                (rpc_incomplete, 'semantic_rpc_stream_incomplete'),
                (rpc_empty, 'semantic_rpc_events_empty'),
            ]
            for artifact, reason in diagnostic_cases:
                diagnostic_result = await session.call_tool(
                    'get_rpc_trace', {'name': artifact.name})
                diagnostic = payload(diagnostic_result)
                assert_rpc_trace_contract(diagnostic_result, rpc_schema, diagnostic)
                assert diagnostic['status'] in {'limited', 'unresolved'}
                assert reason in {row['reason'] for row in diagnostic['unresolved']}
            empty_incidents_result = await session.call_tool('list_incidents', {'session_id': 'absent'})
            empty_incidents = payload(empty_incidents_result)
            empty_incidents_structured = validate_structured_payload(
                empty_incidents_result, incident_schema)
            assert empty_incidents_structured == {'result': empty_incidents}
            assert empty_incidents['incidents'] == [] and empty_incidents['total'] == 0
            missing_incidents_result = await session.call_tool('list_incidents', {'db': 'absent.sqlite'})
            missing_incidents = payload(missing_incidents_result)
            missing_incidents_structured = validate_structured_payload(
                missing_incidents_result, incident_schema)
            assert missing_incidents_structured == {'result': missing_incidents}
            assert missing_incidents['error']['code'] == 'INCIDENT_QUERY_ERROR'
            invalid = [
                ('open_fault', {'name': '../escape.fault'}),
                ('open_fault', {'name': str(capture)}),
                ('get_incident_report', {'names': ['../escape.fault']}),
                ('get_incident_report', {'names': ['nested/fault-malformed.json']}),
                ('get_thread_trace', {'name': capture.name, 'page': -1}),
                ('get_thread_trace', {'name': '../escape.fault'}),
                ('get_fault_flow', {'name': capture.name, 'max_events': 501}),
                ('get_fault_flow', {'name': capture.name, 'debug_directory': '../outside'}),
                ('get_call_relations', {'name': capture.name, 'function_id': 'f', 'direction': 'both'}),
                ('get_call_relations', {'name': capture.name, 'function_id': 'absent-function',
                                        'bundle': source_bundle_path}),
                ('get_call_relations', {'name': capture.name, 'function_id': 'fn-main',
                                        'bundle': 'malformed-bundle'}),
                ('get_function_source', {'name': capture.name, 'function_id': 'fn-main'}),
                ('get_call_relations', {'name': capture.name, 'function_id': 'fn-main'}),
                ('get_function_source', {'name': capture.name, 'function_id': 'fn-main',
                                        'bundle': 'malformed-bundle'}),
                ('discover_bundles', {'page': -1}),
                ('list_sessions', {'trust_state': 'made-up'}),
                ('resolve_addresses', {'name': capture.name, 'addresses': [-1]}),
                ('resolve_addresses', {'name': capture.name, 'addresses': [1] * 1001}),
                ('resolve_addresses', {'name': capture.name, 'addresses': [], 'debug_directory': '/tmp'}),
                ('collect_faults', {'names': [capture.name] * 1001}),
                ('get_source_evidence', {'incident_id': 'i', 'bundle': '.', 'function_ids': ['f'] * 101}),
                ('get_rpc_trace', {'name': rpc_bad_version.name}),
                ('get_rpc_trace', {'name': rpc_duplicate.name}),
                ('query_artifact_index', {'name': 'empty.sqlite'}),
                ('query_artifact_index', {'name': 'missing.sqlite'}),
            ]
            for name, arguments in invalid:
                result = await session.call_tool(name, arguments)
                assert result.isError is True, (name, result)
            error = payload(await session.call_tool('get_incident_slice', {'incident_id': 'absent'}))
            assert error['error']['code'] == 'INCIDENT_QUERY_ERROR'
            health_result = await session.call_tool('check_store', {'db': 'absent.sqlite'})
            health = payload(health_result)
            health_structured = validate_structured_payload(
                health_result, tools['check_store'].outputSchema)
            assert health_structured['status'] == health['status']
            assert health_structured['error'] == health['error']
            assert health['read_only'] is True
            healthy_result = await session.call_tool('check_store', {'db': 'evidence.sqlite3'})
            healthy = payload(healthy_result)
            healthy_structured = validate_structured_payload(
                healthy_result, tools['check_store'].outputSchema)
            assert healthy['status'] == healthy_structured['status'] == 'healthy'
            assert healthy_structured['base_schema']['compatible'] is True
            invalid_path_result = await session.call_tool('check_store', {'db': '../escape.sqlite'})
            invalid_path = payload(invalid_path_result)
            assert validate_structured_payload(
                invalid_path_result, tools['check_store'].outputSchema)['error'] == invalid_path['error']
            assert invalid_path['error']['code'] == 'STORE_PATH_INVALID'
    assert snapshot(root) == before, 'MCP calls wrote or created evidence files'
    focused_params = StdioServerParameters(
        command=sys.executable,
        args=['-m', 'faultdebug.cli', 'mcp', '--root', str(root), '--tool-profile', 'focused'],
        cwd=str(ROOT))
    async with stdio_client(focused_params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.instructions and len(initialized.instructions) <= 512
            focused_listing = await session.list_tools()
            focused_tools = {tool.name: tool for tool in focused_listing.tools}
            assert set(focused_tools) == FOCUSED_TOOLS, sorted(focused_tools)
            assert_profile_descriptions(tools, focused_tools)
            assert all(tool.title and tool.title != name and len(tool.title) > len(name)
                       and tool.annotations and tool.annotations.title == tool.title
                       for name, tool in focused_tools.items())
            assert {name for name, tool in focused_tools.items() if tool.outputSchema} == FOCUSED_OUTPUT_SCHEMA_TOOLS
            assert focused_tools['get_function_source'].outputSchema == source_schema
            assert focused_tools['list_incidents'].outputSchema == incident_schema
            assert focused_tools['get_source_evidence'].outputSchema == source_evidence_schema
            assert focused_tools['get_rpc_trace'].outputSchema == rpc_schema
            assert focused_tools['get_fault_flow'].outputSchema == fault_flow_schema
            assert focused_tools['get_incident_report'].outputSchema == incident_report_schema
            assert focused_tools['resolve_addresses'].outputSchema == resolve_addresses_schema
            assert focused_tools['get_call_relations'].outputSchema == call_relations_schema
            assert focused_tools['get_thread_trace'].outputSchema == thread_trace_schema
            assert all(tool.annotations and tool.annotations.readOnlyHint is True
                       for tool in focused_tools.values())
            focused_parameters = 0
            for tool in focused_tools.values():
                for parameter, schema in tool.inputSchema.get('properties', {}).items():
                    assert schema.get('description', '').strip(), (tool.name, parameter)
                    focused_parameters += 1
            assert focused_parameters == 44, focused_parameters
            focused_incidents_result = await session.call_tool('list_incidents', {})
            focused_incidents = payload(focused_incidents_result)
            assert validate_structured_payload(
                focused_incidents_result, focused_tools['list_incidents'].outputSchema
            ) == {'result': focused_incidents}
            assert focused_incidents['total'] == 1
            focused_empty_incidents_result = await session.call_tool(
                'list_incidents', {'session_id': 'absent'})
            focused_empty_incidents = payload(focused_empty_incidents_result)
            assert validate_structured_payload(
                focused_empty_incidents_result, focused_tools['list_incidents'].outputSchema
            ) == {'result': focused_empty_incidents}
            assert focused_empty_incidents['incidents'] == []
            focused_source_result = await session.call_tool('get_source_evidence', {
                'incident_id': 'incident-a', 'bundle': source_bundle_path,
                'function_ids': ['fn-main']})
            focused_source = payload(focused_source_result)
            assert_source_evidence_contract(
                focused_source_result, focused_tools['get_source_evidence'].outputSchema,
                focused_source)
            assert focused_source['resolved'] is True and focused_source['total'] == 1
            focused_relations_result = await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-main',
                'bundle': source_bundle_path})
            focused_relations = payload(focused_relations_result)
            assert_call_relations_contract(
                focused_relations_result,
                focused_tools['get_call_relations'].outputSchema,
                focused_relations)
            assert focused_relations['relations'][0]['confidence'] == 'index-fixture'
            focused_inbound_result = await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-helper',
                'bundle': source_bundle_path, 'direction': 'inbound'})
            focused_inbound = payload(focused_inbound_result)
            assert_call_relations_contract(
                focused_inbound_result,
                focused_tools['get_call_relations'].outputSchema,
                focused_inbound)
            assert focused_inbound['relations'][0]['caller_id'] == 'fn-main'
            focused_thread_trace_result = await session.call_tool('get_thread_trace', {
                'name': thread_history.name, 'tid': 77})
            focused_thread_trace = payload(focused_thread_trace_result)
            assert_thread_trace_contract(
                focused_thread_trace_result,
                focused_tools['get_thread_trace'].outputSchema,
                focused_thread_trace)
            assert [row['generation'] for row in focused_thread_trace['items']] == [1, 2]
            focused_sparse_result = await session.call_tool('get_thread_trace', {
                'name': sparse_thread_history.name})
            focused_sparse_text = payload(focused_sparse_result)
            focused_sparse = assert_thread_trace_contract(
                focused_sparse_result,
                focused_tools['get_thread_trace'].outputSchema,
                focused_sparse_text)
            assert set(focused_sparse_text['items'][0]) == {'tid', 'generation', 'events'}
            assert focused_sparse['items'][0]['event_count'] is None
            assert focused_sparse['items'][0]['events'][0]['generation'] is None
            focused_rpc_result = await session.call_tool('get_rpc_trace', {'name': rpc_good.name})
            focused_rpc = payload(focused_rpc_result)
            assert_rpc_trace_contract(
                focused_rpc_result, focused_tools['get_rpc_trace'].outputSchema, focused_rpc)
            assert focused_rpc['status'] == 'complete' and focused_rpc['total'] == 201
            focused_incident_page0_result = await session.call_tool(
                'get_incident_report', {'names': [rpc_good.name]})
            focused_incident_page0 = payload(focused_incident_page0_result)
            assert_incident_report_contract(
                focused_incident_page0_result,
                focused_tools['get_incident_report'].outputSchema,
                focused_incident_page0)
            assert focused_incident_page0['total_rpc_events'] == 201
            focused_incident_join_result = await session.call_tool(
                'get_incident_report', {'names': [incident_sender.name, incident_receiver.name]})
            focused_incident_join = payload(focused_incident_join_result)
            assert_incident_report_contract(
                focused_incident_join_result,
                focused_tools['get_incident_report'].outputSchema,
                focused_incident_join)
            assert len(focused_incident_join['observed']['process_relations']) == 1
            focused_incident_empty_result = await session.call_tool(
                'get_incident_report', {'names': [capture.name]})
            focused_incident_empty = payload(focused_incident_empty_result)
            assert_incident_report_contract(
                focused_incident_empty_result,
                focused_tools['get_incident_report'].outputSchema,
                focused_incident_empty)
            assert focused_incident_empty['status'] == 'unresolved'
            focused_empty_resolutions_result = await session.call_tool(
                'resolve_addresses', {'name': capture.name, 'addresses': []})
            focused_empty_resolutions = payload(focused_empty_resolutions_result)
            assert_resolve_addresses_contract(
                focused_empty_resolutions_result,
                focused_tools['resolve_addresses'].outputSchema,
                focused_empty_resolutions)
            assert focused_empty_resolutions['items'] == []
            focused_unresolved_addresses_result = await session.call_tool(
                'resolve_addresses', {'name': capture.name, 'addresses': [1]})
            focused_unresolved_addresses = payload(focused_unresolved_addresses_result)
            assert_resolve_addresses_contract(
                focused_unresolved_addresses_result,
                focused_tools['resolve_addresses'].outputSchema,
                focused_unresolved_addresses)
            assert focused_unresolved_addresses['items'][0]['reason'] == 'missing_module'
            focused_fault_flow_result = await session.call_tool(
                'get_fault_flow', {'name': flow_good.name})
            focused_fault_flow = payload(focused_fault_flow_result)
            assert_fault_flow_contract(
                focused_fault_flow_result,
                focused_tools['get_fault_flow'].outputSchema,
                focused_fault_flow)
            assert focused_fault_flow['threads'][0]['events'][0]['kind'] == 'enter'
            focused_capabilities_result = await session.call_tool('get_capabilities', {})
            focused_capabilities = payload(focused_capabilities_result)
            assert validate_structured_payload(
                focused_capabilities_result, focused_tools['get_capabilities'].outputSchema
            ) == focused_capabilities
            assert focused_capabilities['mcp_tool_profile'] == 'focused'
            assert set(focused_capabilities['exposed_tools']) == FOCUSED_TOOLS
            assert set(focused_capabilities['required_tools']) <= FOCUSED_TOOLS
            for category in ('required_tools', 'additional_tools', 'v09_tools'):
                assert set(focused_capabilities[category]) <= FOCUSED_TOOLS, category
            hidden_tool = await session.call_tool('get_timeline', {'names': [capture.name]})
            assert hidden_tool.isError is True, hidden_tool
    assert snapshot(root) == before, 'focused MCP calls wrote or created evidence files'
    connection = sqlite3.connect(root / 'empty.sqlite')
    try:
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    finally:
        connection.close()
    readonly = ArtifactIndex(root / 'index.sqlite', readonly=True)
    try:
        try:
            readonly.db.execute('DROP TABLE artifacts')
        except sqlite3.OperationalError:
            pass
        else:
            raise AssertionError('read-only artifact index accepted a write')
    finally:
        readonly.close()
    return {'status': 'PASS', 'transport': 'stdio', 'tool_count': len(tools),
            'described_parameters': parameters, 'schema_description_coverage_percent': 100,
            'annotated_tools': len(tools), 'invalid_call_checks': len(invalid),
            'evidence_files_unchanged': True,
            'structured_output_tools': sorted(OUTPUT_SCHEMA_TOOLS),
            'focused_structured_output_tools': sorted(FOCUSED_OUTPUT_SCHEMA_TOOLS),
            'titled_tool_count': sum(bool(tool.title) for tool in tools.values()),
            'focused_titled_tool_count': sum(bool(tool.title) for tool in focused_tools.values()),
            'tdqs': {'status': 'NOT_EVALUATED', 'reason': 'Official score requires Glama rubric evaluation.'},
            'focused_tool_count': len(FOCUSED_TOOLS),
            'focused_parameter_count': focused_parameters,
            'tools': [tool.model_dump(by_alias=True, exclude_none=True) for tool in listed.tools]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional tools/list inventory and audit JSON')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='faultdebug-metadata-') as directory:
        result = asyncio.run(asyncio.wait_for(audit(Path(directory)), timeout=45))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(f"PASS: {result['tool_count']} full-profile tools/{result['described_parameters']} parameters, "
          f"{result['focused_tool_count']} focused-profile tools/{result['focused_parameter_count']} parameters; "
          f"{result['titled_tool_count']} full and {result['focused_titled_tool_count']} focused titles, "
          f"{len(result['structured_output_tools'])} full/{len(result['focused_structured_output_tools'])} focused structured-output tools, "
          f"{result['invalid_call_checks']} invalid calls rejected; evidence unchanged (TDQS not evaluated)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

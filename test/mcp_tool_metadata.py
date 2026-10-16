#!/usr/bin/env python3
"""Audit real tools/list schemas and read-only behavior; do not estimate TDQS."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
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
    'get_function_source',
}


def payload(result):
    assert not result.isError, result
    return json.loads(next(block.text for block in result.content if block.type == 'text'))


def structured_payload(result):
    assert not result.isError, result
    structured = getattr(result, 'structuredContent', None)
    assert isinstance(structured, dict), result
    return structured


def validate_structured_payload(result, output_schema):
    structured = structured_payload(result)
    jsonschema.validate(structured, output_schema)
    return structured


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


async def audit(root):
    capture = write_artifact({'process': {'pid': 7}, 'threads': [], 'crashes': []}, root, 7)
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
    }))
    source_root = root / 'source'
    source_root.mkdir()
    (source_root / 'main.c').write_text('int main(void) {\n  return 0;\n}\n')
    source_index = root / 'index.json'
    source_index.write_text(json.dumps({'functions': [
        {'id': 'fn-main', 'name': 'main', 'file': 'main.c', 'line': 1,
         'source_range': {'start': 1, 'end': 3}, 'edges': [], 'unresolved_edges': []},
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
            relations = payload(await session.call_tool('get_call_relations', {
                'name': capture.name, 'function_id': 'fn-main', 'bundle': source_bundle_path}))
            assert relations['evidence'] == 'static_index' and relations['direction'] == 'outbound', relations
            caps = payload(await session.call_tool('get_capabilities', {}))
            assert caps['platform_toolchain']['mcp_transport'] == 'stdio'
            opened = payload(await session.call_tool('open_fault', {'name': capture.name}))
            assert opened['process']['pid'] == 7
            assert payload(await session.call_tool('resolve_addresses', {
                'name': capture.name, 'addresses': [], 'debug_directory': 'debug'}))['items'] == []
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
            sessions = payload(await session.call_tool('list_sessions', {}))
            assert sessions['total'] == 2
            unassigned = payload(await session.call_tool('get_session', {'session_id': None}))
            assert unassigned['total_artifacts'] == 1
            assert unassigned['session']['session_id'] is None
            assert payload(await session.call_tool('get_session', {'session_id': 'absent'}))['artifacts'] == []
            invalid = [
                ('open_fault', {'name': '../escape.fault'}),
                ('open_fault', {'name': str(capture)}),
                ('get_thread_trace', {'name': capture.name, 'page': -1}),
                ('get_fault_flow', {'name': capture.name, 'max_events': 501}),
                ('get_fault_flow', {'name': capture.name, 'debug_directory': '../outside'}),
                ('get_call_relations', {'name': capture.name, 'function_id': 'f', 'direction': 'both'}),
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
            assert all(tool.title and tool.title != name and len(tool.title) > len(name)
                       and tool.annotations and tool.annotations.title == tool.title
                       for name, tool in focused_tools.items())
            assert {name for name, tool in focused_tools.items() if tool.outputSchema} == OUTPUT_SCHEMA_TOOLS
            assert focused_tools['get_function_source'].outputSchema == source_schema
            assert all(tool.annotations and tool.annotations.readOnlyHint is True
                       for tool in focused_tools.values())
            focused_parameters = 0
            for tool in focused_tools.values():
                for parameter, schema in tool.inputSchema.get('properties', {}).items():
                    assert schema.get('description', '').strip(), (tool.name, parameter)
                    focused_parameters += 1
            assert focused_parameters == 44, focused_parameters
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
          f"{len(result['structured_output_tools'])} structured-output tools, "
          f"{result['invalid_call_checks']} invalid calls rejected; evidence unchanged (TDQS not evaluated)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

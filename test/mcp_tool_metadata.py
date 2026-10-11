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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from faultdebug.aggregate import ArtifactIndex
from faultdebug.artifact import write_artifact
from faultdebug.evidence_store import EvidenceStore


def payload(result):
    assert not result.isError, result
    return json.loads(next(block.text for block in result.content if block.type == 'text'))


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


async def audit(root):
    capture = write_artifact({'process': {'pid': 7}, 'threads': [], 'crashes': []}, root, 7)
    nested = root / 'nested'
    nested.mkdir()
    (nested / 'fault-nested.json').write_text(json.dumps({'process': {'pid': 8}}))
    declared = root / 'declared.json'
    declared.write_text(json.dumps({
        'session': {'schema': 1, 'session_id': 'session-a', 'participant_id': 'proc-a'},
        'process': {'pid': 9, 'start_monotonic_ns': 100,
                    'identity': {'schema': 1, 'session_id': 'session-a',
                                 'process_id': 'proc-a', 'process_generation': 1}},
    }))
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
            assert len(tools) == 25, sorted(tools)
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
            caps = payload(await session.call_tool('get_capabilities', {}))
            assert caps['platform_toolchain']['mcp_transport'] == 'stdio'
            opened = payload(await session.call_tool('open_fault', {'name': capture.name}))
            assert opened['process']['pid'] == 7
            found = payload(await session.call_tool('discover_artifacts', {'include_json': True}))
            assert 'nested/fault-nested.json' in {row['path'] for row in found['artifacts']}
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
                ('get_call_relations', {'name': capture.name, 'function_id': 'f', 'direction': 'both'}),
                ('list_sessions', {'trust_state': 'made-up'}),
                ('resolve_addresses', {'name': capture.name, 'addresses': [-1]}),
                ('resolve_addresses', {'name': capture.name, 'addresses': [1] * 1001}),
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
            health = payload(await session.call_tool('check_store', {'db': 'absent.sqlite'}))
            assert health['read_only'] is True
            invalid_path = payload(await session.call_tool('check_store', {'db': '../escape.sqlite'}))
            assert invalid_path['error']['code'] == 'STORE_PATH_INVALID'
    assert snapshot(root) == before, 'MCP calls wrote or created evidence files'
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
            'tdqs': {'status': 'NOT_EVALUATED', 'reason': 'Official score requires Glama rubric evaluation.'},
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
    print(f"PASS: {result['tool_count']} stdio tools, {result['described_parameters']} documented parameters; "
          f"{result['invalid_call_checks']} invalid calls rejected; evidence unchanged (TDQS not evaluated)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

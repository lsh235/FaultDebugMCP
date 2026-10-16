#!/usr/bin/env python3
"""Bounded inputs, stable pagination and real read-only CLI/MCP parity."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import service_report_test as fixtures
from faultdebug import service_evidence as limits
from faultdebug.service_report import build_service_report
from faultdebug.service_query import COLLECTIONS, query_service_flow
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def fixture(root):
    fixtures.ServiceEvidenceTests().fixture(root)


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class ServiceQueryTests(unittest.TestCase):
    def test_page_union_and_snapshot_relocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'inputs'; root.mkdir(); fixture(root)
            summary = query_service_flow(root)
            self.assertNotIn('items', summary)
            model = build_service_report(root)
            for section in COLLECTIONS:
                combined, page = [], 0
                while True:
                    result = query_service_flow(root, section=section, page=page,
                                                page_size=1, snapshot_id=summary['snapshot_id'])
                    combined.extend(result['items'])
                    self.assertEqual(result['total'], len(model[section]))
                    if result['next_page'] is None: break
                    page = result['next_page']
                self.assertEqual(combined, model[section], section)
            clone = Path(tmp) / 'clone'; shutil.copytree(root, clone)
            self.assertEqual(query_service_flow(clone), summary)
            beyond = query_service_flow(root, section='events', page=999)
            self.assertEqual(beyond['items'], [])
            self.assertIsNone(beyond['next_page'])

    def test_snapshot_rejects_changed_added_and_deleted_evidence(self):
        for mutation in ('change', 'add', 'delete'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root)
                snapshot = query_service_flow(root)['snapshot_id']
                log = root / 'checkout/events.jsonl'
                if mutation == 'change': log.write_text(log.read_text().replace('order', 'other'))
                elif mutation == 'delete': log.unlink()
                else:
                    folder = root / 'extra'; folder.mkdir(); (folder / 'events.jsonl').write_text('')
                with self.assertRaisesRegex(ValueError, 'evidence changed'):
                    query_service_flow(root, snapshot_id=snapshot)

    def test_invalid_queries_fail_before_input_read(self):
        for arguments in ({'page': -1}, {'page': True}, {'page_size': 0}, {'page_size': 201},
                          {'page_size': True}, {'section': 'unknown'}, {'snapshot_id': 'bad'}, {'page': 1}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                query_service_flow(Path('/nonexistent'), **arguments)

    def test_response_budget_is_not_silent_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            with patch('faultdebug.service_query.MAX_RESPONSE_BYTES', 10):
                with self.assertRaisesRegex(ValueError, 'response byte budget'):
                    query_service_flow(root, section='events')

    def test_total_file_scan_and_capture_budgets(self):
        for constant, value in [('MAX_TOTAL_BYTES', 1), ('MAX_FILE_BYTES', 1),
                                ('MAX_FILES', 1), ('MAX_SCAN_ENTRIES', 1), ('MAX_CAPTURES', 1)]:
            with self.subTest(constant=constant), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root)
                with patch.object(limits, constant, value), self.assertRaises(ValueError):
                    build_service_report(root)

    def test_all_invalid_lines_consume_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            (root / 'checkout/events.jsonl').write_text('not-json\n' * 4)
            with patch('faultdebug.service_report.MAX_EVENTS', 3):
                with self.assertRaisesRegex(ValueError, 'Application event budget'):
                    build_service_report(root)

    def test_symlinks_and_fifo_are_rejected(self):
        for special in ('file-link', 'directory-link', 'fifo'):
            with self.subTest(special=special), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); fixture(root)
                if special == 'file-link': (root / 'linked.fault').symlink_to(next(root.rglob('*.fault')))
                elif special == 'directory-link': (root / 'linked').symlink_to(root / 'checkout', target_is_directory=True)
                else: os.mkfifo(root / 'events.jsonl')
                with self.assertRaises(ValueError): build_service_report(root)

    def test_reader_rejects_fifo_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'events.jsonl'; os.mkfifo(path)
            with self.assertRaises(ValueError): limits.EvidenceReader().read(path)

    def test_cli_parity_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            before = digest(root)
            command = [sys.executable, '-m', 'faultdebug.cli', 'service-query', str(root),
                       '--section', 'events', '--page-size', '1']
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
            self.assertEqual(json.loads(result.stdout), query_service_flow(root, section='events', page_size=1))
            bad = subprocess.run(command + ['--page', '-1'], capture_output=True, text=True, timeout=20)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, '')
            self.assertEqual(before, digest(root))

    def test_real_mcp_parity_root_errors_and_readonly(self):
        async def run(root):
            before = digest(root)
            params = StdioServerParameters(command=sys.executable,
                args=['-m', 'faultdebug.cli', 'mcp', '--root', str(root)])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool('get_service_flow', {'evidence': '.', 'section': 'events', 'page_size': 1})
                    self.assertFalse(result.isError)
                    payload = json.loads(next(block.text for block in result.content if block.type == 'text'))
                    self.assertEqual(payload, query_service_flow(root, section='events', page_size=1))
                    for args in ({'evidence': '../escape'}, {'evidence': str(root)},
                                 {'evidence': '.', 'page': -1}, {'evidence': '.', 'page_size': 201},
                                 {'evidence': '.', 'snapshot_id': '0' * 64}):
                        error = await session.call_tool('get_service_flow', args)
                        self.assertTrue(error.isError, args)
            self.assertEqual(before, digest(root))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            asyncio.run(asyncio.wait_for(run(root), timeout=30))


if __name__ == '__main__': unittest.main()

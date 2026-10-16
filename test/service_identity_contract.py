#!/usr/bin/env python3
"""Independent negative oracles for application/native evidence joins."""
import json
from pathlib import Path
import tempfile
import unittest
import service_report_test as fixtures
from service_report_test import capture
from faultdebug.artifact import write_artifact
from faultdebug.service_report import build_service_report


class IdentityContractTests(unittest.TestCase):
    def fixture(self, root):
        fixtures.ServiceEvidenceTests().fixture(root)

    def rewrite_logs(self, root, transform):
        for path in root.rglob('events.jsonl'):
            rows = [transform(json.loads(line)) for line in path.read_text().splitlines()]
            path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def test_high_trace_mismatch_never_corroborates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            self.rewrite_logs(root, lambda row: {**row, 'trace_id_hi': 1})
            model = build_service_report(root)
            self.assertEqual(model['calls'], [])
            self.assertTrue(all(cause['assessment'] == 'unresolved' for cause in model['causes']))

    def test_matching_full_trace_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            for role, direction in [('checkout', 2), ('inventory', 1)]:
                folder = root / role
                next(folder.glob('*.fault')).unlink()
                report = capture(role, direction, status=409)
                for event in report['rpc_events']: event['trace_id_hi'] = 42
                write_artifact(report, folder, 8)
            self.rewrite_logs(root, lambda row: {**row, 'trace_id_hi': 42})
            model = build_service_report(root)
            self.assertEqual(model['calls'][0]['trace_id_hi'], 42)
            self.assertEqual(model['calls'][0]['status'], 409)
            self.assertEqual(model['causes'][0]['assessment'], 'corroborated_rpc_status')

    def test_previous_generation_end_cannot_supply_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            # A separate generation exists but has no matching RPC endpoint.
            folder = root / 'old-checkout'; folder.mkdir()
            report = capture('checkout', 2, generation=2, trace=99)
            write_artifact(report, folder, 8)
            self.rewrite_logs(root, lambda row: {**row, 'process_generation': 2}
                              if row['kind'] == 'client_end' else row)
            model = build_service_report(root)
            self.assertEqual(len(model['calls']), 1)
            self.assertNotIn('status', model['calls'][0])
            self.assertNotIn('duration_ms', model['calls'][0])

    def test_invalid_identity_and_trace_types_are_rejected(self):
        for field, value in [('process_generation', True), ('pid', True),
                             ('trace_id_hi', True), ('trace_id_hi', -1),
                             ('trace_id_hi', 2**64), ('process_id', [])]:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); self.fixture(root)
                self.rewrite_logs(root, lambda row: {**row, field: value})
                with self.assertRaises(ValueError): build_service_report(root)

    def test_native_generation_conflict_cannot_corroborate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            folder = root / 'inventory'
            next(folder.glob('*.fault')).unlink()
            report = capture('inventory', 1, status=409)
            for event in report['rpc_events']: event['process_generation'] = 2
            write_artifact(report, folder, 8)
            model = build_service_report(root)
            self.assertEqual(model['causes'][0]['assessment'], 'unresolved')
            self.assertEqual(model['calls'], [])

    def test_missing_application_status_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            def strip_status(row):
                row.pop('status', None)
                return row
            self.rewrite_logs(root, strip_status)
            model = build_service_report(root)
            self.assertNotIn('status', model['calls'][0])
            self.assertEqual(model['causes'][0]['assessment'], 'unresolved_native_status_absent')

    def test_negative_duration_stays_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            self.rewrite_logs(root, lambda row: {**row, 'monotonic_ns': 0}
                              if row['kind'] == 'client_end' else row)
            model = build_service_report(root)
            self.assertNotIn('duration_ms', model['calls'][0])
            self.assertTrue(any(row['reason'] == 'application_time_order_invalid' for row in model['unresolved']))

    def test_duplicate_end_is_explicitly_unresolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.fixture(root)
            log = root / 'checkout/events.jsonl'
            log.write_text(log.read_text() + log.read_text().splitlines()[-1] + '\n')
            model = build_service_report(root)
            self.assertNotIn('status', model['calls'][0])
            self.assertTrue(any(row['reason'] == 'application_call_end_not_unique' for row in model['unresolved']))


if __name__ == '__main__': unittest.main()

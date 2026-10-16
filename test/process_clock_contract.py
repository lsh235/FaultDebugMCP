#!/usr/bin/env python3
"""Negative contracts for process generations and local clock provenance."""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from faultdebug.clock import local_clock_identity, local_deadline_ns
from faultdebug.session import (
    PARENT_PROCESS_ID_ENV, PROCESS_GENERATION_ENV, PROCESS_ID_ENV, PROCESS_ROLE_ENV,
    SESSION_ID_ENV, ProcessIdentity, SessionIdentityError, identity_from_env,
    identity_to_env, session_manifest,
)


BOOT_A = "e13b91ab-4e34-46f5-ac50-d63f57b710f4"
BOOT_B = "8a905a40-f976-4ebc-82d8-a8af42f93ce1"
NAMESPACE_A = "time:[4026531834]"
NAMESPACE_B = "time:[4026531835]"


class ClockContractTests(unittest.TestCase):
    def sample(self, boot=BOOT_A, namespace=NAMESPACE_A):
        return local_clock_identity(read_text=lambda _path, _limit: boot,
                                    readlink=lambda _path: namespace)

    def test_known_local_sources_give_repeatable_identity(self):
        first = self.sample()
        self.assertEqual(first, self.sample())
        self.assertEqual(first["schema"], 1)
        self.assertEqual(first["clock"], "monotonic")
        self.assertEqual(first["host_boot_id"], BOOT_A)
        self.assertEqual(first["time_namespace_id"], NAMESPACE_A)
        self.assertEqual(first["status"], "known")
        self.assertTrue(first["clock_domain_id"].startswith("linux-monotonic-v1:"))
        self.assertIn("sampling_process_only", first["limitations"])

    def test_different_boot_or_time_namespace_changes_domain(self):
        domain = self.sample()["clock_domain_id"]
        self.assertNotEqual(domain, self.sample(boot=BOOT_B)["clock_domain_id"])
        self.assertNotEqual(domain, self.sample(namespace=NAMESPACE_B)["clock_domain_id"])

    def test_missing_either_source_stays_unknown(self):
        for boot, namespace, limitation in [
            (None, NAMESPACE_A, "host_boot_id_unavailable"),
            (BOOT_A, None, "time_namespace_identity_unavailable"),
            (None, None, "host_boot_id_unavailable"),
        ]:
            with self.subTest(boot=boot, namespace=namespace):
                record = self.sample(boot, namespace)
                self.assertIsNone(record["clock_domain_id"])
                self.assertEqual(record["status"], "unknown")
                self.assertIn(limitation, record["limitations"])
                self.assertNotIn("hostname", record)
                self.assertNotIn("pid", record)

    def test_unreadable_proc_sources_stay_unknown(self):
        def unavailable(*_args):
            raise PermissionError("unavailable")
        result = local_clock_identity(read_text=unavailable, readlink=unavailable)
        self.assertIsNone(result["host_boot_id"])
        self.assertIsNone(result["time_namespace_id"])
        self.assertIsNone(result["clock_domain_id"])
        self.assertEqual(result["source"], {"host_boot_id": None, "time_namespace_id": None})

    def test_malformed_or_oversized_sources_are_not_identities(self):
        for value in ["", "not-a-boot-id", BOOT_A * 3, "{" + BOOT_A + "}"]:
            with self.subTest(boot=value):
                self.assertIsNone(self.sample(boot=value)["clock_domain_id"])
        for value in ["", "pid:[4026531834]", "time:[0]", "time:[01]", NAMESPACE_A + "\n"]:
            with self.subTest(namespace=value):
                self.assertIsNone(self.sample(namespace=value)["clock_domain_id"])

    def test_boot_source_requests_a_tiny_bounded_read(self):
        calls = []
        def read_boot(path, limit):
            calls.append((path, limit))
            return BOOT_A + "\n"
        result = local_clock_identity(read_text=read_boot, readlink=lambda _path: NAMESPACE_A)
        self.assertEqual(calls, [("/proc/sys/kernel/random/boot_id", 64)])
        self.assertEqual(result["status"], "known")

    def test_default_file_reader_does_not_read_an_unbounded_file(self):
        with patch("builtins.open", unittest.mock.mock_open(read_data=BOOT_A + "\n")) as source:
            result = local_clock_identity(readlink=lambda _path: NAMESPACE_A)
        source.return_value.read.assert_called_once_with(65)
        self.assertEqual(result["status"], "known")

    def test_receiver_local_deadline_uses_relative_budget(self):
        self.assertEqual(local_deadline_ns(1, now_ns=100), 1_000_100)
        self.assertEqual(local_deadline_ns(5000, now_ns=100), 5_000_000_100)
        with patch("faultdebug.clock.time.monotonic_ns", return_value=123):
            self.assertEqual(local_deadline_ns(50), 50_000_123)

    def test_invalid_or_unbounded_timeouts_are_rejected(self):
        for value in [True, False, 1.0, "1", None, -1, 0, 5001]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_deadline_ns(value, now_ns=100)
        for value in [True, False, -1, 1.0, "100"]:
            with self.subTest(now_ns=value), self.assertRaises(ValueError):
                local_deadline_ns(1, now_ns=value)


class ProcessGenerationContractTests(unittest.TestCase):
    def test_valid_generation_always_stores_an_actual_integer(self):
        for value in [1, 2, 0xFFFFFFFF, "1", "2", "4294967295"]:
            with self.subTest(value=value):
                direct = ProcessIdentity("session-a", "process-a", process_generation=value)
                self.assertIs(type(direct.process_generation), int)
                self.assertEqual(direct.process_generation, int(value))
                supplied = identity_from_env({"session_id": "session-a", "process_id": "process-a",
                                              "process_generation": value}, env={})
                self.assertIs(type(supplied.process_generation), int)

    def test_bool_float_and_noncanonical_generation_are_rejected(self):
        bad = [True, False, 1.0, 1.9, None, [], {}, "", "01", "+1", " 1", "1 ",
               "1\n", "1.0", "\uff11", "-1", "0", 0, -1, 2**32, "4294967296", "1" * 5000]
        for value in bad:
            with self.subTest(value=repr(value)[:50]), self.assertRaises(SessionIdentityError):
                ProcessIdentity("session-a", "process-a", process_generation=value)
            if value is not None:
                with self.subTest(supplied=repr(value)[:50]), self.assertRaises(SessionIdentityError):
                    identity_from_env({"process_generation": value}, env={})

    def test_environment_generation_and_parent_inheritance_remain_compatible(self):
        inherited = identity_from_env(env={SESSION_ID_ENV: "session-a", PROCESS_ID_ENV: "parent-a",
                                          PROCESS_GENERATION_ENV: "42", PROCESS_ROLE_ENV: "worker"})
        self.assertEqual(inherited.session_id, "session-a")
        self.assertNotEqual(inherited.process_id, "parent-a")
        self.assertEqual(inherited.parent_process_id, "parent-a")
        self.assertIs(type(inherited.process_generation), int)
        self.assertEqual(inherited.process_generation, 42)
        self.assertEqual(inherited.role, "worker")
        exported = identity_to_env(inherited, {})
        self.assertEqual(exported[PROCESS_GENERATION_ENV], "42")
        explicit_parent = identity_from_env(env={PROCESS_ID_ENV: "parent-a",
                                                 PARENT_PROCESS_ID_ENV: "supervisor-a"})
        self.assertEqual(explicit_parent.parent_process_id, "supervisor-a")

    def test_invalid_environment_generation_is_not_coerced(self):
        for value in ["01", "+1", "1.0", " 1", "0", "4294967296", True, 1.5]:
            with self.subTest(value=value), self.assertRaises(SessionIdentityError):
                identity_from_env(env={PROCESS_GENERATION_ENV: value})

    def test_absent_environment_keeps_legacy_default(self):
        identity = identity_from_env(env={})
        self.assertTrue(identity.session_id.startswith("session-"))
        self.assertTrue(identity.process_id.startswith("process-"))
        self.assertEqual(identity.process_generation, 1)
        self.assertIsNone(identity.parent_process_id)
        self.assertIsNone(identity.role)

    def test_clock_is_explicit_opt_in_and_old_reports_still_read(self):
        identity = ProcessIdentity("session-a", "process-a", role="worker")
        legacy = identity.process_record(pid=123)
        self.assertNotIn("clock", legacy)
        self.assertEqual(legacy["process_generation"], 1)
        clock = local_clock_identity(read_text=lambda _path, _limit: BOOT_A,
                                     readlink=lambda _path: NAMESPACE_A)
        enriched = identity.process_record(pid=123, clock=clock)
        self.assertEqual(enriched["clock"], clock)
        self.assertIsNot(enriched["clock"], clock)
        for record in [legacy, enriched]:
            manifest = session_manifest([{"session": identity.session_record(),
                                          "process": {"identity": record}}])
            participant = manifest["participants"][0]
            self.assertEqual(participant["process_generation"], 1)
            if "clock" in record:
                self.assertEqual(participant["clock"], clock)
            else:
                self.assertNotIn("clock", participant)


if __name__ == "__main__":
    unittest.main()

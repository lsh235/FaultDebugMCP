#!/usr/bin/env python3
"""Independent vectors and adversarial inputs at the HTTP context boundary."""
from dataclasses import FrozenInstanceError
from http.client import HTTPMessage
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from faultdebug.http_context import (TraceParent, child_traceparent,
                                    extract_traceparent, new_traceparent,
                                    parse_traceparent)


VECTOR = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


class HttpContextTests(unittest.TestCase):
    def test_known_w3c_vector_and_serialization(self):
        context = parse_traceparent(VECTOR)
        self.assertEqual(context.trace_id_hi, 0x4BF92F3577B34DA6)
        self.assertEqual(context.trace_id_lo, 0xA3CE929D0E0E4736)
        self.assertEqual(context.parent_id, 0x00F067AA0BA902B7)
        self.assertEqual(context.trace_flags, 1)
        self.assertEqual(context.to_header(), VECTOR)
        with self.assertRaises(FrozenInstanceError):
            context.parent_id = 2

    def test_full_128_bit_identity_and_u64_bounds(self):
        a = parse_traceparent("00-00000000000000010000000000000000-ffffffffffffffff-00")
        b = parse_traceparent("00-00000000000000020000000000000000-ffffffffffffffff-00")
        self.assertNotEqual(a, b)
        self.assertEqual((a.trace_id_hi, a.trace_id_lo), (1, 0))
        self.assertEqual((b.trace_id_hi, b.trace_id_lo), (2, 0))
        self.assertEqual(a.parent_id, 2**64 - 1)
        self.assertEqual(parse_traceparent("00-00000000000000000000000000000001-0000000000000001-ff"),
                         TraceParent(0, 1, 1, 255))

    def test_invalid_wire_forms(self):
        bad = ["", VECTOR.upper(), " " + VECTOR, VECTOR + " ", VECTOR + "\n",
               VECTOR[:-1], VECTOR + "0", VECTOR + "-extra", VECTOR.replace("-", ":", 1),
               VECTOR.replace("4bf92f", "4bg92f"),
               "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
               "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
               VECTOR.replace("4bf92f", "４bf92f")]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_traceparent(value)
        for value in (None, b"traceparent", 1, True, [VECTOR]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                parse_traceparent(value)

    def test_unsupported_versions_are_explicit(self):
        for version in ("01", "02", "ff"):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "Unsupported.*version"):
                parse_traceparent(version + VECTOR[2:])

    def test_constructor_rejects_bool_wrong_types_and_ranges(self):
        for field in ("trace_id_hi", "trace_id_lo", "parent_id", "trace_flags"):
            for value in (True, False, 1.0, "1", None):
                args = dict(trace_id_hi=1, trace_id_lo=2, parent_id=3, trace_flags=0)
                args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(TypeError):
                    TraceParent(**args)
            for value in (-1, 256 if field == "trace_flags" else 2**64):
                args = dict(trace_id_hi=1, trace_id_lo=2, parent_id=3, trace_flags=0)
                args[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    TraceParent(**args)
        for args in ((0, 0, 1, 0), (1, 0, 0, 0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                TraceParent(*args)

    def test_mapping_and_httpmessage_extraction(self):
        self.assertIsNone(extract_traceparent({"Content-Type": "application/json"}))
        self.assertIsNone(extract_traceparent(HTTPMessage()))
        self.assertEqual(extract_traceparent({"TrAcEpArEnT": VECTOR}), parse_traceparent(VECTOR))
        message = HTTPMessage()
        message.add_header("TraceParent", VECTOR)
        self.assertEqual(extract_traceparent(message), parse_traceparent(VECTOR))
        message.add_header("traceparent", VECTOR)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            extract_traceparent(message)
        repeated = HTTPMessage()
        repeated.add_header("traceparent", VECTOR)
        repeated.add_header("traceparent", VECTOR)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            extract_traceparent(repeated)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            extract_traceparent({"traceparent": VECTOR, "TraceParent": VECTOR})

    def test_no_silent_fallback_for_invalid_present_header(self):
        for value in ("", "garbage", VECTOR + ", " + VECTOR, VECTOR + ",", "\t" + VECTOR):
            with self.subTest(value=value), self.assertRaises(ValueError):
                extract_traceparent({"traceparent": value})
        for value in (None, True, 1, b"header", [VECTOR]):
            with self.subTest(value=value), self.assertRaises(TypeError):
                extract_traceparent({"traceparent": value})
        for headers in (None, [], [("traceparent", VECTOR)], {1: VECTOR}):
            with self.subTest(headers=headers), self.assertRaises(TypeError):
                extract_traceparent(headers)

    def test_new_trace_retries_zero_and_formats_independent_expected_value(self):
        with patch("faultdebug.http_context.secrets.randbits", side_effect=[0, 2**64, 0, 7]) as random:
            context = new_traceparent()
        self.assertEqual(context.to_header(),
                         "00-00000000000000010000000000000000-0000000000000007-00")
        self.assertEqual([call.args for call in random.call_args_list], [(128,), (128,), (64,), (64,)])

    def test_child_preserves_unsampled_and_other_flag_bits(self):
        for flags in (0, 1, 2, 0xFE, 0xFF):
            parent = TraceParent(0x4BF92F3577B34DA6, 0xA3CE929D0E0E4736, 7, flags)
            with patch("faultdebug.http_context.secrets.randbits", side_effect=[0, 7, 9]):
                child = child_traceparent(parent)
            self.assertEqual((child.trace_id_hi, child.trace_id_lo),
                             (0x4BF92F3577B34DA6, 0xA3CE929D0E0E4736))
            self.assertEqual(child.parent_id, 9)
            self.assertEqual(child.trace_flags, flags)
            self.assertTrue(child.to_header().endswith(f"-{flags:02x}"))
            self.assertEqual(parent.parent_id, 7)
        for parent in (None, VECTOR, {}, True):
            with self.subTest(parent=parent), self.assertRaises(TypeError):
                child_traceparent(parent)

    def test_random_contexts_have_nonzero_ids(self):
        for _ in range(16):
            context = new_traceparent()
            self.assertGreater(context.trace_id_hi | context.trace_id_lo, 0)
            self.assertGreater(context.parent_id, 0)
            self.assertEqual(len(context.to_header()), 55)
            self.assertEqual(parse_traceparent(context.to_header()), context)


if __name__ == "__main__":
    unittest.main()

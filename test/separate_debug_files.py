#!/usr/bin/env python3
"""Build-ID-checked separate debug ELF lookup and per-call symbol caching."""
from __future__ import annotations

import shutil
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faultdebug.inspect import _build_id, _source_for_address, _symbols, resolve_addresses


class SeparateDebugFileTests(unittest.TestCase):
    def test_stripped_binary_uses_only_matching_build_id_debug_file(self):
        compiler = shutil.which("cc") or shutil.which("gcc")
        objcopy = shutil.which("objcopy")
        strip = shutil.which("strip")
        if not compiler or not objcopy or not strip:
            self.skipTest("a C compiler, objcopy, and strip are required")
        with tempfile.TemporaryDirectory(prefix="faultdebug-debugfile-") as temporary:
            root = Path(temporary)
            source = root / "fixture.c"
            source.write_text(
                "__attribute__((noinline)) int fd_debug_target(int x) {\n"
                "  volatile int value = x + BUILD_VARIANT;\n"
                "  return value;\n"
                "}\n"
                "int main(int argc, char **argv) { (void)argv; return fd_debug_target(argc); }\n",
                encoding="utf-8",
            )

            def build(name: str, variant: int) -> tuple[Path, str, int]:
                binary = root / name
                subprocess.run([compiler, "-g", "-O0", "-fno-inline", "-no-pie",
                                f"-DBUILD_VARIANT={variant}", "-Wl,--build-id=sha1",
                                str(source), "-o", str(binary)], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                build_id = _build_id(binary)
                self.assertTrue(build_id)
                target = next(row for row in _symbols(binary) if row["name"] == "fd_debug_target")
                return binary, build_id, target["value"]

            binary, expected_id, address = build("app", 1)
            debug_root = root / "debug"
            debug_path = debug_root / ".build-id" / expected_id[:2] / f"{expected_id[2:]}.debug"
            debug_path.parent.mkdir(parents=True)
            subprocess.run([objcopy, "--only-keep-debug", str(binary), str(debug_path)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(_build_id(debug_path), expected_id)
            subprocess.run([strip, "--strip-all", str(binary)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            report = {"modules": [{"path": str(binary), "build_id": expected_id,
                                   "text_start": 0, "text_end": 1 << 64, "load_bias": 0}]}
            with patch("faultdebug.inspect._symbols", wraps=_symbols) as symbol_reader:
                resolved = resolve_addresses(report, [address, address],
                                             debug_directories=[debug_root])
            self.assertTrue(all(row["resolved"] for row in resolved), resolved)
            self.assertTrue(all(row["symbol"] == "fd_debug_target" for row in resolved), resolved)
            self.assertEqual(resolved[0]["debug_file"], str(debug_path.resolve()))
            self.assertEqual(resolved[0]["debug_file_build_id"], expected_id)
            self.assertEqual(symbol_reader.call_count, 2,
                             "binary and sidecar symbol tables should each be read once per call")

            without_sidecar = resolve_addresses(report, [address])
            self.assertFalse(without_sidecar[0]["resolved"], without_sidecar)
            self.assertEqual(without_sidecar[0]["reason"], "missing_symbol")

            wrong_binary, wrong_id, _ = build("wrong", 2)
            self.assertNotEqual(wrong_id, expected_id)
            wrong_root = root / "wrong-debug"
            wrong_path = wrong_root / ".build-id" / expected_id[:2] / f"{expected_id[2:]}.debug"
            wrong_path.parent.mkdir(parents=True)
            subprocess.run([objcopy, "--only-keep-debug", str(wrong_binary), str(wrong_path)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            mismatch = resolve_addresses(report, [address], debug_directories=[wrong_root])
            self.assertFalse(mismatch[0]["resolved"], mismatch)
            self.assertEqual(mismatch[0]["reason"], "missing_symbol")

    def test_bad_debug_directory_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "must exist and be directories"):
            resolve_addresses({"modules": []}, [], debug_directories=["/path/that/does/not/exist"])

    def test_symbolizer_is_local_and_receives_debug_root(self):
        with tempfile.TemporaryDirectory(prefix="faultdebug-symbolizer-") as temporary:
            root = Path(temporary)
            capture = root / "invocation.json"
            tool = root / "symbolizer"
            tool.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "open(os.environ['CAPTURE_FILE'], 'w').write(json.dumps({'args': sys.argv[1:], 'opts': os.environ.get('LLVM_SYMBOLIZER_OPTS')}))\n"
                "print('fd_debug_target\\nfixture.c:2:3')\n",
                encoding="utf-8",
            )
            tool.chmod(0o700)
            debug_root = root / "symbols"
            debug_root.mkdir()
            with patch.dict(os.environ, {
                "FAULTDEBUG_LLVM_SYMBOLIZER": str(tool),
                "LLVM_SYMBOLIZER_OPTS": "--debuginfod",
                "CAPTURE_FILE": str(capture),
            }):
                source = _source_for_address(root / "stripped", 0x401000, [debug_root])
            self.assertEqual(source, {"name": "fd_debug_target", "file": "fixture.c",
                                      "line": 2, "column": 3})
            invocation = __import__("json").loads(capture.read_text(encoding="utf-8"))
            self.assertIn("--no-debuginfod", invocation["args"])
            self.assertIn("--debug-file-directory", invocation["args"])
            self.assertIn(str(debug_root), invocation["args"])
            self.assertIsNone(invocation["opts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

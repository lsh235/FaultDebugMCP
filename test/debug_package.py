#!/usr/bin/env python3
"""End-to-end contract for safe separate-debug ELF package generation."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faultdebug.debug_package import DebugPackageError, create_debug_package
from faultdebug.inspect import _build_id, _symbols, resolve_addresses


class DebugPackageTests(unittest.TestCase):
    def setUp(self):
        self.compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        self.objcopy = shutil.which("objcopy") or shutil.which("llvm-objcopy")
        if not self.compiler or not self.objcopy:
            self.skipTest("a C compiler and objcopy are required")
        self.temporary = tempfile.TemporaryDirectory(prefix="faultdebug-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _build(self, name: str, *, debug: bool = True) -> Path:
        source = self.root / f"{name}.c"
        source.write_text(
            "__attribute__((noinline)) int fd_package_target(int x) {\n"
            "  volatile int value = x + 17;\n"
            "  return value;\n"
            "}\n"
            "int main(int argc, char **argv) { (void)argv; return fd_package_target(argc); }\n",
            encoding="utf-8",
        )
        binary = self.root / name
        command = [self.compiler, "-O0", "-no-pie", "-Wl,--build-id=sha1", str(source), "-o", str(binary)]
        if debug:
            command.insert(1, "-g")
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return binary

    def test_cli_creates_verified_runtime_and_build_id_debug_root(self):
        source = self._build("app")
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        output = self.root / "package"
        process = subprocess.run(
            [sys.executable, "-m", "faultdebug.cli", "debug-package", str(source),
             "--output", str(output), "--objcopy", self.objcopy],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        result = json.loads(process.stdout)
        self.assertTrue(result["verified"])
        build_id = _build_id(source)
        self.assertEqual(result["build_id"], build_id)
        runtime = Path(result["runtime"])
        debug_file = Path(result["debug_file"])
        self.assertEqual(runtime.relative_to(output).as_posix(), f"runtime/{source.name}")
        self.assertEqual(debug_file.relative_to(output).as_posix(),
                         f"debug/.build-id/{build_id[:2]}/{build_id[2:]}.debug")
        self.assertEqual(_build_id(runtime), build_id)
        self.assertEqual(_build_id(debug_file), build_id)
        self.assertNotIn("fd_package_target", {row["name"] for row in _symbols(runtime)})
        self.assertIn("fd_package_target", {row["name"] for row in _symbols(debug_file)})
        self.assertTrue(os.access(runtime, os.X_OK))
        self.assertEqual(stat.S_IMODE(runtime.stat().st_mode), stat.S_IMODE(source.stat().st_mode))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_digest)

        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["build_id"], build_id)
        self.assertEqual(manifest["source"]["sha256"], source_digest)
        report = {"modules": [{"path": str(runtime), "build_id": build_id,
                               "text_start": 0, "text_end": 1 << 64, "load_bias": 0}]}
        address = next(row["value"] for row in _symbols(debug_file)
                       if row["name"] == "fd_package_target")
        resolved = resolve_addresses(report, [address], debug_directories=[result["debug_root"]])
        self.assertTrue(resolved[0]["resolved"], resolved)
        self.assertEqual(resolved[0]["symbol"], "fd_package_target")
        self.assertEqual(resolved[0]["debug_file_build_id"], build_id)

    def test_existing_output_and_missing_debug_information_fail_closed(self):
        binary = self._build("existing")
        occupied = self.root / "occupied"
        occupied.mkdir()
        sentinel = occupied / "sentinel"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(DebugPackageError, "already exists"):
            create_debug_package(binary, occupied, objcopy=self.objcopy)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

        no_debug = self._build("no-debug", debug=False)
        output = self.root / "no-debug-package"
        with self.assertRaisesRegex(DebugPackageError, "no DWARF debug sections"):
            create_debug_package(no_debug, output, objcopy=self.objcopy)
        self.assertFalse(output.exists())

        invalid = self.root / "not-elf"
        invalid.write_text("not an ELF file", encoding="utf-8")
        with self.assertRaisesRegex(DebugPackageError, "not a readable ELF"):
            create_debug_package(invalid, self.root / "invalid-package", objcopy=self.objcopy)
        self.assertFalse((self.root / "invalid-package").exists())

    def test_objcopy_failure_removes_staging_output_and_preserves_input(self):
        binary = self._build("failure")
        original = hashlib.sha256(binary.read_bytes()).hexdigest()
        failing = self.root / "failing-objcopy"
        failing.write_text("#!/bin/sh\necho intentional failure >&2\nexit 19\n", encoding="utf-8")
        failing.chmod(0o700)
        output = self.root / "failed-package"
        with self.assertRaisesRegex(DebugPackageError, "intentional failure"):
            create_debug_package(binary, output, objcopy=failing)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".failed-package.staging-*")), [])
        self.assertEqual(hashlib.sha256(binary.read_bytes()).hexdigest(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)

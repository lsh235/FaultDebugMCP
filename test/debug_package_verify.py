#!/usr/bin/env python3
"""Read-only package manifest, hash, path, and Build-ID verification contract."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from faultdebug.debug_package import DebugPackageError, create_debug_package, verify_debug_package


class DebugPackageVerifyTests(unittest.TestCase):
    def setUp(self):
        self.compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        self.objcopy = shutil.which("objcopy") or shutil.which("llvm-objcopy")
        if not self.compiler or not self.objcopy:
            self.skipTest("a C compiler and objcopy are required")
        self.temporary = tempfile.TemporaryDirectory(prefix="faultdebug-package-verify-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _package(self, name: str) -> Path:
        source = self.root / f"{name}.c"
        source.write_text(
            "__attribute__((noinline)) int fd_verify_target(int x) {\n"
            "  volatile int value = x + 23;\n"
            "  return value;\n"
            "}\n"
            "int main(int argc, char **argv) { (void)argv; return fd_verify_target(argc); }\n",
            encoding="utf-8",
        )
        binary = self.root / name
        subprocess.run([self.compiler, "-g", "-O0", "-no-pie", "-Wl,--build-id=sha1",
                        str(source), "-o", str(binary)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = self.root / f"{name}-package"
        create_debug_package(binary, output, objcopy=self.objcopy)
        return output

    def test_cli_verifies_generated_package_without_writing(self):
        package = self._package("good")
        before = {path.relative_to(package).as_posix(): path.read_bytes()
                  for path in package.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, "-m", "faultdebug.cli", "debug-verify", str(package)],
                                cwd=ROOT, check=True, capture_output=True, text=True)
        report = json.loads(result.stdout)
        self.assertTrue(report["verified"])
        self.assertFalse(report["source_rehashed"])
        self.assertEqual(report["runtime"]["build_id"], report["debug"]["build_id"])
        after = {path.relative_to(package).as_posix(): path.read_bytes()
                 for path in package.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_changed_file_is_rejected_by_sha256(self):
        package = self._package("changed")
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        debug_file = package / manifest["debug"]["path"]
        with debug_file.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(DebugPackageError, "debug SHA-256"):
            verify_debug_package(package)

    def test_different_build_id_is_rejected_even_when_manifest_hash_matches(self):
        package = self._package("identity-a")
        other = self._package("identity-b")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        other_manifest = json.loads((other / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(manifest["build_id"], other_manifest["build_id"])
        debug_file = package / manifest["debug"]["path"]
        other_debug = other / other_manifest["debug"]["path"]
        debug_file.write_bytes(other_debug.read_bytes())
        manifest["debug"]["sha256"] = hashlib.sha256(debug_file.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DebugPackageError, "Build IDs do not match"):
            verify_debug_package(package)

    def test_manifest_traversal_and_symlink_paths_are_rejected(self):
        package = self._package("unsafe")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["runtime"]["path"] = "../outside"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DebugPackageError, "invalid runtime path"):
            verify_debug_package(package)

        package = self._package("symlink")
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        runtime = package / manifest["runtime"]["path"]
        outside = self.root / "outside-runtime"
        shutil.copy2(runtime, outside)
        runtime.unlink()
        runtime.symlink_to(outside)
        with self.assertRaisesRegex(DebugPackageError, "must not contain symlinks"):
            verify_debug_package(package)


if __name__ == "__main__":
    unittest.main(verbosity=2)

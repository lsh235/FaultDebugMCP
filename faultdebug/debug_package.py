"""Create an immutable, Build-ID-addressable runtime/debug ELF package."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from .inspect import _build_id


class DebugPackageError(ValueError):
    """Raised when an ELF cannot be packaged without weakening identity."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _debug_sections(path: Path) -> set[str]:
    try:
        from elftools.common.exceptions import ELFError
        from elftools.elf.elffile import ELFFile
    except ImportError as exc:
        raise DebugPackageError(f"cannot inspect ELF debug sections: {exc}") from exc
    try:
        with path.open("rb") as stream:
            elf = ELFFile(stream)
            return {section.name for section in elf.iter_sections()
                    if section.name.startswith((".debug_", ".zdebug_"))}
    except (ELFError, OSError, ValueError, KeyError) as exc:
        raise DebugPackageError(f"cannot inspect ELF debug sections: {exc}") from exc


def _objcopy_path(configured: str | os.PathLike[str] | None) -> str:
    requested = str(configured) if configured is not None else os.environ.get("FAULTDEBUG_OBJCOPY")
    if requested:
        resolved = shutil.which(requested)
        if resolved is None:
            candidate = Path(requested).expanduser()
            if candidate.is_file() and os.access(candidate, os.X_OK):
                resolved = str(candidate.resolve())
        if resolved is None:
            raise DebugPackageError("configured objcopy was not found or is not executable")
        return resolved
    for name in ("objcopy", "llvm-objcopy"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise DebugPackageError("GNU objcopy or llvm-objcopy is required (or set FAULTDEBUG_OBJCOPY)")


def _run_objcopy(tool: str, *arguments: str) -> None:
    try:
        result = subprocess.run([tool, *arguments], text=True, capture_output=True,
                                timeout=300, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DebugPackageError(f"objcopy could not complete: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise DebugPackageError(f"objcopy failed: {detail[-2000:]}")


def create_debug_package(binary: str | os.PathLike[str], output: str | os.PathLike[str], *,
                         objcopy: str | os.PathLike[str] | None = None) -> dict:
    """Split one linked ELF into a stripped runtime and a build-id debug root.

    The input is never modified. Output must be a new directory. All files are
    generated in a sibling staging directory and published only after the
    runtime and sidecar retain the input Build ID.
    """
    source = Path(binary).expanduser().resolve()
    destination = Path(output).expanduser().absolute()
    if not source.is_file():
        raise DebugPackageError("input must be an existing ELF file")
    if destination.exists() or destination.is_symlink():
        raise DebugPackageError("output directory already exists")
    try:
        from elftools.common.exceptions import ELFError
        from elftools.elf.elffile import ELFFile
        with source.open("rb") as stream:
            elf = ELFFile(stream)
            if str(elf.header["e_type"]) not in {"ET_EXEC", "ET_DYN"}:
                raise DebugPackageError("input must be a fully linked ET_EXEC or ET_DYN ELF")
    except ImportError as exc:
        raise DebugPackageError("pyelftools is required to validate ELF identity") from exc
    except (ELFError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, DebugPackageError):
            raise
        raise DebugPackageError(f"input is not a readable ELF file: {exc}") from exc

    build_id = _build_id(source)
    if not build_id:
        raise DebugPackageError("input ELF has no readable GNU Build ID")
    if not _debug_sections(source):
        raise DebugPackageError("input ELF contains no DWARF debug sections; build with debug information first")
    tool = _objcopy_path(objcopy)
    source_digest = _sha256(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise DebugPackageError("output directory already exists")
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=destination.parent))
    try:
        runtime_relative = Path("runtime") / source.name
        debug_relative = Path("debug") / ".build-id" / build_id[:2] / f"{build_id[2:]}.debug"
        runtime_path = staging / runtime_relative
        debug_path = staging / debug_relative
        runtime_path.parent.mkdir(parents=True)
        debug_path.parent.mkdir(parents=True)

        _run_objcopy(tool, "--only-keep-debug", str(source), str(debug_path))
        _run_objcopy(tool, "--strip-all", str(source), str(runtime_path))
        os.chmod(runtime_path, stat.S_IMODE(source.stat().st_mode))

        runtime_id = _build_id(runtime_path)
        debug_id = _build_id(debug_path)
        if runtime_id != build_id or debug_id != build_id:
            raise DebugPackageError("objcopy output Build IDs do not match the input ELF")
        if not _debug_sections(debug_path):
            raise DebugPackageError("objcopy output did not retain DWARF debug sections")
        if _debug_sections(runtime_path):
            raise DebugPackageError("objcopy output still contains DWARF debug sections in the runtime ELF")
        if _sha256(source) != source_digest:
            raise DebugPackageError("input ELF changed during packaging")

        manifest = {
            "schema": 1,
            "build_id": build_id,
            "source": {"filename": source.name, "sha256": source_digest},
            "runtime": {"path": runtime_relative.as_posix(), "sha256": _sha256(runtime_path)},
            "debug": {"path": debug_relative.as_posix(), "sha256": _sha256(debug_path)},
            "objcopy": Path(tool).name,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.rename(staging, destination)
        try:
            parent_fd = os.open(destination.parent, getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY)
        except OSError:
            parent_fd = None
        if parent_fd is not None:
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        return {
            "package": str(destination),
            "build_id": build_id,
            "runtime": str(destination / runtime_relative),
            "debug_root": str(destination / "debug"),
            "debug_file": str(destination / debug_relative),
            "manifest": str(destination / "manifest.json"),
            "verified": True,
        }
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

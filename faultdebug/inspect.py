from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .bundle import SourceBundle, load_bundle


class InspectionError(ValueError):
    pass

STATUS_EVENT_OVERFLOW = 1 << 3
STATUS_PARTIAL = 1 << 9


def _build_id(binary: Path) -> str | None:
    try:
        from elftools.common.exceptions import ELFError
        from elftools.elf.elffile import ELFFile
    except ImportError:
        return None
    try:
        with binary.open("rb") as stream:
            elf = ELFFile(stream)
            for section in elf.iter_sections():
                if section.name == ".note.gnu.build-id":
                    for note in section.iter_notes():
                        if note["n_type"] == "NT_GNU_BUILD_ID":
                            value = note["n_desc"]
                            return value.hex() if isinstance(value, bytes) else str(value).replace("0x", "").lower()
    except (ELFError, OSError, ValueError, KeyError):
        return None
    return None


def _symbols(binary: Path) -> list[dict]:
    try:
        from elftools.elf.elffile import ELFFile
    except ImportError as exc:
        raise InspectionError("pyelftools is required for offline ELF resolution") from exc
    rows: dict[tuple[int, int, str], dict] = {}
    with binary.open("rb") as stream:
        elf = ELFFile(stream)
        for section in elf.iter_sections():
            if section.header.get("sh_type") not in ("SHT_SYMTAB", "SHT_DYNSYM"):
                continue
            for symbol in section.iter_symbols():
                if symbol.entry["st_info"]["type"] not in ("STT_FUNC", "STT_NOTYPE") or not symbol.name:
                    continue
                value, size = int(symbol.entry["st_value"]), int(symbol.entry["st_size"])
                if value == 0: continue
                rows[(value, size, symbol.name)] = {"name": symbol.name, "value": value, "size": size, "end": value + max(size, 1)}
    return sorted(rows.values(), key=lambda row: (row["value"], row["size"], row["name"]))


def _symbolizer() -> str | None:
    configured = os.environ.get("FAULTDEBUG_LLVM_SYMBOLIZER")
    if configured and Path(configured).is_file(): return configured
    local = Path(__file__).resolve().parents[1] / ".tools" / "bin" / "llvm-symbolizer"
    return str(local) if local.is_file() else shutil.which("llvm-symbolizer-18") or shutil.which("llvm-symbolizer")


def _source_for_address(binary: Path, address: int, debug_directories: list[Path] | None = None) -> dict[str, Any] | None:
    tool = _symbolizer()
    if not tool: return None
    try:
        debug_args = [arg for root in (debug_directories or []) for arg in ("--debug-file-directory", str(root))]
        environment = os.environ.copy()
        environment.pop("LLVM_SYMBOLIZER_OPTS", None)
        proc = subprocess.run([tool, "--no-debuginfod", *debug_args, f"--obj={binary}", "--functions=linkage", "--inlining", hex(address)], text=True, capture_output=True, timeout=3, check=False, env=environment)
    except (OSError, subprocess.SubprocessError): return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) < 2: return None
    result: dict[str, Any] = {"name": lines[0]}
    match = re.match(r"^(.*?):(\d+)(?::(\d+))?$", lines[1])
    if match: result.update({"file": match.group(1), "line": int(match.group(2)), "column": int(match.group(3) or 0)})
    return result


def _separate_debug_file(build_id: str, directories: list[Path]) -> Path | None:
    """Find a matching GNU build-id debug file without network or broad scans."""
    normalized = build_id.lower()
    if len(normalized) < 4 or len(normalized) % 2 or not re.fullmatch(r"[0-9a-f]+", normalized):
        return None
    relative = Path(".build-id") / normalized[:2] / f"{normalized[2:]}.debug"
    for directory in directories:
        candidate = (directory / relative).resolve()
        if directory not in candidate.parents or not candidate.is_file():
            continue
        if _build_id(candidate) == normalized:
            return candidate
    return None


def _symbol_rows_for_address(binary: Path, address: int, debug_file: Path | None,
                             cache: dict[Path, list[dict]]) -> list[dict]:
    rows = cache.get(binary)
    if rows is None:
        rows = _symbols(binary)
        cache[binary] = rows
    matches = [row for row in rows if row["value"] <= address < row["end"]]
    if matches or debug_file is None:
        return matches
    rows = cache.get(debug_file)
    if rows is None:
        rows = _symbols(debug_file)
        cache[debug_file] = rows
    return [row for row in rows if row["value"] <= address < row["end"]]


def _binary_for_module(module: dict, bundle: SourceBundle | None) -> Path | None:
    original = module.get("path") or module.get("binary")
    candidates = [Path(original)] if original else []
    if bundle:
        for row in bundle.manifest.get("binaries", []):
            if (row.get("source") == original or Path(row.get("source", "")).name == Path(original or "").name
                    or (not original and row.get("build_id", "").lower() == str(module.get("build_id", "")).lower())):
                candidates.append(bundle.root / row["path"])
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _match_function(rows: list[dict], symbol: dict, source: dict | None) -> tuple[dict | None, list[dict]]:
    name = symbol.get("name")
    candidates = [row for row in rows if row.get("linkage_name") == name or row.get("name") == name]
    if source and source.get("file"):
        line = int(source.get("line", 0)); filename = Path(source["file"]).name
        exact = [row for row in candidates if row.get("file") and Path(row["file"]).name == filename and int(row.get("line", 0)) <= line <= int(row.get("source_range", {}).get("end", row.get("line", 0)))]
        if exact: candidates = exact
    return (candidates[0], candidates) if len(candidates) == 1 else (None, candidates)


def resolve_addresses(report: dict, addresses: list[int], bundle: SourceBundle | str | os.PathLike[str] | None = None, *, kind: str = "address", debug_directories: list[str | os.PathLike[str]] | None = None) -> list[dict]:
    """Resolve PC/function/callsite addresses only against BuildID-matched evidence."""
    if bundle is not None and not isinstance(bundle, SourceBundle): bundle = load_bundle(bundle)
    index_rows = bundle.index_rows() if bundle else list(report.get("functions", []))
    debug_roots = [Path(value).expanduser().resolve() for value in (debug_directories or [])]
    if any(not path.is_dir() for path in debug_roots):
        raise InspectionError("separate debug directories must exist and be directories")
    symbol_cache: dict[Path, list[dict]] = {}
    debug_file_cache: dict[str, Path | None] = {}
    out = []
    for address in addresses:
        base: dict[str, Any] = {"address": address, "kind": kind}
        matches = [m for m in report.get("modules", []) if int(m.get("text_start", 0)) <= address < int(m.get("text_end", 0))]
        if len(matches) != 1:
            base.update({"resolved": False, "reason": "missing_module" if not matches else "ambiguous_module"}); out.append(base); continue
        module = matches[0]; binary = _binary_for_module(module, bundle)
        if binary is None:
            base.update({"resolved": False, "module": module.get("path"), "reason": "captured_binary_missing"}); out.append(base); continue
        expected, actual = str(module.get("build_id", "")).lower(), _build_id(binary)
        if not expected or not actual or expected != actual:
            base.update({"resolved": False, "module": module.get("path"), "build_id": expected, "actual_build_id": actual, "reason": "build_id_mismatch" if actual else "binary_build_id_missing"}); out.append(base); continue
        debug_file = debug_file_cache.get(actual)
        if actual not in debug_file_cache:
            debug_file = _separate_debug_file(actual, debug_roots) if debug_roots else None
            debug_file_cache[actual] = debug_file
        relative = address - int(module.get("load_bias", 0))
        symbols = _symbol_rows_for_address(binary, relative, debug_file, symbol_cache)
        if len(symbols) != 1:
            base.update({"resolved": False, "module": module.get("path"), "build_id": actual, "reason": "missing_symbol" if not symbols else "ambiguous_symbol", "candidates": [s["name"] for s in symbols]}); out.append(base); continue
        symbol, source = symbols[0], _source_for_address(binary, relative, debug_roots)
        row, candidates = _match_function(index_rows, symbol, source)
        if index_rows and row is None:
            base.update({"resolved": False, "module": module.get("path"), "build_id": actual, "symbol": symbol["name"], "reason": "ambiguous_function_index" if candidates else "function_not_in_index", "candidates": [c.get("id") for c in candidates]}); out.append(base); continue
        base.update({"resolved": True, "module": module.get("path"), "build_id": actual, "load_bias": int(module.get("load_bias", 0)), "relative_address": relative, "symbol": symbol["name"], "function_id": row.get("id") if row else None})
        if debug_file is not None:
            base["debug_file"] = str(debug_file)
            base["debug_file_build_id"] = actual
        if row:
            base["static_edges"] = list(row.get("edges", []))
            base["static_unresolved_edges"] = list(row.get("unresolved_edges", []))
        if source:
            base["source"] = source
            if bundle and source.get("file"):
                source_path = bundle.source_path(source["file"])
                if source_path is None: base.update({"resolved": False, "reason": "captured_source_missing"})
                else: base["source"]["file"] = str(source_path)
        out.append(base)
    return out


def thread_trace(report: dict, tid: int | None = None) -> list[dict]:
    return [t for t in report.get("threads", []) if tid is None or t.get("tid") == tid]


def verified_function_source(function_id: str, bundle: SourceBundle | str | os.PathLike[str]) -> dict[str, Any]:
    """Read a function only from a verified immutable bundle index/source."""
    if not isinstance(bundle, SourceBundle):
        bundle = load_bundle(bundle)
    rows = bundle.index_rows()
    row = next((item for item in rows if item.get("id") == function_id), None)
    if row is None:
        raise InspectionError("function id not found in verified bundle index")
    source = bundle.source_path(row.get("file", ""))
    if source is None:
        raise InspectionError("verified source for function is missing")
    lines = source.read_text(errors="replace").splitlines()
    start = max(1, int(row.get("source_range", {}).get("start", row.get("line", 1))))
    end = min(len(lines), int(row.get("source_range", {}).get("end", start)))
    return {"resolved": True, "function_id": function_id, "bundle": str(bundle.root),
            "file": str(source), "start_line": start, "end_line": end,
            "source": "\n".join(lines[start - 1:end])}


def verified_call_relations(function_id: str, direction: str, bundle: SourceBundle | str | os.PathLike[str]) -> dict[str, Any]:
    """Return static index relations with their evidence class preserved."""
    if direction not in {"inbound", "outbound"}:
        raise InspectionError("direction must be inbound or outbound")
    if not isinstance(bundle, SourceBundle):
        bundle = load_bundle(bundle)
    rows = bundle.index_rows()
    row = next((item for item in rows if item.get("id") == function_id), None)
    if row is None:
        raise InspectionError("function id not found in verified bundle index")
    if direction == "outbound":
        relations = list(row.get("edges", [])) + list(row.get("unresolved_edges", []))
    else:
        relations = [{"caller_id": item["id"], "edge": edge}
                     for item in rows for edge in item.get("edges", [])
                     if edge.get("callee_id") == function_id]
    return {"function_id": function_id, "direction": direction,
            "relations": relations, "evidence": "static_index", "bundle": str(bundle.root)}


def diagnose(report: dict, resolutions: list[dict] | None = None) -> list[dict]:
    """Return stable, actionable diagnostics without inventing missing evidence."""
    diagnostics: list[dict] = []
    for result in resolutions or []:
        reason = result.get("reason")
        if reason in {"missing_symbol", "ambiguous_symbol", "function_not_in_index", "ambiguous_function_index"}:
            diagnostics.append({"code": "FD-MISSING-SYMBOL", "severity": "error", "message": "No unique symbol could be verified for this address.", "evidence": result})
        elif reason in {"build_id_mismatch", "binary_build_id_missing", "captured_binary_missing"}:
            diagnostics.append({"code": "FD-PROVENANCE-MISMATCH", "severity": "error", "message": "The captured module does not match a verified binary in the supplied bundle.", "evidence": result})
    status = int(report.get("header", {}).get("status", 0))
    if status & (STATUS_PARTIAL | STATUS_EVENT_OVERFLOW):
        diagnostics.append({"code": "FD-INCOMPLETE-TRACE", "severity": "warning", "message": "The trace is partial or contains recorder overflow; retained events do not describe the complete execution.", "evidence": {"status": status}})
    for thread in report.get("threads", []):
        events = sorted(thread.get("events", []), key=lambda event: int(event.get("sequence", 0)))
        if thread.get("dropped_count", 0) or (events and any(b["sequence"] != a["sequence"] + 1 for a, b in zip(events, events[1:]))):
            diagnostics.append({"code": "FD-INCOMPLETE-TRACE", "severity": "warning", "message": "A thread trace has dropped, evicted, or missing sequence records.", "evidence": {"tid": thread.get("tid"), "slot": thread.get("slot"), "dropped_count": thread.get("dropped_count", 0)}})
        depth = 0
        for event in events:
            if event.get("type") == 1: depth += 1
            elif event.get("type") == 2: depth -= 1
        if depth != 0:
            diagnostics.append({"code": "FD-INCOMPLETE-TRACE", "severity": "warning", "message": "A retained thread trace has unbalanced enter/exit events; interruption or ring loss may have removed context.", "evidence": {"tid": thread.get("tid"), "depth": depth}})
    return diagnostics

"""Bounded local inputs for frozen service evidence directories."""
from __future__ import annotations

import os
from pathlib import Path
import stat

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 256
MAX_SCAN_ENTRIES = 4096
MAX_CAPTURES = 64
MAX_EVENTS = 100_000


def discover_inputs(root: Path) -> tuple[list[Path], list[Path]]:
    """Bound traversal itself, including irrelevant entries; never follow links."""
    if not root.is_dir():
        raise ValueError("Evidence directory does not exist")
    pending, captures, logs = [root], [], []
    scanned = 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                scanned += 1
                if scanned > MAX_SCAN_ENTRIES:
                    raise ValueError("Evidence directory scan budget exceeded")
                if entry.is_symlink():
                    raise ValueError("Evidence directory must not contain symlinks")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.name.endswith('.fault') or entry.name == 'events.jsonl':
                    if not entry.is_file(follow_symlinks=False):
                        raise ValueError("Evidence must be a regular bounded file")
                    (captures if entry.name.endswith('.fault') else logs).append(Path(entry.path))
                    if len(captures) + len(logs) > MAX_FILES:
                        raise ValueError("Evidence file count budget exceeded")
                    if len(captures) > MAX_CAPTURES:
                        raise ValueError(f"Expected 1..{MAX_CAPTURES} native captures")
    if not captures:
        raise ValueError(f"Expected 1..{MAX_CAPTURES} native captures")
    return sorted(captures), sorted(logs)


class EvidenceReader:
    """Charge actual bytes across every native capture and application log."""

    def __init__(self):
        self.total_bytes = 0

    def read(self, path: Path) -> bytes:
        # O_NONBLOCK prevents a swapped FIFO from blocking before fstat checks it.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            metadata = os.fstat(stream.fileno())
            remaining = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - self.total_bytes)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > remaining:
                raise ValueError("Evidence regular-file or byte budget exceeded")
            data = stream.read(remaining + 1)
        if len(data) > remaining:
            raise ValueError("Evidence byte budget exceeded")
        self.total_bytes += len(data)
        return data

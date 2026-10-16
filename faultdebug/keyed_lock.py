"""Bounded process-local locks for concurrent work with stable string keys.

Holders and waiters retain the same lock entry until all leave. Idle entries
are removed immediately; the capacity limit rejects a new live key rather than
evicting a key whose work could still be active. This provides no coordination
between processes, persistence, fairness, or reentrant acquisition guarantees.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import math
import threading
import time
from typing import Iterator


class KeyedLockCapacityError(RuntimeError):
    """The pool is full of keys with active holders or waiters."""


class KeyedLockTimeout(TimeoutError):
    """The requested key could not be acquired within its wait budget."""


@dataclass(slots=True)
class _Entry:
    lock: object = field(default_factory=threading.Lock)
    references: int = 0


class KeyedLockPool:
    """Serialize a key while allowing distinct keys to make progress.

    Keys are exact strings containing 1..1024 UTF-8 bytes. ``max_keys`` counts
    distinct keys with holders or waiters, with no retained idle-key cache.
    ``timeout`` is None (wait indefinitely) or a finite nonnegative number of
    seconds up to ``threading.TIMEOUT_MAX``; zero attempts immediate acquisition.
    Acquisition is not reentrant. Create a fresh pool in each process.
    """

    def __init__(self, max_keys: int = 1024):
        if type(max_keys) is not int:
            raise TypeError("max_keys must be an integer, excluding bool")
        if not 1 <= max_keys <= 1_000_000:
            raise ValueError("max_keys must be in 1..1000000")
        self.max_keys = max_keys
        self._guard = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    @property
    def active_keys(self) -> int:
        """Return a snapshot of distinct keys with holders or waiters."""
        with self._guard:
            return len(self._entries)

    @contextmanager
    def hold(self, key: str, *, timeout: float | None = None) -> Iterator[None]:
        """Hold one key, releasing its entry on success, timeout or exception."""
        if type(key) is not str:
            raise TypeError("key must be a string")
        try:
            size = len(key.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("key must contain valid Unicode") from exc
        if not 1 <= size <= 1024:
            raise ValueError("key must contain 1..1024 UTF-8 bytes")
        if timeout is not None:
            if type(timeout) not in (int, float):
                raise TypeError("timeout must be a number of seconds, excluding bool")
            if not 0 <= timeout <= threading.TIMEOUT_MAX or not math.isfinite(timeout):
                raise ValueError("timeout must be finite and in 0..threading.TIMEOUT_MAX")
        end = None if timeout is None else time.monotonic() + timeout
        with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self.max_keys:
                    raise KeyedLockCapacityError("keyed lock capacity reached")
                entry = self._entries[key] = _Entry()
            entry.references += 1  # Include waiters before releasing the guard.
        acquired = False
        try:
            if end is None:
                acquired = entry.lock.acquire()
            else:
                acquired = entry.lock.acquire(timeout=max(0.0, end - time.monotonic()))
            if not acquired:
                raise KeyedLockTimeout("keyed lock wait budget expired")
            yield
        finally:
            if acquired:
                entry.lock.release()
            with self._guard:
                entry.references -= 1
                if entry.references == 0:
                    del self._entries[key]

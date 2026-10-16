"""Bounded, durable retries for mutations in one local SQLite database.

The callback must perform all business writes on the supplied connection. Its
mutation and a detached JSON response commit in the same transaction; a retry
with the same operation ID and canonical payload then returns that response.
This does not make network, payment, filesystem, or other database side effects
exactly once. Callbacks are trusted application code, not sandboxed code.

No entries expire or are evicted: deleting an identity could repeat a mutation.
The row limit instead rejects new operations while preserving existing replays.
Use a trusted local directory and a filesystem supporting SQLite durability;
the ledger requests synchronous=FULL, but cannot promise hardware durability.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time


_MAX_JSON_BYTES = 64 * 1024
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 4096
_MAX_BUSY_SECONDS = 1.0
_TABLE = "faultdebug_retry_operations"
_OPERATION_ID = re.compile(r"[!-~]{1,128}")


class RetryConflict(ValueError):
    """An existing operation ID was presented with a different payload."""


class RetryDeadlineExceeded(TimeoutError):
    """The caller's local monotonic deadline expired before commit."""


class RetryCapacityExceeded(RuntimeError):
    """The ledger is full; existing operation IDs remain replayable."""


@dataclass(frozen=True, slots=True)
class RetryResult:
    value: dict
    replayed: bool


def _json_object(value: dict, label: str) -> str:
    """Validate a finite, bounded JSON tree without silent type coercions."""
    if type(value) is not dict:
        raise TypeError(f"{label} must be a JSON object")
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise ValueError(f"{label} exceeds the JSON size or depth limit")
        kind = type(item)
        if kind is dict:
            if len(item) > _MAX_JSON_NODES:
                raise ValueError(f"{label} exceeds the JSON size limit")
            for key, child in item.items():
                if type(key) is not str:
                    raise TypeError(f"{label} object keys must be strings")
                pending.append((key, depth + 1))
                pending.append((child, depth + 1))
        elif kind is list:
            if len(item) > _MAX_JSON_NODES:
                raise ValueError(f"{label} exceeds the JSON size limit")
            pending.extend((child, depth + 1) for child in item)
        elif kind is str:
            try:
                encoded = item.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError(f"{label} strings must be valid Unicode") from exc
            if len(encoded) > _MAX_JSON_BYTES:
                raise ValueError(f"{label} exceeds the JSON byte limit")
        elif kind is int:
            if not -(1 << 63) <= item < (1 << 63):
                raise ValueError(f"{label} integers must fit signed 64 bits")
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError(f"{label} numbers must be finite")
        elif kind not in (bool, type(None)):
            raise TypeError(f"{label} contains a non-JSON value")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    if len(canonical.encode("ascii")) > _MAX_JSON_BYTES:
        raise ValueError(f"{label} exceeds the JSON byte limit")
    return canonical


def _deadline(deadline_ns: int | None) -> None:
    if deadline_ns is not None:
        if type(deadline_ns) is not int:
            raise TypeError("deadline_ns must be an integer, excluding bool")
        if not 0 <= deadline_ns < (1 << 63):
            raise ValueError("deadline_ns must fit a nonnegative signed 64-bit integer")


def _check_deadline(deadline_ns: int | None) -> None:
    if deadline_ns is not None and time.monotonic_ns() >= deadline_ns:
        raise RetryDeadlineExceeded("retry deadline expired before commit")


class RetryLedger:
    """Persistent per-database operation IDs with a fixed storage entry limit.

    Payloads and responses must be exact dict/list JSON trees, at most 64 KiB,
    4096 nodes and 16 levels deep, with finite floats and signed 64-bit integers.
    Operation IDs are 1..128 printable ASCII characters without whitespace.
    A deadline is an absolute monotonic nanosecond value in this process's clock
    domain, never a wire timestamp. Lock waits are bounded to one second and
    additionally limited by the remaining deadline.
    """

    def __init__(self, path: str | os.PathLike[str], *, max_operations: int = 10000):
        if type(max_operations) is not int:
            raise TypeError("max_operations must be an integer, excluding bool")
        if not 1 <= max_operations <= 1_000_000:
            raise ValueError("max_operations must be in 1..1000000")
        raw = os.fspath(path)
        if not isinstance(raw, str):
            raise TypeError("ledger path must be a text filesystem path")
        if not raw or raw == ":memory:" or "\x00" in raw:
            raise ValueError("ledger requires a persistent file path")
        candidate = Path(raw).expanduser()
        self.path = candidate.parent.resolve(strict=True) / candidate.name
        self.max_operations = max_operations
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        try:
            fd = os.open(self.path, flags, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("ledger path must be a regular file, not a symlink")
        self._identity = (info.st_dev, info.st_ino)
        conn = self._connect(None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
                operation_id TEXT PRIMARY KEY NOT NULL,
                payload_sha256 TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )""")
            columns = [(row[1], row[2], row[3], row[5])
                       for row in conn.execute(f"PRAGMA table_info({_TABLE})")]
            if columns != [("operation_id", "TEXT", 1, 1),
                           ("payload_sha256", "TEXT", 1, 0),
                           ("payload_json", "TEXT", 1, 0),
                           ("result_json", "TEXT", 1, 0)]:
                raise ValueError("incompatible retry ledger schema")
            conn.commit()
        except BaseException:
            self._rollback(conn)
            raise
        finally:
            conn.close()

    def _connect(self, deadline_ns: int | None) -> sqlite3.Connection:
        _check_deadline(deadline_ns)
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode)
                or (info.st_dev, info.st_ino) != self._identity):
            raise ValueError("ledger file was replaced or is no longer a regular file")
        timeout = _MAX_BUSY_SECONDS
        if deadline_ns is not None:
            timeout = min(timeout, max(0.0, (deadline_ns - time.monotonic_ns()) / 1e9))
        conn = sqlite3.connect(self.path, timeout=timeout, isolation_level=None)
        try:
            conn.execute("PRAGMA synchronous=FULL")
        except BaseException:
            conn.close()
            raise
        return conn

    @staticmethod
    def _rollback(conn: sqlite3.Connection) -> None:
        try:
            if conn.in_transaction:
                conn.rollback()
        except sqlite3.Error:
            # Preserve the original exception; close also aborts an open txn.
            pass

    @staticmethod
    def _commit(conn: sqlite3.Connection, deadline_ns: int | None) -> None:
        # Callback execution may consume almost all of the original lock budget.
        # Refresh it so COMMIT cannot wait on a reader using that stale budget.
        if deadline_ns is not None:
            remaining = deadline_ns - time.monotonic_ns()
            if remaining <= 0:
                raise RetryDeadlineExceeded("retry deadline expired before commit")
            busy_ms = min(int(_MAX_BUSY_SECONDS * 1000), remaining // 1_000_000)
            conn.execute(f"PRAGMA busy_timeout={busy_ms}")
        _check_deadline(deadline_ns)
        conn.commit()

    @staticmethod
    def _mutation_authorizer(action: int, arg1: str | None, arg2: str | None,
                             db_name: str | None, source: str | None) -> int:
        # Stop accidental commits/executescript/ATTACH or ledger writes. This
        # guard is not a security boundary against a malicious Python callback.
        if action in (sqlite3.SQLITE_TRANSACTION, sqlite3.SQLITE_SAVEPOINT,
                      sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA):
            return sqlite3.SQLITE_DENY
        if arg1 == _TABLE and action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE,
                                        sqlite3.SQLITE_DELETE, sqlite3.SQLITE_DROP_TABLE,
                                        sqlite3.SQLITE_ALTER_TABLE):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def apply_once(self, operation_id: str, payload: dict,
                   mutation: Callable[[sqlite3.Connection], dict], *,
                   deadline_ns: int | None = None) -> RetryResult:
        """Atomically apply a local mutation, or replay its committed JSON result.

        The trusted callback must use only the supplied connection for effects,
        must not close it or change its transaction/authorizer, and must return
        bounded JSON. Callback/result/deadline failures roll back business writes.
        An expired deadline rejects replays too. SQLite busy errors before the
        deadline propagate, allowing the caller to retry using the same identity.
        """
        if type(operation_id) is not str:
            raise TypeError("operation_id must be a string")
        if _OPERATION_ID.fullmatch(operation_id) is None:
            raise ValueError("operation_id must be 1..128 printable ASCII characters without whitespace")
        _deadline(deadline_ns)
        _check_deadline(deadline_ns)
        payload_json = _json_object(payload, "payload")
        payload_hash = hashlib.sha256(payload_json.encode("ascii")).hexdigest()
        if not callable(mutation):
            raise TypeError("mutation must be callable")
        conn = self._connect(deadline_ns)
        try:
            conn.execute("BEGIN IMMEDIATE")
            _check_deadline(deadline_ns)
            existing = conn.execute(
                f"SELECT payload_sha256, payload_json, result_json FROM {_TABLE} WHERE operation_id=?",
                (operation_id,)).fetchone()
            if existing is not None:
                if existing[0] != payload_hash or existing[1] != payload_json:
                    raise RetryConflict("operation ID already has a different payload")
                value = json.loads(existing[2])
                _json_object(value, "stored result")
                self._commit(conn, deadline_ns)
                return RetryResult(value=value, replayed=True)
            count = conn.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0]
            if count >= self.max_operations:
                raise RetryCapacityExceeded("retry ledger capacity reached; existing IDs remain replayable")
            conn.set_authorizer(self._mutation_authorizer)
            try:
                value = mutation(conn)
            finally:
                conn.set_authorizer(None)
            if not conn.in_transaction:
                raise RuntimeError("mutation must preserve the ledger transaction")
            result_json = _json_object(value, "result")
            conn.execute(
                f"INSERT INTO {_TABLE} (operation_id, payload_sha256, payload_json, result_json) VALUES (?,?,?,?)",
                (operation_id, payload_hash, payload_json, result_json))
            self._commit(conn, deadline_ns)
            return RetryResult(value=json.loads(result_json), replayed=False)
        except sqlite3.OperationalError as exc:
            self._rollback(conn)
            if deadline_ns is not None and time.monotonic_ns() >= deadline_ns:
                raise RetryDeadlineExceeded("retry deadline expired while waiting for SQLite") from exc
            raise
        except BaseException:
            self._rollback(conn)
            raise
        finally:
            conn.close()

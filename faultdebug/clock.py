"""Local monotonic-clock provenance and receiver-local deadline helpers.

An absolute monotonic timestamp is meaningful only in its clock domain.  A
hostname, PID, or session ID does not establish that domain.  Linux boot and
time-namespace identities let callers describe their own sampled domain;
unavailable evidence remains unknown instead of receiving a default identity.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from typing import Callable


_BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
_TIME_NAMESPACE_PATH = "/proc/self/ns/time"
_MAX_SOURCE_LENGTH = 64
_TIME_NAMESPACE = re.compile(r"time:\[([1-9][0-9]{0,19})\]", re.ASCII)


def _read_small_text(path: str, limit: int) -> str:
    with open(path, "r", encoding="ascii") as source:
        return source.read(limit + 1)


def local_clock_identity(*, read_text: Callable[[str, int], str] | None = None,
                         readlink: Callable[[str], str] | None = None) -> dict[str, object]:
    """Sample the calling process's Linux monotonic clock-domain evidence.

    The injectable readers make missing, malformed, and namespace-specific
    sources testable.  A domain ID is derived only when both source identities
    are available.  It describes the sampling process, never an arbitrary
    process whose PID a launcher or collector happens to record.  The ID is
    provenance, not clock synchronization or a timestamp conversion factor.
    """
    text_reader = _read_small_text if read_text is None else read_text
    link_reader = os.readlink if readlink is None else readlink
    boot_id: str | None = None
    namespace_id: str | None = None
    try:
        raw_boot = text_reader(_BOOT_ID_PATH, _MAX_SOURCE_LENGTH)
        if isinstance(raw_boot, str) and len(raw_boot) <= _MAX_SOURCE_LENGTH:
            candidate = raw_boot.strip()
            parsed = uuid.UUID(candidate)
            if str(parsed) == candidate.lower():
                boot_id = str(parsed)
    except (OSError, UnicodeError, ValueError):
        pass
    try:
        raw_namespace = link_reader(_TIME_NAMESPACE_PATH)
        if (isinstance(raw_namespace, str) and len(raw_namespace) <= _MAX_SOURCE_LENGTH
                and _TIME_NAMESPACE.fullmatch(raw_namespace)):
            namespace_id = raw_namespace
    except (OSError, UnicodeError, ValueError):
        pass

    limitations = ["sampling_process_only", "cross_domain_timestamp_subtraction_unsupported"]
    domain_id: str | None = None
    if boot_id is None:
        limitations.append("host_boot_id_unavailable")
    if namespace_id is None:
        limitations.append("time_namespace_identity_unavailable")
    if boot_id is not None and namespace_id is not None:
        material = f"linux-monotonic-v1\0{boot_id}\0{namespace_id}".encode("ascii")
        domain_id = "linux-monotonic-v1:" + hashlib.sha256(material).hexdigest()
        # Namespace inode identities may be reused after their namespace dies.
        limitations.append("namespace_identity_lifetime_not_persistently_verified")
    return {
        "schema": 1,
        "clock": "monotonic",
        "host_boot_id": boot_id,
        "time_namespace_id": namespace_id,
        "clock_domain_id": domain_id,
        "source": {"host_boot_id": _BOOT_ID_PATH if boot_id is not None else None,
                   "time_namespace_id": _TIME_NAMESPACE_PATH if namespace_id is not None else None},
        "status": "known" if domain_id is not None else "unknown",
        "limitations": limitations,
    }


def local_deadline_ns(timeout_ms: int, *, now_ns: int | None = None) -> int:
    """Start a bounded relative timeout in the receiver's local clock domain.

    Call this after receiving a relative timeout of 1..5000 milliseconds.  Do
    not subtract a peer's absolute monotonic timestamp to obtain a budget.
    ``now_ns`` is an explicit receiver-local sample, useful for deterministic
    tests; when absent the calling process's monotonic clock is sampled.
    """
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 5000:
        raise ValueError("timeout_ms must be an integer between 1 and 5000")
    if now_ns is None:
        now_ns = time.monotonic_ns()
    if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns < 0:
        raise ValueError("now_ns must be a non-negative receiver-local integer")
    return now_ns + timeout_ms * 1_000_000

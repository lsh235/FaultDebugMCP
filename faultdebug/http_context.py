"""A bounded W3C traceparent version 00 transport adapter.

These identifiers are untrusted correlation context, not observed RPC events.
No sampler, tracestate processing, or native span instrumentation is provided.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from email.message import Message
import re
import secrets


_U64_MAX = (1 << 64) - 1
_V00 = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")


def _integer(name: str, value: int, maximum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, excluding bool")
    if not 0 <= value <= maximum:
        raise ValueError(f"{name} is outside its unsigned integer range")


@dataclass(frozen=True, slots=True)
class TraceParent:
    """Immutable version 00 context; parent_id is the header's sender span ID."""

    trace_id_hi: int
    trace_id_lo: int
    parent_id: int
    trace_flags: int

    def __post_init__(self) -> None:
        for name in ("trace_id_hi", "trace_id_lo", "parent_id"):
            _integer(name, getattr(self, name), _U64_MAX)
        _integer("trace_flags", self.trace_flags, 0xFF)
        if self.trace_id_hi == self.trace_id_lo == 0:
            raise ValueError("trace ID must be nonzero")
        if self.parent_id == 0:
            raise ValueError("parent ID must be nonzero")

    def to_header(self) -> str:
        """Serialize exactly 55 lowercase ASCII characters, without whitespace."""
        return (f"00-{self.trace_id_hi:016x}{self.trace_id_lo:016x}-"
                f"{self.parent_id:016x}-{self.trace_flags:02x}")


def parse_traceparent(value: str) -> TraceParent:
    """Parse only version 00; reject malformed or unsupported context explicitly."""
    if not isinstance(value, str):
        raise TypeError("traceparent must be a string")
    if (len(value) >= 3 and re.fullmatch(r"[0-9a-f]{2}", value[:2])
            and value[2] == "-" and value[:2] != "00"):
        raise ValueError(f"Unsupported traceparent version {value[:2]}; only version 00 is supported")
    match = _V00.fullmatch(value)
    if match is None:
        raise ValueError("traceparent version 00 requires exactly 55 lowercase hexadecimal characters and separators")
    trace, parent, flags = match.groups()
    return TraceParent(int(trace[:16], 16), int(trace[16:], 16),
                       int(parent, 16), int(flags, 16))


def extract_traceparent(headers: Mapping[str, str] | Message) -> TraceParent | None:
    """Extract one case-insensitive header; reject duplicates instead of choosing one.

    HTTPMessage inherits Message, whose get_all preserves repeated fields even
    when their spellings differ. Mapping keys are inspected case-insensitively.
    Comma-joined values are rejected; traceparent is not a list-valued field.
    """
    if isinstance(headers, Message):
        values = headers.get_all("traceparent", [])
    elif isinstance(headers, Mapping):
        values = []
        for name, value in headers.items():
            if not isinstance(name, str):
                raise TypeError("HTTP header names must be strings")
            if name.lower() == "traceparent":
                values.append(value)
    else:
        raise TypeError("headers must be a mapping or HTTPMessage")
    if not values:
        return None
    if len(values) != 1:
        raise ValueError("duplicate traceparent headers are not accepted")
    value = values[0]
    if not isinstance(value, str):
        raise TypeError("traceparent must be a string")
    if "," in value:
        raise ValueError("comma-joined traceparent headers are not accepted")
    return parse_traceparent(value)


def _new_span_id(exclude: int = 0) -> int:
    while True:
        value = secrets.randbits(64)
        if value != 0 and value != exclude:
            return value


def new_traceparent() -> TraceParent:
    """Start a random nonzero 128-bit trace and span, with trace flags 00."""
    trace = 0
    while trace == 0:
        trace = secrets.randbits(128)
    return TraceParent(trace >> 64, trace & _U64_MAX, _new_span_id(), 0)


def child_traceparent(parent: TraceParent) -> TraceParent:
    """Preserve trace/flags and generate a distinct nonzero sender span ID.

    This transforms context only; it neither records nor proves a native edge.
    """
    if not isinstance(parent, TraceParent):
        raise TypeError("parent must be a TraceParent")
    return TraceParent(parent.trace_id_hi, parent.trace_id_lo,
                       _new_span_id(parent.parent_id), parent.trace_flags)

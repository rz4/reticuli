"""Validate and serialize portable claim attestation records."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from . import core


_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment",
    "when", "cost", "producer", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "cutoff", "blind"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "environment", "mismatch"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


def _object(value: Any, allowed: frozenset[str], required: frozenset[str],
            label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise core.ClaimError(f"{label} must be an object")
    if not required <= value.keys() or not value.keys() <= allowed:
        raise core.ClaimError(f"{label} has missing or unknown members")
    return value


def _text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise core.ClaimError(f"{label} must be nonempty text")


def record_validate(record: Any) -> None:
    """Reject malformed records with an in-band claim error."""
    doc = _object(record, _RECORD_MEMBERS, _RECORD_REQUIRED, "record")
    if type(doc["record"]) is not int or doc["record"] != 1:
        raise core.ClaimError("unknown record version")
    _text(doc["name"], "name")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or not _RECORD_HEX.fullmatch(doc[key]):
            raise core.ClaimError(f"{key} must be a SHA-256 digest")
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.fullmatch(doc["when"]):
        raise core.ClaimError("when must be an ISO 8601 timestamp")

    environment = _object(doc["environment"], _RECORD_ENVIRONMENT,
                          _RECORD_ENVIRONMENT, "environment")
    for key in _RECORD_ENVIRONMENT:
        _text(environment[key], f"environment.{key}")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("gates must be a list")
    for gate in gates:
        gate = _object(gate, _RECORD_GATE, _RECORD_GATE, "gate")
        _text(gate["output"], "gate.output")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError("invalid gate status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError("invalid gate sandbox")

    if "tool" in doc:
        _text(doc["tool"], "tool")
    if "producer" in doc:
        producer = _object(doc["producer"], _RECORD_PRODUCER,
                           frozenset(), "producer")
        for key in ("vendor", "model", "cutoff"):
            if key in producer:
                _text(producer[key], f"producer.{key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            raise core.ClaimError("producer.blind must be boolean")
    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not all(
            isinstance(key, str) and isinstance(value, (int, float))
            and not isinstance(value, bool) for key, value in cost.items()
        ):
            raise core.ClaimError("cost must contain numeric values")


def record_canonical(record: Any) -> bytes:
    """Return the identity JSON serialization of a valid record."""
    record_validate(record)
    return json.dumps(record, sort_keys=True).encode("utf-8")


def record_digest(record: Any) -> str:
    """Return the SHA-256 digest of a record's canonical bytes."""
    return hashlib.sha256(record_canonical(record)).hexdigest()


def record_read(path: str) -> dict[str, Any]:
    """Read one JSON record from a file."""
    try:
        with open(path, "r", encoding="utf-8") as source:
            record = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record: {exc}") from exc
    record_validate(record)
    return record


def record_signer(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the producer declaration, when present."""
    record_validate(record)
    return record.get("producer")

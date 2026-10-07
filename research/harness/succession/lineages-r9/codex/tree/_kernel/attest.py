"""Read, validate, and identify portable claim records."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "cost",
    "producer", "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"\d{4}-\d{2}\Z")
_RECORD_COST = frozenset(core.COST_KEYS)


def _object(value: object, allowed: frozenset[str], required: frozenset[str],
            label: str) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"record {label} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise core.ClaimError(f"record {label} has a non-string member")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown:
        raise core.ClaimError(f"record {label} has unknown member: {sorted(unknown)[0]}")
    if missing:
        raise core.ClaimError(f"record {label} lacks required member: {sorted(missing)[0]}")
    return value


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise core.ClaimError(f"record {label} must be a string")


def record_validate(doc: object) -> None:
    """Refuse malformed version-one records with a claim error."""
    data = _object(doc, _RECORD_MEMBERS, _RECORD_REQUIRED, "")
    version = data["record"]
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be a positive integer")
    if version > RECORD_FORMAT:
        raise core.ClaimError(
            f"record version {version} is newer than this kernel understands "
            f"(version {RECORD_FORMAT})")

    for key in ("name", "root", "build_digest", "when"):
        _string(data[key], key)
    for key in ("root", "build_digest"):
        if not _RECORD_HEX.fullmatch(data[key]):
            raise core.ClaimError(f"record {key} must be 64 lowercase hex characters")
    if not _RECORD_WHEN.fullmatch(data["when"]):
        raise core.ClaimError("record when must be a UTC timestamp")
    if "tool" in data:
        _string(data["tool"], "tool")

    gates = data["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("record gates must be an array")
    for index, gate in enumerate(gates):
        gate = _object(gate, _RECORD_GATE, _RECORD_GATE, f"gate {index}")
        _string(gate["output"], f"gate {index} output")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"record gate {index} has unknown status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"record gate {index} has unknown sandbox")

    environment = _object(data["environment"], _RECORD_ENVIRONMENT,
                          _RECORD_ENVIRONMENT, "environment")
    for key in _RECORD_ENVIRONMENT:
        _string(environment[key], f"environment {key}")

    if "cost" in data:
        cost = _object(data["cost"], _RECORD_COST, frozenset(), "cost")
        for key, value in cost.items():
            if (type(value) not in (int, float) or value < 0
                    or not math.isfinite(value)):
                raise core.ClaimError(f"record cost {key} must be a non-negative number")

    if "producer" in data:
        producer = _object(data["producer"], _RECORD_PRODUCER,
                           frozenset(), "producer")
        for key in ("vendor", "model"):
            if key in producer:
                _string(producer[key], f"producer {key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            raise core.ClaimError("record producer blind must be a boolean")
        if "cutoff" in producer:
            _string(producer["cutoff"], "producer cutoff")
            if not _RECORD_CUTOFF.fullmatch(producer["cutoff"]):
                raise core.ClaimError("record producer cutoff must be YYYY-MM")


def record_canonical(doc: object) -> bytes:
    """Return identity-format JSON bytes for a valid record."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    """Return the SHA-256 content address of a valid record."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read a JSON record and reject malformed bytes in band."""
    try:
        with open(path, "r", encoding="utf-8") as source:
            doc = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Find a trusted SSH principal that signed the record's canonical bytes."""
    data = record_canonical(record_read(path))
    signature = os.fspath(path) + ".sig"
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", os.fspath(anchor),
             "-s", signature], capture_output=True, check=False, text=True)
        if found.returncode:
            return None
        for principal in found.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=data, capture_output=True, check=False)
            if verified.returncode == 0:
                return principal
    except OSError:
        pass
    return None

"""Read and validate portable, signed statements about claim results."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import subprocess

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest", "gates",
                             "cost", "producer", "environment", "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest", "gates",
                              "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"\d{4}-\d{2}\Z")
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def _object(value: object, label: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"{label} must be an object")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown:
        raise core.ClaimError(f"{label} has unknown members: {sorted(unknown)!r}")
    if missing:
        raise core.ClaimError(f"{label} is missing members: {sorted(missing)!r}")
    return value


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise core.ClaimError(f"{label} must be a string")


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        qualifier = "positive" if positive else "non-negative"
        raise core.ClaimError(f"{label} must be a finite {qualifier} number")


def record_validate(doc: object) -> None:
    """Refuse malformed records with a ClaimError, including unknown members."""
    if not isinstance(doc, dict):
        raise core.ClaimError("record must be a JSON object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be a positive integer")
    if version > RECORD_FORMAT:
        raise core.ClaimError(
            f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    allowed = _RECORD_MEMBERS | (frozenset({"claim"}) if version >= 2 else frozenset())
    required = _RECORD_REQUIRED | (frozenset({"claim"}) if version >= 2 else frozenset())
    _object(doc, "record", allowed, required)
    _string(doc["name"], "record name")
    for field in ("root", "build_digest"):
        value = doc[field]
        if not isinstance(value, str) or not _RECORD_HEX.fullmatch(value):
            raise core.ClaimError(f"record {field} must be 64 lowercase hex characters")
    gates = doc["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("record gates must be an array")
    for index, value in enumerate(gates):
        gate = _object(value, f"gate {index}", _RECORD_GATE, _RECORD_GATE)
        _string(gate["output"], f"gate {index} output")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"gate {index} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"gate {index} has invalid sandbox")
    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for field in _RECORD_ENVIRONMENT:
        _string(environment[field], f"environment {field}")
    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.fullmatch(when):
        raise core.ClaimError("record when must be YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise core.ClaimError("record when is not a valid UTC time") from exc
    if "tool" in doc:
        _string(doc["tool"], "record tool")
    if "cost" in doc:
        cost = _object(doc["cost"], "cost", _RECORD_COST)
        for unit, value in cost.items():
            _number(value, f"cost {unit}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", _RECORD_PRODUCER)
        for field in ("vendor", "model"):
            if field in producer:
                _string(producer[field], f"producer {field}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            raise core.ClaimError("producer blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if (not isinstance(cutoff, str) or not _RECORD_CUTOFF.fullmatch(cutoff)
                    or not 1 <= int(cutoff[-2:]) <= 12):
                raise core.ClaimError("producer cutoff must be YYYY-MM")
    if version >= 2:
        claim = _object(doc["claim"], "claim", _RECORD_CLAIM)
        for field in ("tolerance", "mutation_floor"):
            if field in claim:
                _number(claim[field], f"claim {field}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim envelope", _RECORD_COST)
            if not envelope:
                raise core.ClaimError("claim envelope must not be empty")
            for unit, value in envelope.items():
                _number(value, f"claim envelope {unit}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity format's sorted, default-separator JSON bytes."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    """Name a record by the SHA-256 of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read one UTF-8 JSON record from disk and validate it."""
    try:
        with open(path, "r", encoding="utf-8") as source:
            doc = json.load(source)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return the trusted SSH principal for a detached record signature."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        with open(signature, "rb") as source:
            signed = source.read()
        with open(anchor, "r", encoding="utf-8") as source:
            principals = [line.split()[0] for line in source
                          if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, UnicodeError, IndexError) as exc:
        raise core.ClaimError(f"cannot read record signature or anchor: {exc}") from exc
    if not signed:
        raise core.ClaimError("empty record signature")
    for principal in principals:
        try:
            checked = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, timeout=15,
                check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
        if checked.returncode == 0:
            return principal
    return None

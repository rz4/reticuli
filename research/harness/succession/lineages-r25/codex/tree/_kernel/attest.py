"""Validate, read, and cite the portable record format."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import subprocess
from collections.abc import Mapping

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
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_COST = frozenset(core.COST_KEYS)


def _object(value: object, label: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"{label} must be a JSON object")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown:
        raise core.ClaimError(f"unknown {label} member: {sorted(unknown)!r}")
    if missing:
        raise core.ClaimError(f"missing {label} member: {sorted(missing)!r}")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise core.ClaimError(f"{label} must be a finite {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse any document outside the closed, versioned record schema."""
    if not isinstance(doc, dict):
        raise core.ClaimError("record must be a JSON object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be a positive integer")
    if version > RECORD_FORMAT:
        raise core.ClaimError(
            f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    members = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    _object(doc, "record", frozenset(members), frozenset(required))

    for key in ("name", "tool"):
        if key in doc and not isinstance(doc[key], str):
            raise core.ClaimError(f"record {key} must be a string")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or not _RECORD_HEX.fullmatch(doc[key]):
            raise core.ClaimError(f"record {key} must be 64 lowercase hexadecimal characters")
    if not isinstance(doc["gates"], list):
        raise core.ClaimError("record gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        _object(gate, f"gate {index}", _RECORD_GATE, _RECORD_GATE)
        if not isinstance(gate["output"], str):
            raise core.ClaimError(f"gate {index} output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"gate {index} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"gate {index} has invalid sandbox")

    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key, value in environment.items():
        if not isinstance(value, str):
            raise core.ClaimError(f"environment {key} must be a string")
    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.fullmatch(when):
        raise core.ClaimError("record when must be a UTC timestamp")
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise core.ClaimError("record when is not a valid UTC timestamp") from exc

    if "cost" in doc:
        for unit, value in _object(doc["cost"], "cost", _RECORD_COST).items():
            _number(value, f"cost {unit}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"producer {key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise core.ClaimError("producer blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", cutoff):
                raise core.ClaimError("producer cutoff must be YYYY-MM")
    if version == 2:
        claim = _object(doc["claim"], "claim", _RECORD_CLAIM)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim {key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "envelope", _RECORD_COST)
            if not envelope:
                raise core.ClaimError("claim envelope must not be empty")
            for unit, value in envelope.items():
                _number(value, f"envelope {unit}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity serialization verbatim, after validation."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    """Cite a valid record by the SHA-256 of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read a canonical record file without changing its signed bytes."""
    try:
        with open(path, "rb") as stream:
            data = stream.read()
        doc = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    canonical = record_canonical(doc)
    if data != canonical:
        raise core.ClaimError(f"record {path} does not contain canonical bytes")
    return doc


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return the anchored SSH signer of a detached record signature, if any."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
             "-I", core.NAMESPACE, "-n", RECORD_NAMESPACE, "-s", signature],
            input=record_canonical(doc), capture_output=True, check=False)
    except OSError as exc:
        raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
    return core.NAMESPACE if result.returncode == 0 else None

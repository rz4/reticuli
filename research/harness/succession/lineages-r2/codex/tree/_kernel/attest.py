"""Read, validate, and identify portable claim records."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest",
                             "gates", "cost", "producer", "environment",
                             "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest",
                              "gates", "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])\Z")
_COST_KEYS = frozenset({"usd", "tokens", "calls", "seconds"})
_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError(f"invalid record: {message}")


def _members(value: object, allowed: frozenset[str], required: frozenset[str],
             label: str) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{label} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra:
        _refuse(f"{label} has unknown members: {', '.join(sorted(extra))}")
    if missing:
        _refuse(f"{label} is missing members: {', '.join(sorted(missing))}")
    return value


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        _refuse(f"{label} must be a string")


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        _refuse(f"{label} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse documents outside the closed, versioned record schema."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    if version == 1:
        _members(doc, _RECORD_MEMBERS, _RECORD_REQUIRED, "document")
    else:
        _members(doc, _RECORD_MEMBERS | {"claim"}, _RECORD_REQUIRED | {"claim"}, "document")

    for key in ("name", "tool"):
        if key in doc:
            _string(doc[key], key)
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            _refuse(f"{key} must be 64 lowercase hexadecimal characters")
    when = doc["when"]
    if not isinstance(when, str) or _RECORD_WHEN.fullmatch(when) is None:
        _refuse("when must be a UTC timestamp ending in Z")
    try:
        datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise core.ClaimError(f"invalid record: when is not a valid date: {exc}") from exc

    environment = _members(doc["environment"], _RECORD_ENVIRONMENT,
                           _RECORD_ENVIRONMENT, "environment")
    for key in _RECORD_ENVIRONMENT:
        _string(environment[key], f"environment.{key}")

    gates = doc["gates"]
    if not isinstance(gates, list):
        _refuse("gates must be an array")
    for index, item in enumerate(gates):
        gate = _members(item, _RECORD_GATE, _RECORD_GATE, f"gate {index}")
        _string(gate["output"], f"gate {index} output")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gate {index} has unknown status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gate {index} has unknown sandbox")

    if "cost" in doc:
        cost = _members(doc["cost"], _COST_KEYS, frozenset(), "cost")
        for key, value in cost.items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        producer = _members(doc["producer"], _RECORD_PRODUCER, frozenset(), "producer")
        for key in ("vendor", "model"):
            if key in producer:
                _string(producer[key], f"producer.{key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or _RECORD_CUTOFF.fullmatch(cutoff) is None:
                _refuse("producer.cutoff must be YYYY-MM")

    if version == 2:
        claim = _members(doc["claim"], _CLAIM_KEYS, frozenset(), "claim")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _members(claim["envelope"], _COST_KEYS,
                                frozenset(), "claim.envelope")
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the exact JSON bytes covered by a record signature."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    """Return the SHA-256 digest of a record's canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read a record file, refusing malformed JSON and invalid records."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return a trusted SSH principal for a record's detached .sig, if any."""
    statement = record_canonical(record_read(path))
    signature = os.fspath(path) + ".sig"
    if not Path(signature).is_file():
        return None
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", os.fspath(anchor),
             "-s", signature], capture_output=True, text=True, timeout=30, check=False)
        if found.returncode != 0:
            return None
        for principal in found.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            checked = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=statement, capture_output=True, timeout=30, check=False)
            if checked.returncode == 0:
                return principal
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None

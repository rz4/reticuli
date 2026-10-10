"""Validate and read the portable, signed record of a claim audit."""

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
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"[0-9]{4}-[0-9]{2}\Z")


def _object(value: object, label: str, required: frozenset[str],
            permitted: frozenset[str]) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"{label} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - permitted
    if missing:
        raise core.ClaimError(f"{label} missing member: {sorted(missing)[0]}")
    if unknown:
        raise core.ClaimError(f"{label} has unknown member: {sorted(unknown)[0]}")
    if any(not isinstance(key, str) for key in value):
        raise core.ClaimError(f"{label} keys must be strings")
    return value


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        raise core.ClaimError(f"{label} must be a string")


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or (value <= 0 if positive else value < 0):
        raise core.ClaimError(f"{label} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse a malformed or extended version-1 or version-2 record."""
    if not isinstance(doc, dict):
        raise core.ClaimError("record must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be 1 or 2")
    if version > RECORD_FORMAT:
        raise core.ClaimError(
            f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    members = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    doc = _object(doc, "record", frozenset(required), frozenset(members))

    _string(doc["name"], "record name")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            raise core.ClaimError(f"record {key} must be 64 lowercase hex characters")
    if not isinstance(doc["gates"], list):
        raise core.ClaimError("record gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        gate = _object(gate, f"gate {index}", _RECORD_GATE, _RECORD_GATE)
        _string(gate["output"], f"gate {index} output")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"gate {index} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"gate {index} has invalid sandbox")

    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key in _RECORD_ENVIRONMENT:
        _string(environment[key], f"environment {key}")
    when = doc["when"]
    if not isinstance(when, str) or _RECORD_WHEN.fullmatch(when) is None:
        raise core.ClaimError("record when must be a UTC timestamp")
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise core.ClaimError("record when must be a valid UTC timestamp") from exc

    if "tool" in doc:
        _string(doc["tool"], "record tool")
    if "cost" in doc:
        cost = _object(doc["cost"], "cost", frozenset(), frozenset(core.COST_KEYS))
        for key, value in cost.items():
            _number(value, f"cost {key}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", frozenset(), _RECORD_PRODUCER)
        for key, value in producer.items():
            if key == "blind":
                if type(value) is not bool:
                    raise core.ClaimError("producer blind must be a boolean")
            elif key == "cutoff":
                if not isinstance(value, str) or _RECORD_CUTOFF.fullmatch(value) is None:
                    raise core.ClaimError("producer cutoff must be YYYY-MM")
                if not 1 <= int(value[5:]) <= 12:
                    raise core.ClaimError("producer cutoff has invalid month")
            else:
                _string(value, f"producer {key}")
    if version == 2:
        claim = _object(doc["claim"], "claim", frozenset(), _RECORD_CLAIM)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim {key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim envelope",
                               frozenset(), frozenset(core.COST_KEYS))
            if not envelope:
                raise core.ClaimError("claim envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim envelope {key}", positive=True)


def record_canonical(doc: dict) -> bytes:
    """Serialize a valid record exactly as a claim identity serializes JSON."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read a JSON record, turning bad input into a claim refusal."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return an allowed SSH signer principal, or None if verification fails."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-s", signature, "-f", os.fspath(anchor)],
            capture_output=True, text=True, check=False)
    except OSError as exc:
        raise core.ClaimError(f"cannot check record signature: {exc}") from exc
    if found.returncode:
        return None
    canonical = record_canonical(doc)
    for principal in found.stdout.splitlines():
        principal = principal.strip()
        if not principal:
            continue
        verified = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
             "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
            input=canonical, capture_output=True, check=False)
        if verified.returncode == 0:
            return principal
    return None

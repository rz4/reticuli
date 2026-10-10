"""Validate and read the portable, signed record format."""

from __future__ import annotations

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
_COST = frozenset(core.COST_KEYS)
_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError(f"invalid record: {message}")


def _members(value: object, allowed: frozenset[str], required: frozenset[str],
             label: str) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{label} must be an object")
    if any(not isinstance(key, str) for key in value):
        _refuse(f"{label} keys must be strings")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown:
        _refuse(f"{label} has unknown member {sorted(unknown)[0]!r}")
    if missing:
        _refuse(f"{label} needs {sorted(missing)[0]!r}")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        _refuse(f"{label} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse any document outside the closed record vocabulary."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands")
    members = _RECORD_MEMBERS | ({"claim"} if version >= 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version >= 2 else set())
    _members(doc, frozenset(members), frozenset(required), "document")

    for key in ("name", "tool"):
        if key in doc and not isinstance(doc[key], str):
            _refuse(f"{key} must be a string")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            _refuse(f"{key} must be 64 lowercase hex characters")
    if not isinstance(doc["when"], str) or _RECORD_WHEN.fullmatch(doc["when"]) is None:
        _refuse("when must be a UTC timestamp")

    environment = _members(doc["environment"], _RECORD_ENVIRONMENT,
                           _RECORD_ENVIRONMENT, "environment")
    if any(not isinstance(value, str) for value in environment.values()):
        _refuse("environment values must be strings")

    gates = doc["gates"]
    if not isinstance(gates, list):
        _refuse("gates must be an array")
    for index, gate in enumerate(gates):
        gate = _members(gate, _RECORD_GATE, _RECORD_GATE, f"gate {index}")
        if not isinstance(gate["output"], str):
            _refuse(f"gate {index} output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gate {index} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gate {index} has invalid sandbox")

    if "cost" in doc:
        cost = _members(doc["cost"], _COST, frozenset(), "cost")
        for key, value in cost.items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        producer = _members(doc["producer"], _RECORD_PRODUCER, frozenset(), "producer")
        for key, value in producer.items():
            if key == "blind":
                if not isinstance(value, bool):
                    _refuse("producer.blind must be boolean")
            elif not isinstance(value, str):
                _refuse(f"producer.{key} must be a string")
        if "cutoff" in producer and _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None:
            _refuse("producer.cutoff must be YYYY-MM")
    if version >= 2:
        claim = _members(doc["claim"], _CLAIM, frozenset(), "claim")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _members(claim["envelope"], _COST, frozenset(), "claim.envelope")
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity format's default-spaced, ASCII JSON bytes."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read a record, converting malformed input into a claim refusal."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return the anchored ssh principal that verifies a detached record signature."""
    canonical = record_canonical(record_read(path))
    signature = os.fspath(path) + ".sig"
    try:
        with open(anchor, "r", encoding="utf-8") as stream:
            principals = [line.split()[0] for line in stream if line.strip()
                          and not line.lstrip().startswith("#")]
        for principal in principals:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=canonical, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                return principal
    except (OSError, IndexError) as exc:
        raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
    return None

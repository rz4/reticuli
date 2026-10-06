"""Validate and read the portable, signed result record."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import subprocess

from . import core


RECORD_FORMAT = 2
RECORD_NAMESPACE = "reticuli.record"

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
_RECORD_COST = frozenset(core.COST_KEYS)
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError(f"malformed record: {message}")


def _members(value: object, name: str, allowed: frozenset[str],
             required: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{name} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra:
        _refuse(f"{name} has unknown member {sorted(extra)!r}")
    if missing:
        _refuse(f"{name} is missing {sorted(missing)!r}")
    return value


def _number(value: object, name: str, *, positive: bool = False) -> None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        _refuse(f"{name} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse malformed or extended records with ClaimError."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands")
    v2 = version == 2
    allowed = _RECORD_MEMBERS | ({"claim"} if v2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if v2 else set())
    _members(doc, "document", allowed, required)

    for name in ("name", "tool"):
        if name in doc and not isinstance(doc[name], str):
            _refuse(f"{name} must be a string")
    for name in ("root", "build_digest"):
        if not isinstance(doc[name], str) or _RECORD_HEX.fullmatch(doc[name]) is None:
            _refuse(f"{name} must be 64 lowercase hex characters")
    when = doc["when"]
    if not isinstance(when, str) or _RECORD_WHEN.fullmatch(when) is None:
        _refuse("when must be a UTC second timestamp")
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _refuse("when is not a valid UTC time")

    if not isinstance(doc["gates"], list):
        _refuse("gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        gate = _members(gate, f"gate {index}", _RECORD_GATE, _RECORD_GATE)
        if not isinstance(gate["output"], str):
            _refuse(f"gate {index} output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gate {index} status is invalid")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gate {index} sandbox is invalid")

    environment = _members(doc["environment"], "environment",
                           _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    if any(not isinstance(value, str) for value in environment.values()):
        _refuse("environment values must be strings")

    if "cost" in doc:
        cost = _members(doc["cost"], "cost", _RECORD_COST)
        for key, value in cost.items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        producer = _members(doc["producer"], "producer", _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer and not isinstance(producer[key], str):
                _refuse(f"producer.{key} must be a string")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", cutoff) is None:
                _refuse("producer.cutoff must be YYYY-MM")
    if v2:
        claim = _members(doc["claim"], "claim", _RECORD_CLAIM)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _members(claim["envelope"], "claim.envelope", _RECORD_COST)
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity format's exact sorted JSON bytes."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a JSON record, refusing malformed bytes in band."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: str, anchor: str) -> str | None:
    """Return the anchored SSH identity that signed a record, if any."""
    doc = record_read(path)
    signature = path + ".sig"
    if not os.path.isfile(signature):
        return None
    try:
        with open(anchor, "r", encoding="utf-8") as stream:
            identities = [line.split()[0] for line in stream
                          if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read allowed signers {anchor}: {exc}") from exc
    for identity in identities:
        try:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", identity,
                 "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return identity
    return None

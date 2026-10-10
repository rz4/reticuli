"""Validation and canonical serialization of portable claim records."""

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
_RECORD_WHEN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError("invalid record: " + message)


def _members(value: object, required: frozenset[str], allowed: frozenset[str], where: str) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{where} must be an object")
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        _refuse(f"{where} missing {', '.join(sorted(missing))}")
    if extra:
        _refuse(f"{where} has unknown member {', '.join(sorted(map(str, extra)))}")
    if any(not isinstance(key, str) for key in value):
        _refuse(f"{where} keys must be strings")
    return value


def _string(value: object, where: str) -> None:
    if not isinstance(value, str):
        _refuse(f"{where} must be a string")


def _number(value: object, where: str, *, positive: bool = False) -> None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        _refuse(f"{where} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse malformed records with ClaimError, including unknown members."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    allowed = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    _members(doc, frozenset(required), frozenset(allowed), "document")

    _string(doc["name"], "name")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or not _RECORD_HEX.fullmatch(doc[key]):
            _refuse(f"{key} must be 64 lowercase hex characters")
    if not isinstance(doc["gates"], list):
        _refuse("gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        _members(gate, _RECORD_GATE, _RECORD_GATE, f"gates[{index}]")
        _string(gate["output"], f"gates[{index}].output")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gates[{index}].status is unknown")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gates[{index}].sandbox is unknown")

    environment = _members(doc["environment"], _RECORD_ENVIRONMENT,
                           _RECORD_ENVIRONMENT, "environment")
    for key in _RECORD_ENVIRONMENT:
        _string(environment[key], f"environment.{key}")
    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.fullmatch(when):
        _refuse("when must be a UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _refuse("when is not a valid date and time")

    if "tool" in doc:
        _string(doc["tool"], "tool")
    if "cost" in doc:
        cost = _members(doc["cost"], frozenset(), frozenset(core.COST_KEYS), "cost")
        for key, value in cost.items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        producer = _members(doc["producer"], frozenset(), _RECORD_PRODUCER, "producer")
        for key in ("vendor", "model"):
            if key in producer:
                _string(producer[key], f"producer.{key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", cutoff):
                _refuse("producer.cutoff must be YYYY-MM")

    if version == 2:
        claim = _members(doc["claim"], frozenset(), _RECORD_CLAIM, "claim")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _members(claim["envelope"], frozenset(),
                                frozenset(core.COST_KEYS), "claim.envelope")
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: dict) -> bytes:
    """Encode a validated record with the identity JSON convention."""
    record_validate(doc)
    try:
        return json.dumps(doc, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot serialize record: {exc}") from exc


def record_digest(doc: dict) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read and validate a JSON record from disk."""
    core._hash_file(path)
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return the trusted ssh signer for a detached ``.sig`` record signature."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        with open(signature, "rb") as stream:
            signed = stream.read()
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
             "-I", "reticuli", "-n", RECORD_NAMESPACE, "-s", signature],
            input=record_canonical(doc), capture_output=True, timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
    if not signed or done.returncode != 0:
        raise core.ClaimError("record signature did not verify against the anchor")
    return "reticuli"

"""Validate, serialize, and read portable claim records."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime

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
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"\d{4}-\d{2}\Z")
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_COST = frozenset(core.COST_KEYS)


def _refuse(message: str) -> None:
    raise core.ClaimError("malformed record: " + message)


def _members(value: object, allowed: frozenset[str], required: frozenset[str],
             label: str) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{label} must be an object")
    unknown = value.keys() - allowed
    missing = required - value.keys()
    if unknown:
        _refuse(f"{label} has unknown member {sorted(unknown)!r}")
    if missing:
        _refuse(f"{label} is missing {sorted(missing)!r}")
    return value


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0 if positive else False):
        _refuse(f"{label} must be a positive finite number")
    if not positive and (isinstance(value, bool) or not isinstance(value, (int, float))
                         or not math.isfinite(value) or value < 0):
        _refuse(f"{label} must be a nonnegative finite number")


def record_validate(doc: object) -> None:
    """Refuse malformed or extended versioned records with ClaimError."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands")
    allowed = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    _members(doc, frozenset(allowed), frozenset(required), "document")

    for key in ("name", "tool"):
        if key in doc and not isinstance(doc[key], str):
            _refuse(f"{key} must be a string")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or not _RECORD_HEX.fullmatch(doc[key]):
            _refuse(f"{key} must be 64 lowercase hexadecimal characters")
    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.fullmatch(when):
        _refuse("when must be UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        _refuse(f"invalid when: {error}")

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
        cost = _members(doc["cost"], _RECORD_COST, frozenset(), "cost")
        for key, value in cost.items():
            _number(value, f"cost.{key}")

    if "producer" in doc:
        producer = _members(doc["producer"], _RECORD_PRODUCER,
                            frozenset(), "producer")
        for key in ("vendor", "model"):
            if key in producer and not isinstance(producer[key], str):
                _refuse(f"producer.{key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or not _RECORD_CUTOFF.fullmatch(cutoff):
                _refuse("producer.cutoff must be YYYY-MM")
            try:
                datetime.strptime(cutoff, "%Y-%m")
            except ValueError as error:
                _refuse(f"invalid producer.cutoff: {error}")

    if version == 2:
        claim = _members(doc["claim"], _RECORD_CLAIM, frozenset(), "claim")
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _members(claim["envelope"], _RECORD_COST,
                                frozenset(), "claim.envelope")
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: dict) -> bytes:
    """Return the identity serialization of a valid record."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """Return SHA-256 of a record's canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read and validate a record JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as source:
            doc = json.load(source)
    except (OSError, UnicodeError, ValueError) as error:
        raise core.ClaimError(f"cannot read record {path}: {error}") from error
    record_validate(doc)
    return doc


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return an anchored SSH signer for a detached record signature, if any."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        principals = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", os.fspath(anchor),
             "-s", signature], capture_output=True, text=True, timeout=15,
            check=False)
        if principals.returncode:
            return None
        for principal in principals.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, timeout=15,
                check=False)
            if verified.returncode == 0:
                return principal
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None

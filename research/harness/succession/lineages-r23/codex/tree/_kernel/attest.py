"""Validate and read the portable, signed record of a claim run."""

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
_COST_KEYS = frozenset(core.COST_KEYS)
_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError(f"invalid record: {message}")


def _object(value: object, label: str, required: frozenset[str],
            permitted: frozenset[str]) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{label} must be an object")
    missing = required - value.keys()
    extra = value.keys() - permitted
    if missing:
        _refuse(f"{label} missing {', '.join(sorted(missing))}")
    if extra:
        _refuse(f"{label} has unknown member {', '.join(sorted(extra))}")
    return value


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        _refuse(f"{label} must be a string")


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        _refuse(f"{label} must be a finite number")
    if value <= 0 if positive else value < 0:
        _refuse(f"{label} must be {'positive' if positive else 'nonnegative'}")


def record_validate(doc: object) -> None:
    """Refuse malformed records with a ClaimError, including unknown members."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    members = _RECORD_MEMBERS | ({"claim"} if version >= 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version >= 2 else set())
    _object(doc, "document", required, members)

    _string(doc["name"], "name")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            _refuse(f"{key} must be 64 lowercase hexadecimal characters")
    if not isinstance(doc["gates"], list):
        _refuse("gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        label = f"gate {index}"
        _object(gate, label, _RECORD_GATE, _RECORD_GATE)
        _string(gate["output"], f"{label} output")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"{label} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"{label} has invalid sandbox")
    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key in _RECORD_ENVIRONMENT:
        _string(environment[key], f"environment {key}")
    if not isinstance(doc["when"], str) or _RECORD_WHEN.fullmatch(doc["when"]) is None:
        _refuse("when must be a UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
    if "tool" in doc:
        _string(doc["tool"], "tool")

    if "cost" in doc:
        cost = _object(doc["cost"], "cost", frozenset(), _COST_KEYS)
        for key, value in cost.items():
            _number(value, f"cost {key}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", frozenset(), _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer:
                _string(producer[key], f"producer {key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer blind must be boolean")
        if "cutoff" in producer and (not isinstance(producer["cutoff"], str) or
                                     _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None):
            _refuse("producer cutoff must be YYYY-MM")

    if version >= 2:
        claim = _object(doc["claim"], "claim", frozenset(), _CLAIM_KEYS)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim {key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim envelope", frozenset(), _COST_KEYS)
            if not envelope:
                _refuse("claim envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim envelope {key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity JSON serialization, byte for byte."""
    record_validate(doc)
    try:
        return json.dumps(doc, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise core.ClaimError(f"record has no canonical JSON form: {exc}") from exc


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read and validate a JSON record from disk."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return an anchored SSH signer principal, or None if verification fails."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", os.fspath(anchor),
             "-s", signature], capture_output=True, text=True, timeout=10,
            check=False,
        )
        if found.returncode:
            return None
        for principal in found.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, timeout=10,
                check=False,
            )
            if verified.returncode == 0:
                return principal
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None

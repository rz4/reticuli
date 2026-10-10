"""Read and validate the portable, signed record of a claim judgment."""

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
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"\d{4}-\d{2}\Z")


def _object(value: object, where: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"{where} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra or missing:
        raise core.ClaimError(f"{where} has unknown {sorted(extra)} or missing {sorted(missing)} members")
    return value


def _number(value: object, where: str, *, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise core.ClaimError(f"{where} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(doc: object) -> None:
    """Refuse records outside the versioned, closed document format."""
    if not isinstance(doc, dict):
        raise core.ClaimError("record must be a JSON object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be a positive integer")
    if version > RECORD_FORMAT:
        raise core.ClaimError(f"record version {version} is newer than this kernel understands (version {RECORD_FORMAT})")
    members = _RECORD_MEMBERS | ({"claim"} if version >= 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version >= 2 else set())
    _object(doc, "record", frozenset(members), frozenset(required))
    for key in ("name", "tool"):
        if key in doc and not isinstance(doc[key], str):
            raise core.ClaimError(f"record {key} must be a string")
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            raise core.ClaimError(f"record {key} must be 64 lowercase hex characters")
    if not isinstance(doc["when"], str) or _RECORD_WHEN.fullmatch(doc["when"]) is None:
        raise core.ClaimError("record when must be a UTC timestamp")
    if not isinstance(doc["gates"], list):
        raise core.ClaimError("record gates must be an array")
    for index, gate in enumerate(doc["gates"]):
        gate = _object(gate, f"gate {index}", _RECORD_GATE, _RECORD_GATE)
        if not isinstance(gate["output"], str) or gate["status"] not in _RECORD_STATUSES or gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"gate {index} has invalid output, status, or sandbox")
    environment = _object(doc["environment"], "environment", _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    if any(not isinstance(value, str) for value in environment.values()):
        raise core.ClaimError("record environment values must be strings")
    if "cost" in doc:
        cost = _object(doc["cost"], "cost", _RECORD_COST)
        for key, value in cost.items():
            _number(value, f"cost {key}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"producer {key} must be a string")
        if "blind" in producer and type(producer["blind"]) is not bool:
            raise core.ClaimError("producer blind must be a boolean")
        if "cutoff" in producer and (not isinstance(producer["cutoff"], str) or _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None):
            raise core.ClaimError("producer cutoff must be YYYY-MM")
    if version >= 2:
        claim = _object(doc["claim"], "claim", _RECORD_CLAIM)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim {key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim envelope", _RECORD_COST)
            if not envelope:
                raise core.ClaimError("claim envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim envelope {key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return the identity serialization, with default JSON separators."""
    record_validate(doc)
    try:
        return json.dumps(doc, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot serialize record: {exc}") from exc


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read and validate a record without trusting its JSON bytes."""
    try:
        core._hash_file(path)
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return the anchored SSH principal that signed a detached record."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        core._hash_file(signature)
        core._hash_file(anchor)
        with open(anchor, "r", encoding="utf-8") as stream:
            principals = [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, UnicodeError, IndexError, core.ClaimError) as exc:
        raise core.ClaimError(f"cannot read record signature or anchor: {exc}") from exc
    for principal in principals:
        try:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor), "-I", principal,
                 "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
        if result.returncode == 0:
            return principal
    return None

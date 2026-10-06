"""Read and validate the portable, signed record format."""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import subprocess
from typing import Any

from . import core


RECORD_FORMAT = 2
RECORD_NAMESPACE = "reticuli.record"

_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest",
                             "gates", "cost", "producer", "environment", "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest",
                              "gates", "environment", "when"})
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


def _fail(message: str) -> None:
    raise core.ClaimError(f"invalid record: {message}")


def _object(value: Any, label: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra:
        _fail(f"{label} has unknown member {sorted(extra)!r}")
    if missing:
        _fail(f"{label} lacks required member {sorted(missing)!r}")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        _fail(f"{label} must be a finite number")
    if value <= 0 if positive else value < 0:
        _fail(f"{label} must be {'positive' if positive else 'nonnegative'}")


def _string(value: Any, label: str) -> None:
    if not isinstance(value, str):
        _fail(f"{label} must be a string")


def record_validate(doc: Any) -> None:
    """Refuse malformed or extended record documents with a ClaimError."""
    if not isinstance(doc, dict):
        _fail("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _fail("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _fail(f"record version {version} is newer than this kernel understands ({RECORD_FORMAT})")
    allowed = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    _object(doc, "document", allowed, frozenset(required))

    for key in ("name", "when"):
        _string(doc[key], key)
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or not _RECORD_HEX.fullmatch(doc[key]):
            _fail(f"{key} must be 64 lowercase hex characters")
    if not _RECORD_WHEN.fullmatch(doc["when"]):
        _fail("when must be a UTC timestamp in YYYY-MM-DDTHH:MM:SSZ form")
    try:
        datetime.datetime.strptime(doc["when"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        _fail(f"when is not a real UTC time: {exc}")
    if "tool" in doc:
        _string(doc["tool"], "tool")

    if not isinstance(doc["gates"], list):
        _fail("gates must be an array")
    for index, entry in enumerate(doc["gates"]):
        gate = _object(entry, f"gates[{index}]", _RECORD_GATE, _RECORD_GATE)
        _string(gate["output"], f"gates[{index}].output")
        if gate["status"] not in _RECORD_STATUSES:
            _fail(f"gates[{index}].status is unknown")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _fail(f"gates[{index}].sandbox is unknown")

    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key, value in environment.items():
        _string(value, f"environment.{key}")

    if "cost" in doc:
        for key, value in _object(doc["cost"], "cost", _RECORD_COST).items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        for key, value in _object(doc["producer"], "producer", _RECORD_PRODUCER).items():
            if key == "blind":
                if type(value) is not bool:
                    _fail("producer.blind must be a boolean")
            else:
                _string(value, f"producer.{key}")
                if key == "cutoff" and not _RECORD_CUTOFF.fullmatch(value):
                    _fail("producer.cutoff must be YYYY-MM")

    if version == 2:
        claim = _object(doc["claim"], "claim", _RECORD_CLAIM)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim.envelope", _RECORD_COST)
            if not envelope:
                _fail("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: Any) -> bytes:
    """Return the identity JSON serialization of a valid record."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: Any) -> str:
    """Return the SHA-256 digest of the canonical record bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict[str, Any]:
    """Read a JSON record, reporting malformed input in band."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str:
    """Return the trusted SSH principal that signed a record's canonical bytes."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    try:
        with open(anchor, "r", encoding="utf-8") as stream:
            principals = [line.split()[0] for line in stream
                          if line.strip() and not line.lstrip().startswith("#")]
        for principal in principals:
            done = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=record_canonical(doc), capture_output=True, check=False)
            if done.returncode == 0:
                return principal
    except (OSError, subprocess.SubprocessError) as exc:
        raise core.ClaimError(f"cannot verify record signature: {exc}") from exc
    raise core.ClaimError(f"record signature is not trusted: {path}")

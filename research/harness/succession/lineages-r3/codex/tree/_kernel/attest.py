"""Read and validate portable, signed claim records.

Record bytes use the same JSON serialization as claim identity.  This module
only reads records; creating and signing them belongs to the exchange layer.
"""

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
_RECORD_CUTOFF = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")
_COST_KEYS = frozenset({"usd", "tokens", "calls", "seconds"})
_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError("invalid record: " + message)


def _object(value: object, label: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict:
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
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        _refuse(f"{label} must be a {'positive' if positive else 'non-negative'} number")


def _string(value: object, label: str) -> None:
    if not isinstance(value, str):
        _refuse(f"{label} must be a string")


def record_validate(doc: object) -> None:
    """Refuse any malformed record with a ClaimError."""
    if not isinstance(doc, dict):
        _refuse("document must be an object")
    version = doc.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands")
    members = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    _object(doc, "document", members, required)

    for key in ("name", "tool"):
        if key in doc:
            _string(doc[key], key)
    for key in ("root", "build_digest"):
        if not isinstance(doc[key], str) or _RECORD_HEX.fullmatch(doc[key]) is None:
            _refuse(f"{key} must be 64 lowercase hexadecimal characters")
    if not isinstance(doc["when"], str) or _RECORD_WHEN.fullmatch(doc["when"]) is None:
        _refuse("when must be a UTC timestamp ending in Z")
    # A matching shape alone admits impossible dates and times.
    import datetime
    try:
        datetime.datetime.strptime(doc["when"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        _refuse(f"when is not a valid UTC timestamp: {exc}")

    environment = _object(doc["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key, value in environment.items():
        _string(value, f"environment.{key}")
    if not isinstance(doc["gates"], list):
        _refuse("gates must be an array")
    for index, entry in enumerate(doc["gates"]):
        gate = _object(entry, f"gates[{index}]", _RECORD_GATE, _RECORD_GATE)
        _string(gate["output"], f"gates[{index}].output")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gates[{index}].status is unknown")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gates[{index}].sandbox is unknown")

    if "cost" in doc:
        cost = _object(doc["cost"], "cost", _COST_KEYS)
        for key, value in cost.items():
            _number(value, f"cost.{key}")
    if "producer" in doc:
        producer = _object(doc["producer"], "producer", _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer:
                _string(producer[key], f"producer.{key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer and (not isinstance(producer["cutoff"], str)
                                     or _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None):
            _refuse("producer.cutoff must be YYYY-MM")
    if version == 2:
        claim = _object(doc["claim"], "claim", _CLAIM_KEYS)
        for key in ("tolerance", "mutation_floor"):
            if key in claim:
                _number(claim[key], f"claim.{key}")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim.envelope", _COST_KEYS)
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(doc: object) -> bytes:
    """Return validated record bytes in the identity JSON format."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    """Return the SHA-256 digest of the canonical record bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read a record JSON file and validate its closed schema."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return the trusted SSH principal for a detached record signature.

    A neighboring ``.sig`` file contains the ssh-keygen signature.  The
    verifier's allowed-signers file supplies principals; each is tried in
    that file's order against the canonical record bytes.
    """
    message = record_canonical(record_read(path))
    signature = os.fspath(path) + ".sig"
    try:
        with open(anchor, "r", encoding="utf-8") as stream:
            principals = [line.split()[0] for line in stream
                          if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read allowed signers {anchor}: {exc}") from exc
    for principal in principals:
        try:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                 "-I", principal, "-n", RECORD_NAMESPACE, "-s", signature],
                input=message, capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode == 0:
            return principal
    return None

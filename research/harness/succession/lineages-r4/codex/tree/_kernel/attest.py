"""Read and validate the portable, signed record of a claim run."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

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
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})


def _object(value: object, allowed: frozenset[str], required: frozenset[str],
            label: str) -> dict:
    if not isinstance(value, dict):
        raise core.ClaimError(f"record {label} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra:
        raise core.ClaimError(f"record {label} has unknown member: {sorted(extra)!r}")
    if missing:
        raise core.ClaimError(f"record {label} is missing member: {sorted(missing)!r}")
    return value


def _number(value: object, *, positive: bool = False) -> bool:
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def record_validate(doc: object) -> None:
    """Refuse an invalid version-1 record with an in-band reason."""
    data = _object(doc, _RECORD_MEMBERS, _RECORD_REQUIRED, "document")
    version = data["record"]
    if type(version) is not int or version < 1:
        raise core.ClaimError("record version must be a positive integer")
    if version > RECORD_FORMAT:
        raise core.ClaimError(f"record version {version} is newer than this kernel understands")
    for key in ("name", "tool"):
        if key in data and not isinstance(data[key], str):
            raise core.ClaimError(f"record {key} must be a string")
    for key in ("root", "build_digest"):
        if not isinstance(data[key], str) or _RECORD_HEX.fullmatch(data[key]) is None:
            raise core.ClaimError(f"record {key} must be 64 lowercase hex characters")
    if not isinstance(data["when"], str) or _RECORD_WHEN.fullmatch(data["when"]) is None:
        raise core.ClaimError("record when must be a UTC timestamp")

    gates = data["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("record gates must be an array")
    for index, gate in enumerate(gates):
        gate = _object(gate, _RECORD_GATE, _RECORD_GATE, f"gate {index}")
        if not isinstance(gate["output"], str):
            raise core.ClaimError(f"record gate {index} output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"record gate {index} has invalid status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"record gate {index} has invalid sandbox")

    environment = _object(data["environment"], _RECORD_ENVIRONMENT,
                          _RECORD_ENVIRONMENT, "environment")
    if any(not isinstance(value, str) for value in environment.values()):
        raise core.ClaimError("record environment values must be strings")

    if "cost" in data:
        cost = _object(data["cost"], _RECORD_COST, frozenset(), "cost")
        if any(not _number(value) for value in cost.values()):
            raise core.ClaimError("record cost values must be non-negative numbers")

    if "producer" in data:
        producer = _object(data["producer"], _RECORD_PRODUCER,
                           frozenset(), "producer")
        for key in ("vendor", "model"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"record producer {key} must be a string")
        if "blind" in producer and type(producer["blind"]) is not bool:
            raise core.ClaimError("record producer blind must be boolean")
        if ("cutoff" in producer and
                (not isinstance(producer["cutoff"], str) or
                 _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None)):
            raise core.ClaimError("record producer cutoff must be YYYY-MM")


def record_canonical(doc: object) -> bytes:
    """Serialize a valid record with identity's sorted, default JSON form."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: object) -> str:
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: os.PathLike[str] | str) -> dict:
    """Read an untrusted JSON record, refusing malformed content in band."""
    try:
        with open(path, "r", encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: os.PathLike[str] | str,
                  anchor: os.PathLike[str] | str) -> str | None:
    """Return an anchored SSH principal for a detached record signature."""
    doc = record_read(path)
    signature = os.fspath(path) + ".sig"
    if not os.path.isfile(signature):
        return None
    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", os.fspath(anchor),
             "-s", signature], capture_output=True, text=True, check=False)
        if found.returncode != 0:
            return None
        message = record_canonical(doc)
        for principal in found.stdout.splitlines():
            principal = principal.strip()
            if not principal:
                continue
            with open(signature, "rb") as stream:
                verified = subprocess.run(
                    ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                     "-I", principal, "-n", RECORD_NAMESPACE, "-s", "/dev/stdin"],
                    input=message, capture_output=True, check=False)
            if verified.returncode == 0:
                return principal
    except OSError as exc:
        raise core.ClaimError(f"cannot verify record signature {signature}: {exc}") from exc
    return None

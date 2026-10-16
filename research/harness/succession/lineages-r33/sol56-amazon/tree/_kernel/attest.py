"""Read and identify portable Reticuli result records.

A record is the kernel's deliberately small interchange format.  Its JSON
serialization is protocol data: sorted keys, the default :mod:`json`
separators, and the default ASCII escaping.  Claim-controlled data is always
validated before it is canonicalized or digested.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from typing import Any

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

# Version-one names are retained as constants because they are the original
# record-format seam.  Version two adds the required ``claim`` member.
_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "cost",
    "producer", "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment",
    "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({
    "ok", "failed", "timeout", "mismatch", "environment",
})
_RECORD_SANDBOXES = frozenset({
    "none", "seatbelt", "bubblewrap", "inherited",
})
_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(
    r"^[0-9]{4}-(?:0[1-9]|1[0-2])-"
    r"(?:0[1-9]|[12][0-9]|3[01])T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)

_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_CUTOFF = re.compile(r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")


def _refuse(message: str) -> None:
    raise core.ClaimError(message)


def _number(value: Any, *, positive: bool = False) -> bool:
    """Whether *value* is an admitted finite record number."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return value > 0 if positive else value >= 0


def _closed(value: Any, members: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _refuse(f"record {label} must be a JSON object")
    unknown = set(value) - members
    if unknown:
        _refuse(f"record {label} has unknown member {sorted(unknown, key=str)[0]!r}")
    return value


def _validate_cost(value: Any) -> None:
    cost = _closed(value, _RECORD_COST, "cost")
    for unit, amount in cost.items():
        if not _number(amount):
            _refuse(
                f"record cost {unit!r} must be a finite non-negative number"
            )


def _validate_producer(value: Any) -> None:
    producer = _closed(value, _RECORD_PRODUCER, "producer")
    for key in ("vendor", "model"):
        if key in producer and not isinstance(producer[key], str):
            _refuse(f"record producer {key!r} must be a string")
    if "blind" in producer and not isinstance(producer["blind"], bool):
        _refuse("record producer 'blind' must be a boolean")
    if "cutoff" in producer and (
        not isinstance(producer["cutoff"], str)
        or _RECORD_CUTOFF.fullmatch(producer["cutoff"]) is None
    ):
        _refuse("record producer 'cutoff' must have form YYYY-MM")


def _validate_claim(value: Any) -> None:
    claim = _closed(value, _RECORD_CLAIM, "claim")
    for key in ("tolerance", "mutation_floor"):
        if key in claim and not _number(claim[key]):
            _refuse(f"record claim {key!r} must be a finite non-negative number")

    if "envelope" in claim:
        envelope = _closed(claim["envelope"], _RECORD_COST, "claim envelope")
        if not envelope:
            _refuse("record claim envelope must not be empty")
        for unit, ceiling in envelope.items():
            if not _number(ceiling, positive=True):
                _refuse(
                    f"record claim envelope {unit!r} must be a finite "
                    "positive number"
                )


def record_validate(doc: Any) -> None:
    """Validate one record, raising :class:`ClaimError` on any refusal.

    The member set is closed.  Version one uses the original member set;
    version two additionally requires the ``claim`` obligations object.
    """

    if not isinstance(doc, dict):
        _refuse("record must be a JSON object")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        _refuse("record version is required and must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(
            f"record version {version} is newer than this kernel understands "
            f"(record {RECORD_FORMAT})"
        )

    members = _RECORD_MEMBERS | ({"claim"} if version == 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version == 2 else set())
    unknown = set(doc) - members
    if unknown:
        _refuse(f"record has unknown member {sorted(unknown, key=str)[0]!r}")
    missing = required - set(doc)
    if missing:
        _refuse(f"record is missing required member {sorted(missing)[0]!r}")

    if not isinstance(doc["name"], str):
        _refuse("record name must be a string")
    for key in ("root", "build_digest"):
        value = doc[key]
        if not isinstance(value, str) or _RECORD_HEX.fullmatch(value) is None:
            _refuse(f"record {key} must be 64 lowercase hex characters")

    gates = doc["gates"]
    if not isinstance(gates, list):
        _refuse("record gates must be a JSON array")
    for index, value in enumerate(gates):
        gate = _closed(value, _RECORD_GATE, f"gate {index + 1}")
        missing_gate = _RECORD_GATE - set(gate)
        if missing_gate:
            _refuse(
                f"record gate {index + 1} is missing member "
                f"{sorted(missing_gate)[0]!r}"
            )
        if not isinstance(gate["output"], str):
            _refuse(f"record gate {index + 1} output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"record gate {index + 1} has unknown status")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"record gate {index + 1} has unknown sandbox")

    environment = _closed(doc["environment"], _RECORD_ENVIRONMENT, "environment")
    missing_environment = _RECORD_ENVIRONMENT - set(environment)
    if missing_environment:
        _refuse(
            "record environment is missing member "
            f"{sorted(missing_environment)[0]!r}"
        )
    for key in _RECORD_ENVIRONMENT:
        if not isinstance(environment[key], str):
            _refuse(f"record environment {key!r} must be a string")

    when = doc["when"]
    if not isinstance(when, str) or _RECORD_WHEN.fullmatch(when) is None:
        _refuse("record when must be a UTC timestamp YYYY-MM-DDTHH:MM:SSZ")

    if "tool" in doc and not isinstance(doc["tool"], str):
        _refuse("record tool must be a string")
    if "cost" in doc:
        _validate_cost(doc["cost"])
    if "producer" in doc:
        _validate_producer(doc["producer"])
    if version == 2:
        _validate_claim(doc["claim"])


def record_canonical(doc: Any) -> bytes:
    """Return the canonical protocol bytes for a validated record."""

    record_validate(doc)
    try:
        return json.dumps(doc, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        # Validation should have excluded these, but always keep a malformed
        # caller value in band even on unusual mapping subclasses.
        raise core.ClaimError(f"cannot canonicalize record: {exc}") from None


def record_digest(doc: Any) -> str:
    """Return the lowercase SHA-256 citation of a validated record."""

    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a canonical JSON record from *path*.

    Files are required to contain exactly their canonical bytes.  This makes
    the bytes read, the bytes signed, and the bytes named by
    :func:`record_digest` one and the same value.
    """

    try:
        with open(path, "rb") as stream:
            raw = stream.read()
        doc = json.loads(raw)
    except core.ClaimError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record: {exc}") from None

    record_validate(doc)
    canonical = record_canonical(doc)
    if raw != canonical:
        _refuse("record file is not in canonical JSON form")
    return doc


def _signature_paths(path: str | os.PathLike[str]) -> list[str]:
    """Return conventional detached-signature names for a record file."""

    value = os.fspath(path)
    candidates = [value + ".sign", value + ".sig"]
    stem, extension = os.path.splitext(value)
    if extension:
        candidates.extend((stem + ".sign", stem + ".sig"))
    result: list[str] = []
    for candidate in candidates:
        if candidate not in result and os.path.isfile(candidate):
            result.append(candidate)
    return result


def _anchor_identities(path: str | os.PathLike[str]) -> list[str]:
    """Extract literal principals worth trying from an allowed-signers file."""

    identities: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                field = line.split(None, 1)[0]
                for identity in field.split(","):
                    if identity and identity not in identities:
                        identities.append(identity)
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read record trust anchor: {exc}") from None
    return identities


def record_signer(
    path: str | os.PathLike[str], anchor: str | os.PathLike[str]
) -> str | None:
    """Return the anchored principal signing *path*, or ``None``.

    Detached signatures conventionally sit beside the record as ``.sign`` or
    ``.sig``.  Verification uses OpenSSH's ``ssh-keygen -Y`` mechanism and
    the record-specific namespace.  The record is read first, so a signature
    can never bless bytes that are not themselves an admitted record.
    """

    doc = record_read(path)
    payload = record_canonical(doc)
    executable = shutil.which("ssh-keygen")
    signatures = _signature_paths(path)
    if executable is None or not signatures:
        return None

    identities = _anchor_identities(anchor)
    # A wildcard anchor is useful with the literal identity OpenSSH is asked
    # to verify; keep it as a candidate rather than attempting key parsing.
    for identity in identities:
        for signature in signatures:
            try:
                done = subprocess.run(
                    [
                        executable, "-Y", "verify", "-f", os.fspath(anchor),
                        "-I", identity, "-n", RECORD_NAMESPACE,
                        "-s", signature,
                    ],
                    input=payload,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except (OSError, TypeError, ValueError):
                continue
            if done.returncode == 0:
                return identity
    return None


ClaimError = core.ClaimError

__all__ = [
    "ClaimError", "RECORD_FORMAT", "RECORD_NAMESPACE", "record_canonical",
    "record_digest", "record_read", "record_signer", "record_validate",
]

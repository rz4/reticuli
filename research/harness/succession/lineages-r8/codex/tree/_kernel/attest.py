"""Read and validate portable, signed claim records."""

from __future__ import annotations

import datetime as _datetime
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

from . import core


RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 2

_RECORD_MEMBERS = frozenset({"when", "cost", "gates", "producer", "environment",
                             "name", "root", "record", "build_digest", "tool"})
_RECORD_REQUIRED = frozenset({"build_digest", "when", "environment", "record",
                              "name", "root", "gates"})
_RECORD_GATE = frozenset({"status", "sandbox", "output"})
_RECORD_ENVIRONMENT = frozenset({"platform", "runtime", "machine"})
_RECORD_PRODUCER = frozenset({"blind", "model", "cutoff", "vendor"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "inherited", "bubblewrap"})
_RECORD_STATUSES = frozenset({"timeout", "ok", "environment", "failed", "mismatch"})
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")

_COST_KEYS = frozenset(core.COST_KEYS)
_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(message: str) -> None:
    raise core.ClaimError(f"malformed record: {message}")


def _object(value: object, label: str, allowed: frozenset[str],
            required: frozenset[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        _refuse(f"{label} must be an object")
    extra = value.keys() - allowed
    missing = required - value.keys()
    if extra:
        _refuse(f"{label} has unknown members: {sorted(extra)!r}")
    if missing:
        _refuse(f"{label} is missing members: {sorted(missing)!r}")
    return value


def _text(value: object, label: str) -> None:
    if not isinstance(value, str):
        _refuse(f"{label} must be a string")


def _number(value: object, label: str, *, positive: bool = False) -> None:
    if (type(value) not in (int, float) or not math.isfinite(value)
            or (value <= 0 if positive else value < 0)):
        _refuse(f"{label} must be a {'positive' if positive else 'non-negative'} number")


def record_validate(document: object) -> None:
    """Refuse any malformed record, including unknown versioned members."""
    if not isinstance(document, dict):
        _refuse("document must be an object")
    version = document.get("record")
    if type(version) is not int or version < 1:
        _refuse("record version must be a positive integer")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this kernel understands "
                f"(record {RECORD_FORMAT})")

    allowed = _RECORD_MEMBERS | ({"claim"} if version >= 2 else set())
    required = _RECORD_REQUIRED | ({"claim"} if version >= 2 else set())
    _object(document, "document", allowed, required)
    _text(document["name"], "name")
    for key in ("root", "build_digest"):
        if not isinstance(document[key], str) or _RECORD_HEX.fullmatch(document[key]) is None:
            _refuse(f"{key} must be 64 lowercase hexadecimal characters")

    _text(document["when"], "when")
    if _RECORD_WHEN.fullmatch(document["when"]) is None:
        _refuse("when must be UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        _datetime.datetime.strptime(document["when"], "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise core.ClaimError(f"malformed record: invalid when: {exc}") from exc

    gates = document["gates"]
    if not isinstance(gates, list):
        _refuse("gates must be an array")
    for index, gate in enumerate(gates):
        gate = _object(gate, f"gates[{index}]", _RECORD_GATE, _RECORD_GATE)
        _text(gate["output"], f"gates[{index}].output")
        if gate["status"] not in _RECORD_STATUSES:
            _refuse(f"gates[{index}].status is unknown")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"gates[{index}].sandbox is unknown")

    environment = _object(document["environment"], "environment",
                          _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT)
    for key in _RECORD_ENVIRONMENT:
        _text(environment[key], f"environment.{key}")

    if "cost" in document:
        cost = _object(document["cost"], "cost", _COST_KEYS)
        for key, value in cost.items():
            _number(value, f"cost.{key}")

    if "producer" in document:
        producer = _object(document["producer"], "producer", _RECORD_PRODUCER)
        for key in ("vendor", "model"):
            if key in producer:
                _text(producer[key], f"producer.{key}")
        if "blind" in producer and type(producer["blind"]) is not bool:
            _refuse("producer.blind must be a boolean")
        if "cutoff" in producer:
            cutoff = producer["cutoff"]
            if not isinstance(cutoff, str) or re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", cutoff) is None:
                _refuse("producer.cutoff must be YYYY-MM")

    if "tool" in document:
        _text(document["tool"], "tool")

    if version >= 2:
        claim = _object(document["claim"], "claim", _CLAIM_KEYS)
        if "tolerance" in claim:
            _number(claim["tolerance"], "claim.tolerance")
            if not 1.5 <= claim["tolerance"] < 4.0:
                _refuse("claim.tolerance must be in [1.5, 4.0)")
        if "mutation_floor" in claim:
            _number(claim["mutation_floor"], "claim.mutation_floor")
            if claim["mutation_floor"] > 1:
                _refuse("claim.mutation_floor must be at most 1")
        if "envelope" in claim:
            envelope = _object(claim["envelope"], "claim.envelope", _COST_KEYS)
            if not envelope:
                _refuse("claim.envelope must not be empty")
            for key, value in envelope.items():
                _number(value, f"claim.envelope.{key}", positive=True)


def record_canonical(document: dict) -> bytes:
    """The identity JSON serialization, verbatim, as UTF-8 bytes."""
    record_validate(document)
    return json.dumps(document, sort_keys=True).encode("utf-8")


def record_digest(document: dict) -> str:
    return hashlib.sha256(record_canonical(document)).hexdigest()


def record_read(path: str | os.PathLike[str]) -> dict:
    """Read a JSON record and refuse invalid documents in band."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ClaimError(f"cannot read record {path}: {exc}") from exc
    record_validate(document)
    return document


def record_signer(path: str | os.PathLike[str], anchor: str | os.PathLike[str]) -> str | None:
    """Return an allowed SSH signer of a record's canonical bytes, if any.

    A detached signature is kept beside the record as ``<path>.sig``. Each
    principal in the caller's allowed-signers file is tried in this record's
    namespace; failure to verify is not evidence of a signer.
    """
    document = record_read(path)
    try:
        signature = Path(os.fspath(path) + ".sig")
        if not signature.is_file():
            return None
        lines = Path(anchor).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise core.ClaimError(f"cannot read record signer files: {exc}") from exc
    canonical = record_canonical(document)
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for principal in line.split(None, 1)[0].split(","):
            try:
                completed = subprocess.run(
                    ["ssh-keygen", "-Y", "verify", "-f", os.fspath(anchor),
                     "-I", principal, "-n", RECORD_NAMESPACE,
                     "-s", os.fspath(signature)],
                    input=canonical, capture_output=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                return None
            if completed.returncode == 0:
                return principal
    return None

"""Kernel attest: the record reader (spec/record.md).

A record is the one parseable file: a closed-member JSON document whose
canonical bytes are the identity serialization and whose digest is the sha256
of those bytes.  Every entry point that consumes a document validates first.
"""
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile

from . import core
from .core import ClaimError

_RECORD_VERSIONS = (1, 2)
_RECORD_HEX = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_RECORD_CUTOFF = re.compile(r"\d{4}-\d{2}\Z")

_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest", "gates",
                             "cost", "producer", "environment", "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest", "gates",
                              "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch",
                              "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_COST = frozenset(core.COST_KEYS)
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v) -> bool:
    return not isinstance(v, float) or math.isfinite(v)


def _check_hex(doc: dict, key: str) -> None:
    v = doc[key]
    if not isinstance(v, str) or not _RECORD_HEX.match(v):
        raise ClaimError(f"malformed record: {key} is not 64 lowercase hex")


def _check_closed(obj, allowed, what: str, required=None) -> None:
    if not isinstance(obj, dict):
        raise ClaimError(f"malformed record: {what} is not an object")
    for k in obj:
        if not isinstance(k, str) or k not in allowed:
            raise ClaimError(f"malformed record: unknown member {k!r} in {what}")
    if required is not None:
        for k in required:
            if k not in obj:
                raise ClaimError(f"malformed record: {what} lacks {k!r}")


def record_validate(doc) -> None:
    """Refuse, with a reason, anything that is not a well-formed record."""
    if not isinstance(doc, dict):
        raise ClaimError("malformed record: not a JSON object")
    version = doc.get("record")
    if "record" not in doc:
        raise ClaimError("malformed record: missing member 'record'")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ClaimError("malformed record: record version is not an integer")
    if version > max(_RECORD_VERSIONS):
        raise ClaimError(f"record version {version} is newer than this reader "
                         f"understands (up to {max(_RECORD_VERSIONS)})")
    if version < min(_RECORD_VERSIONS):
        raise ClaimError(f"unknown record version {version}")
    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        allowed.add("claim")
        required.add("claim")
    _check_closed(doc, allowed, "record", required)

    if not isinstance(doc["name"], str):
        raise ClaimError("malformed record: name is not a string")
    _check_hex(doc, "root")
    _check_hex(doc, "build_digest")
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.match(doc["when"]):
        raise ClaimError("malformed record: when is not YYYY-MM-DDTHH:MM:SSZ")
    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("malformed record: tool is not a string")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise ClaimError("malformed record: gates is not an array")
    for g in gates:
        _check_closed(g, _RECORD_GATE, "gate", _RECORD_GATE)
        if not isinstance(g["output"], str):
            raise ClaimError("malformed record: gate output is not a string")
        if not isinstance(g["status"], str) or g["status"] not in _RECORD_STATUSES:
            raise ClaimError(f"malformed record: bad gate status {g['status']!r}")
        if (not isinstance(g["sandbox"], str)
                or g["sandbox"] not in _RECORD_SANDBOXES):
            raise ClaimError(f"malformed record: bad gate sandbox {g['sandbox']!r}")

    env = doc["environment"]
    _check_closed(env, _RECORD_ENVIRONMENT, "environment", _RECORD_ENVIRONMENT)
    for k, v in env.items():
        if not isinstance(v, str):
            raise ClaimError(f"malformed record: environment {k} is not a string")

    if "cost" in doc:
        cost = doc["cost"]
        _check_closed(cost, _RECORD_COST, "cost")
        for k, v in cost.items():
            if not _is_number(v) or not _finite(v) or v < 0:
                raise ClaimError(f"malformed record: cost {k} must be a "
                                 "finite non-negative number")

    if "producer" in doc:
        prod = doc["producer"]
        _check_closed(prod, _RECORD_PRODUCER, "producer")
        for k, v in prod.items():
            if k == "blind":
                if not isinstance(v, bool):
                    raise ClaimError("malformed record: producer blind is "
                                     "not a boolean")
            elif not isinstance(v, str):
                raise ClaimError(f"malformed record: producer {k} is not a string")
            elif k == "cutoff" and not _RECORD_CUTOFF.match(v):
                raise ClaimError("malformed record: producer cutoff is not "
                                 "YYYY-MM")

    if "claim" in doc:
        claim = doc["claim"]
        _check_closed(claim, _RECORD_CLAIM, "claim")
        for k in ("tolerance", "mutation_floor"):
            if k in claim:
                v = claim[k]
                if not _is_number(v) or not _finite(v) or v < 0:
                    raise ClaimError(f"malformed record: claim {k} must be a "
                                     "finite non-negative number")
        if "envelope" in claim:
            env = claim["envelope"]
            if not isinstance(env, dict) or not env:
                raise ClaimError("malformed record: claim envelope must be a "
                                 "non-empty object")
            for unit, v in env.items():
                if not isinstance(unit, str) or unit not in core.COST_UNITS:
                    raise ClaimError(f"malformed record: unknown envelope "
                                     f"unit {unit!r}")
                if not _is_number(v) or not _finite(v) or v <= 0:
                    raise ClaimError(f"malformed record: envelope {unit} must "
                                     "be a positive number")


def record_canonical(doc) -> bytes:
    """The canonical bytes of a valid record (refuses anything else)."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """Lowercase hex sha256 of the canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a record file; it must be valid and hold its own canonical bytes."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record: {e}")
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise ClaimError(f"cannot read record: {e}")
    canon = record_canonical(doc)
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw != canon:
        raise ClaimError("record does not hold its own canonical bytes")
    return doc


def record_signer(path: str, anchor: str):
    """Principal whose detached signature (`<path>.sig`, namespace
    reticuli.record) over the record's canonical bytes verifies against the
    verifier's `anchor` (an ssh allowed_signers file); else a refusal."""
    doc = record_read(path)
    canon = record_canonical(doc)
    if not isinstance(anchor, str) or not os.path.isfile(anchor):
        raise ClaimError("no trust anchor: allowed_signers file not found")
    sigpath = path + ".sig"
    if not os.path.isfile(sigpath):
        raise ClaimError("record is unsigned: no signature file")
    try:
        with open(anchor, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ClaimError(f"cannot read trust anchor: {e}")
    principals = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for p in line.split()[0].split(","):
            p = p.strip('"')
            if p and p not in principals:
                principals.append(p)
    tmp = tempfile.mkdtemp(prefix="reticuli-record-")
    try:
        for who in principals:
            try:
                done = subprocess.run(
                    ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", who,
                     "-n", core.RECORD_NAMESPACE, "-s", sigpath],
                    input=canon, capture_output=True, timeout=60, check=False)
            except (OSError, subprocess.SubprocessError):
                break
            if done.returncode == 0:
                return who
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    raise ClaimError("record signature does not verify against the anchor")

"""Kernel attest: the record -- the one file other programs may parse.

spec/record.md owns the format; this is its reader. Validation is a
PRECONDITION of the format, not a service of one function: every entry point
that consumes a document refuses what a reader refuses, canonicalizing and
digesting included, because a digest is how a record is cited.
"""
import os
import re
import subprocess

from .core import (COST_UNITS, ClaimError, RECORD_FORMAT, RECORD_NAMESPACE,
                   _canonical, _finite, _is_number, _sha256_hex)

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

#: The closed member set, version 1. Version 2 adds `claim`.
_RECORD_MEMBERS = frozenset({"record", "name", "root", "build_digest",
                             "gates", "cost", "producer", "environment",
                             "when", "tool"})
_RECORD_REQUIRED = frozenset({"record", "name", "root", "build_digest",
                              "gates", "environment", "when"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch",
                              "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_OBLIGATIONS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _refuse(why: str):
    raise ClaimError(f"not a record: {why}")


def _check_cost(table) -> None:
    if not isinstance(table, dict):
        _refuse("cost must be an object")
    for unit, value in table.items():
        if unit not in COST_UNITS:
            _refuse(f"cost names an unknown unit {unit!r}")
        if not _is_number(value):
            _refuse(f"cost {unit} is not a number")
        if not _finite(value):
            _refuse(f"cost {unit} is not finite; a cost measures work done")
        if value < 0:
            _refuse(f"cost {unit} is negative")


def _check_obligations(table) -> None:
    if not isinstance(table, dict):
        _refuse("claim must be an object")
    for key, value in table.items():
        if key not in _RECORD_OBLIGATIONS:
            _refuse(f"claim names an unknown obligation {key!r}")
        if key in ("tolerance", "mutation_floor"):
            if not _is_number(value) or not _finite(value) or value < 0:
                _refuse(f"claim {key} must be a non-negative number")
        else:
            if not isinstance(value, dict) or not value:
                _refuse("claim envelope must be a non-empty object")
            for unit, ceiling in value.items():
                if unit not in COST_UNITS:
                    _refuse(f"claim envelope names an unknown unit {unit!r}")
                if not _is_number(ceiling) or not _finite(ceiling) \
                        or ceiling <= 0:
                    _refuse(f"claim envelope {unit} must be positive")


def record_validate(document) -> dict:
    """Refuse, in band and with a reason, anything this format does not admit."""
    if not isinstance(document, dict):
        _refuse("the document is not a JSON object")
    version = document.get("record")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        _refuse("the `record` member must be a positive integer version")
    if version > RECORD_FORMAT:
        _refuse(f"record version {version} is newer than this reader "
                f"understands (version {RECORD_FORMAT})")
    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        allowed.add("claim")
        required.add("claim")
    unknown = set(document) - allowed
    if unknown:
        _refuse(f"version {version} does not name {sorted(unknown)}")
    absent = required - set(document)
    if absent:
        _refuse(f"missing required member(s) {sorted(absent)}")

    if not isinstance(document.get("name"), str):
        _refuse("name must be a string")
    for field in ("root", "build_digest"):
        value = document.get(field)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            _refuse(f"{field} must be 64 lowercase hex characters")
    gates = document.get("gates")
    if not isinstance(gates, list):
        _refuse("gates must be an array")
    for entry in gates:
        if not isinstance(entry, dict):
            _refuse("a gate entry must be an object")
        extra = set(entry) - _RECORD_GATE
        if extra:
            _refuse(f"a gate entry does not name {sorted(extra)}")
        if set(entry) != _RECORD_GATE:
            _refuse(f"a gate entry needs {sorted(_RECORD_GATE)}")
        if not isinstance(entry["output"], str):
            _refuse("a gate's output must be a string")
        if entry["status"] not in _RECORD_STATUSES:
            _refuse(f"unknown gate status {entry['status']!r}")
        if entry["sandbox"] not in _RECORD_SANDBOXES:
            _refuse(f"unknown sandbox {entry['sandbox']!r}")
    environment = document.get("environment")
    if not isinstance(environment, dict) \
            or set(environment) != _RECORD_ENVIRONMENT:
        _refuse(f"environment must name exactly "
                f"{sorted(_RECORD_ENVIRONMENT)}")
    for value in environment.values():
        if not isinstance(value, str):
            _refuse("environment values must be strings")
    if not isinstance(document.get("when"), str) \
            or not _RECORD_WHEN.match(document["when"]):
        _refuse("when must be YYYY-MM-DDTHH:MM:SSZ")
    if "tool" in document and not isinstance(document["tool"], str):
        _refuse("tool must be a string")
    if "cost" in document:
        _check_cost(document["cost"])
    if "producer" in document:
        producer = document["producer"]
        if not isinstance(producer, dict):
            _refuse("producer must be an object")
        extra = set(producer) - _RECORD_PRODUCER
        if extra:
            _refuse(f"producer does not name {sorted(extra)}")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            _refuse("producer.blind must be a boolean")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                _refuse(f"producer.{key} must be a string")
    if "claim" in document:
        _check_obligations(document["claim"])
    return document


def record_canonical(document) -> bytes:
    """The canonical bytes: the identity serialization, numbers verbatim."""
    record_validate(document)
    return _canonical(document)


def record_digest(document) -> str:
    """How a record is cited: sha256 over its canonical bytes."""
    return _sha256_hex(record_canonical(document))


def record_read(path: str) -> dict:
    """Read a record file. The file IS its canonical bytes, or it is not one."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ClaimError(f"no record at {path}: {exc}") from exc
    import json
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ClaimError(f"damaged record at {path}: {exc}") from exc
    record_validate(document)
    if raw != _canonical(document):
        raise ClaimError(
            f"the file at {path} does not hold its own canonical bytes; "
            f"a record is its canonical form or it is not a record")
    return document


def _principals(signers: str) -> list:
    names = []
    try:
        with open(signers, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                first = line.split()[0]
                for principal in first.split(","):
                    if principal and principal not in names:
                        names.append(principal)
    except OSError:
        return []
    return names


def _ssh_verify(path: str, signature: str, signers: str, namespace: str,
                identity: str) -> bool:
    if not shutil_which("ssh-keygen"):
        return False
    try:
        with open(path, "rb") as handle:
            payload = handle.read()
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", signers, "-I", identity,
             "-n", namespace, "-s", signature],
            input=payload, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def shutil_which(name: str):
    import shutil
    return shutil.which(name)


def record_signer(path: str, anchor: str | None = None) -> str | None:
    """Who signed this record, relative to the verifier's own anchor."""
    signature = path + ".sig"
    if not anchor or not os.path.isfile(anchor) \
            or not os.path.isfile(signature):
        return None
    for identity in _principals(anchor):
        if _ssh_verify(path, signature, anchor, RECORD_NAMESPACE, identity):
            return identity
    return None

"""The record reader: a signed statement of one machine's results.

A record is the one file this project promises other programs may parse
(spec/record.md). This module reads, validates, and digests records; it does
not author them -- emitting and signing belongs to the exchange layer.

The canonical bytes of a record are the same serialization the identity uses
(spec/identity.md): sorted keys, default separators, non-ASCII escaped,
encoded UTF-8. The record digest is the sha256 hex of those bytes.

Stdlib only, never the network.
"""
import hashlib
import json
import re
import subprocess

from . import core

_RECORD_FORMAT = 1
_RECORD_NAMESPACE = "reticuli.record"

_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates",
    "cost", "producer", "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def record_validate(doc) -> None:
    """Refuse, in band, any document this spec does not accept as a record."""
    if not isinstance(doc, dict):
        raise core.ClaimError("a record must be a JSON object")

    keys = set(doc.keys())
    unknown = keys - _RECORD_MEMBERS
    if unknown:
        raise core.ClaimError(f"record has unknown member(s): {sorted(unknown)}")
    missing = _RECORD_REQUIRED - keys
    if missing:
        raise core.ClaimError(f"record is missing required member(s): {sorted(missing)}")

    version = doc["record"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise core.ClaimError("record version must be an integer")
    if version != _RECORD_FORMAT:
        raise core.ClaimError(
            f"record format {version} is newer than this reader understands "
            f"(format {_RECORD_FORMAT})"
        )

    if not isinstance(doc["name"], str):
        raise core.ClaimError("record name must be a string")

    for key in ("root", "build_digest"):
        value = doc[key]
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise core.ClaimError(f"record {key} must be 64 lowercase hex characters")

    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise core.ClaimError("record when must be YYYY-MM-DDTHH:MM:SSZ")

    environment = doc["environment"]
    if not isinstance(environment, dict) or set(environment.keys()) != _RECORD_ENVIRONMENT:
        raise core.ClaimError("record environment must have exactly platform, machine, runtime")
    for value in environment.values():
        if not isinstance(value, str):
            raise core.ClaimError("record environment values must be strings")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("record gates must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate.keys()) != _RECORD_GATE:
            raise core.ClaimError("each gate entry must have exactly output, status, sandbox")
        if not isinstance(gate["output"], str):
            raise core.ClaimError("gate output must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"gate status must be one of {sorted(_RECORD_STATUSES)}")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise core.ClaimError("record cost must be an object")
        unknown_cost = set(cost.keys()) - _RECORD_COST
        if unknown_cost:
            raise core.ClaimError(f"record cost has unknown key(s): {sorted(unknown_cost)}")
        for value in cost.values():
            if not _is_number(value) or value < 0:
                raise core.ClaimError("record cost values must be non-negative numbers")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            raise core.ClaimError("record producer must be an object")
        unknown_producer = set(producer.keys()) - _RECORD_PRODUCER
        if unknown_producer:
            raise core.ClaimError(f"record producer has unknown key(s): {sorted(unknown_producer)}")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"record producer {key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise core.ClaimError("record producer blind must be a boolean")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise core.ClaimError("record tool must be a string")


def record_canonical(doc) -> bytes:
    """The canonical bytes: sorted keys, default separators, ASCII-escaped."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: sha256 hex of the canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read a record file, refusing malformed bytes or an invalid document."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise core.ClaimError(f"malformed record at {path!r}: {e}") from e
    record_validate(doc)
    return doc


def _principals(anchor: str) -> list:
    """The principal names named in an ssh allowed_signers file."""
    names = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first_field = line.split(None, 1)[0]
            names.extend(p for p in first_field.split(",") if p)
    return names


def record_signer(path: str, anchor: str) -> str:
    """Verify a record's detached ssh signature against an anchor file.

    Returns the identity (principal) whose key in `anchor` verifies the
    signature at `path + ".sig"` over the record's canonical bytes, in the
    `reticuli.record` namespace (spec/record.md). Refuses if no principal
    verifies.
    """
    doc = record_read(path)
    canon = record_canonical(doc)
    sig_path = path + ".sig"

    try:
        principals = _principals(anchor)
    except OSError as e:
        raise core.ClaimError(f"cannot read signer anchor {anchor!r}: {e}") from e

    for principal in principals:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify",
             "-f", anchor, "-I", principal, "-n", _RECORD_NAMESPACE,
             "-s", sig_path],
            input=canon, capture_output=True, check=False,
        )
        if done.returncode == 0:
            return principal

    raise core.ClaimError(
        f"no signer in {anchor!r} verifies the signature at {sig_path!r}"
    )

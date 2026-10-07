"""The record reader: a signed statement of one machine's results (`spec/record.md`).

A record's canonical bytes are the identity serialization verbatim --
`json.dumps(doc, sort_keys=True)`, default separators, non-ASCII escaped,
encoded UTF-8 -- so a record travels between kernels byte-identical and its
digest (the sha256 of those bytes) is what a signature covers. The member
set is closed per version: this kernel reads record version 1 (`RECORD_FORMAT`),
and refuses anything newer, anything malformed, or anything carrying a member
this version does not name, in band and with a reason.

`record_read` loads and validates a record file; `record_signer` verifies its
detached ssh signature against an allowed-signers anchor and returns the
signer's identity. The kernel owns the format; authoring a record --
emitting, writing, signing one -- belongs to the layer above.

Stdlib only, never the network.
"""
import hashlib
import json
import os
import re
import subprocess

from . import core

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "cost", "producer",
    "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})


def record_canonical(doc) -> bytes:
    """The record's canonical bytes: the identity serialization verbatim."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: sha256 hex of its canonical bytes -- what a
    signature covers and how a record is cited."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def _refuse_number(value, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise core.ClaimError(f"refused: {label} must be a non-negative number")


def record_validate(doc) -> None:
    """Refuse, in band and with a reason, any record this version does not
    accept (`spec/record.md`): not an object, an unknown member, a missing
    required member, a version this kernel does not understand, or a value
    outside its vocabulary.
    """
    if not isinstance(doc, dict):
        raise core.ClaimError("refused: a record must be a JSON object")

    unknown = set(doc) - _RECORD_MEMBERS
    if unknown:
        raise core.ClaimError(f"refused: unknown record member(s): {sorted(unknown)}")
    missing = _RECORD_REQUIRED - set(doc)
    if missing:
        raise core.ClaimError(f"refused: record missing required member(s): {sorted(missing)}")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool):
        raise core.ClaimError("refused: record 'record' (version) must be an integer")
    if version != RECORD_FORMAT:
        raise core.ClaimError(
            f"refused: record version {version} is newer than this kernel "
            f"understands (version {RECORD_FORMAT})"
        )

    if not isinstance(doc.get("name"), str):
        raise core.ClaimError("refused: record 'name' must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise core.ClaimError(
                f"refused: record {key!r} must be 64 lowercase hex characters"
            )

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise core.ClaimError("refused: record 'when' must be UTC YYYY-MM-DDTHH:MM:SSZ")

    environment = doc.get("environment")
    if (not isinstance(environment, dict)
            or set(environment) != _RECORD_ENVIRONMENT
            or not all(isinstance(v, str) for v in environment.values())):
        raise core.ClaimError(
            "refused: record 'environment' must hold platform/machine/runtime strings"
        )

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise core.ClaimError("refused: record 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise core.ClaimError(f"refused: malformed gate entry: {gate!r}")
        if not isinstance(gate.get("output"), str):
            raise core.ClaimError("refused: a gate's 'output' must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise core.ClaimError(f"refused: unknown gate status: {gate.get('status')!r}")
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"refused: unknown gate sandbox: {gate.get('sandbox')!r}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not set(cost) <= set(core.COST_KEYS):
            raise core.ClaimError("refused: record 'cost' carries an unknown key")
        for key, value in cost.items():
            _refuse_number(value, f"record 'cost.{key}'")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or not set(producer) <= _RECORD_PRODUCER:
            raise core.ClaimError("refused: record 'producer' carries an unknown key")
        if "vendor" in producer and not isinstance(producer["vendor"], str):
            raise core.ClaimError("refused: producer 'vendor' must be a string")
        if "model" in producer and not isinstance(producer["model"], str):
            raise core.ClaimError("refused: producer 'model' must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise core.ClaimError("refused: producer 'blind' must be a boolean")
        if "cutoff" in producer and not isinstance(producer["cutoff"], str):
            raise core.ClaimError("refused: producer 'cutoff' must be a string")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise core.ClaimError("refused: record 'tool' must be a string")


def record_read(path: str) -> dict:
    """Read and validate a record file; refused, never crashed, when
    missing or malformed."""
    if not os.path.isfile(path):
        raise core.ClaimError(f"refused: no record at {path!r}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise core.ClaimError(f"refused: malformed record {path!r}: {e}") from e
    record_validate(doc)
    return doc


def _allowed_identity(anchor: str) -> str:
    """The first signer identity named in an ssh allowed-signers file."""
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                return line.split()[0]
    raise core.ClaimError(f"refused: no signer identity in {anchor!r}")


def record_signer(path: str, anchor: str) -> str:
    """Verify a record's detached ssh signature against an allowed-signers
    anchor and return the signer's identity (`spec/record.md`: signed over
    the record's canonical bytes, in the `reticuli.record` namespace,
    distinct from `reticuli` and `reticuli.mint` so one signature cannot be
    presented for another purpose).
    """
    doc = record_read(path)
    canon = record_canonical(doc)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        raise core.ClaimError(f"refused: no signature at {sig_path!r}")
    if not os.path.isfile(anchor):
        raise core.ClaimError(f"refused: no allowed-signers file at {anchor!r}")
    identity = _allowed_identity(anchor)
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", identity,
             "-n", RECORD_NAMESPACE, "-s", sig_path],
            input=canon, capture_output=True, timeout=10,
        )
    except OSError as e:
        raise core.ClaimError(f"refused: ssh-keygen unavailable: {e}") from e
    if done.returncode != 0:
        raise core.ClaimError(f"refused: signature at {sig_path!r} does not verify")
    return identity

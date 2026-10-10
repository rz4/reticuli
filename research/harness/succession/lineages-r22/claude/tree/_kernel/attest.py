"""The record reader: a signed statement of one machine's results (spec/record.md).

A record is a small JSON document whose canonical bytes are the identity
serialization verbatim (spec/identity.md): sorted keys, default separators,
non-ASCII escaped, encoded UTF-8. `record_canonical`/`record_digest` compute
those bytes and their sha256; `record_validate` refuses, in band and with a
reason, anything the spec does not allow at the document's own declared
version -- the member set is closed per version, and version 2 adds exactly
one member (`claim`), required there and refused at version 1. `record_read`
parses one document off disk, refusing malformed bytes rather than crashing.
`record_signer` is the ssh verification half: which principal, among an
`allowed_signers` file's own listed names, can be shown to have produced the
detached signature beside the record, in the record's own signature
namespace -- trust is verifier-relative, so a record proves nothing against
an anchor that does not name its signer.
"""
import hashlib
import json
import os
import re

from . import build as build_module
from . import core
from .core import ClaimError

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1
_RECORD_FORMAT_MAX = 2

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_RECORD_CUTOFF = re.compile(r"^\d{4}-\d{2}$")

# The member set is closed per version -- no other member may be present,
# and every one named here must be the stated type and vocabulary
# (spec/record.md). Version 2 adds `claim`, folded in by `record_validate`.
_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates",
    "cost", "producer", "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})


def record_canonical(doc) -> bytes:
    """The record's canonical bytes: `json.dumps(doc, sort_keys=True)` at
    its defaults -- ASCII-escaped, default separators -- encoded UTF-8.
    The same rule the identity root uses (spec/identity.md), applied here
    to a record document rather than the root's `parts` map."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: sha256 hex of the canonical bytes -- what a
    signature covers and how a record is cited."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def _closed(obj: dict, allowed: frozenset, required: frozenset, where: str) -> None:
    """Refuse `obj` unless its keys are exactly `allowed`, minus `required`
    that must all be present -- the shared shape of every closed member set
    this document uses, at every nesting level."""
    unknown = set(obj) - allowed
    if unknown:
        raise ClaimError(f"record: {where} carries unknown member(s): {sorted(unknown)}")
    missing = required - set(obj)
    if missing:
        raise ClaimError(f"record: {where} is missing member(s): {sorted(missing)}")


def _validate_environment(env) -> None:
    if not isinstance(env, dict):
        raise ClaimError("record: 'environment' must be an object")
    _closed(env, _RECORD_ENVIRONMENT, _RECORD_ENVIRONMENT, "'environment'")
    for key in _RECORD_ENVIRONMENT:
        if not isinstance(env[key], str) or not env[key]:
            raise ClaimError(f"record: 'environment.{key}' must be a non-empty string")


def _validate_gates(gates) -> None:
    if not isinstance(gates, list):
        raise ClaimError("record: 'gates' must be an array")
    for entry in gates:
        if not isinstance(entry, dict):
            raise ClaimError("record: each entry of 'gates' must be an object")
        _closed(entry, _RECORD_GATE, _RECORD_GATE, "a 'gates' entry")
        if not isinstance(entry["output"], str) or not entry["output"]:
            raise ClaimError("record: a gate's 'output' must be a non-empty string")
        if entry["status"] not in _RECORD_STATUSES:
            raise ClaimError(f"record: a gate 'status' must be one of {sorted(_RECORD_STATUSES)}")
        if entry["sandbox"] not in _RECORD_SANDBOXES:
            raise ClaimError(f"record: a gate 'sandbox' must be one of {sorted(_RECORD_SANDBOXES)}")


def _validate_cost(cost) -> None:
    if not isinstance(cost, dict):
        raise ClaimError("record: 'cost' must be an object")
    unknown = set(cost) - set(core.COST_KEYS)
    if unknown:
        raise ClaimError(f"record: 'cost' carries unknown key(s): {sorted(unknown)}")
    for key, value in cost.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ClaimError(f"record: 'cost.{key}' must be a non-negative number")


def _validate_producer(producer) -> None:
    if not isinstance(producer, dict):
        raise ClaimError("record: 'producer' must be an object")
    unknown = set(producer) - _RECORD_PRODUCER
    if unknown:
        raise ClaimError(f"record: 'producer' carries unknown member(s): {sorted(unknown)}")
    for key in ("vendor", "model", "cutoff"):
        if key in producer and not isinstance(producer[key], str):
            raise ClaimError(f"record: 'producer.{key}' must be a string")
    if "cutoff" in producer and not _RECORD_CUTOFF.match(producer["cutoff"]):
        raise ClaimError("record: 'producer.cutoff' must be 'YYYY-MM'")
    if "blind" in producer and not isinstance(producer["blind"], bool):
        raise ClaimError("record: 'producer.blind' must be a boolean")


def _validate_claim_obligations(claim) -> None:
    if not isinstance(claim, dict):
        raise ClaimError("record: 'claim' must be an object")
    unknown = set(claim) - _RECORD_CLAIM
    if unknown:
        raise ClaimError(f"record: 'claim' carries unknown key(s): {sorted(unknown)}")
    for key in ("tolerance", "mutation_floor"):
        if key in claim:
            value = claim[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError(f"record: 'claim.{key}' must be a non-negative number")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("record: 'claim.envelope' must be a non-empty object")
        unknown_units = set(envelope) - set(core.COST_UNITS)
        if unknown_units:
            raise ClaimError(f"record: 'claim.envelope' carries unknown unit(s): {sorted(unknown_units)}")
        for unit, value in envelope.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ClaimError(f"record: 'claim.envelope.{unit}' must be a positive number")


def record_validate(doc) -> None:
    """Refuse, in band and with a reason, anything spec/record.md does not
    allow at the document's own declared version. The member set is closed
    per version: version 1 must not carry `claim`; version 2 requires it.
    A record newer than this reader understands is named, not guessed at."""
    if not isinstance(doc, dict):
        raise ClaimError(f"a record must be a JSON object, got {doc!r:.60}")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ClaimError("record: 'record' (the format version) must be an integer")
    if version < 1:
        raise ClaimError(f"record: unknown format version {version}")
    if version > _RECORD_FORMAT_MAX:
        raise ClaimError(
            f"record format {version} is newer than this kernel understands "
            f"(up to {_RECORD_FORMAT_MAX}); upgrade reticuli to read it"
        )

    members = _RECORD_MEMBERS | {"claim"} if version >= 2 else _RECORD_MEMBERS
    required = _RECORD_REQUIRED | {"claim"} if version >= 2 else _RECORD_REQUIRED
    _closed(doc, members, required, "a record")

    if not isinstance(doc["name"], str) or not doc["name"]:
        raise ClaimError("record: 'name' must be a non-empty string")
    for key in ("root", "build_digest"):
        value = doc[key]
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise ClaimError(f"record: {key!r} must be 64 lowercase hex characters")
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.match(doc["when"]):
        raise ClaimError("record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    _validate_environment(doc["environment"])
    _validate_gates(doc["gates"])
    if "cost" in doc:
        _validate_cost(doc["cost"])
    if "producer" in doc:
        _validate_producer(doc["producer"])
    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record: 'tool' must be a string")
    if "claim" in doc:
        _validate_claim_obligations(doc["claim"])


def record_read(path: str) -> dict:
    """Read and validate a record off disk -- refuses malformed bytes with
    a reason, the same discipline `seal.read_manifest` applies to the
    manifest."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError) as exc:
        raise ClaimError(f"malformed record {path!r}: {exc}") from exc
    record_validate(doc)
    return doc


def _signers(anchor: str) -> list:
    """Every principal name an ssh `allowed_signers` file lists, in file
    order with duplicates dropped."""
    if not os.path.isfile(anchor):
        return []
    names = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            who = line.split(None, 1)[0]
            names.extend(who.split(","))
    seen = set()
    ordered = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def record_signer(path: str, anchor: str):
    """Which principal, among `anchor`'s (an ssh `allowed_signers` file)
    listed names, signed the record at `path` -- verified over the
    record's own canonical bytes, in its own namespace (`RECORD_NAMESPACE`),
    reading the detached signature from `path + ".sig"` (ssh-keygen's own
    default signature filename). `None` if no listed signer's signature
    verifies, including when there is no signature file at all: trust is
    verifier-relative, so a record proves nothing against an anchor that
    does not name its signer (spec/record.md)."""
    doc = record_read(path)
    canon = record_canonical(doc)
    signature_path = path + ".sig"
    if not os.path.isfile(signature_path):
        return None
    for principal in _signers(anchor):
        if build_module._ssh_verify(canon, signature_path, anchor, RECORD_NAMESPACE, principal):
            return principal
    return None

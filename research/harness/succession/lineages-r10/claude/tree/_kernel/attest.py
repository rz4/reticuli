"""The record: a signed statement of one machine's results (`spec/record.md`).

A record is a small JSON document -- exactly the members this module names,
no others -- stating what one machine established about one claim: its
root, its generated-bytes digest, its gate verdicts, the host that recorded
it, and when. Its canonical bytes are the same serialization the identity
uses (`json.dumps(doc, sort_keys=True)`, default separators, ASCII-escaped,
encoded UTF-8); its digest is the sha256 of those bytes, and that digest is
what a detached ssh signature (`ssh-keygen -Y`, namespace `reticuli.record`)
covers. This module implements record format 1 (`RECORD_FORMAT`); a version
this kernel does not understand is refused in words, not silently accepted.

Stdlib only.
"""
import hashlib
import json
import os
import re

from .core import ClaimError
from .build import _ssh_verify

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_MEMBERS = _RECORD_REQUIRED | frozenset({"cost", "producer", "tool"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def record_canonical(doc) -> bytes:
    """The canonical bytes of a record: sorted-key JSON, default
    separators, non-ASCII escaped, encoded UTF-8 -- the identity
    serialization verbatim."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: sha256 hex of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_validate(doc) -> None:
    """Refuse, as a `ClaimError`, anything that is not a well-formed
    record: not a JSON object, an unknown or missing member, a version
    this kernel does not understand, or a value outside its vocabulary.
    The member set is closed -- extension is a version bump."""
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    extra = set(doc) - _RECORD_MEMBERS
    if extra:
        raise ClaimError(f"a record's member set is closed: unknown member(s) {sorted(extra)}")
    missing = _RECORD_REQUIRED - set(doc)
    if missing:
        raise ClaimError(f"a record is missing required member(s) {sorted(missing)}")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ClaimError("a record's record (version) must be an integer")
    if version != RECORD_FORMAT:
        raise ClaimError(
            f"record version {version} is newer than this kernel understands "
            f"(version {RECORD_FORMAT}); upgrade reticuli to read it"
        )

    if not isinstance(doc.get("name"), str):
        raise ClaimError("a record's name must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise ClaimError(f"a record's {key} must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("a record's when must be YYYY-MM-DDTHH:MM:SSZ")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError("a record's environment must carry exactly platform/machine/runtime")
    for value in environment.values():
        if not isinstance(value, str):
            raise ClaimError("a record's environment values must be strings")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("a record's gates must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise ClaimError("a record's gate entry must carry exactly output/status/sandbox")
        if not isinstance(gate.get("output"), str):
            raise ClaimError("a record's gate output must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise ClaimError(f"a record's gate status must be one of {sorted(_RECORD_STATUSES)}")
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise ClaimError(f"a record's gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not set(cost) <= _RECORD_COST:
            raise ClaimError("a record's cost must hold only usd/tokens/calls/seconds")
        for value in cost.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError("a record's cost values must be non-negative numbers")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or not set(producer) <= _RECORD_PRODUCER:
            raise ClaimError("a record's producer must hold only vendor/model/blind/cutoff")
        for key, value in producer.items():
            if key == "blind":
                if not isinstance(value, bool):
                    raise ClaimError("a record's producer.blind must be a boolean")
            elif not isinstance(value, str):
                raise ClaimError(f"a record's producer.{key} must be a string")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("a record's tool must be a string")


def record_read(path: str) -> dict:
    """Read and validate a record document from `path`; refuses malformed
    bytes or a malformed document as a `ClaimError`, never a raw crash."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClaimError(f"no readable record at {path!r}: {exc}") from exc
    record_validate(doc)
    return doc


def _allowed_identities(anchor: str) -> list:
    """Identities named in an ssh `allowed_signers` file, first field of
    each non-blank, non-comment line, in file order with duplicates
    dropped."""
    try:
        with open(anchor, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        raise ClaimError(f"no readable allowed_signers at {anchor!r}: {exc}") from exc
    identities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        identity = line.split()[0]
        if identity not in identities:
            identities.append(identity)
    return identities


def record_signer(path: str, anchor: str):
    """Verify a record's detached ssh signature (expected alongside it at
    `path + ".sig"`) against every identity named in `anchor` (an ssh
    `allowed_signers` file), in the `reticuli.record` namespace. Returns
    the identity that verifies, or `None` if no anchored identity signs
    it. Refuses, as a `ClaimError`, an unreadable record, an unreadable
    anchor, or a record with no signature file to check."""
    doc = record_read(path)
    data = record_canonical(doc)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        raise ClaimError(f"no detached signature at {sig_path!r}")
    for identity in _allowed_identities(anchor):
        if _ssh_verify(anchor, identity, RECORD_NAMESPACE, data, sig_path):
            return identity
    return None

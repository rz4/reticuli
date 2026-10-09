"""The record reader: a signed statement of one machine's results (`spec/record.md`).

A record is a small, closed-member JSON document. Its canonical bytes are
the identity serialization verbatim (sorted keys, default separators,
non-ASCII escaped) -- the same rule `identity.py` hashes recipes with --
so a record travels between kernels and its digest (`record_digest`) is
the sha256 of exactly those bytes. `record_validate` refuses, in band,
any document that is not this format's closed shape: wrong type, an
unknown or missing member, a version this kernel does not understand (only
format 1 -- no `claim` member), a `root`/`build_digest` that is not 64
lowercase hex, a `when` outside its timestamp shape, or a value outside one
of the closed vocabularies (`gates[].status`, `gates[].sandbox`, `cost`'s
keys, `producer`'s keys). `record_read` parses a file through the same
refusal, never a raw crash. `record_signer` verifies a record's detached
`ssh-keygen -Y` signature, in the `reticuli.record` namespace, against
every principal an `allowed_signers` anchor names, reusing the generic
verifier `build._ssh_verify` already builds on this primitive for --
returning the signer identity that verifies, or refusing if none does.
"""
import hashlib
import json
import re

from .build import _ssh_verify
from .core import ClaimError, COST_KEYS

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_ENVIRONMENT = frozenset({'platform', 'runtime', 'machine'})
_RECORD_GATE = frozenset({'status', 'sandbox', 'output'})
_RECORD_MEMBERS = frozenset({'when', 'cost', 'gates', 'producer', 'environment', 'name', 'root', 'record', 'build_digest', 'tool'})
_RECORD_PRODUCER = frozenset({'blind', 'model', 'cutoff', 'vendor'})
_RECORD_REQUIRED = frozenset({'build_digest', 'when', 'environment', 'record', 'name', 'root', 'gates'})
_RECORD_SANDBOXES = frozenset({'none', 'seatbelt', 'inherited', 'bubblewrap'})
_RECORD_STATUSES = frozenset({'timeout', 'ok', 'environment', 'failed', 'mismatch'})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def record_canonical(doc: dict) -> bytes:
    """The canonical bytes: sorted-key JSON, default separators, ASCII-escaped."""
    return json.dumps(doc, sort_keys=True, ensure_ascii=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The sha256 of the record's canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_validate(doc) -> None:
    """Refuse, in band, any document that is not a well-formed version-1 record."""
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    version = doc.get("record")
    if version != RECORD_FORMAT:
        raise ClaimError(
            f"record format {version!r} is newer than this kernel understands "
            f"(format {RECORD_FORMAT}); upgrade reticuli to read it"
        )

    members = set(doc)
    unknown = members - _RECORD_MEMBERS
    if unknown:
        raise ClaimError(f"refused unknown record member(s): {sorted(unknown)!r}")
    missing = _RECORD_REQUIRED - members
    if missing:
        raise ClaimError(f"record is missing required member(s): {sorted(missing)!r}")

    if not isinstance(doc.get("name"), str):
        raise ClaimError("record 'name' must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise ClaimError(f"record {key!r} must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError("record 'environment' needs exactly platform/machine/runtime")
    for key in _RECORD_ENVIRONMENT:
        if not isinstance(environment.get(key), str):
            raise ClaimError(f"record environment {key!r} must be a string")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("record 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise ClaimError(f"malformed gate entry: {gate!r:.60}")
        if not isinstance(gate.get("output"), str):
            raise ClaimError("gate 'output' must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise ClaimError(f"refused gate status: {gate.get('status')!r}")
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise ClaimError(f"refused gate sandbox: {gate.get('sandbox')!r}")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record 'tool' must be a string")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("record 'cost' must be an object")
        for key, value in cost.items():
            if key not in COST_KEYS:
                raise ClaimError(f"refused cost key: {key!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError(f"record cost {key!r} must be a non-negative number")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or set(producer) - _RECORD_PRODUCER:
            raise ClaimError("record 'producer' holds only vendor/model/blind/cutoff")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record producer 'blind' must be a boolean")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"record producer {key!r} must be a string")


def record_read(path: str) -> dict:
    """Parse and validate a record file; refusals, never a raw crash."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed record {path!r}: {e}") from e
    record_validate(doc)
    return doc


def _read_signers(anchor: str) -> list:
    """Every principal named in an `allowed_signers` file, in file order."""
    try:
        with open(anchor, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise ClaimError(f"cannot read allowed_signers {anchor!r}: {e}") from e
    identities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        principals, _, _ = line.partition(" ")
        for name in principals.split(","):
            name = name.strip()
            if name and name not in identities:
                identities.append(name)
    return identities


def record_signer(path: str, anchor: str):
    """The signer identity of `path`'s detached `reticuli.record` signature,
    verified against `anchor` (an `allowed_signers` file). Tries every
    principal the anchor names, since a signature alone carries no identity;
    refuses if none verifies.
    """
    doc = record_read(path)
    message = record_canonical(doc)
    sig_path = path + ".sig"
    try:
        with open(sig_path, "rb") as f:
            signature = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record signature {sig_path!r}: {e}") from e
    for identity in _read_signers(anchor):
        if _ssh_verify(anchor, identity, RECORD_NAMESPACE, message, signature):
            return identity
    raise ClaimError(f"record signature at {path!r} does not verify against {anchor!r}")

"""The record reader: a signed statement of one machine's results
(`spec/record.md`).

A record is a small, closed-schema JSON document. Its canonical bytes are
the same serialization the identity layer uses -- sorted keys, default
separators, non-ASCII escaped -- so a record travels between kernels and its
digest is the sha256 of those bytes. `record_validate` enforces the closed
member set, per version; `record_read` parses a file into a validated
document; `record_signer` checks a detached ssh signature over a record's
canonical bytes against a verifier-supplied anchor.

Authoring a record -- emitting, writing, signing -- belongs to the exchange
layer above this one; the kernel only owns the format and consumes records
as crosscheck legs.

Stdlib only.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from . import core
from .core import ClaimError

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_VERSIONS = (1, 2)

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
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_RECORD_HEX = re.compile(r"[0-9a-f]{64}")
_RECORD_WHEN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_hex64(v) -> bool:
    return isinstance(v, str) and _RECORD_HEX.fullmatch(v) is not None


def _check_environment(environment) -> None:
    if not isinstance(environment, dict):
        raise ClaimError("record 'environment' must be an object")
    if set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError(
            f"record 'environment' must have exactly {sorted(_RECORD_ENVIRONMENT)}"
        )
    for k, v in environment.items():
        if not isinstance(v, str):
            raise ClaimError(f"record environment.{k} must be a string")


def _check_gates(gates) -> None:
    if not isinstance(gates, list):
        raise ClaimError("record 'gates' must be a list")
    for entry in gates:
        if not isinstance(entry, dict) or set(entry) != _RECORD_GATE:
            raise ClaimError(f"each gate entry must have exactly {sorted(_RECORD_GATE)}")
        if not isinstance(entry["output"], str) or not entry["output"]:
            raise ClaimError("gate 'output' must be a non-empty string")
        if entry["status"] not in _RECORD_STATUSES:
            raise ClaimError(
                f"gate 'status' must be one of {sorted(_RECORD_STATUSES)}, "
                f"got {entry['status']!r}"
            )
        if entry["sandbox"] not in _RECORD_SANDBOXES:
            raise ClaimError(
                f"gate 'sandbox' must be one of {sorted(_RECORD_SANDBOXES)}, "
                f"got {entry['sandbox']!r}"
            )


def _check_cost(cost) -> None:
    if not isinstance(cost, dict):
        raise ClaimError("record 'cost' must be an object")
    unknown = set(cost) - set(core.COST_KEYS)
    if unknown:
        raise ClaimError(f"unknown cost key(s): {sorted(unknown)}")
    for k, v in cost.items():
        if not _is_number(v) or v < 0:
            raise ClaimError(f"record cost.{k} must be a non-negative number")


def _check_producer(producer) -> None:
    if not isinstance(producer, dict):
        raise ClaimError("record 'producer' must be an object")
    unknown = set(producer) - _RECORD_PRODUCER
    if unknown:
        raise ClaimError(f"unknown producer key(s): {sorted(unknown)}")
    for k in ("vendor", "model", "cutoff"):
        if k in producer and not isinstance(producer[k], str):
            raise ClaimError(f"producer.{k} must be a string")
    if "blind" in producer and not isinstance(producer["blind"], bool):
        raise ClaimError("producer.blind must be a boolean")


def _check_claim(claim) -> None:
    if not isinstance(claim, dict):
        raise ClaimError("record 'claim' must be an object")
    unknown = set(claim) - _RECORD_CLAIM
    if unknown:
        raise ClaimError(f"unknown claim key(s): {sorted(unknown)}")
    for k in ("tolerance", "mutation_floor"):
        if k in claim and (not _is_number(claim[k]) or claim[k] < 0):
            raise ClaimError(f"claim.{k} must be a non-negative number")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("claim.envelope must be a non-empty object")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"claim.envelope has an unknown unit {unit!r}")
            if not _is_number(ceiling) or ceiling <= 0:
                raise ClaimError(f"claim.envelope.{unit} must be a positive number")


def record_validate(doc) -> None:
    """Refuse, in band, any document that is not a well-formed record
    (`spec/record.md`). The member set is closed per version.
    """
    if not isinstance(doc, dict):
        raise ClaimError(f"a record must be a JSON object, got {type(doc).__name__}")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ClaimError("record 'record' (version) must be an integer")
    if version not in _RECORD_VERSIONS:
        raise ClaimError(
            f"record version {version} is newer than this reader understands "
            f"(supports {sorted(_RECORD_VERSIONS)})"
        )

    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        allowed.add("claim")
        required.add("claim")

    members = set(doc)
    unknown = members - allowed
    if unknown:
        raise ClaimError(f"unknown record member(s): {sorted(unknown)}")
    missing = required - members
    if missing:
        raise ClaimError(f"missing required record member(s): {sorted(missing)}")

    if not isinstance(doc["name"], str):
        raise ClaimError("record 'name' must be a string")
    if not _is_hex64(doc["root"]):
        raise ClaimError("record 'root' must be 64 lowercase hex characters")
    if not _is_hex64(doc["build_digest"]):
        raise ClaimError("record 'build_digest' must be 64 lowercase hex characters")
    if not isinstance(doc["when"], str) or not _RECORD_WHEN.fullmatch(doc["when"]):
        raise ClaimError("record 'when' must be UTC time as YYYY-MM-DDTHH:MM:SSZ")

    _check_environment(doc["environment"])
    _check_gates(doc["gates"])

    if "cost" in doc:
        _check_cost(doc["cost"])
    if "producer" in doc:
        _check_producer(doc["producer"])
    if "claim" in doc:
        _check_claim(doc["claim"])
    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record 'tool' must be a string")


def record_canonical(doc) -> bytes:
    """The canonical bytes of a record: the same serialization the identity
    layer uses (`spec/record.md`) -- sorted keys, default separators, ASCII
    escaping of non-ASCII, encoded UTF-8.
    """
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: the lowercase hex sha256 of its canonical bytes --
    what a signature covers and how a record is cited.
    """
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Parse and validate the record at `path`; refuses malformed bytes or
    a malformed document, with a reason, never a raw parse crash.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    record_validate(doc)
    return doc


def _allowed_identities(allowed_signers: str) -> list:
    """Every identity named in an ssh `AllowedSignersFile`."""
    identities = []
    with open(allowed_signers, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split(" ", 1)[0]
            identities.extend(head.split(","))
    return identities


def _ssh_verify(allowed_signers: str, identity_name: str, namespace: str,
                 signature_path: str, data: bytes) -> bool:
    """Verify a detached ssh signature over `data`: `ssh-keygen -Y verify`
    against `allowed_signers`, for `identity_name` in `namespace`
    (`spec/record.md`). `False` on any failure to verify -- never raises.
    """
    if not shutil.which("ssh-keygen"):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", identity_name, "-n", namespace, "-s", signature_path],
            input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def record_signer(path: str, anchor: str):
    """The identity that signed the record at `path`, verified against
    `anchor` (an ssh `AllowedSignersFile`), or `None` if no identity named
    in `anchor` verifies the detached signature alongside the record
    (`<path>.sig`). Trust is verifier-relative (`spec/verification.md`):
    meaningful only against a key the caller names.
    """
    sig_path = path + ".sig"
    if not anchor or not os.path.isfile(anchor) or not os.path.isfile(sig_path):
        return None
    doc = record_read(path)
    canonical = record_canonical(doc)
    for identity_name in _allowed_identities(anchor):
        if _ssh_verify(anchor, identity_name, RECORD_NAMESPACE, sig_path, canonical):
            return identity_name
    return None

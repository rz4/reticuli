"""The record reader: a signed statement of one machine's results.

A record is the one file this project promises other programs may parse
(`spec/record.md`). Its canonical bytes are the identity serialization
verbatim -- sorted keys, default separators, non-ASCII escaped -- so the
record digest is the sha256 of exactly what travels between kernels, and a
signature covers exactly those bytes. The member set is closed per version:
version 1 carries the base members, version 2 additionally requires `claim`,
the recipe's relayed obligations. Validation is a precondition of the
format, not a service of one function -- every entry point that reads a
document (canonicalizing, digesting) refuses what `record_validate` refuses,
so a digest never names a document the format does not admit.

Stdlib only.
"""
import hashlib
import json
import math
import os
import re

from . import build, core
from .core import ClaimError

# -- the on-disk / signing contract ------------------------------------------

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

# -- the closed vocabularies (spec/record.md) --------------------------------

_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "cost", "producer",
    "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_VERSIONS = frozenset({1, 2})
_RECORD_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})

_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})

_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# -- small member-level checks ------------------------------------------------


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_finite_nonnegative(v, label: str) -> None:
    if not _is_number(v):
        raise ClaimError(f"{label} must be a number, never a boolean")
    if isinstance(v, float) and not math.isfinite(v):
        raise ClaimError(f"{label} must be finite")
    if v < 0:
        raise ClaimError(f"{label} must not be negative")


def _check_hex(v, label: str) -> None:
    if not isinstance(v, str) or not _RECORD_HEX.match(v):
        raise ClaimError(f"{label} must be 64 lowercase hex characters")


def _check_gate(entry) -> None:
    if not isinstance(entry, dict) or set(entry) != _RECORD_GATE:
        raise ClaimError(f"a gate entry must have exactly {sorted(_RECORD_GATE)}")
    if not isinstance(entry["output"], str):
        raise ClaimError("gate.output must be a string")
    if entry["status"] not in _RECORD_STATUSES:
        raise ClaimError(f"gate.status must be one of {sorted(_RECORD_STATUSES)}")
    if entry["sandbox"] not in _RECORD_SANDBOXES:
        raise ClaimError(f"gate.sandbox must be one of {sorted(_RECORD_SANDBOXES)}")


def _check_environment(env) -> None:
    if not isinstance(env, dict) or set(env) != _RECORD_ENVIRONMENT:
        raise ClaimError(f"record.environment must have exactly {sorted(_RECORD_ENVIRONMENT)}")
    for key in _RECORD_ENVIRONMENT:
        if not isinstance(env[key], str):
            raise ClaimError(f"record.environment.{key} must be a string")


def _check_when(when) -> None:
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record.when must be YYYY-MM-DDTHH:MM:SSZ")


def _check_cost(cost) -> None:
    if not isinstance(cost, dict):
        raise ClaimError("record.cost must be an object")
    extra = set(cost) - set(core.COST_KEYS)
    if extra:
        raise ClaimError(f"record.cost has unknown keys: {sorted(extra)}")
    for key, value in cost.items():
        _check_finite_nonnegative(value, f"cost.{key}")


def _check_producer(producer) -> None:
    if not isinstance(producer, dict):
        raise ClaimError("record.producer must be an object")
    extra = set(producer) - _RECORD_PRODUCER
    if extra:
        raise ClaimError(f"record.producer has unknown keys: {sorted(extra)}")
    for key in ("vendor", "model", "cutoff"):
        if key in producer and not isinstance(producer[key], str):
            raise ClaimError(f"record.producer.{key} must be a string")
    if "blind" in producer and not isinstance(producer["blind"], bool):
        raise ClaimError("record.producer.blind must be a boolean")


def _check_claim(claim) -> None:
    if not isinstance(claim, dict):
        raise ClaimError("record.claim must be an object")
    extra = set(claim) - _RECORD_CLAIM_KEYS
    if extra:
        raise ClaimError(f"record.claim has unknown keys: {sorted(extra)}")
    for key in ("tolerance", "mutation_floor"):
        if key in claim:
            if not _is_number(claim[key]):
                raise ClaimError(f"record.claim.{key} must be a number, never a boolean")
            if claim[key] < 0:
                raise ClaimError(f"record.claim.{key} must not be negative")
    if "envelope" in claim:
        envelope = claim["envelope"]
        if not isinstance(envelope, dict) or not envelope:
            raise ClaimError("record.claim.envelope must be a non-empty object")
        for unit, ceiling in envelope.items():
            if unit not in core.COST_UNITS:
                raise ClaimError(f"record.claim.envelope has an unknown unit: {unit!r}")
            if not _is_number(ceiling) or ceiling <= 0:
                raise ClaimError(f"record.claim.envelope.{unit} must be a positive number")


# -- the document ------------------------------------------------------------


def record_validate(doc) -> None:
    """Refuse, in band, anything `spec/record.md`'s Validation section refuses."""
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ClaimError("record.record must be an integer format version")
    if version not in _RECORD_VERSIONS:
        raise ClaimError(
            f"record version {version} is newer than this kernel understands "
            f"(understands {sorted(_RECORD_VERSIONS)})"
        )

    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        allowed.add("claim")
        required.add("claim")

    extra = set(doc) - allowed
    if extra:
        raise ClaimError(f"a record must not carry unknown members: {sorted(extra)}")
    missing = required - set(doc)
    if missing:
        raise ClaimError(f"a record is missing required members: {sorted(missing)}")

    if not isinstance(doc["name"], str):
        raise ClaimError("record.name must be a string")
    _check_hex(doc["root"], "record.root")
    _check_hex(doc["build_digest"], "record.build_digest")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise ClaimError("record.gates must be an array")
    for entry in gates:
        _check_gate(entry)

    _check_environment(doc["environment"])
    _check_when(doc["when"])

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record.tool must be a string")
    if "cost" in doc:
        _check_cost(doc["cost"])
    if "producer" in doc:
        _check_producer(doc["producer"])
    if "claim" in doc:
        _check_claim(doc["claim"])


def record_canonical(doc) -> bytes:
    """The identity serialization, verbatim: sorted keys, default separators."""
    record_validate(doc)
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc) -> str:
    """The record digest: the sha256 hex of the canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path: str) -> dict:
    """Read, parse, and validate a record file; refusals, never crashes."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed record {path!r}: {e}") from e
    record_validate(doc)
    return doc


def record_signer(path: str, anchor: str):
    """The principal whose signature over the record at `path` verifies
    against `anchor` (an ssh `allowed_signers` file), or `None` if the
    record is unsigned or signed by no key the anchor trusts.

    The detached `ssh-keygen -Y` signature lives beside the record, at
    `path` with `.sig` appended, in the `reticuli.record` namespace
    (`spec/record.md`) -- distinct from a claim's own signing namespace so
    one signature can never be presented for the other's purpose.
    """
    doc = record_read(path)
    canon = record_canonical(doc)
    signature_path = path + ".sig"
    if not (os.path.isfile(signature_path) and os.path.isfile(anchor)):
        return None
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            principal = line.split()[0]
            if build._ssh_verify(canon, signature_path, RECORD_NAMESPACE, anchor, principal):
                return principal
    return None

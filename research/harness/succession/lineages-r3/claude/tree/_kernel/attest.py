"""The record: a signed statement of one machine's results (spec/record.md).

A record's canonical bytes are the identity serialization verbatim --
`json.dumps(doc, sort_keys=True)`, sorted keys, default separators,
non-ASCII escaped, encoded UTF-8 -- so a record travels between kernels
byte for byte; `record_digest` is the sha256 hex of those bytes, what a
signature covers and how a record is cited. `record_validate` enforces the
closed member set this kernel understands (`RECORD_FORMAT = 1`: no
`claim` member yet, see spec/record.md's version-2 note) and refuses, in
band, anything malformed rather than crashing -- a record is untrusted
bytes like a recipe or a manifest. `record_read` parses a record file off
disk and validates it. `record_signer` verifies a detached `ssh-keygen -Y`
signature over a record's canonical bytes in `RECORD_NAMESPACE`, distinct
from attestation (`core.NAMESPACE`) and authorization
(`core.SIGN_NAMESPACE`) -- a record signature states only "these are the
results I obtained".
"""
import hashlib
import json
import os
import re
import shutil
import subprocess

from .core import ClaimError

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

# -- The record's closed member sets (spec/record.md, "The document") ------

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
_RECORD_COST = frozenset({"usd", "tokens", "calls", "seconds"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# -- Canonical bytes and the record digest ---------------------------------


def record_canonical(doc: dict) -> bytes:
    """The record's canonical bytes: the identity serialization verbatim --
    sorted keys, default separators, non-ASCII escaped (spec/record.md,
    "Canonical bytes and the record digest").
    """
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The record digest: the sha256 hex of its canonical bytes -- what a
    signature covers and how a record is cited.
    """
    return hashlib.sha256(record_canonical(doc)).hexdigest()


# -- Validation (spec/record.md, "Validation") -----------------------------


def record_validate(doc) -> None:
    """Refuse, in band and with a reason, anything that is not a
    well-formed record this kernel understands: not a JSON object, an
    unknown or missing member, a `record` version newer than
    `RECORD_FORMAT`, a bad hex digest, an out-of-vocabulary gate status or
    sandbox, or a malformed `cost`/`producer` block. The member set is
    closed on purpose (spec/record.md): extension is a version bump, not a
    quiet extra field.
    """
    if not isinstance(doc, dict):
        raise ClaimError("a record must be a JSON object")

    extra = set(doc) - _RECORD_MEMBERS
    if extra:
        raise ClaimError(f"record carries unknown member(s): {sorted(extra)}")

    missing = _RECORD_REQUIRED - set(doc)
    if missing:
        raise ClaimError(f"record is missing required member(s): {sorted(missing)}")

    version = doc.get("record")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ClaimError("record: 'record' must be a positive integer")
    if version > RECORD_FORMAT:
        raise ClaimError(
            f"record format {version} is newer than this kernel understands "
            f"(format {RECORD_FORMAT})"
        )

    if not isinstance(doc.get("name"), str):
        raise ClaimError("record: 'name' must be a string")

    for key in ("root", "build_digest"):
        value = doc.get(key)
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise ClaimError(f"record: {key!r} must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError(
            "record: 'environment' must carry exactly platform/machine/runtime"
        )
    for value in environment.values():
        if not isinstance(value, str):
            raise ClaimError("record: environment values must be strings")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("record: 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise ClaimError(
                "record: each gate entry must carry exactly output/status/sandbox"
            )
        if not isinstance(gate.get("output"), str):
            raise ClaimError("record: gate 'output' must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise ClaimError(
                f"record: gate status must be one of {sorted(_RECORD_STATUSES)}"
            )
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise ClaimError(
                f"record: gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}"
            )

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict):
            raise ClaimError("record: 'cost' must be an object")
        extra_cost = set(cost) - _RECORD_COST
        if extra_cost:
            raise ClaimError(f"record: cost carries unknown unit(s): {sorted(extra_cost)}")
        for value in cost.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ClaimError("record: cost values must be non-negative numbers")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict):
            raise ClaimError("record: 'producer' must be an object")
        extra_producer = set(producer) - _RECORD_PRODUCER
        if extra_producer:
            raise ClaimError(
                f"record: producer carries unknown member(s): {sorted(extra_producer)}"
            )
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise ClaimError(f"record: producer {key!r} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record: producer 'blind' must be a boolean")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise ClaimError("record: 'tool' must be a string")


# -- Reading a record off disk ----------------------------------------------


def record_read(path: str) -> dict:
    """Read a record file and validate it. Refuses, with a reason, bytes
    that are not JSON, not an object, or not a well-formed record -- a
    record is untrusted-on-disk state, like a recipe or a manifest.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ClaimError(f"cannot read record {path!r}: {exc}") from exc

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimError(f"malformed record {path!r}: {exc}") from exc

    record_validate(doc)
    return doc


# -- Signing (spec/record.md, "Signing") ------------------------------------


def record_signer(path: str, allowed_signers: str):
    """The identity that signed the record at `path`, verified against the
    `allowed_signers` anchor in `RECORD_NAMESPACE` -- distinct from
    attestation and from authorization, so a record signature can never be
    presented as either (spec/record.md). `None` when there is no
    detached signature (`path + ".sig"`), no usable `ssh-keygen`, or the
    signature does not verify against the anchor; trust is verifier-relative,
    never assumed.
    """
    signature_path = path + ".sig"
    if not (os.path.isfile(path) and os.path.isfile(signature_path)):
        return None
    if not shutil.which("ssh-keygen"):
        return None

    try:
        doc = record_read(path)
    except ClaimError:
        return None
    data = record_canonical(doc)

    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", "signer",
             "-n", RECORD_NAMESPACE, "-s", signature_path],
            input=data, capture_output=True, timeout=10, check=False,
        )
    except OSError:
        return None
    if done.returncode != 0:
        return None

    text = (done.stdout or b"").decode("utf-8", "replace") + \
        (done.stderr or b"").decode("utf-8", "replace")
    match = re.search(r"for (\S+)", text)
    return match.group(1) if match else "signer"

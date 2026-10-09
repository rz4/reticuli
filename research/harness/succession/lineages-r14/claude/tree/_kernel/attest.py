"""The record reader: a signed statement of one machine's results (spec/record.md).

A record is a small, closed-membership JSON document -- not this tool's
internal bookkeeping -- so it is the one file other programs may parse. Its
canonical bytes are the identity serialization verbatim (sorted keys, default
separators, non-ASCII escaped, UTF-8), and its digest is the sha256 of those
bytes. `record_validate` refuses, in band, anything the spec does not allow:
a non-object, an unknown version, a closed member set violated, a malformed
field. `record_read` parses a file from disk; `record_signer` checks a
detached ssh signature over the canonical bytes against an allowed-signers
anchor. Stdlib only, never the network.
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
RECORD_FORMAT = 2

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_RECORD_MEMBERS = frozenset({
    "when", "cost", "gates", "producer", "environment",
    "name", "root", "record", "build_digest", "tool",
})
_RECORD_REQUIRED = frozenset({
    "build_digest", "when", "environment", "record", "name", "root", "gates",
})
_RECORD_GATE = frozenset({"status", "sandbox", "output"})
_RECORD_ENVIRONMENT = frozenset({"platform", "runtime", "machine"})
_RECORD_PRODUCER = frozenset({"blind", "model", "cutoff", "vendor"})
_RECORD_STATUSES = frozenset({"timeout", "ok", "environment", "failed", "mismatch"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "inherited", "bubblewrap"})

_RECORD_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# -- canonical bytes and digest ------------------------------------------

def record_canonical(doc: dict) -> bytes:
    """The identity serialization verbatim: sorted keys, default separators,
    non-ASCII escaped, UTF-8 (spec/record.md, spec/identity.md)."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The sha256 hex digest of `doc`'s canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


# -- validation: the member set is closed, per version -------------------

def record_validate(doc) -> None:
    """Refuse, in band, anything spec/record.md does not allow."""
    if not isinstance(doc, dict):
        raise ClaimError("record must be a JSON object")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ClaimError("record: 'record' version must be a positive integer")
    if version > RECORD_FORMAT:
        raise ClaimError(
            f"record version {version} is newer than this kernel understands "
            f"(format {RECORD_FORMAT})"
        )

    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version >= 2:
        allowed.add("claim")
        required.add("claim")
    elif "claim" in doc:
        raise ClaimError("record: 'claim' is refused at version 1")

    extra = set(doc) - allowed
    if extra:
        raise ClaimError(f"record carries unknown member(s): {sorted(extra)}")
    missing = required - set(doc)
    if missing:
        raise ClaimError(f"record missing required member(s): {sorted(missing)}")

    if not isinstance(doc.get("name"), str):
        raise ClaimError("record: 'name' must be a string")

    root = doc.get("root")
    if not isinstance(root, str) or not _RECORD_HEX.match(root):
        raise ClaimError("record: 'root' must be 64 lowercase hex characters")

    build_digest = doc.get("build_digest")
    if not isinstance(build_digest, str) or not _RECORD_HEX.match(build_digest):
        raise ClaimError("record: 'build_digest' must be 64 lowercase hex characters")

    when = doc.get("when")
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise ClaimError("record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    tool = doc.get("tool")
    if tool is not None and not isinstance(tool, str):
        raise ClaimError("record: 'tool' must be a string")

    environment = doc.get("environment")
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise ClaimError(
            f"record: 'environment' must have exactly {sorted(_RECORD_ENVIRONMENT)}"
        )
    for key in _RECORD_ENVIRONMENT:
        if not isinstance(environment[key], str):
            raise ClaimError(f"record: environment.{key} must be a string")

    gates = doc.get("gates")
    if not isinstance(gates, list):
        raise ClaimError("record: 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise ClaimError(f"record: a gates entry must have exactly {sorted(_RECORD_GATE)}")
        if not isinstance(gate.get("output"), str):
            raise ClaimError("record: a gates entry's 'output' must be a string")
        if gate.get("status") not in _RECORD_STATUSES:
            raise ClaimError(
                f"record: gate status {gate.get('status')!r} outside {sorted(_RECORD_STATUSES)}"
            )
        if gate.get("sandbox") not in _RECORD_SANDBOXES:
            raise ClaimError(
                f"record: gate sandbox {gate.get('sandbox')!r} outside {sorted(_RECORD_SANDBOXES)}"
            )

    cost = doc.get("cost")
    if cost is not None:
        if not isinstance(cost, dict):
            raise ClaimError("record: 'cost' must be an object")
        for key, value in cost.items():
            if key not in core.COST_KEYS:
                raise ClaimError(f"record: cost key {key!r} is not a recognized unit")
            if not _is_number(value) or value < 0:
                raise ClaimError(f"record: cost.{key} must be a non-negative number")

    producer = doc.get("producer")
    if producer is not None:
        if not isinstance(producer, dict) or not set(producer) <= _RECORD_PRODUCER:
            raise ClaimError(f"record: 'producer' must be a subset of {sorted(_RECORD_PRODUCER)}")
        if "vendor" in producer and not isinstance(producer["vendor"], str):
            raise ClaimError("record: producer.vendor must be a string")
        if "model" in producer and not isinstance(producer["model"], str):
            raise ClaimError("record: producer.model must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise ClaimError("record: producer.blind must be a boolean")
        if "cutoff" in producer and not isinstance(producer["cutoff"], str):
            raise ClaimError("record: producer.cutoff must be a string")

    if version >= 2:
        claim = doc.get("claim")
        if not isinstance(claim, dict) or not set(claim) <= _RECORD_CLAIM_KEYS:
            raise ClaimError(f"record: 'claim' must be a subset of {sorted(_RECORD_CLAIM_KEYS)}")
        if "tolerance" in claim:
            value = claim["tolerance"]
            if not _is_number(value) or value < 0:
                raise ClaimError("record: claim.tolerance must be a non-negative number")
        if "mutation_floor" in claim:
            value = claim["mutation_floor"]
            if not _is_number(value) or value < 0:
                raise ClaimError("record: claim.mutation_floor must be a non-negative number")
        if "envelope" in claim:
            envelope = claim["envelope"]
            if not isinstance(envelope, dict) or not envelope:
                raise ClaimError("record: claim.envelope must be a non-empty object")
            for key, value in envelope.items():
                if key not in core.COST_UNITS:
                    raise ClaimError(f"record: claim.envelope unit {key!r} is unknown")
                if not _is_number(value) or value <= 0:
                    raise ClaimError(f"record: claim.envelope.{key} must be a positive number")


# -- reading a record from disk ------------------------------------------

def record_read(path: str) -> dict:
    """Parse and validate the record at `path`; refuses, never crashes."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e

    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed record {path!r}: {e}") from e

    record_validate(doc)
    return doc


# -- signatures: ssh-keygen -Y verify, namespace `reticuli.record` -------

def _anchor_identities(anchor: str) -> list:
    """Every principal named in an ssh allowed-signers file."""
    identities = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split(None, 1)[0]
            identities.extend(p for p in head.split(",") if p)
    return identities


def record_signer(path: str, anchor: str):
    """The identity whose signature over the record at `path` verifies
    against `anchor` (an ssh allowed-signers file), or `None`."""
    doc = record_read(path)
    data = record_canonical(doc)

    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        return None
    if not anchor or not os.path.isfile(anchor):
        return None
    if shutil.which("ssh-keygen") is None:
        return None

    for identity in _anchor_identities(anchor):
        argv = [
            "ssh-keygen", "-Y", "verify", "-f", anchor,
            "-n", RECORD_NAMESPACE, "-s", sig_path, "-I", identity,
        ]
        try:
            done = subprocess.run(argv, input=data, capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return identity
    return None

"""The record: a signed statement of one machine's results (spec/record.md).

A record is the one file this project promises other programs may parse, so
its canonical bytes are the identity serialization verbatim -- sorted keys,
default separators, non-ASCII escaped -- the same rule `_kernel/identity.py`
hashes recipes with. `record_validate` refuses, in band, anything outside
the closed member set this kernel understands (`RECORD_FORMAT = 1`); it
never raises a bare parser or KeyError.
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

_RECORD_ENVIRONMENT = frozenset({'platform', 'runtime', 'machine'})
_RECORD_GATE = frozenset({'status', 'sandbox', 'output'})
_RECORD_MEMBERS = frozenset({'when', 'cost', 'gates', 'producer', 'environment', 'name', 'root', 'record', 'build_digest', 'tool'})
_RECORD_PRODUCER = frozenset({'blind', 'model', 'cutoff', 'vendor'})
_RECORD_REQUIRED = frozenset({'build_digest', 'when', 'environment', 'record', 'name', 'root', 'gates'})
_RECORD_SANDBOXES = frozenset({'none', 'seatbelt', 'inherited', 'bubblewrap'})
_RECORD_STATUSES = frozenset({'timeout', 'ok', 'environment', 'failed', 'mismatch'})


def record_canonical(doc: dict) -> bytes:
    """The identity serialization verbatim: sorted keys, default separators,
    non-ASCII escaped, encoded UTF-8."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The record digest: sha256 hex of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def _require_keys(obj, allowed, where: str) -> None:
    if not isinstance(obj, dict) or set(obj) != allowed:
        raise core.ClaimError(f"{where} must have exactly {sorted(allowed)}")


def record_validate(doc) -> None:
    """Refuse, in band, anything outside the closed record format this
    kernel understands. The member set is closed per version; this kernel
    understands only `RECORD_FORMAT`."""
    if not isinstance(doc, dict):
        raise core.ClaimError("a record must be a JSON object")

    unknown = set(doc) - _RECORD_MEMBERS
    if unknown:
        raise core.ClaimError(f"a record names unknown members: {sorted(unknown)}")

    missing = _RECORD_REQUIRED - set(doc)
    if missing:
        raise core.ClaimError(f"a record is missing required members: {sorted(missing)}")

    version = doc["record"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise core.ClaimError("record: record must be an integer")
    if version != RECORD_FORMAT:
        raise core.ClaimError(
            f"record format {version} is newer than this kernel understands "
            f"(format {RECORD_FORMAT}); upgrade reticuli to read it"
        )

    name = doc["name"]
    if not isinstance(name, str) or not name:
        raise core.ClaimError("record: name must be a non-empty string")

    for key in ("root", "build_digest"):
        value = doc[key]
        if not isinstance(value, str) or not _RECORD_HEX.match(value):
            raise core.ClaimError(f"record: {key} must be 64 lowercase hex characters")

    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise core.ClaimError("record: when must be YYYY-MM-DDTHH:MM:SSZ")

    _require_keys(doc["environment"], _RECORD_ENVIRONMENT, "record: environment")
    for key, value in doc["environment"].items():
        if not isinstance(value, str) or not value:
            raise core.ClaimError(f"record: environment.{key} must be a non-empty string")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("record: gates must be an array")
    for gate in gates:
        _require_keys(gate, _RECORD_GATE, "record: each gate")
        output = gate["output"]
        if not isinstance(output, str) or not output:
            raise core.ClaimError("record: gate output must be a non-empty string")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"record: gate status must be one of {sorted(_RECORD_STATUSES)}")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"record: gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not set(cost) <= set(core.COST_KEYS):
            raise core.ClaimError(f"record: cost keys must be a subset of {sorted(core.COST_KEYS)}")
        for key, value in cost.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise core.ClaimError(f"record: cost.{key} must be a non-negative number")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or not set(producer) <= _RECORD_PRODUCER:
            raise core.ClaimError(f"record: producer keys must be a subset of {sorted(_RECORD_PRODUCER)}")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"record: producer.{key} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise core.ClaimError("record: producer.blind must be a boolean")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise core.ClaimError("record: tool must be a string")


def record_read(path: str) -> dict:
    """Read and validate a record document from disk. Refusals are
    `ClaimError`, never a raw parser crash."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as exc:
        raise core.ClaimError(f"cannot read record {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise core.ClaimError(f"malformed record {path!r}: {exc}") from exc
    record_validate(doc)
    return doc


def record_signer(path: str, anchor: str):
    """The signer identity whose detached ssh signature over the record at
    `path` verifies against `anchor` (an `allowed_signers` file), in the
    `reticuli.record` namespace -- or `None` if no principal verifies."""
    signature = path + ".sig"
    if not (os.path.isfile(path) and os.path.isfile(signature) and os.path.isfile(anchor)):
        return None
    try:
        doc = record_read(path)
    except core.ClaimError:
        return None
    data = record_canonical(doc)

    try:
        found = subprocess.run(
            ["ssh-keygen", "-Y", "find-principals", "-f", anchor, "-s", signature],
            capture_output=True, timeout=30, text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    principals = [line.split()[0] for line in found.stdout.splitlines() if line.strip()]

    for principal in principals:
        try:
            verified = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
                 "-n", RECORD_NAMESPACE, "-s", signature],
                input=data, capture_output=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if verified.returncode == 0:
            return principal
    return None

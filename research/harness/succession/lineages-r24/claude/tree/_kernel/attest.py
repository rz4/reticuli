"""The record reader: a signed statement of one machine's results
(spec/record.md).

A record is a small, closed-membership JSON document -- the only file this
project promises other programs may parse. The kernel owns the format and
consumes records as crosscheck legs (`record_read`, `record_signer`);
authoring one -- emitting, writing, signing -- belongs to the exchange
layer above. `record_canonical` / `record_digest` give a record the same
canonical-JSON identity treatment `identity.py` gives a claim; `record_validate`
refuses, in band and with a reason, any document the spec's closed member
set does not describe.
"""
import hashlib
import json
import os
import re
import subprocess

from reticuli._kernel import core

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

# -- the closed member sets of spec/record.md, version 1 ------------------
_RECORD_MEMBERS = frozenset({
    "record", "name", "root", "build_digest", "gates", "cost", "producer",
    "environment", "when", "tool",
})
_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_CLAIM = frozenset({"tolerance", "envelope", "mutation_floor"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def record_canonical(doc: dict) -> bytes:
    """The canonical bytes of a record: sorted-key JSON, default
    separators, non-ASCII escaped, encoded UTF-8 -- the identity
    serialization verbatim (spec/record.md, spec/identity.md)."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The record digest: the sha256 of its canonical bytes -- what a
    signature covers and how a record is cited (spec/record.md)."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_validate(doc) -> None:
    """Refuse, in band and with a reason, any document the closed member
    set of spec/record.md does not describe (`core.ClaimError`)."""
    if not isinstance(doc, dict):
        raise core.ClaimError("malformed record: not a JSON object")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool):
        raise core.ClaimError("malformed record: 'record' must be an integer")
    if version not in (1, 2):
        raise core.ClaimError(
            f"record version {version} is newer than this kernel understands "
            f"(record versions 1 and 2)"
        )

    allowed = set(_RECORD_MEMBERS)
    required = set(_RECORD_REQUIRED)
    if version == 2:
        allowed.add("claim")
        required.add("claim")

    present = set(doc)
    unknown = present - allowed
    if unknown:
        raise core.ClaimError(f"malformed record: unknown member(s) {sorted(unknown)}")
    missing = required - present
    if missing:
        raise core.ClaimError(f"malformed record: missing member(s) {sorted(missing)}")

    if not isinstance(doc["name"], str):
        raise core.ClaimError("malformed record: 'name' must be a string")

    for key in ("root", "build_digest"):
        v = doc[key]
        if not isinstance(v, str) or not _RECORD_HEX.match(v):
            raise core.ClaimError(
                f"malformed record: {key!r} must be 64 lowercase hex characters"
            )

    when = doc["when"]
    if not isinstance(when, str) or not _RECORD_WHEN.match(when):
        raise core.ClaimError(
            "malformed record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'"
        )

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise core.ClaimError("malformed record: 'gates' must be an array")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != _RECORD_GATE:
            raise core.ClaimError(
                f"malformed record: a gate entry must have exactly {sorted(_RECORD_GATE)}"
            )
        if not isinstance(gate["output"], str):
            raise core.ClaimError("malformed record: a gate's 'output' must be a string")
        if gate["status"] not in _RECORD_STATUSES:
            raise core.ClaimError(f"malformed record: unknown gate status {gate['status']!r}")
        if gate["sandbox"] not in _RECORD_SANDBOXES:
            raise core.ClaimError(f"malformed record: unknown gate sandbox {gate['sandbox']!r}")

    environment = doc["environment"]
    if not isinstance(environment, dict) or set(environment) != _RECORD_ENVIRONMENT:
        raise core.ClaimError(
            f"malformed record: 'environment' must have exactly {sorted(_RECORD_ENVIRONMENT)}"
        )
    for k, v in environment.items():
        if not isinstance(v, str):
            raise core.ClaimError(f"malformed record: environment {k!r} must be a string")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise core.ClaimError("malformed record: 'tool' must be a string")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not set(cost) <= set(core.COST_KEYS):
            raise core.ClaimError(
                f"malformed record: 'cost' keys must be a subset of {sorted(core.COST_KEYS)}"
            )
        for k, v in cost.items():
            if not _is_number(v) or v < 0:
                raise core.ClaimError(f"malformed record: cost {k!r} must be a non-negative number")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or not set(producer) <= _RECORD_PRODUCER:
            raise core.ClaimError(
                f"malformed record: 'producer' keys must be a subset of {sorted(_RECORD_PRODUCER)}"
            )
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise core.ClaimError(f"malformed record: producer {key!r} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise core.ClaimError("malformed record: producer 'blind' must be a boolean")

    if version == 2:
        claim = doc["claim"]
        if not isinstance(claim, dict) or not set(claim) <= _RECORD_CLAIM:
            raise core.ClaimError(
                f"malformed record: 'claim' keys must be a subset of {sorted(_RECORD_CLAIM)}"
            )
        if "tolerance" in claim:
            t = claim["tolerance"]
            if not _is_number(t) or t < 0:
                raise core.ClaimError("malformed record: 'claim.tolerance' must be a non-negative number")
        if "mutation_floor" in claim:
            m = claim["mutation_floor"]
            if not _is_number(m) or m < 0:
                raise core.ClaimError("malformed record: 'claim.mutation_floor' must be a non-negative number")
        if "envelope" in claim:
            env = claim["envelope"]
            if not isinstance(env, dict) or not env:
                raise core.ClaimError("malformed record: 'claim.envelope' must be a non-empty object")
            for unit, ceiling in env.items():
                if unit not in core.COST_UNITS:
                    raise core.ClaimError(f"malformed record: unknown envelope unit {unit!r}")
                if not _is_number(ceiling) or ceiling <= 0:
                    raise core.ClaimError(
                        f"malformed record: envelope {unit!r} must be a positive number"
                    )


def record_read(path: str) -> dict:
    """Read a record from `path`: parsed JSON, validated against
    spec/record.md. A malformed file is a refusal, never a crash."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise core.ClaimError(f"cannot read record {path!r}: {e}") from e
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise core.ClaimError(f"malformed record {path!r}: {e}") from e
    record_validate(doc)
    return doc


def _allowed_principals(anchor: str) -> list:
    """Every principal named in an ssh `allowed_signers` file."""
    principals = []
    try:
        with open(anchor, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                principals.append(line.split()[0])
    except OSError:
        pass
    return principals


def _verify_signature(anchor: str, principal: str, sig_path: str, data: bytes) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data`, for one
    candidate principal, in `RECORD_NAMESPACE`."""
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
             "-n", RECORD_NAMESPACE, "-s", sig_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def record_signer(path: str, anchor: str):
    """The principal whose detached signature over the record at `path`
    verifies against `anchor` (an ssh `allowed_signers` file), in
    `RECORD_NAMESPACE` -- or `None` when no principal's signature
    verifies. Trust is verifier-relative: a record's signature means
    something only against a key in the verifier's own anchor
    (spec/record.md)."""
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path) or not os.path.isfile(anchor):
        return None
    doc = record_read(path)
    data = record_canonical(doc)
    for principal in _allowed_principals(anchor):
        if _verify_signature(anchor, principal, sig_path, data):
            return principal
    return None

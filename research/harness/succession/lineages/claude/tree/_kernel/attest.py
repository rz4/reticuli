"""reticuli._kernel.attest -- the record: a signed statement of one
machine's results (`spec/record.md`).

`record_canonical` / `record_digest` give a record the same canonical-bytes
treatment `identity.py` gives a recipe: sorted keys, default separators,
ASCII-escaped, encoded UTF-8 -- what a signature covers and how a record is
cited. `record_validate` is the closed-member-set reader: it refuses, in
band and with a reason, any document that is not shaped exactly like this
spec's version-1 record. `record_read` loads and validates one from disk.
`record_signer` verifies a detached ssh signature over a record's canonical
bytes, in the `reticuli.record` namespace, against an allowed-signers file.
"""
import hashlib
import json
import os
import re
import subprocess

from . import core

RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

_RECORD_HEX = re.compile(r'^[0-9a-f]{64}$')
_RECORD_WHEN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')

_RECORD_REQUIRED = frozenset({
    "record", "name", "root", "build_digest", "gates", "environment", "when",
})
_RECORD_MEMBERS = _RECORD_REQUIRED | frozenset({"cost", "producer", "tool"})
_RECORD_GATE = frozenset({"output", "status", "sandbox"})
_RECORD_ENVIRONMENT = frozenset({"platform", "machine", "runtime"})
_RECORD_PRODUCER = frozenset({"vendor", "model", "blind", "cutoff"})
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_RECORD_COST_KEYS = frozenset({"usd", "tokens", "calls", "seconds"})


# ---------------------------------------------------------------------------
# Canonical bytes and the record digest
# ---------------------------------------------------------------------------
def record_canonical(doc: dict) -> bytes:
    """A record's canonical bytes: sorted-key JSON, default separators,
    non-ASCII escaped, encoded UTF-8 -- identical treatment to a recipe's
    root preimage (`spec/identity.md`)."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The record digest: the sha256 hex of its canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


# ---------------------------------------------------------------------------
# Validation: the member set is closed, in band, per `spec/record.md`
# ---------------------------------------------------------------------------
def _require(cond, msg: str) -> None:
    if not cond:
        raise core.ClaimError(msg)


def _check_gate(gate) -> None:
    _require(isinstance(gate, dict), "a gate entry must be an object")
    _require(
        set(gate) == _RECORD_GATE,
        f"a gate entry must have exactly {sorted(_RECORD_GATE)}, got {sorted(gate)}",
    )
    _require(isinstance(gate["output"], str), "gate.output must be a string")
    _require(
        gate["status"] in _RECORD_STATUSES,
        f"gate.status must be one of {sorted(_RECORD_STATUSES)}, got {gate['status']!r}",
    )
    _require(
        gate["sandbox"] in _RECORD_SANDBOXES,
        f"gate.sandbox must be one of {sorted(_RECORD_SANDBOXES)}, got {gate['sandbox']!r}",
    )


def _check_environment(environment) -> None:
    _require(isinstance(environment, dict), "environment must be an object")
    _require(
        set(environment) == _RECORD_ENVIRONMENT,
        f"environment must have exactly {sorted(_RECORD_ENVIRONMENT)}, "
        f"got {sorted(environment)}",
    )
    for key, value in environment.items():
        _require(isinstance(value, str), f"environment.{key} must be a string")


def _check_cost(cost) -> None:
    _require(isinstance(cost, dict), "cost must be an object")
    extra = set(cost) - _RECORD_COST_KEYS
    _require(not extra, f"cost has unknown key(s): {sorted(extra)}")
    for key, value in cost.items():
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0,
            f"cost.{key} must be a non-negative number, got {value!r}",
        )


def _check_producer(producer) -> None:
    _require(isinstance(producer, dict), "producer must be an object")
    extra = set(producer) - _RECORD_PRODUCER
    _require(not extra, f"producer has unknown member(s): {sorted(extra)}")
    for key in ("vendor", "model", "cutoff"):
        if key in producer:
            _require(isinstance(producer[key], str), f"producer.{key} must be a string")
    if "blind" in producer:
        _require(isinstance(producer["blind"], bool), "producer.blind must be a boolean")


def record_validate(doc) -> None:
    """Refuse, in band and with a reason, any document not shaped exactly
    like a record (`spec/record.md`, "Validation"). Silent on success."""
    _require(isinstance(doc, dict), "a record must be a JSON object")

    version = doc.get("record")
    _require(
        isinstance(version, int) and not isinstance(version, bool),
        f"record must be an integer, got {version!r}",
    )
    _require(version >= 1, f"record version must be positive, got {version!r}")
    _require(
        version <= RECORD_FORMAT,
        f"record version {version} is newer than this kernel understands "
        f"(format {RECORD_FORMAT}); upgrade reticuli to read it",
    )

    extra = set(doc) - _RECORD_MEMBERS
    _require(not extra, f"record has unknown member(s): {sorted(extra)}")
    missing = _RECORD_REQUIRED - set(doc)
    _require(not missing, f"record is missing required member(s): {sorted(missing)}")

    _require(isinstance(doc["name"], str), "name must be a string")
    _require(
        isinstance(doc["root"], str) and bool(_RECORD_HEX.match(doc["root"])),
        "root must be 64 lowercase hex characters",
    )
    _require(
        isinstance(doc["build_digest"], str) and bool(_RECORD_HEX.match(doc["build_digest"])),
        "build_digest must be 64 lowercase hex characters",
    )
    _require(
        isinstance(doc["when"], str) and bool(_RECORD_WHEN.match(doc["when"])),
        "when must be YYYY-MM-DDTHH:MM:SSZ",
    )

    _require(isinstance(doc["gates"], list), "gates must be an array")
    for gate in doc["gates"]:
        _check_gate(gate)

    _check_environment(doc["environment"])

    if "cost" in doc:
        _check_cost(doc["cost"])
    if "producer" in doc:
        _check_producer(doc["producer"])
    if "tool" in doc:
        _require(isinstance(doc["tool"], str), "tool must be a string")


# ---------------------------------------------------------------------------
# Reading a record from disk
# ---------------------------------------------------------------------------
def record_read(path: str) -> dict:
    """Read and validate a record from `path`."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as exc:
        raise core.ClaimError(f"no record at {path!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise core.ClaimError(f"malformed record {path!r}: {exc}") from exc
    record_validate(doc)
    return doc


# ---------------------------------------------------------------------------
# Signing: verified against a verifier-relative allowed-signers file
# ---------------------------------------------------------------------------
def record_signer(path: str, anchor: str, signer: str = "*") -> str:
    """Verify `path`'s detached ssh signature over its record's canonical
    bytes, in the `reticuli.record` namespace, against `anchor` (an ssh
    `allowed_signers` file naming trusted keys). Returns the signer
    identity on success; refuses with a reason otherwise -- an absent
    signature, or one that does not verify, is not evidence.
    """
    doc = record_read(path)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        raise core.ClaimError(f"no signature found for record {path!r}")
    if not os.path.isfile(anchor):
        raise core.ClaimError(f"no allowed-signers file at {anchor!r}")
    data = record_canonical(doc)
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", signer,
             "-n", RECORD_NAMESPACE, "-s", sig_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise core.ClaimError(f"could not verify signature for {path!r}: {exc}") from exc
    if done.returncode != 0:
        raise core.ClaimError(f"signature verification failed for record {path!r}")
    return signer

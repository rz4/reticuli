"""The record: a signed statement of one machine's results (`spec/record.md`).

A record is a small JSON document -- the one file this project promises other
programs may parse. `record_canonical`/`record_digest` give it the same
canonical bytes and digest the identity computation uses (sorted keys,
default separators, ASCII-escaped, utf-8). `record_validate` enforces the
closed member set and every per-member rule in band, refusing a malformed or
extended document rather than crashing on one. `record_read` parses a record
file off disk. `record_signer` recovers the signer identity of a record's
detached `ssh-keygen -Y` signature, verified against a trust anchor -- `None`
if the record carries none, or if it does not verify.

Stdlib only.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile

from . import core
from .core import ClaimError

# -- the record format (`spec/record.md`, version 1) ------------------------
RECORD_NAMESPACE = "reticuli.record"
RECORD_FORMAT = 1

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
_RECORD_STATUSES = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})

_RECORD_HEX = re.compile(r"^[0-9a-f]{64}$")
_RECORD_WHEN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


# -- canonical bytes and the record digest -----------------------------------

def record_canonical(doc: dict) -> bytes:
    """The record's canonical bytes: sorted keys, default separators,
    non-ASCII escaped, encoded utf-8 -- the same rule the identity uses."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def record_digest(doc: dict) -> str:
    """The record digest: sha256 hex of the record's canonical bytes."""
    return hashlib.sha256(record_canonical(doc)).hexdigest()


# -- validation: the closed member set, in band ------------------------------

def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ClaimError(message)


def _require_str(value, what: str) -> None:
    _require(isinstance(value, str), f"{what} must be a string, got {value!r}")


def _validate_gate(entry) -> None:
    _require(isinstance(entry, dict), f"a gate entry must be an object, got {entry!r}")
    _require(set(entry) == _RECORD_GATE,
              f"a gate entry must carry exactly {sorted(_RECORD_GATE)}, "
              f"got {sorted(entry)}")
    _require_str(entry.get("output"), "a gate entry's output")
    _require(entry.get("status") in _RECORD_STATUSES,
              f"a gate status must be one of {sorted(_RECORD_STATUSES)}, "
              f"got {entry.get('status')!r}")
    _require(entry.get("sandbox") in _RECORD_SANDBOXES,
              f"a gate sandbox must be one of {sorted(_RECORD_SANDBOXES)}, "
              f"got {entry.get('sandbox')!r}")


def _validate_environment(env) -> None:
    _require(isinstance(env, dict), f"environment must be an object, got {env!r}")
    _require(set(env) == _RECORD_ENVIRONMENT,
              f"environment must carry exactly {sorted(_RECORD_ENVIRONMENT)}, "
              f"got {sorted(env)}")
    for key in _RECORD_ENVIRONMENT:
        _require_str(env.get(key), f"environment {key!r}")


def _validate_cost(cost) -> None:
    _require(isinstance(cost, dict), f"cost must be an object, got {cost!r}")
    for key, value in cost.items():
        _require(key in core.COST_KEYS,
                  f"cost key must be one of {sorted(core.COST_KEYS)}, got {key!r}")
        _require(isinstance(value, (int, float)) and not isinstance(value, bool)
                  and value >= 0,
                  f"cost {key!r} must be a non-negative number, got {value!r}")


def _validate_producer(producer) -> None:
    _require(isinstance(producer, dict), f"producer must be an object, got {producer!r}")
    for key in producer:
        _require(key in _RECORD_PRODUCER,
                  f"producer key must be one of {sorted(_RECORD_PRODUCER)}, "
                  f"got {key!r}")
    if "vendor" in producer:
        _require_str(producer["vendor"], "producer vendor")
    if "model" in producer:
        _require_str(producer["model"], "producer model")
    if "cutoff" in producer:
        _require_str(producer["cutoff"], "producer cutoff")
    if "blind" in producer:
        _require(isinstance(producer["blind"], bool),
                  f"producer blind must be a boolean, got {producer['blind']!r}")


def record_validate(doc) -> dict:
    """Refuse, in band, any document that is not a well-formed record.

    The member set is closed: an unknown member, a missing required member,
    or a member whose value fails its own rule is refused with a reason
    (`spec/record.md`, "Validation").
    """
    _require(isinstance(doc, dict), f"a record must be a JSON object, got {doc!r}")

    unknown = set(doc) - _RECORD_MEMBERS
    _require(not unknown, f"a record carries unknown members: {sorted(unknown)}")
    missing = _RECORD_REQUIRED - set(doc)
    _require(not missing, f"a record is missing required members: {sorted(missing)}")

    version = doc.get("record")
    _require(isinstance(version, int) and not isinstance(version, bool),
              f"record version must be an integer, got {version!r}")
    _require(version == RECORD_FORMAT,
              f"record version {version} is newer than this reader understands "
              f"(record {RECORD_FORMAT}); upgrade to read it")

    _require_str(doc.get("name"), "a record's name")

    root = doc.get("root")
    _require(isinstance(root, str) and _RECORD_HEX.match(root) is not None,
              f"root must be 64 lowercase hex characters, got {root!r}")
    build_digest = doc.get("build_digest")
    _require(isinstance(build_digest, str)
              and _RECORD_HEX.match(build_digest) is not None,
              f"build_digest must be 64 lowercase hex characters, "
              f"got {build_digest!r}")

    gates = doc.get("gates")
    _require(isinstance(gates, list), f"gates must be an array, got {gates!r}")
    for entry in gates:
        _validate_gate(entry)

    _validate_environment(doc.get("environment"))

    when = doc.get("when")
    _require(isinstance(when, str) and _RECORD_WHEN.match(when) is not None,
              f"when must be YYYY-MM-DDTHH:MM:SSZ, got {when!r}")

    if "cost" in doc:
        _validate_cost(doc["cost"])
    if "producer" in doc:
        _validate_producer(doc["producer"])
    if "tool" in doc:
        _require_str(doc["tool"], "tool")

    return doc


# -- reading a record off disk -----------------------------------------------

def record_read(path: str) -> dict:
    """Parse and validate the record at `path`; refusals, not crashes."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        raise ClaimError(f"cannot read record {path!r}: {e}") from e
    except json.JSONDecodeError as e:
        raise ClaimError(f"malformed record {path!r}: {e}") from e
    return record_validate(doc)


# -- the signer of a record's detached signature -----------------------------

def _ssh_verify(namespace: str, allowed_signers: str, signer_id: str,
                 signature: bytes, data: bytes) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `data`."""
    if not allowed_signers or not os.path.isfile(allowed_signers):
        return False
    fd, sig_path = tempfile.mkstemp(suffix=".sig")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(signature)
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", signer_id, "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=10)
    except OSError:
        return False
    finally:
        try:
            os.remove(sig_path)
        except OSError:
            pass
    return result.returncode == 0


def record_signer(path: str, anchor: str):
    """The signer identity of the record at `path`, verified against the ssh
    allowed_signers file `anchor`; `None` if the record carries no signature,
    its sidecar is malformed, or the signature does not verify.

    The signature sidecar lives at `<path>.sign.json`:
    `{"signer": ..., "signature": <base64>}`, the detached `ssh-keygen -Y`
    signature over the record's canonical bytes, in the `reticuli.record`
    namespace.
    """
    sign_path = path + ".sign.json"
    if not os.path.isfile(sign_path):
        return None
    try:
        with open(sign_path, "r", encoding="utf-8") as f:
            sidecar = json.load(f)
        signature = base64.b64decode(sidecar["signature"])
        signer = sidecar["signer"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(signer, str):
        return None

    doc = record_read(path)
    canon = record_canonical(doc)
    if _ssh_verify(RECORD_NAMESPACE, anchor, signer, signature, canon):
        return signer
    return None

"""record: a signed statement of one machine's results (spec/record.md).

`emit` earns its verdicts (running the audit fresh, never reporting a
sealed-time status); the file on disk is its canonical bytes; `validate`
closes the vocabulary in band; signatures live in the record's own
namespace (`reticuli.record`), distinct from attestation and authorization.
"""
import hashlib
import json
import os
import platform
import re
import subprocess
import sys

from reticuli import _util, kernel

FORMAT = 2

_MEMBERS = frozenset({"record", "claim", "name", "root", "build_digest", "gates",
                      "cost", "producer", "environment", "when", "tool"})
_REQUIRED_V1 = frozenset({"record", "name", "root", "build_digest", "gates",
                          "environment", "when"})
_GATE_MEMBERS = frozenset({"output", "status", "sandbox"})
_GATE_STATUS = frozenset({"ok", "failed", "timeout", "mismatch", "environment"})
_GATE_SANDBOX = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})
_COST_KEYS = frozenset({"usd", "tokens", "calls", "seconds"})
_PRODUCER_KEYS = frozenset({"vendor", "model", "blind", "cutoff"})
_CLAIM_KEYS = frozenset({"tolerance", "envelope", "mutation_floor"})
_ENV_KEYS = frozenset({"platform", "machine", "runtime"})
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_WHEN_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _environment() -> dict:
    return {"platform": sys.platform, "machine": platform.machine(),
            "runtime": f"CPython {platform.python_version()}"}


def _producer_from_ledger(d: str):
    for e in reversed(kernel.ledger_events(d)):
        if e.get("event") == "producer":
            out = {k: e[k] for k in ("vendor", "model", "blind", "cutoff") if k in e}
            return out or None
    return None


def emit(d: str) -> dict:
    """A fresh record of `d`: refuses an unsealed or drifted claim; every
    gate is re-earned now, never reported from the sealed-time state."""
    manifest = kernel.read_manifest(d)
    v = kernel.verify(d)
    if not v["ok"]:
        raise kernel.ClaimError(f"record: claim at {d!r} has drifted; refusing to emit")

    a = kernel.audit(d)
    parsed = kernel.load_recipe(d)
    gates = []
    for g in a.get("gates", []):
        gates.append({"output": g["output"], "status": g["status"], "sandbox": g["quarantine"]})
    if not gates and a.get("environment"):
        for step in parsed.get("step", []) or []:
            if step.get("kind") == "gate":
                gates.append({"output": step["output"], "status": "environment", "sandbox": "none"})

    claim_fields = {k: val for k, val in parsed.get("claim", {}).items()
                    if k in _CLAIM_KEYS}

    doc = {
        "record": FORMAT,
        "claim": claim_fields,
        "name": manifest["name"],
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": _environment(),
        "when": _util.stamp(),
    }
    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _producer_from_ledger(d)
    if producer:
        doc["producer"] = producer
    return doc


def validate(doc) -> None:
    """Refuse, in band and with a reason, any document the closed member
    set of spec/record.md does not describe."""
    if not isinstance(doc, dict):
        raise kernel.ClaimError("malformed record: not a JSON object")

    version = doc.get("record")
    if not isinstance(version, int) or isinstance(version, bool):
        raise kernel.ClaimError("malformed record: 'record' must be an integer")
    if version not in (1, 2):
        raise kernel.ClaimError(
            f"record version {version} is newer than this tool understands (versions 1 and 2)")

    allowed = set(_MEMBERS)
    required = set(_REQUIRED_V1)
    if version == 2:
        required.add("claim")
    else:
        allowed.discard("claim")

    present = set(doc)
    unknown = present - allowed
    if unknown:
        raise kernel.ClaimError(f"malformed record: unknown member(s) {sorted(unknown)}")
    missing = required - present
    if missing:
        raise kernel.ClaimError(f"malformed record: missing member(s) {sorted(missing)}")

    if not isinstance(doc["name"], str):
        raise kernel.ClaimError("malformed record: 'name' must be a string")
    for key in ("root", "build_digest"):
        v = doc[key]
        if not isinstance(v, str) or not _HEX64.match(v):
            raise kernel.ClaimError(f"malformed record: {key!r} must be 64 lowercase hex characters")

    when = doc["when"]
    if not isinstance(when, str) or not _WHEN_RE.match(when):
        raise kernel.ClaimError("malformed record: 'when' must be 'YYYY-MM-DDTHH:MM:SSZ'")

    gates = doc["gates"]
    if not isinstance(gates, list):
        raise kernel.ClaimError("malformed record: 'gates' must be an array")
    for g in gates:
        if not isinstance(g, dict) or set(g) != _GATE_MEMBERS:
            raise kernel.ClaimError(f"malformed record: a gate must have exactly {sorted(_GATE_MEMBERS)}")
        if not isinstance(g["output"], str):
            raise kernel.ClaimError("malformed record: gate 'output' must be a string")
        if g["status"] not in _GATE_STATUS:
            raise kernel.ClaimError(f"malformed record: unknown gate status {g['status']!r}")
        if g["sandbox"] not in _GATE_SANDBOX:
            raise kernel.ClaimError(f"malformed record: unknown gate sandbox {g['sandbox']!r}")

    environment = doc["environment"]
    if not isinstance(environment, dict) or set(environment) != _ENV_KEYS:
        raise kernel.ClaimError(f"malformed record: 'environment' must have exactly {sorted(_ENV_KEYS)}")
    for k, v in environment.items():
        if not isinstance(v, str):
            raise kernel.ClaimError(f"malformed record: environment {k!r} must be a string")

    if "tool" in doc and not isinstance(doc["tool"], str):
        raise kernel.ClaimError("malformed record: 'tool' must be a string")

    if "cost" in doc:
        cost = doc["cost"]
        if not isinstance(cost, dict) or not set(cost) <= _COST_KEYS:
            raise kernel.ClaimError(f"malformed record: 'cost' keys must be a subset of {sorted(_COST_KEYS)}")
        for k, v in cost.items():
            if not _is_num(v) or v < 0:
                raise kernel.ClaimError(f"malformed record: cost {k!r} must be a non-negative number")

    if "producer" in doc:
        producer = doc["producer"]
        if not isinstance(producer, dict) or not set(producer) <= _PRODUCER_KEYS:
            raise kernel.ClaimError(
                f"malformed record: 'producer' keys must be a subset of {sorted(_PRODUCER_KEYS)}")
        for key in ("vendor", "model", "cutoff"):
            if key in producer and not isinstance(producer[key], str):
                raise kernel.ClaimError(f"malformed record: producer {key!r} must be a string")
        if "blind" in producer and not isinstance(producer["blind"], bool):
            raise kernel.ClaimError("malformed record: producer 'blind' must be a boolean")

    if version == 2:
        claim = doc["claim"]
        if not isinstance(claim, dict) or not set(claim) <= _CLAIM_KEYS:
            raise kernel.ClaimError(f"malformed record: 'claim' keys must be a subset of {sorted(_CLAIM_KEYS)}")
        if "tolerance" in claim:
            t = claim["tolerance"]
            if not _is_num(t) or t < 0:
                raise kernel.ClaimError("malformed record: 'claim.tolerance' must be a non-negative number")
        if "mutation_floor" in claim:
            m = claim["mutation_floor"]
            if not _is_num(m) or m < 0:
                raise kernel.ClaimError("malformed record: 'claim.mutation_floor' must be a non-negative number")
        if "envelope" in claim:
            env = claim["envelope"]
            if not isinstance(env, dict) or not env:
                raise kernel.ClaimError("malformed record: 'claim.envelope' must be a non-empty object")
            for unit, ceiling in env.items():
                if unit not in _COST_KEYS:
                    raise kernel.ClaimError(f"malformed record: unknown envelope unit {unit!r}")
                if not _is_num(ceiling) or ceiling <= 0:
                    raise kernel.ClaimError(f"malformed record: envelope {unit!r} must be a positive number")


def canonical(doc: dict) -> bytes:
    """The identity serialization, verbatim: sorted-key JSON, default
    separators, ASCII escaping, encoded UTF-8."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def digest(doc: dict) -> str:
    """The sha256 hex digest of `doc`'s canonical bytes."""
    return hashlib.sha256(canonical(doc)).hexdigest()


def write(doc: dict, path: str) -> None:
    """Write `doc`'s canonical bytes to `path` -- no prettying, no newline."""
    validate(doc)
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    """Read a record from `path`; refused unless its bytes are exactly its
    own canonical form."""
    with open(path, "rb") as f:
        raw = f.read()
    doc = json.loads(raw.decode("utf-8"))
    validate(doc)
    if canonical(doc) != raw:
        raise kernel.ClaimError(f"record at {path!r} is not its own canonical bytes")
    return doc


def _allowed_principals(anchor: str) -> list:
    out = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.append(line.split()[0])
    return out


def _verify_sig(anchor, namespace, principal, sig_path, data: bytes) -> bool:
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
             "-n", namespace, "-s", sig_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def sign(path: str, key: str) -> None:
    """Sign a record at `path` with the existing ssh mechanism, in the
    record namespace, as a detached signature."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
                   check=True, capture_output=True)


def signer(path: str, anchor: str):
    """The principal whose signature over the record at `path` verifies
    against `anchor`, in the record namespace -- or `None`."""
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path) or not os.path.isfile(anchor):
        return None
    try:
        doc = read(path)
    except kernel.ClaimError:
        return None
    data = canonical(doc)
    for principal in _allowed_principals(anchor):
        if _verify_sig(anchor, kernel.RECORD_NAMESPACE, principal, sig_path, data):
            return principal
    return None

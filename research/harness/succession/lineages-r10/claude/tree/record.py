"""record.py: authoring the record (`spec/record.md`) -- the one document
other programs may parse.

Emission re-earns every gate verdict (a record states what one machine
JUST established, never a carried status), the file on disk is its own
canonical bytes, validation closes the vocabulary in band (delegated to
the kernel, which owns the format), and signing lives in the record's
own namespace, distinct from attestation and authorization.
"""
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys

from . import kernel

_CLAIM_KEYS = ("tolerance", "envelope", "mutation_floor")


# ---- canonical bytes -------------------------------------------------------

def canonical(doc) -> bytes:
    """The identity serialization, verbatim: sorted-key JSON, default
    separators, non-ASCII escaped, encoded UTF-8."""
    return json.dumps(doc, sort_keys=True).encode("utf-8")


def digest(doc) -> str:
    return hashlib.sha256(canonical(doc)).hexdigest()


def validate(doc) -> None:
    """The vocabulary is the kernel's to own; this module only authors
    and transports documents in it."""
    kernel.record_validate(doc)


def write(doc, path: str) -> None:
    """The file on disk IS the canonical bytes -- no prettying, no
    trailing newline."""
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    """Read a record back, refusing one whose on-disk bytes are not its
    own canonical form -- a record is its canonical bytes or it is not
    a record."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise kernel.ClaimError(f"no readable record at {path!r}: {exc}") from exc
    validate(doc)
    if raw != canonical(doc):
        raise kernel.ClaimError(f"record at {path!r} is not its own canonical bytes")
    return doc


# ---- emission: re-earn every verdict, relay only what was measured --------

def _environment() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(d: str) -> dict:
    """State what this machine just established about claim `d`: its
    identity, its generated-bytes digest, and its gate verdicts, earned
    now by running them. Refuses a claim whose identity does not hold --
    a record is about a root, and an unsealed or drifted claim has none."""
    vr = kernel.verify(d)
    if not vr["ok"]:
        raise kernel.ClaimError(f"no record for a claim that does not verify: {d!r}")
    parsed = kernel.load_recipe(d)
    aud = kernel.audit(d)

    claim = parsed.get("claim") or {}
    doc = {
        "record": 2,
        "name": claim["name"],
        "root": vr["root"],
        "build_digest": kernel.build_digest(d),
        "claim": {k: claim[k] for k in _CLAIM_KEYS if k in claim},
        "gates": [{"output": g["output"], "status": g["status"], "sandbox": g["quarantine"]}
                  for g in aud["gates"]],
        "environment": _environment(),
        "when": _now(),
    }

    cost = kernel.cost(d)
    if cost is not None:
        doc["cost"] = cost

    producer = None
    for event in reversed(kernel.ledger_events(d)):
        if event.get("event") == "producer":
            producer = {k: v for k, v in event.items() if k != "event"}
            break
    if producer is not None:
        doc["producer"] = producer

    return doc


# ---- signing: the record's own namespace -----------------------------------

def _allowed_identities(anchor: str) -> list:
    with open(anchor, "r", encoding="utf-8") as f:
        lines = f.readlines()
    identities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        identity = line.split()[0]
        if identity not in identities:
            identities.append(identity)
    return identities


def _ssh_verify(allowed_signers: str, identity: str, namespace: str,
                 data: bytes, signature_path: str) -> bool:
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", identity,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True,
        )
    except OSError:
        return False
    return proc.returncode == 0


def sign(path: str, key: str) -> None:
    """Sign a record's canonical bytes (the file on disk) in the
    `reticuli.record` namespace -- distinct from attestation and
    authorization, so a signature made for one purpose can never be
    presented for another."""
    sig_path = path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )


def signer(path: str, anchor: str):
    """The anchored identity whose signature verifies over this
    record's exact on-disk bytes, in the record namespace -- `None` if
    none does, including when the record itself is unreadable or has
    drifted from its own canonical form."""
    try:
        read(path)
    except kernel.ClaimError:
        return None
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    for identity in _allowed_identities(anchor):
        if _ssh_verify(anchor, identity, kernel.RECORD_NAMESPACE, data, sig_path):
            return identity
    return None

"""The record: a signed statement of one machine's results (`spec/record.md`).

A record is produced once, by `emit`, which re-earns every verdict on the
claim's present bytes (`kernel.audit`) rather than trusting any verdict
already on disk -- a failing gate still emits (a failed rebuild is
evidence); a drifted or unsealed claim refuses, since a record is *about*
a root. `canonical`/`digest` are the identity serialization reused for this
format (`spec/identity.md`); `validate` is the kernel's own corrected,
version-2-aware reader (`kernel.record_validate`), so the two stay in
lock-step. `sign`/`signer` are the record's own ssh-signature namespace,
distinct from attestation and authorization.
"""
import json
import os
import platform
import subprocess
import sys

from reticuli import kernel
from reticuli import _util

validate = kernel.record_validate


def canonical(doc: dict) -> bytes:
    """The canonical bytes: sorted-key JSON, default separators, ASCII-escaped."""
    return kernel.record_canonical(doc)


def digest(doc: dict) -> str:
    """The sha256 of the record's canonical bytes."""
    return kernel.record_digest(doc)


def _producer_declaration(d: str):
    """The most recent declared-producer ledger event, relayed verbatim."""
    for event in reversed(kernel.ledger_events(d)):
        if event.get("event") == "producer":
            return {k: event[k] for k in ("vendor", "model", "blind", "cutoff")
                     if k in event}
    return None


def emit(d: str) -> dict:
    """Earn and state what this machine finds for the claim at `d`, now."""
    v = kernel.verify(d)
    if not v["ok"]:
        raise kernel.ClaimError(f"claim at {d!r} is drifted: no record")

    aud = kernel.audit(d)
    recipe = kernel.load_recipe(d)
    claim_tbl = recipe.get("claim", {})

    gates = []
    for g in aud.get("gates", []):
        gates.append({
            "output": g["output"],
            "status": g["status"],
            "sandbox": g.get("quarantine") or "none",
        })

    doc = {
        "record": 2,
        "claim": {k: claim_tbl[k] for k in ("tolerance", "envelope", "mutation_floor")
                   if k in claim_tbl},
        "name": claim_tbl["name"],
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": {
            "platform": sys.platform,
            "machine": platform.machine(),
            "runtime": f"{platform.python_implementation()} {platform.python_version()}",
        },
        "when": _util.stamp(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _producer_declaration(d)
    if producer:
        doc["producer"] = producer

    return doc


def write(doc: dict, path: str) -> None:
    """Write a record's canonical bytes to `path` -- no prettying, no newline."""
    validate(doc)
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    """Parse a record file back; refusals, never a raw crash. Refuses a
    file that is not its own canonical bytes."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise kernel.ClaimError(f"cannot read record {path!r}: {e}") from e
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise kernel.ClaimError(f"malformed record {path!r}: {e}") from e
    validate(doc)
    if raw != canonical(doc):
        raise kernel.ClaimError(f"record {path!r} is not its own canonical bytes")
    return doc


def sign(path: str, key: str) -> None:
    """Sign a record file's bytes, detached, in the record's own namespace."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )


def signer(path: str, anchor: str):
    """The signer identity of `path`'s detached record signature, verified
    against `anchor`. `None` if nothing verifies -- never raises."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        with open(path + ".sig", "rb") as f:
            signature = f.read()
        identities = _util.read_signers(anchor)
    except OSError:
        return None
    for identity in identities:
        if _util.ssh_verify(anchor, identity, kernel.RECORD_NAMESPACE, raw, signature):
            return identity
    return None

"""Authoring records (`spec/record.md`): emitting, writing, signing.

Canonical bytes, validation, and signature verification are the kernel's
own (`kernel.record_canonical`, `kernel.record_validate`, `kernel.record_read`,
`kernel.record_signer`) -- the kernel both produces and consumes records as
crosscheck legs, so it owns the format. This module adds the producing
half the kernel does not: `emit` turns a claim directory's present bytes
into a record document (by re-earning its verdicts), `write` places the
canonical bytes on disk, and `sign` makes the detached signature the
kernel's reader already knows how to verify.

Stdlib only.
"""
import os
import platform
import subprocess
import sys

from reticuli import _util, kernel

RECORD_FORMAT = kernel.RECORD_FORMAT


def canonical(doc: dict) -> bytes:
    return kernel.record_canonical(doc)


def digest(doc: dict) -> str:
    return kernel.record_digest(doc)


def validate(doc) -> dict:
    return kernel.record_validate(doc)


def read(path: str) -> dict:
    return kernel.record_read(path)


def signer(path: str, anchor: str):
    return kernel.record_signer(path, anchor)


def write(doc: dict, path: str) -> None:
    """Write a record's canonical bytes: no prettying, no trailing newline."""
    with open(path, "wb") as f:
        f.write(kernel.record_canonical(doc))


def sign(path: str, key_path: str) -> None:
    """Detached-sign a record file in its own namespace (`reticuli.record`)."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key_path, "-n",
         kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True)


def _environment() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} "
                   f"{platform.python_version()}",
    }


def _producer_declared(d: str):
    info = kernel.independence(d)
    if not info.get("vendor") and not info.get("model"):
        return None
    producer = {}
    for key in ("vendor", "model", "blind"):
        if info.get(key) is not None:
            producer[key] = info[key]
    return producer or None


def emit(d: str) -> dict:
    """Earn and state a record of `d`'s present bytes (`spec/record.md`).

    Precondition: identity must hold (`spec/record.md`, "Precondition") -- a
    claim that fails `verify` gets a refusal, never a record. A failing gate
    still emits: a failed rebuild is evidence.
    """
    v = kernel.verify(d)
    if not v["ok"]:
        raise kernel.ClaimError(
            f"cannot record {d!r}: identity does not hold (bytes do not "
            f"recompute to the sealed root)")

    parsed = kernel.load_recipe(d)
    claim = parsed.get("claim", {})
    claim_obligations = {}
    for key in ("tolerance", "mutation_floor"):
        if key in claim:
            claim_obligations[key] = claim[key]
    if "envelope" in claim:
        claim_obligations["envelope"] = claim["envelope"]

    a = kernel.audit(d)
    gate_steps = [s for s in parsed.get("step", []) if s.get("kind") == "gate"]
    gate_rows = []
    for i, step in enumerate(gate_steps):
        row = a["gates"][i] if i < len(a["gates"]) else {}
        gate_rows.append({
            "output": step["output"],
            "status": row.get("status", a.get("verdict", "environment")),
            "sandbox": row.get("quarantine") or "none",
        })

    doc = {
        "record": 2,
        "claim": claim_obligations,
        "name": claim.get("name"),
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gate_rows,
        "environment": _environment(),
        "when": _util.stamp(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _producer_declared(d)
    if producer:
        doc["producer"] = producer

    return doc

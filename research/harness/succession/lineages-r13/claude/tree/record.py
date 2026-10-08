"""Authoring a record: emitting, writing, and signing one machine's
statement (spec/record.md). Reading, validating, and consuming a record
as a crosscheck leg belong to the kernel, which already owns the format
(`spec/kernel-api.md`); this module adds only the write half.

`emit` may be called only once a claim's identity holds -- a record is
*about* a root, and an unsealed or drifted claim has nothing to be about.
A failing gate still emits: a failed rebuild is evidence.
"""
import os
import platform
import subprocess
import sys

from . import _util
from . import kernel

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read
signer = kernel.record_signer


def _environment() -> dict:
    return {"platform": platform.system().lower(), "machine": platform.machine(),
            "runtime": f"{platform.python_implementation()} {sys.version.split()[0]}"}


def _producer_from_ledger(d: str):
    for event in reversed(kernel.ledger_events(d)):
        if event.get("event") == "producer":
            info = {k: event[k] for k in ("vendor", "model", "blind", "cutoff")
                     if event.get(k) is not None}
            return info or None
    return None


def emit(d: str) -> dict:
    """Recompute identity, re-earn every gate, and state the result as a
    version-2 record: `claim` carries the recipe's declared obligations
    verbatim, `{}` when it declares none."""
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(
            f"emit refuses: {d!r} does not verify against its sealed root")
    recipe = kernel.load_recipe(d)
    claim_tbl = recipe.get("claim", {}) or {}
    audit_result = kernel.audit(d)
    gates = [{"output": g["output"], "status": g["status"],
              "sandbox": g.get("quarantine") or "none"}
             for g in audit_result.get("gates", [])]

    doc = {
        "record": 2,
        "name": recipe["claim"]["name"],
        "root": verified["root"],
        "build_digest": kernel.build_digest(d),
        "claim": {k: claim_tbl[k] for k in ("tolerance", "envelope", "mutation_floor")
                  if k in claim_tbl},
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


def write(doc: dict, path: str) -> None:
    """The file on disk IS the canonical bytes: no prettying, no newline."""
    with open(path, "wb") as f:
        f.write(canonical(doc))


def sign(path: str, key: str) -> None:
    """Detached ssh signature over the record's canonical bytes, in the
    record namespace. A stale signature is removed first -- `ssh-keygen
    -Y sign` otherwise prompts interactively before overwriting one."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
                   check=True, capture_output=True)

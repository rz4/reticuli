"""Authoring a record: emit, write, sign (spec/record.md).

The kernel owns the record FORMAT and consumes records as crosscheck legs;
this module is the other half — producing one, putting it on disk, and
signing it in the record's own namespace.

A record may be produced only when the claim's identity HOLDS: a record is
*about* a root, and if the bytes present do not hash to one there is nothing
to be about.  Gate failure is the opposite case — a record whose gates failed
is valid and worth keeping, because a failed rebuild is evidence about the
claim — and it states the failure plainly.

Two rules give `cost` its meaning: it is the cost of PRODUCING the generated
bytes (gate runtime is outside the document entirely), and **an absent key
means unmeasured, which is never written as zero** — so a reader can always
tell "free" from "unknown".
"""
import os
import shutil
import subprocess

from . import _util, kernel

#: The record's own signature namespace.  A record signature says "these are
#: the results I obtained"; it must never authorize an implementation.
NAMESPACE = kernel.RECORD_NAMESPACE
#: The version this module emits.
FORMAT = kernel.RECORD_FORMAT

_OBLIGATIONS = ("tolerance", "envelope", "mutation_floor")
_PRODUCER_KEYS = ("vendor", "model", "blind", "cutoff")


def emit(claimdir: str) -> dict:
    """Earn this claim's verdicts now and state what was established."""
    checked = kernel.verify(claimdir)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"{claimdir!r} does not verify, so it has no record: a record is "
            f"about a root, and these bytes do not hash to one")
    parsed = kernel.load_recipe(claimdir)
    declared = parsed.get("claim") or {}
    verdict = kernel.audit(claimdir)
    doc = {
        "record": FORMAT,
        "name": checked["name"],
        "root": checked["recomputed"],
        "build_digest": kernel.build_digest(claimdir),
        # `{}` states, positively, that the recipe declares no obligations —
        # a statement a version-1 record could not make.
        "claim": {key: declared[key] for key in _OBLIGATIONS
                  if key in declared},
        "gates": [{"output": gate["output"], "status": gate["status"],
                   "sandbox": gate.get("quarantine") or "none"}
                  for gate in verdict["gates"]],
        "environment": {
            "platform": kernel._judging_host()["platform"],
            "machine": kernel._judging_host()["machine"],
            "runtime": kernel._judging_host()["python"],
        },
        "when": _util.stamp(),
    }
    totals = kernel.cost(claimdir) or {}
    measured = {unit: value for unit, value in totals.items()
                if unit in kernel.COST_KEYS}
    if measured:
        doc["cost"] = measured
    producer = {}
    for event in kernel.ledger_events(claimdir):
        if event.get("event") != "producer":
            continue
        for key in _PRODUCER_KEYS:
            if key in event and event[key] is not None:
                producer[key] = event[key]
    if producer:
        doc["producer"] = producer
    kernel.record_validate(doc)
    return doc


def validate(doc) -> dict:
    """Refuse anything this format does not admit, in band."""
    return kernel.record_validate(doc)


def canonical(doc) -> bytes:
    """The record's canonical bytes — validated first, always."""
    return kernel.record_canonical(doc)


def digest(doc) -> str:
    """The record digest: how a record is cited."""
    return kernel.record_digest(doc)


def write(doc, path: str) -> str:
    """Put a record on disk as exactly its own canonical bytes."""
    payload = canonical(doc)
    if path in ("-", "/dev/stdout"):
        import sys
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
        return path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def read(path: str) -> dict:
    """Read a record file, which must hold exactly its own canonical bytes."""
    return kernel.record_read(path)


def sign(path: str, key: str) -> str:
    """Sign a record's canonical bytes in the record namespace."""
    if not shutil.which("ssh-keygen"):
        raise kernel.ClaimError(
            "ssh-keygen is not on PATH, so nothing can be signed here")
    read(path)                      # never sign what a reader would refuse
    signature = path + ".sig"
    if os.path.isfile(signature):
        os.remove(signature)        # ssh-keygen prompts before overwriting
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0 or not os.path.isfile(signature):
        raise kernel.ClaimError(
            f"signing failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return signature


def signer(path: str, anchor: str = None):
    """Who signed this record, as the verifier's own anchor sees it."""
    return kernel.record_signer(path, anchor)

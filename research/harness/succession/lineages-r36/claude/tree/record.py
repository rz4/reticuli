"""Authoring a record: emitting, writing, signing (spec/record.md).

The kernel owns the FORMAT -- canonical bytes, the closed vocabulary, the
refusals, consuming a record as a crosscheck leg. What belongs here is
producing one: re-earning the gates so the results are this machine's own,
relaying the measurements it actually has, and signing the canonical bytes
in the record's own namespace.

A record is ABOUT a root, so a claim whose bytes do not recompute to its
sealed root gets a refusal rather than a record. Gate failure is the
opposite case: a record whose gates failed is valid and worth keeping -- a
failed rebuild is evidence about the claim -- and it says so plainly.
"""
import os
import platform
import shutil
import subprocess
import sys

from . import _util
from . import kernel

NAMESPACE = kernel.RECORD_NAMESPACE
FORMAT = kernel.RECORD_FORMAT
OBLIGATIONS = ("tolerance", "envelope", "mutation_floor")
PRODUCER_KEYS = ("vendor", "model", "blind", "cutoff")


def _environment() -> dict:
    return {"platform": sys.platform,
            "machine": platform.machine() or "unknown",
            "runtime": f"{platform.python_implementation()} "
                       f"{platform.python_version()}"}


def _producer(claim: str):
    """What the ledger was TOLD about who produced the bytes. Testimony,
    relayed as given -- never invented, never completed with defaults."""
    told = {}
    for event in kernel.ledger_events(claim):
        if event.get("event") != "producer":
            continue
        for key in PRODUCER_KEYS:
            if key in event and event[key] is not None:
                told[key] = event[key]
    return told or None


def _cost(claim: str):
    """The measured production cost, in the four units the format fixes.

    An absent key means UNMEASURED, and unmeasured is never written as zero:
    a reader can always tell "free" from "unknown". The discovery bill is
    not part of this vocabulary and stays out of the document.
    """
    totals = kernel.cost(claim)
    if not totals:
        return None
    kept = {k: v for k, v in totals.items() if k in kernel.COST_KEYS}
    return kept or None


def emit(claim: str) -> dict:
    """Earn the verdicts now, and state what this machine established."""
    try:
        checked = kernel.verify(claim)
    except kernel.ClaimError as exc:
        raise kernel.ClaimError(
            f"a record is about a root, and {claim} has none: {exc}") from None
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"the bytes present do not recompute to {claim}'s sealed root, so "
            f"there is nothing for a record to be about")
    verdict = kernel.audit(claim)
    parsed = kernel.load_recipe(claim)
    declared = parsed.get("claim") or {}
    doc = {"record": FORMAT,
           "name": checked["name"],
           "root": checked["root"],
           "build_digest": kernel.build_digest(claim),
           "claim": {k: declared[k] for k in OBLIGATIONS if k in declared},
           "gates": [{"output": g["output"], "status": g["status"],
                      "sandbox": g.get("quarantine") or "none"}
                     for g in verdict["gates"]],
           "environment": _environment(),
           "when": _util.stamp()}
    totals = _cost(claim)
    if totals:
        doc["cost"] = totals
    told = _producer(claim)
    if told:
        doc["producer"] = told
    return validate(doc)


def validate(doc):
    return kernel.record_validate(doc)


def canonical(doc) -> bytes:
    return kernel.record_canonical(doc)


def digest(doc) -> str:
    return kernel.record_digest(doc)


def read(path: str) -> dict:
    return kernel.record_read(path)


def write(doc, path: str) -> str:
    """The file IS the canonical bytes: no prettying, no trailing newline."""
    payload = canonical(doc)
    if path == "-":
        sys.stdout.buffer.write(payload)
        return path
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def sign(path: str, key: str) -> str:
    """Sign a record's canonical bytes in the record's OWN namespace.

    Distinct from `reticuli` (attestation) and `reticuli.mint`
    (authorization) for the same reason those two are distinct from each
    other: a signature stating "these are the results I obtained" must
    never authorize an implementation.
    """
    if not shutil.which("ssh-keygen"):
        raise kernel.ClaimError("ssh-keygen is not on this host")
    read(path)                            # a record, or no signature
    signature = path + ".sig"
    if os.path.isfile(signature):
        os.remove(signature)
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise kernel.ClaimError(
            f"the record could not be signed: "
            f"{(done.stderr or done.stdout).strip()[-200:]}")
    return signature


def signer(path: str, signers: str | None = None):
    """Who signed this record, as named by the verifier's own anchor."""
    return kernel.record_signer(
        path, signers or os.environ.get("RETICULI_SIGNERS"))

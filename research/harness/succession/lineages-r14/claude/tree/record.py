"""Authoring records: the one document other programs may parse
(spec/record.md). Emission earns its verdicts by auditing cold, the file
on disk IS the canonical bytes, validation closes the vocabulary in band,
and the signature lives in the record's own namespace -- distinct from
attestation and authorization. Consuming a record as a crosscheck leg is
the kernel's own, already-pinned half (`kernel.crosscheck`); this module is
the exchange layer's: emit, write, and sign one.
"""
import os
import platform
import subprocess
import sys

from reticuli import kernel, _util

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read

_CLAIM_KEYS = ("tolerance", "envelope", "mutation_floor")
_PRODUCER_KEYS = ("vendor", "model", "blind", "cutoff")


def _judging_host() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _producer_declaration(d: str):
    """The most recent producer declaration on `d`'s ledger, if any --
    relayed as given, never invented (spec/record.md)."""
    events = [e for e in kernel.ledger_events(d) if e.get("event") == "producer"]
    if not events:
        return None
    last = events[-1]
    decl = {k: last[k] for k in _PRODUCER_KEYS if k in last}
    return decl or None


def emit(d: str) -> dict:
    """What one machine establishes about `d` right now: identity
    recomputed, every gate re-earned cold, and declared obligations relayed
    verbatim. Refuses a claim whose identity does not hold -- a record is
    about a root, and a drifted claim names none."""
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(f"a drifted claim has no record: {d!r}")

    manifest = kernel.read_manifest(d)
    parsed = kernel.load_recipe(d)
    audited = kernel.audit(d)
    gates = [{"output": g["output"], "status": g["status"], "sandbox": g.get("quarantine") or "none"}
             for g in audited["gates"]]

    claim = parsed.get("claim", {})
    claim_extras = {k: claim[k] for k in _CLAIM_KEYS if k in claim}

    doc = {
        "record": kernel.RECORD_FORMAT,
        "name": manifest["name"],
        "root": verified["root"],
        "build_digest": kernel.build_digest(d),
        "claim": claim_extras,
        "gates": gates,
        "environment": _judging_host(),
        "when": _util.stamp(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _producer_declaration(d)
    if producer:
        doc["producer"] = producer

    kernel.record_validate(doc)
    return doc


def write(doc: dict, path: str) -> None:
    """The file on disk IS the canonical bytes: no prettying, no newline."""
    with open(path, "wb") as f:
        f.write(kernel.record_canonical(doc))


def sign(path: str, key: str) -> None:
    """Sign the record at `path` (already its own canonical bytes) in its
    own namespace, `reticuli.record` -- distinct from attestation and
    authorization, so one signature can never stand in for another."""
    # ssh-keygen -Y sign prompts before overwriting an existing `.sig`,
    # which hangs/refuses with no stdin to answer it -- a re-sign over the
    # same path must remove the stale one first.
    sig_path = path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
                    check=True, capture_output=True)


def signer(path: str, anchor: str):
    """The identity whose signature over the record at `path` verifies
    against `anchor`, or `None`. First demands the file IS its own
    canonical bytes -- `kernel.record_signer` verifies against a
    RE-SERIALIZATION of the parsed document, so a byte the parse ignores
    (trailing whitespace) would otherwise slip past it; the record's own
    promise ("the file on disk is the canonical bytes") is enforced here,
    in band, before any cryptography runs."""
    try:
        kernel.record_read(path)
    except kernel.ClaimError:
        return None
    return kernel.record_signer(path, anchor)

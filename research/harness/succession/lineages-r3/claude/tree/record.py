"""Authoring a record: the one document other programs may parse
(spec/record.md). The kernel already owns the format -- canonical bytes,
validation, reading, and signature verification are pinned on
`reticuli.kernel` (`record_canonical`/`record_digest`/`record_validate`/
`record_read`/`record_signer`) because it also consumes a record as a
crosscheck leg. This module is the authoring half: emitting one from a
claim's own present bytes, writing it, and signing it in the record's
own namespace.
"""
import os
import platform
import subprocess
import sys

from reticuli import _util
from reticuli import kernel


def emit(d: str) -> dict:
    """A record of `d`'s present state: refuses unless identity holds
    (a record is about a root, and a claim that does not verify has
    nothing to be about). Gate failure is not refused -- a failed
    rebuild is evidence.
    """
    vr = kernel.verify(d)
    if not vr["ok"]:
        raise kernel.ClaimError(f"claim at {d!r} does not verify; no record")

    parsed = kernel.load_recipe(d)
    aud = kernel.audit(d)
    gates = [{"output": g["output"], "status": g["status"], "sandbox": g.get("quarantine") or "none"}
             for g in aud.get("gates", [])]

    claim_section = parsed.get("claim", {})
    claim_decl = {}
    for key in ("tolerance", "envelope", "mutation_floor"):
        if key in claim_section:
            claim_decl[key] = claim_section[key]

    doc = {
        "record": 2,
        "name": vr["name"],
        "root": vr["root"],
        "build_digest": kernel.build_digest(d),
        "claim": claim_decl,
        "gates": gates,
        "environment": {
            "platform": sys.platform,
            "machine": platform.machine(),
            "runtime": f"CPython {platform.python_version()}",
        },
        "when": _util.stamp(),
        "tool": "reticuli-exchange",
    }

    cost_totals = kernel.cost(d)
    if cost_totals:
        doc["cost"] = cost_totals

    producer = kernel.independence(d)
    if producer and producer.get("vendor"):
        doc["producer"] = producer

    return doc


def canonical(doc: dict) -> bytes:
    return kernel.record_canonical(doc)


def digest(doc: dict) -> str:
    return kernel.record_digest(doc)


def validate(doc) -> None:
    kernel.record_validate(doc)


def write(doc: dict, path: str) -> None:
    """Write `doc`'s canonical bytes to `path` -- no prettying, no
    trailing newline: the file on disk IS the canonical bytes.
    """
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    return kernel.record_read(path)


def sign(path: str, key: str) -> None:
    """Sign the record at `path` with the existing ssh mechanism, in the
    record's own namespace (spec/record.md, "Signing") -- distinct from
    attestation and from authorization.
    """
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)  # ssh-keygen -Y sign prompts before overwriting one
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )


def signer(path: str, allowed_signers: str):
    return kernel.record_signer(path, allowed_signers)

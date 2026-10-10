"""Records: the one document other programs may parse (spec/record.md).

`emit` earns a record by re-auditing the claim cold and reading its
identity fresh -- a record is produced once, by re-earning, never by
copying a manifest bit. `canonical`/`digest`/`validate`/`read` are the
kernel's own record reader, used here under the exchange layer's names.
`write` puts exactly the canonical bytes on disk, no prettying, no
trailing newline, so the digest a signature covers is what a reader gets
back. `sign`/`signer` are the record's own signing namespace, distinct
from attestation and from the signing ceremony: `signer` insists the file
on disk IS its own canonical bytes (not merely that it parses), so one
appended byte kills a signature no re-canonicalization would notice.
"""
import os
import platform
import subprocess
import sys

from . import kernel
from . import _util

RECORD_NAMESPACE = kernel.RECORD_NAMESPACE
RECORD_FORMAT = kernel.RECORD_FORMAT

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate


def _environment() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _producer(d: str):
    for event in reversed(kernel.ledger_events(d)):
        if event.get("event") == "producer":
            out = {}
            for key in ("vendor", "model", "blind", "cutoff"):
                if key in event and event[key] is not None:
                    out[key] = event[key]
            return out or None
    return None


def emit(d: str) -> dict:
    """Earn a record of `d`: refuses unless identity holds, then
    re-audits cold so its gate results are fresh fact, never carried."""
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(f"record: {d!r} does not verify, there is nothing to record")

    manifest = kernel.read_manifest(d)
    audited = kernel.audit(d)
    recipe = kernel.load_recipe(d)
    claim = recipe.get("claim", {}) or {}
    obligations = {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor") if k in claim}

    gates = [
        {"output": g["output"], "status": g["status"], "sandbox": g.get("quarantine") or "none"}
        for g in audited["gates"]
    ]

    doc = {
        "record": 2,
        "claim": obligations,
        "name": manifest["name"],
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": _environment(),
        "when": _util.stamp(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _producer(d)
    if producer:
        doc["producer"] = producer
    return doc


def write(doc: dict, path: str) -> None:
    """The record's canonical bytes, nothing else: no prettying, no
    trailing newline."""
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    """Read a record, refusing any file whose bytes are not exactly its
    own canonical serialization."""
    return kernel.record_read(path)


def _signers(anchor: str) -> list:
    if not anchor or not os.path.isfile(anchor):
        return []
    names = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            who = line.split(None, 1)[0]
            names.extend(who.split(","))
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _ssh_verify(data: bytes, sig_path: str, anchor: str, namespace: str, principal: str) -> bool:
    if not os.path.isfile(sig_path):
        return False
    result = subprocess.run(
        ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", principal,
         "-n", namespace, "-s", sig_path],
        input=data, capture_output=True, timeout=30,
    )
    return result.returncode == 0


def sign(path: str, key: str) -> str:
    """Sign a record's canonical bytes in its own namespace, detached,
    at `path + ".sig"`."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )
    return sig_path


def signer(path: str, anchor: str):
    """Which principal `anchor` lists signed the record at `path`, or
    `None` -- refuses a file that is not its own canonical bytes before
    ever checking a signature, so a single appended byte kills it."""
    try:
        doc = kernel.record_read(path)
    except kernel.ClaimError:
        return None
    canon = canonical(doc)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path):
        return None
    for principal in _signers(anchor):
        if _ssh_verify(canon, sig_path, anchor, RECORD_NAMESPACE, principal):
            return principal
    return None

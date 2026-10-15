"""Records: the one document other programs may parse (`spec/record.md`).

Emission (`emit`) earns its verdicts -- it runs `kernel.audit` fresh, never
relays a carried status -- and refuses a claim whose identity does not
hold: a record is ABOUT a root, and a drifted or unsealed claim has
nothing to be about. The canonicalization, digesting, validation, reading,
and signer-identity reader are the kernel's own pinned record format
(`spec/kernel-api.md`'s v2.2 revision); this module only adds the two
things that are the EXCHANGE layer's: building a fresh record from a
claim, and signing one in its own namespace.
"""
import os
import platform
import subprocess

from reticuli import kernel
from . import _util

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read


def _ssh_verify(data: bytes, signature_path: str, namespace: str,
                 allowed_signers: str, principal) -> bool:
    if not principal or not os.path.isfile(signature_path) or not os.path.isfile(allowed_signers):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers, "-I", principal,
             "-n", namespace, "-s", signature_path],
            input=data, capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def signer(path: str, anchor: str):
    """The principal whose signature over the record at `path` verifies
    against `anchor`, or `None` if unsigned, signed by no key the anchor
    trusts, or the file is not its own canonical bytes (`kernel.record_read`
    enforces that bond -- a reformatted or tampered file names nothing)."""
    try:
        doc = kernel.record_read(path)
    except kernel.ClaimError:
        return None
    canon = kernel.record_canonical(doc)
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path) or not os.path.isfile(anchor):
        return None
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            principal = line.split()[0]
            if _ssh_verify(canon, sig_path, kernel.RECORD_NAMESPACE, anchor, principal):
                return principal
    return None

_OBLIGATION_KEYS = ("tolerance", "envelope", "mutation_floor")
_RECORD_SANDBOXES = frozenset({"none", "seatbelt", "bubblewrap", "inherited"})


def _environment() -> dict:
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _last_producer(d: str):
    producer = {}
    for event in kernel.ledger_events(d):
        if event.get("event") == "producer":
            for key in ("vendor", "model", "blind", "cutoff"):
                if key in event:
                    producer[key] = event[key]
    return producer or None


def emit(d: str) -> dict:
    """Build a fresh record of `d`: what this machine establishes about
    one claim at one time, by recomputing identity and re-running gates."""
    ver = kernel.verify(d)
    if not ver["ok"]:
        raise kernel.ClaimError("a drifted claim has no record")

    parsed = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    au = kernel.audit(d)

    gates = []
    for g in au.get("gates", []):
        backend = g.get("quarantine")
        sandbox = backend if backend in _RECORD_SANDBOXES else "none"
        gates.append({"output": g["output"], "status": g["status"], "sandbox": sandbox})

    claim = parsed.get("claim", {})
    obligations = {k: claim[k] for k in _OBLIGATION_KEYS if k in claim}

    doc = {
        "record": 2,
        "claim": obligations,
        "name": manifest.get("name"),
        "root": ver["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": _environment(),
        "when": _util.stamp(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost
    producer = _last_producer(d)
    if producer:
        doc["producer"] = producer

    kernel.record_validate(doc)
    return doc


def write(doc: dict, path: str) -> None:
    """Write a record's canonical bytes verbatim: no prettying, no
    trailing newline -- the file on disk IS the canonical bytes."""
    data = kernel.record_canonical(doc)
    with open(path, "wb") as f:
        f.write(data)


def sign(path: str, key: str) -> None:
    """Sign a record file with the existing ssh mechanism, in its own
    namespace (`reticuli.record`) -- distinct from attestation and
    authorization, so one signature can never stand for another's purpose."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
                   check=True, capture_output=True)

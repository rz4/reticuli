"""Records: the one document other programs may parse (`spec/record.md`).

`emit` states what THIS machine establishes about one claim right now: its
identity (refusing an unsealed or drifted claim -- a record is about a root
that holds), the gate verdicts earned by running them again, and whatever
cost/producer bookkeeping was actually measured, relayed verbatim and never
invented. `canonical`/`digest`/`validate`/`read` are the kernel's own format
functions, exposed under the exchange layer's names. `write` lays down a
record's canonical bytes with no prettying and no trailing newline, so the
file IS the thing that gets signed. `sign`/`signer` operate in the record's
own signature namespace, over the file's literal bytes -- domain-separated
from both the plain attestation and the authorization ceremony.

Stdlib only.
"""
import json
import os
import platform
import shutil
import subprocess

from reticuli import _util, kernel

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read

_PRODUCER_KEYS = ("vendor", "model", "blind", "cutoff")


def _environment_block() -> dict:
    return {
        "platform": platform.system().lower(),
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _producer_block(d: str):
    events = [e for e in kernel.ledger_events(d) if e.get("event") == "producer"]
    if not events:
        return None
    last = events[-1]
    block = {k: last[k] for k in _PRODUCER_KEYS if k in last}
    return block or None


def emit(d: str) -> dict:
    """Build a version-2 record of claim `d` right now: refuses unless the
    claim's identity currently holds, then earns every gate's verdict fresh.
    """
    v = kernel.verify(d)
    if not v["ok"]:
        raise kernel.ClaimError(f"claim {d!r} does not verify: no record of a drifted claim")

    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    claim = doc.get("claim", {})
    declared = {k: claim[k] for k in ("tolerance", "envelope", "mutation_floor") if k in claim}

    gates = []
    for step in doc.get("step", []):
        if step.get("kind") != "gate":
            continue
        output = step["output"]
        result = kernel.run_gate(step["run"], d, doc)
        status = result["status"]
        if status == "ok":
            full = os.path.join(d, output)
            if not os.path.isfile(full):
                status = "mismatch"
            else:
                pinned = (manifest.get("parts") or {}).get("pinned:" + output)
                if pinned is not None:
                    with open(full, "rb") as f:
                        current = _util.hash_bytes(f.read())
                    if current != pinned:
                        status = "mismatch"
        gates.append({"output": output, "status": status, "sandbox": result["quarantine"]})

    document = {
        "record": 2,
        "claim": declared,
        "name": manifest["name"],
        "root": manifest["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": _environment_block(),
        "when": _util.stamp(),
    }
    cost = kernel.cost(d)
    if cost is not None:
        document["cost"] = cost
    producer = _producer_block(d)
    if producer is not None:
        document["producer"] = producer
    return document


def write(doc: dict, path: str) -> None:
    """Lay down `doc`'s canonical bytes at `path` -- no prettying, no
    trailing newline, so the file is exactly what gets signed.
    """
    with open(path, "wb") as f:
        f.write(canonical(doc))


def _allowed_identities(allowed_signers: str) -> list:
    identities = []
    with open(allowed_signers, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split(" ", 1)[0]
            identities.extend(head.split(","))
    return identities


def _ssh_verify(allowed_signers: str, identity_name: str, namespace: str,
                 signature_path: str, data: bytes) -> bool:
    if not shutil.which("ssh-keygen"):
        return False
    try:
        proc = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", allowed_signers,
             "-I", identity_name, "-n", namespace, "-s", signature_path],
            input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def sign(path: str, key: str) -> None:
    """Sign the record at `path`, over its literal current bytes, in the
    record's own namespace -- removing any stale `.sig` first, since
    `ssh-keygen -Y sign` prompts interactively before overwriting one.
    """
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
                    check=True, capture_output=True)


def signer(path: str, anchor: str):
    """The identity that signed the record at `path`, verified against
    `anchor`, over the file's literal bytes -- one changed byte, or a
    signature made in any other namespace, verifies as nobody.
    """
    sig_path = path + ".sig"
    if not anchor or not os.path.isfile(anchor) or not os.path.isfile(sig_path):
        return None
    with open(path, "rb") as f:
        raw = f.read()
    for identity_name in _allowed_identities(anchor):
        if _ssh_verify(anchor, identity_name, kernel.RECORD_NAMESPACE, sig_path, raw):
            return identity_name
    return None

"""reticuli.record -- authoring the record (`spec/record.md`).

The kernel *owns* the record format and *consumes* records as crosscheck
legs (`reticuli.kernel.record_validate` / `record_read` / `record_signer`,
version-2-aware). This module is the other half: *producing* one --
`emit` earns a claim's verdicts fresh (via `kernel.audit`) and states them
in the document's shape, `write`/`read` round-trip its canonical bytes
exactly, and `sign`/`signer` carry the ssh signature in the record's own
namespace (`reticuli.record`, distinct from attestation and mint).
"""
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

from . import kernel

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _environment() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


_CLAIM_OBLIGATIONS = ("tolerance", "envelope", "mutation_floor")


def emit(d: str) -> dict:
    """Earn and state one machine's results about `d` (`spec/record.md`).

    Refuses (raises `kernel.ClaimError`) a claim whose identity does not
    hold -- unsealed, or drifted from its sealed root -- since a record is
    *about* a root, and there is nothing to be about otherwise. A failing
    gate still emits: a failed rebuild is evidence, stated plainly.
    """
    v = kernel.verify(d)
    if not v["ok"]:
        raise kernel.ClaimError(f"claim identity does not hold, no record: {d!r}")

    aud = kernel.audit(d)
    gates = [
        {"output": g["output"], "status": g["status"], "sandbox": g.get("quarantine") or "none"}
        for g in aud.get("gates", [])
    ]

    recipe = kernel.load_recipe(d)
    obligations = {k: recipe.get("claim", {})[k]
                   for k in _CLAIM_OBLIGATIONS if k in recipe.get("claim", {})}

    doc = {
        "record": 2,
        "claim": obligations,
        "name": v["name"],
        "root": v["root"],
        "build_digest": kernel.build_digest(d),
        "gates": gates,
        "environment": _environment(),
        "when": _now(),
    }

    cost = kernel.cost(d)
    if cost:
        doc["cost"] = cost

    producer = {k: val for k, val in kernel.independence(d).items() if val is not None}
    if producer:
        doc["producer"] = producer

    return doc


def write(doc: dict, path: str) -> None:
    """Write `doc` to `path` as exactly its canonical bytes."""
    with open(path, "wb") as f:
        f.write(canonical(doc))


def sign(path: str, key: str) -> str:
    """Sign the record at `path` with `key`, in the `reticuli.record`
    namespace; returns the signature's path."""
    sig_path = path + ".sig"
    if os.path.exists(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )
    return sig_path


def _anchor_principals(anchor: str) -> list:
    principals = []
    with open(anchor, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            principals.append(line.split()[0])
    return principals


def signer(path: str, anchor: str):
    """The identity that verifiably signed the record at `path`, against
    `anchor` (an ssh `allowed_signers` file) -- `None` if the record
    cannot be read, is unsigned, or no candidate identity verifies."""
    try:
        doc = read(path)
    except kernel.ClaimError:
        return None
    sig_path = path + ".sig"
    if not os.path.isfile(sig_path) or not os.path.isfile(anchor):
        return None
    data = canonical(doc)
    for candidate in _anchor_principals(anchor):
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", anchor, "-I", candidate,
             "-n", kernel.RECORD_NAMESPACE, "-s", sig_path],
            input=data, capture_output=True, timeout=30, check=False,
        )
        if done.returncode == 0:
            return candidate
    return None

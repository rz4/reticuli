"""Authoring a record: the one document other programs may parse
(`spec/record.md`). The kernel owns the record FORMAT (parsing, validating,
canonical bytes, consuming one as a crosscheck leg); this module owns
EMITTING one -- earning its verdicts by re-running the gates, writing it in
its own canonical bytes, and signing it in its own namespace
(`reticuli.record`, distinct from attestation and authorization).

Stdlib only.
"""
import os
import platform
import subprocess
import sys

from . import _util
from . import kernel

_OBLIGATIONS = ("tolerance", "envelope", "mutation_floor")


def _environment() -> dict:
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def emit(d: str) -> dict:
    """Produce a version-2 record for `d`: refuses (in band) a claim that
    is unsealed or whose identity has drifted -- a record is ABOUT a root,
    and nothing is about a root the bytes present do not recompute to. A
    failing gate still emits; it is evidence.
    """
    d = os.path.abspath(d)
    verified = kernel.verify(d)
    if not verified["ok"]:
        raise kernel.ClaimError(f"refused: claim at {d!r} is unsealed or drifted")

    recipe = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    root_value = verified["root"]
    digest = kernel.build_digest(d)

    gate_rows = []
    for step in recipe.get("step", []):
        if step.get("kind") != "gate":
            continue
        result = kernel.run_gate(step["run"], d, recipe)
        gate_rows.append({"output": step["output"], "status": result["status"],
                          "sandbox": result["quarantine"]})

    claim = recipe.get("claim", {})
    obligations = {k: claim[k] for k in _OBLIGATIONS if k in claim}

    doc = {
        "record": 2,
        "claim": obligations,
        "name": manifest["name"],
        "root": root_value,
        "build_digest": digest,
        "gates": gate_rows,
        "environment": _environment(),
        "when": _util.stamp(),
    }

    totals = kernel.cost(d)
    if totals:
        doc["cost"] = totals

    producer = kernel.independence(d)
    declared = {k: v for k, v in producer.items() if v is not None}
    if declared:
        doc["producer"] = declared

    return doc


def canonical(doc) -> bytes:
    return kernel.record_canonical(doc)


def digest(doc) -> str:
    return kernel.record_digest(doc)


def validate(doc) -> None:
    kernel.record_validate(doc)


def write(doc, path: str) -> None:
    """Write a record's canonical bytes, exactly -- no prettying, no
    trailing newline."""
    with open(path, "wb") as f:
        f.write(canonical(doc))


def read(path: str) -> dict:
    """Read and validate a record file; refuses unless the file on disk IS
    its own canonical bytes."""
    return kernel.record_read(path)


def sign(path: str, key: str) -> None:
    """Sign a record file in its own namespace (`reticuli.record`),
    detached, over its exact bytes. Removes a stale signature first --
    `ssh-keygen -Y sign` prompts before overwriting one."""
    sig_path = path + ".sig"
    if os.path.isfile(sig_path):
        os.remove(sig_path)
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n", kernel.RECORD_NAMESPACE, path],
        check=True, capture_output=True,
    )


def signer(path: str, anchor: str):
    """The anchored identity that signed `path`'s record, or `None` when
    unsigned, untrusted, or signed for a different purpose."""
    try:
        return kernel.record_signer(path, anchor)
    except kernel.ClaimError:
        return None

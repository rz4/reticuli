"""Authoring a record: the one document this project promises others may parse.

The kernel owns the FORMAT (spec/record.md) and consumes records as crosscheck
legs. Emitting one -- earning the verdicts, writing the canonical bytes,
signing them in the record's own namespace -- belongs here.
"""
import os
import platform
import subprocess
import sys

from . import kernel


def _obligations(parsed: dict) -> dict:
    """The conditions the recipe declares, relayed verbatim.

    An empty table states, positively, that the recipe declares none -- which
    a version-1 record could not say, and which is why version 2 exists.
    """
    table = parsed.get("claim") or {}
    return {key: table[key] for key in
            ("tolerance", "envelope", "mutation_floor") if key in table}


def emit(claim: str, producer: dict | None = None) -> dict:
    """Re-earn the gates and state what this machine established.

    A record is ABOUT a root: a claim whose bytes do not recompute to the
    sealed value gets a refusal, not a record. A record whose gates FAILED is
    valid and worth keeping -- a failed rebuild is evidence about the claim.
    """
    checked = kernel.verify(claim)
    if not checked["ok"]:
        raise kernel.ClaimError(
            f"no record for {claim}: the bytes present recompute to "
            f"{checked['recomputed'][:16]}..., not the sealed "
            f"{checked['root'][:16]}... -- a record is about a root")
    parsed = kernel.load_recipe(claim)
    judged = kernel.audit(claim)
    document = {
        "record": kernel.RECORD_FORMAT,
        "claim": _obligations(parsed),
        "name": checked["name"],
        "root": checked["root"],
        "build_digest": kernel.build_digest(claim),
        "gates": [{"output": row["output"], "status": row["status"],
                   "sandbox": row["quarantine"] or "none"}
                  for row in judged["gates"]],
        "environment": {"platform": sys.platform,
                        "machine": platform.machine() or "unknown",
                        "runtime": "CPython " + platform.python_version()},
        "when": kernel._now(),
    }
    totals = kernel.cost(claim)
    if totals:
        document["cost"] = totals
    declared = dict(producer or {}) or kernel.independence(claim)
    declared = {k: v for k, v in declared.items()
                if k in ("vendor", "model", "blind", "cutoff")}
    if declared:
        document["producer"] = declared
    kernel.record_validate(document)
    return document


def validate(document) -> dict:
    return kernel.record_validate(document)


def canonical(document) -> bytes:
    return kernel.record_canonical(document)


def digest(document) -> str:
    return kernel.record_digest(document)


def read(path: str) -> dict:
    return kernel.record_read(path)


def write(document: dict, path: str) -> str:
    """The file IS the canonical bytes: no prettying, no trailing newline."""
    payload = kernel.record_canonical(document)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def sign(path: str, key: str) -> str:
    """Sign a record's canonical bytes in the record's own namespace."""
    read(path)                      # a signature over a non-record is a lie
    signature = path + ".sig"
    if os.path.exists(signature):
        os.remove(signature)
    done = subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", key, "-n",
         kernel.RECORD_NAMESPACE, path],
        capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise kernel.ClaimError(
            f"could not sign {path}: {(done.stderr or done.stdout)[-300:]}")
    return signature


def signer(path: str, signers: str | None = None) -> str | None:
    """Who signed this record, relative to the verifier's own anchor."""
    return kernel.record_signer(path, signers)

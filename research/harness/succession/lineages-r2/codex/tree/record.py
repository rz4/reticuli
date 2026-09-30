"""Emit and sign the portable, closed-schema record document."""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

from . import kernel
from ._util import ledger_add

if not hasattr(kernel, "ledger"):
    kernel.ledger = ledger_add

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read


def signer(path, signers):
    try:
        doc = read(path)
        with open(path, "rb") as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, signers)
    except (OSError, kernel.ClaimError):
        return None


def emit(directory):
    checked = kernel.verify(directory)
    if not checked["ok"]:
        raise kernel.ClaimError("claim identity does not match its seal")
    recipe = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    gates = [{"output": gate["output"], "status": gate["status"],
              "sandbox": gate.get("quarantine") or "none"} for gate in audit["gates"]]
    obligations = {key: recipe["claim"][key] for key in
                   ("tolerance", "envelope", "mutation_floor") if key in recipe["claim"]}
    doc = {"record": 2, "claim": obligations, "name": recipe["claim"]["name"],
           "root": checked["root"], "build_digest": kernel.build_digest(directory),
           "gates": gates, "environment": {"platform": sys.platform,
           "machine": platform.machine(),
           "runtime": platform.python_implementation() + " " + platform.python_version()},
           "when": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    cost = kernel.cost(directory)
    if cost:
        doc["cost"] = cost
    producer = kernel.independence(directory)
    if producer:
        doc["producer"] = producer
    validate(doc)
    return doc


def write(doc, path):
    data = canonical(doc)
    with open(path, "wb") as stream:
        stream.write(data)
    return path


def sign(path, key):
    # Signing always covers the canonical document, even if a caller supplied
    # a semantically valid but differently formatted file.
    doc = read(path)
    if open(path, "rb").read() != canonical(doc):
        raise kernel.ClaimError("record file is not canonical")
    try:
        if os.path.exists(path + ".sig"):
            os.unlink(path + ".sig")
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key,
                        "-n", kernel.RECORD_NAMESPACE, path],
                       check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise kernel.ClaimError(f"cannot sign record: {exc}") from exc
    return path + ".sig"

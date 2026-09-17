"""Records, the authoring side: emit, write, and sign one machine's results.

Implements the authoring half of spec/record.md. The FORMAT -- canonical
bytes, validation, reading, the signature namespace -- belongs to the kernel,
which also consumes records as crosscheck legs; this module delegates all of
that and adds what only an authoring layer should do: run the gates and state
the results (`emit`), put the canonical bytes on disk (`write`), and sign
them (`sign`). Everything else under `.reticuli/` stays private: the record
is the only file other programs may parse.

Stdlib only.
"""
import os
import platform
import subprocess
import sys
import time

from . import kernel

# The format is the kernel's; these names exist so a caller of the authoring
# layer never has to know which side of the boundary a function lives on.
NAMESPACE = kernel.RECORD_NAMESPACE
FORMAT = kernel.RECORD_FORMAT
canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read
signer = kernel.record_signer


def emit(claimdir: str) -> dict:
    """The record of this claim, earned now: verify, then run every gate.

    Refuses unless the bytes present recompute to the sealed root -- a record
    is about a root, and a drifted claim has nothing to be about. A failing
    gate is the opposite case: it is stated, never refused, because a failed
    rebuild is evidence about the claim.
    """
    checked = kernel.verify(claimdir)
    if not checked["ok"]:
        raise kernel.ClaimError(
            "the bytes present do not recompute to the sealed root "
            f"({checked['recomputed']} != {checked['root']}): a record is "
            "about a root, and this claim has none to be about")

    audited = kernel.audit(claimdir)
    doc = {
        "record": FORMAT,
        "name": checked["name"],
        "root": checked["root"],
        "build_digest": kernel.build_digest(claimdir),
        "gates": [{"output": g.get("output"),
                   "status": g.get("status"),
                   "sandbox": g.get("quarantine") or "none"}
                  for g in audited.get("gates", [])],
        "environment": {
            "platform": sys.platform,
            "machine": platform.machine(),
            "runtime": (f"{platform.python_implementation()} "
                        f"{platform.python_version()}"),
        },
        "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": _tool(),
    }
    cost = kernel.cost(claimdir)
    if cost:
        doc["cost"] = cost           # absent means unmeasured, never zero
    told = _producer(claimdir)
    if told:
        doc["producer"] = told       # relayed as declared, never invented
    validate(doc)
    return doc


def _tool() -> str:
    try:
        from . import __version__
        return f"reticuli {__version__}"
    except ImportError:
        return "reticuli"


def _producer(claimdir: str) -> dict:
    """The last producer declaration on the ledger, relayed as given."""
    told = {}
    for event in kernel.ledger_events(claimdir) or []:
        if event.get("event") != "producer":
            continue
        told = {}
        for key in ("vendor", "model", "cutoff"):
            value = event.get(key)
            if isinstance(value, str) and value:
                told[key] = value
        if isinstance(event.get("blind"), bool):
            told["blind"] = event["blind"]
    return told


def write(doc, path: str) -> str:
    """Validate, then put exactly the canonical bytes on disk.

    The file IS the canonical form -- no trailing newline, no pretty
    printing -- so the digest of the file's bytes is the record's digest and
    a detached signature covers precisely what a reader hashes.
    """
    validate(doc)
    payload = canonical(doc)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(payload)
        os.replace(tmp, path)
    except OSError as exc:
        raise kernel.ClaimError(f"cannot write record {path}: {exc}") from None
    return path


def sign(path: str, key: str) -> str:
    """Detached ssh signature over the file's bytes, in the record namespace.

    An existing signature is replaced: the file's bytes are the authority,
    and a stale signature beside fresh bytes would verify nothing anyway.
    """
    signature = path + ".sig"
    try:
        os.remove(signature)
    except OSError:
        pass
    try:
        done = subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", key, "-n", NAMESPACE, path],
            capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise kernel.ClaimError(f"cannot sign {path}: {exc}") from None
    if done.returncode != 0 or not os.path.isfile(signature):
        why = (done.stderr or done.stdout or b"").decode("utf-8", "replace")
        raise kernel.ClaimError(f"signing failed for {path}: {why.strip()[-300:]}")
    return signature

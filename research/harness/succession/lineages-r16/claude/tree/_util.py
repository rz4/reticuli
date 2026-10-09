"""Small helpers shared by the layers above the kernel.

No layer imports a kernel private (`spec/layers.md`): the exchange modules
(`registry`, `transfer`, `attest`, `record`) reach file, path, ledger, and
ssh-signature primitives here rather than through `reticuli._kernel.*`.
"""
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def safe_path(root: str, name: str) -> str:
    """Resolve a recipe-declared name under root, or refuse."""
    from reticuli.kernel import ClaimError
    if not name or os.path.isabs(name):
        raise ClaimError(f"refused path: {name!r}")
    parts = name.split("/")
    if any(p in ("", "..") for p in parts):
        raise ClaimError(f"refused path: {name!r}")
    root_real = os.path.realpath(root)
    cur = root_real
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"refused symlink component: {name!r}")
    if cur != root_real and not cur.startswith(root_real + os.sep):
        raise ClaimError(f"refused path escape: {name!r}")
    return cur


def copy_into(src: str, dst: str) -> None:
    """Copy a file's bytes (and metadata) to dst, creating parents."""
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    shutil.copy2(src, dst)


def hash_bytes(data: bytes) -> str:
    """The sha256 hex digest of a bytes object."""
    return hashlib.sha256(data).hexdigest()


def read_json(path: str):
    """Parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """Write JSON atomically: build the bytes off to the side, then rename."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def stamp() -> str:
    """UTC time of recording, `YYYY-MM-DDTHH:MM:SSZ`."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def locked_append(path: str, text: str) -> None:
    """Append text to a file, holding an exclusive lock for the write."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(text)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def ledger_add(d: str, entry: dict) -> None:
    """Append one cost/event entry to `d`'s ledger, stamped with `when`."""
    record = dict(entry)
    record.setdefault("when", stamp())
    locked_append(os.path.join(d, LEDGER), json.dumps(record, sort_keys=True) + "\n")


def trace_append(d: str, entry: dict) -> None:
    """Append one residue event to the claim's trace log, beside the ledger."""
    record = dict(entry)
    record.setdefault("when", stamp())
    locked_append(os.path.join(d, STORE, "trace.jsonl"),
                  json.dumps(record, sort_keys=True) + "\n")


def declared_inputs(recipe: dict, d: str) -> list:
    """The claim's explicitly declared pinned inputs."""
    claim = recipe.get("claim", {}) if recipe else {}
    return list(claim.get("inputs", []))


def step_output(step: dict) -> str:
    """A step's declared output path."""
    return step.get("output")


# --------------------------------------------------------- ssh signatures
def read_signers(anchor: str) -> list:
    """Every principal named in an `allowed_signers` file, in file order."""
    with open(anchor, "r", encoding="utf-8") as f:
        lines = f.readlines()
    identities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        principals, _, _ = line.partition(" ")
        for name in principals.split(","):
            name = name.strip()
            if name and name not in identities:
                identities.append(name)
    return identities


def ssh_verify(anchor: str, identity: str, namespace: str,
                message: bytes, signature: bytes) -> bool:
    """Verify a detached `ssh-keygen -Y` signature over `message`, in
    `namespace` for `identity`, against an `allowed_signers` file. False on
    any failure -- an unverifiable signature is simply not trusted."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".sig") as sig_f:
            sig_f.write(signature)
            sig_f.flush()
            proc = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", anchor,
                 "-I", identity, "-n", namespace, "-s", sig_f.name],
                input=message, capture_output=True, timeout=30,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def ssh_check_novalidate(namespace: str, message: bytes, signature: bytes) -> bool:
    """Check a detached `ssh-keygen -Y` signature is well-formed for
    `namespace`, without anchoring it to any identity."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".sig") as sig_f:
            sig_f.write(signature)
            sig_f.flush()
            proc = subprocess.run(
                ["ssh-keygen", "-Y", "check-novalidate", "-n", namespace,
                 "-s", sig_f.name],
                input=message, capture_output=True, timeout=30,
            )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0

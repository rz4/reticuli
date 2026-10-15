"""Kernel core primitives and seam constants for reticuli."""

import datetime
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
from typing import Any

# Protocol constants whose VALUE is the on-disk / environment contract
NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 4
STORE = ".reticuli"
MANIFEST = ".reticuli/manifest.json"
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = ".reticuli/ledger.jsonl"
USAGE = ".reticuli/usage.json"
MUTATION_RESIDUE = ".reticuli/mutation_score.json"
SIGN_DIR = ".reticuli/mint"
SIGN_NAMESPACE = "reticuli.mint"
_JAILED = "RETICULI_JAILED"
_ENV_CACHE = "RETICULI_ENV_CACHE"
_ENV_CLAIM = "RETICULI_CLAIM"
_ENV_MODEL = "RETICULI_MODEL"
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_VENDOR = "RETICULI_VENDOR"
_KEEP_ENV = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TZ",
    "RETICULI_JAILED",
)

# Tuning constants and host-derived values
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 300.0
PRODUCER_TIMEOUT = 300.0
TOLERANCE = 2.0
MUTANT_CEILING = 64
MUTANT_FLOOR = 0.6
MUTANT_HEADROOM = 1.2
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = ("usd", "tokens", "calls", "seconds")
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """Refusal with a reason — the only kernel error."""


def _now() -> str:
    """Current UTC timestamp formatted as ISO-8601 (YYYY-MM-DDTHH:MM:SSZ)."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _judging_host() -> dict:
    """Environment descriptor for the current host."""
    return {
        "platform": sys.platform,
        "machine": platform.machine(),
        "runtime": f"{platform.python_implementation()} {platform.python_version()}",
    }


def _copy_into(src: str, dst: str) -> None:
    """Copy file or directory tree src into dst."""
    if os.path.isdir(src):
        if os.path.exists(dst):
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
        else:
            shutil.copytree(src, dst)
    else:
        if os.path.isdir(dst):
            shutil.copy2(src, os.path.join(dst, os.path.basename(src)))
        else:
            dst_dir = os.path.dirname(dst)
            if dst_dir:
                os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src, dst)


def _safe(root: str, path: str) -> str:
    """Path boundary: names inside the claim resolve, escapes refuse."""
    if not isinstance(path, str) or not path:
        raise ClaimError("Empty or invalid path")
    if os.path.isabs(path) or path.startswith("/") or path.startswith("\\"):
        raise ClaimError(f"Absolute path not allowed: {path!r}")

    parts = path.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ClaimError(f"Path traversal not allowed: {path!r}")

    real_root = os.path.realpath(root)
    cur = real_root
    for part in parts:
        if not part or part == ".":
            continue
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise ClaimError(f"Symlink component not allowed: {cur!r}")

    resolved = os.path.join(real_root, path)
    norm_resolved = os.path.abspath(resolved)
    try:
        common = os.path.commonpath([real_root, norm_resolved])
    except ValueError:
        raise ClaimError(f"Path escapes claim directory: {path!r}")

    if common != real_root or norm_resolved == real_root:
        raise ClaimError(f"Path escapes claim directory: {path!r}")

    return resolved


def _hash_file(path: str) -> str:
    """Bytes boundary: plain sha256 of file bytes."""
    if os.path.islink(path):
        raise ClaimError(f"Symlinks are not allowed: {path}")
    try:
        st = os.lstat(path)
    except OSError as e:
        raise ClaimError(f"Cannot stat {path}: {e}")
    if not stat.S_ISREG(st.st_mode):
        raise ClaimError(f"Not a regular file: {path}")
    if st.st_nlink != 1:
        raise ClaimError(f"Multiple hard links not allowed: {path}")

    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
    except OSError as e:
        raise ClaimError(f"Cannot read {path}: {e}")
    return h.hexdigest()


def _write_json(path: str, data: Any) -> None:
    """Atomic write of JSON data to path."""
    dirname = os.path.dirname(os.path.abspath(path))
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    temp_path = f"{path}.tmp.{os.getpid()}"
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        raise


def canonical_json(val: Any) -> str:
    """Canonical JSON serialization following spec/identity.md."""
    return json.dumps(val, sort_keys=True)


def canonical_bytes(val: Any) -> bytes:
    """Canonical JSON serialized to UTF-8 bytes."""
    return canonical_json(val).encode("utf-8")

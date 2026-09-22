"""Kernel-core conformance gate — the innermost layer.

The two boundaries and the primitives beneath everything: the path boundary
(`_safe` refuses a name that escapes the claim), the bytes boundary (`_hash_file`
is a plain sha256 of the file), atomic JSON write, and the refusal vocabulary.
Stdlib only, never the network. Writes CORE_OK.

    python3 criteria/core_check.py        (from the repository root)
"""
import ast
import hashlib
import json
import os
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import core

_NET = frozenset({"socket", "ssl", "http", "urllib", "ftplib", "smtplib",
                  "poplib", "imaplib", "nntplib", "telnetlib", "asyncio",
                  "xmlrpc", "socketserver", "webbrowser", "requests", "httpx",
                  "aiohttp", "urllib3"})
LAYER = ("reticuli/__init__.py", "reticuli/_kernel/__init__.py",
         "reticuli/_kernel/core.py")


def _imports(path: str) -> set:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return mods


# The seam contract: the names core exposes to the layers above it. The
# behavioral checks below pin how core's OWN primitives act; this pins the
# interface the rest of the kernel imports from core. Without it a regrown core
# passes its own gate with a leaner API and the assembled tool fails at import
# (`from ._kernel.core import _JAILED`) -- the gap the 2026-09-21 assembled
# rebuild found. Every name below is imported from core by a higher layer.
#
# Protocol constants whose VALUE is the on-disk / environment contract, shared
# verbatim across layers and with the record format: a rebuild that changed any
# of these would not be reticuli.
_SEAM_VALUES = {
    "NAMESPACE": "reticuli",
    "DIGEST": "sha256",
    "FORMAT": 3,
    "STORE": ".reticuli",
    "MANIFEST": ".reticuli/manifest.json",
    "RECIPE": "reticuli.toml",
    "LEGACY_RECIPE": "claim.toml",
    "LEDGER": ".reticuli/ledger.jsonl",
    "USAGE": ".reticuli/usage.json",
    "MUTATION_RESIDUE": ".reticuli/mutation_score.json",
    "SIGN_DIR": ".reticuli/mint",
    "SIGN_NAMESPACE": "reticuli.mint",
    "_JAILED": "RETICULI_JAILED",
    "_ENV_CACHE": "RETICULI_ENV_CACHE",
    "_ENV_CLAIM": "RETICULI_CLAIM",
    "_ENV_MODEL": "RETICULI_MODEL",
    "_ENV_OUTPUT": "RETICULI_OUTPUT",
    "_ENV_OUTPUTS": "RETICULI_OUTPUTS",
    "_ENV_REQUEST": "RETICULI_REQUEST",
    "_ENV_SIGNERS": "RETICULI_SIGNERS",
    "_ENV_TIMEOUT": "RETICULI_GATE_TIMEOUT",
    "_ENV_TOLERANCE": "RETICULI_TOLERANCE",
    "_ENV_USAGE": "RETICULI_USAGE",
    "_ENV_VENDOR": "RETICULI_VENDOR",
    "_KEEP_ENV": ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ",
                  "RETICULI_JAILED"),
}
# Tuning constants and host-derived values other layers import: the NAME and
# KIND are the seam (they must exist and be usable); their exact value is
# policy, left to the layers that exercise it rather than over-pinned here.
_SEAM_KINDS = {
    "GATE_TIMEOUT": (int, float),
    "FURNISH_TIMEOUT": (int, float),
    "PRODUCER_TIMEOUT": (int, float),
    "TOLERANCE": (int, float),
    "MUTANT_CEILING": (int, float),
    "MUTANT_FLOOR": (int, float),
    "MUTANT_HEADROOM": (int, float),
    "COST_KEYS": tuple,
    "COST_LADDER": tuple,
    "COST_UNITS": tuple,
    "GUIDANCE_KEYS": tuple,
    "KINDS": frozenset,
    "_SHELL": str,
}
# Helpers other layers import from core; the seam is that they exist and call.
_SEAM_CALLABLES = ("_now", "_copy_into", "_judging_host")


def _seam() -> None:
    """core's export contract -- the names the kernel above it imports."""
    for name, want in _SEAM_VALUES.items():
        assert hasattr(core, name), f"core must export {name} (seam contract)"
        got = getattr(core, name)
        assert got == want, \
            f"core.{name} is the shared contract {want!r}, not {got!r}"
    for name, kind in _SEAM_KINDS.items():
        assert hasattr(core, name), f"core must export {name} (seam contract)"
        assert isinstance(getattr(core, name), kind), \
            f"core.{name} must be {kind}"
    for name in _SEAM_CALLABLES:
        assert callable(getattr(core, name, None)), \
            f"core must export a callable {name} (seam contract)"


def battery() -> None:
    _seam()
    for rel in LAYER:
        path = os.path.join(SRC, rel)
        if os.path.isfile(path):
            leaked = _imports(path) & _NET
            assert not leaked, f"{rel} reaches the network: {leaked}"
            third = {m for m in _imports(path)
                     if m not in sys.stdlib_module_names and m != "reticuli"}
            assert not third, f"{rel} must be stdlib-only: {third}"

    d = tempfile.mkdtemp()
    try:
        # the bytes boundary: a plain sha256 of the file's bytes
        p = os.path.join(d, "f.txt")
        with open(p, "wb") as f:
            f.write("café ☕\n".encode())
        with open(p, "rb") as f:
            assert core._hash_file(p) == hashlib.sha256(f.read()).hexdigest(), \
                "the bytes boundary is a plain sha256"

        # the path boundary: names inside the claim resolve (to a real path
        # under the claim), escapes refuse
        resolved = core._safe(d, "ok.txt")
        assert os.path.basename(resolved) == "ok.txt" \
            and resolved.startswith(os.path.realpath(d) + os.sep), \
            "a plain name resolves under the claim"
        for bad in ("../escape", "/etc/passwd", ""):
            try:
                core._safe(d, bad)
            except core.ClaimError:
                pass
            else:
                raise AssertionError(f"the path boundary must refuse {bad!r}")

        # atomic json write round-trips
        j = os.path.join(d, "x.json")
        core._write_json(j, {"b": 2, "a": 1})
        with open(j, encoding="utf-8") as f:
            assert json.load(f) == {"a": 1, "b": 2}, "_write_json round-trips"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("CORE_OK", "w", encoding="utf-8") as f:
            f.write("core-ok\n")
    print("core-ok")

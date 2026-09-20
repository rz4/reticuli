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


def battery() -> None:
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

"""Kernel-core conformance gate — the acceptance check of the innermost layer.

The kernel's identity machinery, carved out so the kernel is a chain of
sub-claims: the canonical root and build-digest serialization, seal/verify, and
the path/bytes boundaries — everything before a gate is ever run. No sandbox, no
execution, no network. A rebuilt inner layer iterates its `root()` and
`build_digest()` against the golden vectors below until the bytes agree; that is
what lets claims travel between independent kernels.

Writes KERNEL_CORE_OK iff the inner layer conforms. Stdlib only.

    python3 criteria/kernel_inner_check.py        (from the repository root)
"""
import ast
import hashlib
import os
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import inner

# The inner layer is stdlib-only and never reaches the network — the same wall
# the whole kernel carries, applied to the modules this sub-claim owns.
_NET = frozenset({"socket", "ssl", "http", "urllib", "ftplib", "smtplib",
                  "poplib", "imaplib", "nntplib", "telnetlib", "asyncio",
                  "xmlrpc", "socketserver", "webbrowser", "requests", "httpx",
                  "aiohttp", "urllib3"})
CORE_LAYER = ("reticuli/__init__.py", "reticuli/_kernel/__init__.py",
              "reticuli/_kernel/inner.py")


def _toplevel_imports(path: str) -> set:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return mods


# The canonical serializations, pinned by value (spec/identity.md, byte for
# byte). See criteria/kernel_check.py for the full prose; these are the same
# vectors, owned here because identity is the inner layer's concern.
GOLDEN = [
    ("v1-minimal",
     '[claim]\nname = "fx"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\nclass = "generated"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"V": "v"},
     "a7272db5f9c859e6fc92b9a708e4d9e39a90d172e0fe14de9f9c39f3f16c8972"),
    ("v2-one-input",
     '[claim]\nname = "seeded"\ninputs = ["spec.txt"]\n\n[[step]]\nkind = "produce"\noutput = "impl.txt"\nclass = "generated"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"spec.txt": "acceptance criteria: v1\n", "V": "v"},
     "29fe643bab09bf667fa1db8b4fa2b2a9bb5b422d089b83a6dfb2e8bdc1ea8b65"),
    ("v3-two-inputs",
     '[claim]\nname = "two"\ninputs = ["a.txt", "b.txt"]\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"a.txt": "alpha\n", "b.txt": "beta\n", "V": "v"},
     "d1893fd881d7b335027abb5821031867a20cd2db4e912073ea22881fe2ee46ca"),
    ("v4-unicode",
     '[claim]\nname = "café"\ninputs = ["u.txt"]\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"u.txt": "café ☕ naïve\n", "V": "v"},
     "fc8ac405695266daee32a7854f1e08477991608f035c19c8d9059fd4f7f730e2"),
]

BD_GOLDEN = [
    ("rd1-one-generated",
     '[claim]\nname = "a"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\nclass = "generated"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"g.txt": "hello\n", "V": "v"},
     "64ebf69715290d4694644abe15162c52046919ccace6b9352192648e7d733804"),
    ("rd3-absent-generated-omitted",
     '[claim]\nname = "c"\n\n[[step]]\nkind = "produce"\noutput = "present.txt"\nclass = "generated"\nrequest = "x"\n\n[[step]]\nkind = "produce"\noutput = "absent.txt"\nclass = "generated"\nrequest = "y"\n',
     {"present.txt": "here\n"},
     "489de2b990255044569a0189530a415431827fa21c6782c47d049267021a1e99"),
    ("rd6-no-generated",
     '[claim]\nname = "f"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"V": "v"},
     "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
]

SEEDED = ('[claim]\nname = "seeded"\ninputs = ["spec.txt"]\n\n[[step]]\n'
          'kind = "produce"\noutput = "impl.txt"\nclass = "generated"\n'
          'request = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
          'class = "validated"\nrun = "grep -q PASS impl.txt && printf v > V"\n')


def _write(d: str, files: dict) -> None:
    for name, content in files.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            f.write(content)


def battery() -> None:
    # the inner layer stays stdlib-only and net-free
    for rel in CORE_LAYER:
        path = os.path.join(SRC, rel)
        if os.path.isfile(path):
            leaked = _toplevel_imports(path) & _NET
            assert not leaked, f"{rel} reaches the network: {leaked}"

    d = tempfile.mkdtemp()
    try:
        # THE CANONICAL ROOT — pinned by value so claims travel between kernels
        for gname, grecipe, gfiles, groot in GOLDEN:
            gd = os.path.join(d, "g-" + gname)
            os.makedirs(gd)
            _write(gd, {"claim.toml": grecipe, **gfiles})
            got = inner.root(inner.load_recipe(gd), gd)
            assert got == groot, f"canonical root mismatch for {gname}: {got} != {groot}"

        # THE CANONICAL BUILD DIGEST — pinned by value so signatures travel
        for gname, grecipe, gfiles, gdigest in BD_GOLDEN:
            rd = os.path.join(d, "d-" + gname)
            os.makedirs(rd)
            _write(rd, {"claim.toml": grecipe, **gfiles})
            got = inner.build_digest(rd)
            assert got == gdigest, f"build-digest mismatch for {gname}: {got} != {gdigest}"

        # SEAL/VERIFY, and the invariant that IS the equivalence class: the root
        # is a function of the pinned inputs and independent of generated bytes.
        s = os.path.join(d, "seeded")
        os.makedirs(s)
        _write(s, {"claim.toml": SEEDED, "spec.txt": "acceptance criteria: v1\n",
                   "impl.txt": "PASS — implementation one\n"})
        import subprocess
        subprocess.run("grep -q PASS impl.txt && printf v > V",
                       shell=True, cwd=s, check=True)
        inner.seal(s)
        r_seed = inner.verify(s)["root"]
        assert inner.verify(s)["ok"] and len(r_seed) == 64, "the seeded claim seals"
        _write(s, {"impl.txt": "PASS — implementation two, wholly rewritten\n"})
        vs = inner.verify(s)
        assert vs["ok"] and vs["root"] == r_seed, "editing a generated output keeps the root"
        _write(s, {"spec.txt": "acceptance criteria: v2 (stricter)\n"})
        vs = inner.verify(s)
        assert not vs["ok"] and vs["recomputed"] != r_seed, \
            "editing a pinned input moves the claim"

        # the path boundary refuses an escaping name, and the bytes boundary
        # hashes raw file bytes (the two primitives everything above rests on)
        with open(os.path.join(s, "spec.txt"), "rb") as f:
            expect = hashlib.sha256(f.read()).hexdigest()
        assert inner._hash_file(os.path.join(s, "spec.txt")) == expect, \
            "the bytes boundary is a plain sha256 of the file"
        try:
            inner._safe(s, "../escape")
        except inner.ClaimError:
            pass
        else:
            raise AssertionError("the path boundary must refuse an escaping name")
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("KERNEL_CORE_OK", "w", encoding="utf-8") as f:
            f.write("kernel-core-ok\n")
    print("kernel-core-ok")

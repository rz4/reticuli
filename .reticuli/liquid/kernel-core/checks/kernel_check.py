"""Kernel conformance gate — the fixed check that defines "a correct kernel".

This is the seed of the `kernel-core` component record. It imports the
(re)generated kernel and confirms it implements the invariant: seal + verify
hold, an independent redo lands on the *same root* (root = claim), the
three-machine test is satisfied — and is SOUND: verdicts must be earned, not
carried, so a fabricated machine that shares the root but whose gates cannot
reproduce its verdicts from its own bytes neither proves nor mints (audit).
Cost is accounted: a redo leaves a ledger (residue, outside the root), an
unmeasured machine is reported rather than failed, an incomparable redo fails
the test. And gates run in quarantine: where the platform has a jail, an
escaping gate refuses, and the ledger tells the truth about the jail either
way. Writes KERNEL_OK iff it conforms. Stdlib only, so it runs in any clean
room.

THE EXECUTION CONTRACT: gates are judged *inside* a platform jail when the host
has one (sandbox-exec on darwin, bwrap on linux), and jails do not nest. The
environment variable RETICULI_JAILED means "you are already inside one" — a
conformant kernel must then inherit (run the gate unwrapped, record its
quarantine as inherited) rather than re-apply a sandbox, which would refuse.
To make a producer's test environment equal the verdict environment, this check
re-execs itself under the host jail when run bare — so a kernel that re-applies
fails here, visibly, not only at the final gate.

Any kernel that passes this check hashes to the same kernel-core root — the
basin of kernels is what the component *is*. The whole toolchain layers on top:
its own gate ([`surface_check.py`](surface_check.py)) certifies the CLI built
over a conformant kernel, rung by rung.
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, ".")
from reticuli import kernel   # the kernel under test

# The kernel stratum touches the machine (files, subprocess for the jail) but a
# conformant kernel never reaches the NETWORK: no honest realization we have
# collected imports a socket, and a phone-home payload in the deepest stratum
# needs one. This is the first behavioral clause admitted by the divergence rule
# — promote a property only where it separates every honest realization from a
# class of payloads, so it costs zero basin width. `root = hash(...)` cannot see
# free bytes (that freedom IS the basin), so a mutant kernel that imports urllib
# lands the same root and audits clean; this static wall is what catches it.
# It narrows, it does not seal — subprocess remains, and the guide says so.
_NET = frozenset({"socket", "ssl", "http", "urllib", "ftplib", "smtplib",
                  "poplib", "imaplib", "nntplib", "telnetlib", "asyncio",
                  "xmlrpc", "socketserver", "webbrowser", "requests", "httpx",
                  "aiohttp", "urllib3"})
KERNEL_STRATUM = ("reticuli/__init__.py", "reticuli/kernel.py")


def _toplevel_imports(path: str) -> set[str]:
    """Top-level module names a source file imports (stdlib check is by name)."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module.split(".")[0])
    return mods

FIXTURE = '''[record]
name = "fixture"

[[step]]
kind = "produce"
output = "g.txt"
request = "a greeting containing the word hello"
class = "free"

[[step]]
kind = "gate"
output = "V"
run = "grep -qi hello g.txt && printf v > V"
class = "validated"
'''

# A record WITH a dry seed — the acceptance criteria are part of the claim.
# Used to pin the deepest property of the invariant: the root is a function of
# the seed bytes. A kernel that hashes only its validated outputs passes the
# seedless FIXTURE yet fails here — which is exactly the hole a live redo fell
# into (a regrown kernel whose `verify` blesses a record whose check was edited).
SEEDED = '''[record]
name = "seeded"
inputs = ["spec.txt"]

[[step]]
kind = "produce"
output = "impl.txt"
request = "any implementation that satisfies the spec"
class = "free"

[[step]]
kind = "gate"
output = "V"
run = "grep -q PASS impl.txt && printf v > V"
class = "validated"
'''

# THE CANONICAL ROOT SERIALIZATION — the interchange spec that lets records
# TRAVEL between independent implementations of the kernel. Without it, each
# conformant kernel is free to lay out the hash preimage its own way, so two
# kernels compute DIFFERENT roots for the same record and each reads the other's
# records as tampered (verify recomputes a root that will not match the stored
# one). That breaks the deepest self-test: a REHYDRATED kernel, used AS the
# kernel, cannot verify the repo. So the preimage layout is pinned here, and the
# golden vectors below are its conformance check — a regrown kernel iterates its
# `claim()` against them until the bytes agree.
#
# root(recipe, record) is the lowercase hex sha256 of
#     json.dumps(parts, sort_keys=True).encode("utf-8")
# with DEFAULT separators (", " and ": " — not compact), where `parts` is:
#     "recipe"        -> json.dumps(parsed_recipe, sort_keys=True)   (default separators)
#     "seed:<path>"   -> sha256(seed file bytes).hexdigest()   for each [record].inputs path
#     "pin:<output>"  -> sha256(output file bytes).hexdigest()  for each NON-free step's output
# Free outputs never enter the preimage (that freedom is the basin). `<path>` and
# `<output>` are the names exactly as written in the recipe. A kernel that sorts
# keys, uses default JSON separators, hashes raw file bytes, and names the parts
# this way reproduces every GOLDEN root below; any other layout diverges and is
# not conformant. (This pins the VALUE, closing the width that the behavioral
# clauses — root moves on a seed edit, holds on a free edit — leave open.)
GOLDEN = [
    ("v1-minimal",
     '[record]\nname = "fx"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"V": "v"},
     "6b137e60a31a4ceeb3991618a008c7be8627a63b29c9ed32a792c28ea869c152"),
    ("v2-one-seed",
     '[record]\nname = "seeded"\ninputs = ["spec.txt"]\n\n[[step]]\nkind = "produce"\noutput = "impl.txt"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"spec.txt": "acceptance criteria: v1\n", "V": "v"},
     "9378c37832b8791c531aec932d5e5db9dbb197db9636f16110f860c30f0391ee"),
    ("v3-two-seeds",
     '[record]\nname = "two"\ninputs = ["a.txt", "b.txt"]\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"a.txt": "alpha\n", "b.txt": "beta\n", "V": "v"},
     "4a7db23d7afc98136e84e8bce2936ce1c11ab0c43168ec7a232fab22b90268e7"),
    ("v4-unicode",
     '[record]\nname = "café"\ninputs = ["u.txt"]\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"u.txt": "café ☕ naïve\n", "V": "v"},
     "9419b2f604db56b7271466e574313b7be9d27e164d86acfad62213929556a6b1"),
    ("v5-two-pins",
     '[record]\nname = "pins"\n\n[[step]]\nkind = "gate"\noutput = "A"\nclass = "validated"\nrun = "printf a > A"\n\n[[step]]\nkind = "gate"\noutput = "B"\nclass = "validated"\nrun = "printf b > B"\n',
     {"A": "a", "B": "b"},
     "cf93ca18a9855ace24679843a49f9c26118e836d4f09f91678393f7f536c463b"),
    ("v6-record-extras",
     '[record]\nname = "extras"\ngate_timeout = 60\ntolerance = 3.0\ninputs = ["s.txt"]\n\n[[step]]\nkind = "produce"\noutput = "impl.txt"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"s.txt": "seed\n", "V": "v"},
     "817839e78bf6f8bef686f3252ae4323433f9fcb68cc0bd968c29d11918d625db"),
]

# THE CANONICAL REALIZATION-DIGEST SERIALIZATION — the same interchange pin, one
# layer out. The root is the CLAIM (what travels for verify); the realization
# digest is the FREE CRYSTAL a MINT binds — the free bytes the root ignores,
# frozen at authorization. If the digest is implementation-relative, a mint made
# by one kernel will not verify under another: records travel but mints do not.
# So its preimage is pinned here too, with its own golden battery.
#
# realization_digest(record) is the lowercase hex sha256 of
#     json.dumps(sorted(own), sort_keys=True).encode("utf-8")   (default separators)
# where `own` is a list of two-element lists
#     [output_name, sha256(output file bytes).hexdigest()]
# one for each step that is kind="produce", carries NO "from" (a `from` output
# belongs to a component and is covered by folding that component's mint), has
# class="free", AND whose output file is present on disk; the list SORTED
# ascending. An absent free output is omitted; a record with no such outputs
# digests the empty list (sha256 of "[]"). Non-free (pinned) and component
# (`from`) outputs never enter it. Reproduce these RD_GOLDEN digests exactly.
RD_GOLDEN = [
    ("rd1-one-free",
     '[record]\nname = "a"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"g.txt": "hello\n", "V": "v"},
     "64ebf69715290d4694644abe15162c52046919ccace6b9352192648e7d733804"),
    ("rd2-two-free",
     '[record]\nname = "b"\n\n[[step]]\nkind = "produce"\noutput = "a.py"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "produce"\noutput = "b.py"\nclass = "free"\nrequest = "y"\n',
     {"a.py": "print(1)\n", "b.py": "print(2)\n"},
     "b540ad3bb9547b45529f5d4f4aeb87d5cdd2f2ed90792256506dba6aec3b93db"),
    ("rd3-absent-free-omitted",
     '[record]\nname = "c"\n\n[[step]]\nkind = "produce"\noutput = "present.txt"\nclass = "free"\nrequest = "x"\n\n[[step]]\nkind = "produce"\noutput = "absent.txt"\nclass = "free"\nrequest = "y"\n',
     {"present.txt": "here\n"},
     "489de2b990255044569a0189530a415431827fa21c6782c47d049267021a1e99"),
    ("rd4-from-excluded",
     '[record]\nname = "d"\n\n[[step]]\nkind = "produce"\noutput = "base.py"\nclass = "free"\nfrom = "comp"\nrequest = "x"\n\n[[step]]\nkind = "produce"\noutput = "mine.py"\nclass = "free"\nrequest = "y"\n',
     {"base.py": "SUPPLIED\n", "mine.py": "MINE\n"},
     "b7aab24b4cfdda50695cd3984b10d31299f45a7d2594fcab49d625fff5eadf85"),
    ("rd5-unicode",
     '[record]\nname = "e"\n\n[[step]]\nkind = "produce"\noutput = "u.txt"\nclass = "free"\nrequest = "x"\n',
     {"u.txt": "café ☕ naïve\n"},
     "e2a6976a9b816de92aea13bcf80a48b47585155e5953258e9542d96ae1664134"),
    ("rd6-no-free",
     '[record]\nname = "f"\n\n[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n',
     {"V": "v"},
     "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
]


def _rejail() -> None:
    """Judge in the verdict's environment: if the host has a jail and we are not
    already inside one, re-exec this check under it, setting the inherited-jail
    signal (a single well-known name) so a conformant kernel inherits rather than
    re-applies. Jails do not nest."""
    if os.environ.get(kernel._JAILED):
        return                                       # already judged inside a jail
    cwd = os.path.realpath(os.getcwd())
    tmp = os.path.join(cwd, ".kc-tmp")
    os.makedirs(tmp, exist_ok=True)
    env = {**os.environ, "TMPDIR": tmp, "HOME": tmp}
    argv = None
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        profile = ('(version 1)(allow default)(deny network*)(deny file-write*)'
                   f'(allow file-write* (subpath "{cwd}") (subpath "/dev"))')
        argv, env[kernel._JAILED] = ["sandbox-exec", "-p", profile], "seatbelt"
    elif shutil.which("bwrap") and subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
            capture_output=True, check=False).returncode == 0:
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev",
                "--proc", "/proc", "--bind", cwd, cwd, "--unshare-net",
                "--die-with-parent"]
        env[kernel._JAILED] = "bubblewrap"
    if argv:
        os.execvpe(argv[0], argv + [sys.executable, os.path.abspath(__file__)], env)


def _hand_mint(record: str, ident: str, keypath: str, include_proof: bool) -> None:
    """Build and sign mint material by hand (stdlib only, no attest import): a
    packet (root, realization digest, and the recorded proof or None), a
    statement binding the packet digest, and an ssh signature over it."""
    mdir = os.path.join(record, kernel.MINT)
    os.makedirs(mdir, exist_ok=True)
    packet = {"root": kernel.verify(record)["root"],
              "realization_digest": kernel.realization_digest(record),
              "proof": kernel.read_manifest(record).get("proof") if include_proof else None}
    pdig = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
    with open(os.path.join(mdir, "x.packet.json"), "w") as f:
        json.dump(packet, f, sort_keys=True)
    spath = os.path.join(mdir, "x.mint.json")
    with open(spath, "w") as f:
        json.dump({"identity": ident, "root": packet["root"], "packet_digest": pdig,
                   "proof_recorded": bool(packet["proof"])}, f, sort_keys=True)
    subprocess.run(["ssh-keygen", "-Y", "sign", "-f", keypath, "-n", kernel.MINT_NAMESPACE, spath],
                   capture_output=True, check=True)


def battery() -> None:
    # the free clause: the kernel stratum is stdlib-only and never networks.
    # Checked statically against the source under test, so a payload realization
    # that behaves correctly on every gate above yet phones home is still caught.
    for rel in KERNEL_STRATUM:
        mods = _toplevel_imports(rel)
        net = mods & _NET
        assert not net, f"kernel must not reach the network: {sorted(net)} in {rel}"
        third = {m for m in mods if m not in sys.stdlib_module_names and m != "reticuli"}
        assert not third, f"kernel stratum must be stdlib-only: {sorted(third)} in {rel}"

    d = tempfile.mkdtemp()
    try:
        m1 = os.path.join(d, "m1")
        os.makedirs(m1)
        with open(os.path.join(m1, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        with open(os.path.join(m1, "g.txt"), "w") as f:
            f.write("hello, world\n")
        subprocess.run("grep -qi hello g.txt && printf v > V", shell=True, cwd=m1, check=True)
        kernel.seal(m1)
        assert kernel.verify(m1)["ok"], "seal/verify"

        m2 = os.path.join(d, "m2")
        shutil.copytree(m1, m2)                                  # byte-reuse
        m3 = os.path.join(d, "m3")
        kernel.realize(m1, "printf 'why, hello!\\n' > g.txt", m3)  # a different redo
        assert kernel.verify(m1)["root"] == kernel.verify(m3)["root"], "root is the claim"

        r = kernel.three_machine(m1, m2, m3)
        assert r["satisfied"] and len(set(r["roots"].values())) == 1, "three-machine"

        # M2 is a machine, not a passenger: the invariant is ONE root across
        # all three. A doctored M2 — byte-identical outputs under a different
        # recipe (a different claim) — must fail the test, not ride through on
        # byte-reuse. A kernel that compares only M1 and M3 passes above yet
        # fails right here.
        m2x = os.path.join(d, "m2x")
        shutil.copytree(m1, m2x)
        with open(os.path.join(m2x, "reticuli.toml"), "w") as f:
            f.write(FIXTURE.replace("a greeting containing the word hello",
                                    "any bytes at all"))
        kernel.seal(m2x)
        rx = kernel.three_machine(m1, m2x, m3)
        assert rx["roots"]["M2"] != rx["roots"]["M1"], "the doctored M2 is a different claim"
        assert not rx["satisfied"], "a different M2 claim must fail the three-machine test"

        # distinctness: three machines, not one directory presented thrice. One
        # record supplied as M1=M2=M3 trivially "agrees with itself" and proves
        # nothing; identical paths (by realpath — symlink and ./.. aliases too)
        # are refused, and the test reports content-independence as unestablished.
        try:
            kernel.three_machine(m1, m1, m1)
            raise AssertionError("three_machine must refuse identical paths")
        except kernel.ReticuliError:
            pass
        assert "independence" in r, "the test reports independence (unestablished from content)"

        # path confinement: a record's own recipe is untrusted. A seed or output
        # name that is absolute or climbs out with `..` must be refused before any
        # gate runs — else the kernel reads or writes outside the record. One
        # boundary (_safe), so claim() refuses an escaping seed here.
        esc = os.path.join(d, "escape")
        os.makedirs(esc)
        with open(os.path.join(esc, "reticuli.toml"), "w") as f:
            f.write('[record]\nname = "escape"\ninputs = ["../outside.txt"]\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\n'
                    'run = "printf v > V"\nclass = "validated"\n')
        with open(os.path.join(d, "outside.txt"), "w") as f:
            f.write("a file the record must not be able to name\n")
        try:
            kernel.claim(kernel.load_recipe(esc), esc)
            raise AssertionError("claim must refuse a seed that escapes the record root")
        except kernel.ReticuliError:
            pass
        with open(os.path.join(esc, "reticuli.toml"), "w") as f:      # and an absolute path
            f.write('[record]\nname = "escape"\ninputs = ["/etc/hostname"]\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\n'
                    'run = "printf v > V"\nclass = "validated"\n')
        try:
            kernel.claim(kernel.load_recipe(esc), esc)
            raise AssertionError("claim must refuse an absolute seed path")
        except kernel.ReticuliError:
            pass

        # confinement covers SYMLINKS, not only `..` and absolute names: a seed
        # that is a symlink whose target leaves the record must be refused, or the
        # kernel reads outside the record through a name that looks local. A
        # lexical _safe (normpath, never realpath) passes the `..`/absolute cases
        # above yet FOLLOWS this link — exactly the exfil-by-symlink payload class
        # a live draw fell into, so the boundary must resolve links before judging.
        sesc = os.path.join(d, "symesc")
        os.makedirs(sesc)
        with open(os.path.join(d, "sym-outside.txt"), "w") as f:
            f.write("reached only by following a symlink out of the record\n")
        os.symlink(os.path.join(d, "sym-outside.txt"), os.path.join(sesc, "spec.txt"))
        with open(os.path.join(sesc, "reticuli.toml"), "w") as f:
            f.write('[record]\nname = "symesc"\ninputs = ["spec.txt"]\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\n'
                    'run = "printf v > V"\nclass = "validated"\n')
        try:
            kernel.claim(kernel.load_recipe(sesc), sesc)
            raise AssertionError("claim must refuse a seed symlinked out of the record")
        except kernel.ReticuliError:
            pass

        # confinement covers the FILESYSTEM adversaries a path check cannot see:
        # a declared file must be a REGULAR file with a SINGLE link, so its bytes
        # live inside the record and nowhere else. A HARDLINK to an inode outside
        # the record keeps a local-looking path (symlink and `..` checks miss it)
        # yet seals foreign bytes as the record's own — the exfiltration _safe
        # promises to prevent. A FIFO or device would block or return nonsense
        # into the claim (a read-path DoS); a directory is not a file. All are
        # refused at the one bytes boundary (_hf), the way _safe is the one path
        # boundary.
        fsd = os.path.join(d, "fs-adversary")
        os.makedirs(fsd)
        with open(os.path.join(fsd, "reticuli.toml"), "w") as f:
            f.write('[record]\nname = "fsa"\ninputs = ["seed.txt"]\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\n'
                    'run = "printf v > V"\nclass = "validated"\n')
        with open(os.path.join(fsd, "V"), "w") as f:
            f.write("v")
        # a hardlink to a file OUTSIDE the record: path stays inside, content is foreign
        with open(os.path.join(d, "fs-outside-secret.txt"), "w") as f:
            f.write("a secret the record must not be able to seal\n")
        os.link(os.path.join(d, "fs-outside-secret.txt"), os.path.join(fsd, "seed.txt"))
        try:
            kernel.claim(kernel.load_recipe(fsd), fsd)
            raise AssertionError("claim must refuse a seed hardlinked to an outside inode")
        except kernel.ReticuliError:
            pass
        os.remove(os.path.join(fsd, "seed.txt"))
        os.mkfifo(os.path.join(fsd, "seed.txt"))              # a named pipe: not a file
        try:
            kernel.claim(kernel.load_recipe(fsd), fsd)
            raise AssertionError("claim must refuse a FIFO where a file is declared")
        except kernel.ReticuliError:
            pass
        os.remove(os.path.join(fsd, "seed.txt"))
        with open(os.path.join(fsd, "seed.txt"), "w") as f:   # the honest control seals
            f.write("an ordinary self-contained seed\n")
        assert kernel.claim(kernel.load_recipe(fsd), fsd), "a regular single-link seed seals"

        # hostile record bytes are REFUSED, never crashed on and never shrugged
        # past: a corrupt manifest or recipe must raise the kernel's own
        # ReticuliError, not leak a raw UnicodeDecodeError / JSONDecodeError /
        # TOMLDecodeError, and phase() must not answer "liquid" about a manifest it
        # cannot even parse. A verifier facing a damaged record refuses in band; it
        # neither throws an uncaught exception nor blesses the wreckage.
        badm = os.path.join(d, "hostile-manifest")
        os.makedirs(badm)
        with open(os.path.join(badm, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        with open(os.path.join(badm, "g.txt"), "w") as f:
            f.write("hello, world\n")
        subprocess.run("grep -qi hello g.txt && printf v > V", shell=True, cwd=badm, check=True)
        kernel.seal(badm)
        assert kernel.verify(badm)["ok"], "the record is sound before corruption"
        with open(os.path.join(badm, kernel.STORE, "manifest.json"), "wb") as f:
            f.write(b"\xff\xfe not json \x00 at all")
        for fn in (kernel.verify, kernel.phase, kernel.audit):
            try:
                fn(badm)
                raise AssertionError(f"{fn.__name__} must refuse a corrupt manifest")
            except kernel.ReticuliError:
                pass
        badr = os.path.join(d, "hostile-recipe")
        os.makedirs(badr)
        with open(os.path.join(badr, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        with open(os.path.join(badr, "g.txt"), "w") as f:
            f.write("hello, world\n")
        subprocess.run("grep -qi hello g.txt && printf v > V", shell=True, cwd=badr, check=True)
        kernel.seal(badr)
        with open(os.path.join(badr, "reticuli.toml"), "w") as f:
            f.write("[[[ this is not valid TOML at all")
        for fn in (kernel.load_recipe, kernel.verify, kernel.audit):
            try:
                fn(badr)
                raise AssertionError(f"{fn.__name__} must refuse a corrupt recipe")
            except kernel.ReticuliError:
                pass
        with open(os.path.join(badr, "reticuli.toml"), "w") as f:   # parses, but no [record] name
            f.write("[record]\n")
        try:
            kernel.load_recipe(badr)
            raise AssertionError("load_recipe must refuse a recipe with no [record] name")
        except kernel.ReticuliError:
            pass

        # phase AGREES WITH verify on validity: phase reports vapor/liquid/solid
        # only for a well-formed record. A directory with a recipe but no manifest
        # is unsealed — that is "vapor", not an error. But a record sealed clean
        # and then given an escaping or missing seed (or a corrupt recipe) is one
        # verify refuses, so phase must refuse it too, never answer a positive
        # "liquid" an auditor would read as a valid seal. (A kernel whose phase
        # reads only the manifest says "liquid" about a record its own verify
        # raises on — the inconsistency this pins shut.)
        ph = os.path.join(d, "phase-consistency")
        os.makedirs(ph)
        with open(os.path.join(ph, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        with open(os.path.join(ph, "g.txt"), "w") as f:
            f.write("hello, world\n")
        subprocess.run("grep -qi hello g.txt && printf v > V", shell=True, cwd=ph, check=True)
        assert kernel.phase(ph) == "vapor", "a recipe with no manifest is vapor, not an error"
        kernel.seal(ph)
        assert kernel.phase(ph) == "liquid", "a clean sealed record is liquid"
        for mutate, label in (
                ('name = "fixture"\ninputs = ["../ph-outside.txt"]', "seed escapes the root"),
                ('name = "fixture"\ninputs = ["gone.txt"]', "seed is missing")):
            with open(os.path.join(d, "ph-outside.txt"), "w") as f:
                f.write("a file the record must not name\n")
            with open(os.path.join(ph, "reticuli.toml"), "w") as f:
                f.write(FIXTURE.replace('name = "fixture"', mutate))
            for fn in (kernel.phase, kernel.verify):
                try:
                    fn(ph)
                    raise AssertionError(f"{fn.__name__} must refuse a record whose {label}")
                except kernel.ReticuliError:
                    pass

        # confinement covers FREE outputs too, not just seeds: a free output that
        # is a symlink whose target leaves the record must be refused by audit,
        # which copies every produce output through the confinement boundary. A
        # free output is never hashed, but copying one that escapes the record is
        # the same exfiltration a seed symlink would be — so audit resolves links.
        fso = os.path.join(d, "free-symlink-out")
        os.makedirs(fso)
        with open(os.path.join(fso, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        with open(os.path.join(d, "fso-target.txt"), "w") as f:
            f.write("hello, world\n")
        os.symlink(os.path.join(d, "fso-target.txt"), os.path.join(fso, "g.txt"))
        subprocess.run("grep -qi hello g.txt && printf v > V", shell=True, cwd=fso, check=True)
        kernel.seal(fso)
        try:
            kernel.audit(fso)
            raise AssertionError("audit must refuse a free output symlinked out of the record")
        except kernel.ReticuliError:
            pass

        # a recipe's step KINDS are a closed vocabulary — produce and gate. An
        # unknown kind is hostile bytes, refused at parse (load_recipe), never
        # surfacing later as a raw KeyError deep in realize: hostile bytes produce
        # a ReticuliError, not an implementation exception.
        wk = os.path.join(d, "weird-kind")
        os.makedirs(wk)
        with open(os.path.join(wk, "reticuli.toml"), "w") as f:
            f.write('[record]\nname = "w"\n\n[[step]]\nkind = "weird"\nclass = "free"\n\n'
                    '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\nrun = "printf v > V"\n')
        with open(os.path.join(wk, "V"), "w") as f:
            f.write("v")
        for fn in (kernel.load_recipe,
                   lambda p: kernel.realize(p, "printf v > V", os.path.join(d, "wk-m3"))):
            try:
                fn(wk)
                raise AssertionError("an unknown step kind must be refused, not raise KeyError")
            except kernel.ReticuliError:
                pass

        # run_gate is THE gate entry point and its contract is a kernel invariant:
        # a record's gate runs with a SCRUBBED environment, so a hostile gate
        # cannot read an inherited secret and seal it into a verdict. realize,
        # audit, and the authoring paths (condense, pack) all run gates through
        # here — pinning the scrub here makes it hold wherever a gate runs.
        os.environ["RETICULI_LEAK_PROBE"] = "s3cr3t-not-real"
        try:
            gp = os.path.join(d, "gate-scrub")
            os.makedirs(gp)
            with open(os.path.join(gp, "reticuli.toml"), "w") as f:
                f.write(FIXTURE)
            kernel.run_gate('printf "${RETICULI_LEAK_PROBE:-clean}" > leak.txt', gp,
                            kernel.load_recipe(gp))
            with open(os.path.join(gp, "leak.txt")) as f:
                assert "s3cr3t" not in f.read(), \
                    "run_gate must scrub the environment — a gate saw an inherited secret"
        finally:
            os.environ.pop("RETICULI_LEAK_PROBE", None)

        # resource bound: a gate has a wall-clock ceiling (declarable, capped by
        # the environment), so a hostile or broken gate cannot hang the verifier.
        # A `sleep` gate under a 1s ceiling is killed — a failed redo, not a hang.
        slow = os.path.join(d, "slow")
        os.makedirs(slow)
        with open(os.path.join(slow, "reticuli.toml"), "w") as f:
            f.write(FIXTURE.replace("grep -qi hello g.txt && printf v > V",
                                    "sleep 30 && printf v > V"))
        os.environ["RETICULI_GATE_TIMEOUT"] = "1"
        t_slow = time.monotonic()
        try:
            kernel.realize(slow, "printf 'hello\\n' > g.txt", os.path.join(d, "slow-m3"))
            raise AssertionError("a gate exceeding the time limit must be refused")
        except kernel.ReticuliError:
            assert time.monotonic() - t_slow < 10, "the gate was killed at the limit, not run out"
        finally:
            del os.environ["RETICULI_GATE_TIMEOUT"]

        # the root is the CLAIM: it is a function of the dry seeds (the check),
        # and independent of the free outputs (the implementation). Editing a
        # free output must keep the root; editing a seed must move it AND break
        # identity. A kernel that omits the seeds from the root passes the
        # seedless fixture above but fails right here.
        s = os.path.join(d, "seeded")
        os.makedirs(s)
        with open(os.path.join(s, "reticuli.toml"), "w") as f:
            f.write(SEEDED)
        with open(os.path.join(s, "spec.txt"), "w") as f:
            f.write("acceptance criteria: v1\n")
        with open(os.path.join(s, "impl.txt"), "w") as f:
            f.write("PASS — implementation one\n")
        subprocess.run("grep -q PASS impl.txt && printf v > V", shell=True, cwd=s, check=True)
        kernel.seal(s)
        assert kernel.verify(s)["ok"], "seeded record seals"
        r_seed = kernel.verify(s)["root"]
        with open(os.path.join(s, "impl.txt"), "w") as f:      # a different free redo
            f.write("PASS — implementation two, wholly rewritten\n")
        vs = kernel.verify(s)
        assert vs["ok"] and vs["root"] == r_seed, "editing a free output keeps the root"
        with open(os.path.join(s, "spec.txt"), "w") as f:      # edit the claim itself
            f.write("acceptance criteria: v2 (stricter)\n")
        vs = kernel.verify(s)
        assert not vs["ok"] and vs["recomputed"] != r_seed, "editing a dry seed moves the claim"

        # the root is an INTERCHANGE CURRENCY, not a private serial number: the
        # canonical serialization (documented at GOLDEN above) is pinned so every
        # conformant kernel computes the SAME root hex for the same record, and a
        # record travels — a rehydrated kernel can verify what the committed one
        # sealed. The behavioral clauses above pin how the root MOVES; these pin
        # its VALUE. A kernel free to choose its own preimage layout passes every
        # clause above yet computes a different hex here, so its records read as
        # tampered to everyone else; the golden vectors are what a regrown kernel
        # iterates against until its bytes agree.
        for gname, grecipe, gfiles, groot in GOLDEN:
            gd = os.path.join(d, "golden-" + gname)
            os.makedirs(gd)
            with open(os.path.join(gd, "reticuli.toml"), "w", encoding="utf-8") as f:
                f.write(grecipe)
            for fn, content in gfiles.items():
                with open(os.path.join(gd, fn), "w", encoding="utf-8") as f:
                    f.write(content)
            got = kernel.claim(kernel.load_recipe(gd), gd)
            assert got == groot, (
                f"canonical root mismatch for {gname}: the record must hash to the "
                f"pinned value so records travel between kernels; got {got}, want {groot}")

        # the realization digest is a currency too, so MINTS travel: a mint binds
        # this digest, and if two kernels compute it differently, a mint made by
        # one will not verify under another. Pin its canonical serialization (see
        # RD_GOLDEN above) the same way as the root. A kernel free to choose its
        # own digest layout passes the mint clauses below (which check only that
        # the digest MOVES with the free crystal) yet computes a different value
        # here, so its mints are unportable.
        for gname, grecipe, gfiles, gdigest in RD_GOLDEN:
            rd = os.path.join(d, "rd-" + gname)
            os.makedirs(rd)
            with open(os.path.join(rd, "reticuli.toml"), "w", encoding="utf-8") as f:
                f.write(grecipe)
            for fn, content in gfiles.items():
                with open(os.path.join(rd, fn), "w", encoding="utf-8") as f:
                    f.write(content)
            got = kernel.realization_digest(rd)
            assert got == gdigest, (
                f"canonical realization-digest mismatch for {gname}: the mint's "
                f"crystal must hash to the pinned value so mints travel between "
                f"kernels; got {got}, want {gdigest}")

        # the signature NAMESPACES are interchange currency too. Domain separation
        # (attestation and mint sign in different ssh namespaces) is a security
        # property fixed by their DISTINCTNESS — but their VALUES are what a
        # verifier passes to `ssh-keygen -Y verify`, so if two kernels choose
        # different strings, a mint or attestation signed by one does not verify
        # under the other (mints stop travelling — the same interchange gap the
        # root and digest currencies close). Pin the canonical values, not merely
        # that they differ: attestation signs in "reticuli", the mint in
        # "reticuli.mint".
        assert kernel.NAMESPACE == "reticuli", \
            f"the attestation namespace is interchange currency: want 'reticuli', got {kernel.NAMESPACE!r}"
        assert kernel.MINT_NAMESPACE == "reticuli.mint", \
            f"the mint namespace is interchange currency: want 'reticuli.mint', got {kernel.MINT_NAMESPACE!r}"
        assert kernel.NAMESPACE != kernel.MINT_NAMESPACE, "the two domains must stay distinct"

        # the mint: solid identity, bottom-anchored. mint_node folds a rung's
        # claim root, its realization digest, and the mints beneath it, so the
        # bottom is the most significant digit. The realization digest is the
        # FREE crystal the root ignores — editing a free output moves the digest
        # (and so the mint) though the claim root holds. This is the invariant;
        # the DAG fold that composes it bottom-up is the exchange layer's.
        m0 = kernel.mint_node("R", "D", [])
        assert kernel.mint_node("R", "D", []) == m0, "mint_node is deterministic"
        assert kernel.mint_node("R", "D2", []) != m0, "the realization digest binds the mint"
        assert kernel.mint_node("R2", "D", []) != m0, "the claim root binds the mint"
        assert kernel.mint_node("R", "D", ["x"]) != m0, "a component's mint binds the mint above it"
        assert kernel.mint_node("R", "D", ["a", "b"]) == kernel.mint_node("R", "D", ["b", "a"]), \
            "the fold binds the SET of mints below — enumeration order is not claim"
        ms = os.path.join(d, "mint-seeded")
        os.makedirs(ms)
        with open(os.path.join(ms, "reticuli.toml"), "w") as f:
            f.write(SEEDED)
        with open(os.path.join(ms, "spec.txt"), "w") as f:
            f.write("criteria v1\n")
        with open(os.path.join(ms, "impl.txt"), "w") as f:
            f.write("PASS implementation one\n")
        subprocess.run("grep -q PASS impl.txt && printf v > V", shell=True, cwd=ms, check=True)
        kernel.seal(ms)
        r_before, dg_before = kernel.verify(ms)["root"], kernel.realization_digest(ms)
        with open(os.path.join(ms, "impl.txt"), "w") as f:     # a different free crystal
            f.write("PASS implementation two, wholly other\n")
        assert kernel.verify(ms)["root"] == r_before, "a free redo keeps the claim root"
        assert kernel.realization_digest(ms) != dg_before, "but the mint's digest tracks the crystal"

        # soundness: the verdicts must be EARNED, not carried. Root equality is
        # identity; audit re-runs the gates against the bytes present, so a
        # fabricated M3 — M1 copied, free output scribbled over, gate failing —
        # shares the root yet must not prove, and must never mint solid.
        m3f = os.path.join(d, "m3f")
        shutil.copytree(m1, m3f)
        with open(os.path.join(m3f, "g.txt"), "w") as f:
            f.write("fabricated, does not satisfy the gate\n")
        rf = kernel.three_machine(m1, m2, m3f)
        assert rf["equivalence"] and not rf["audited"]["M3"], "audit sees through the root"
        assert not rf["satisfied"], "a carried verdict does not prove"
        assert not kernel.freeze_dry(m1, m2, m3f)["proof_recorded"], "and records no proof"
        assert kernel.audit(m3)["ok"] and not kernel.audit(m3f)["ok"], "audit is the deep check"

        # audit is CLAIM-deep, not gate-shallow. The fabricated M3 above breaks
        # the GATE; this breaks the CLAIM while the gate stays green: edit a dry
        # SEED after sealing (the acceptance criteria change, the root no longer
        # recomputes) but leave the implementation that satisfies the old gate
        # untouched. audit must reject this silent spec-substitution — a kernel
        # that only re-runs the gates, never re-checking the claim still holds,
        # passes the fabricated-M3 case yet blesses a swapped claim.
        sub = os.path.join(d, "subst")
        os.makedirs(sub)
        with open(os.path.join(sub, "reticuli.toml"), "w") as f:
            f.write(SEEDED)
        with open(os.path.join(sub, "spec.txt"), "w") as f:
            f.write("acceptance criteria: v1\n")
        with open(os.path.join(sub, "impl.txt"), "w") as f:
            f.write("PASS — satisfies the gate\n")
        subprocess.run("grep -q PASS impl.txt && printf v > V", shell=True, cwd=sub, check=True)
        kernel.seal(sub)
        assert kernel.audit(sub)["ok"], "the honest seeded record audits clean"
        with open(os.path.join(sub, "spec.txt"), "w") as f:   # swap the CLAIM, gate stays green
            f.write("acceptance criteria: v2 (substituted after sealing)\n")
        assert not kernel.verify(sub)["ok"], "a seed edit breaks the sealed root"
        assert not kernel.audit(sub)["ok"], \
            "audit rejects a broken claim even when the gate still passes"

        # SOLID = AUTHORIZED (by a trusted signer) AND PROVEN (a recorded proof).
        # freeze_dry records the proof as residue; that alone is not solid. A
        # signature from an UNTRUSTED (unanchored) key is not solid — trust is
        # verifier-relative. Only a trusted signature over a coherent packet
        # that binds a recorded proof, on undrifted bytes, is solid.
        fz = kernel.freeze_dry(m1, m2, m3)
        assert fz["proof_recorded"], "a passing test records the proof"
        assert kernel.read_manifest(m1).get("proof"), "the proof is residue on the manifest"
        assert kernel.phase(m1) == "liquid", "proof_recorded alone is not solid"
        os.environ.pop("RETICULI_SIGNERS", None)
        # a hand-written proof, no authorization at all: not solid
        forged = os.path.join(d, "forged")
        shutil.copytree(m1, forged)
        fm = kernel.read_manifest(forged)
        fm["proof"] = {"kind": "three-machine", "m2": "FORGED", "m3": "FORGED"}
        with open(os.path.join(forged, kernel.STORE, "manifest.json"), "w") as f:
            json.dump(fm, f)
        assert kernel.phase(forged) == "liquid", "an injected proof is not an authorization"
        if shutil.which("ssh-keygen"):             # a host without ssh-keygen still gates the rest
            ekey = os.path.join(d, "ekey")
            subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", ekey],
                           capture_output=True, check=True)
            sol = os.path.join(d, "sol")
            shutil.copytree(m1, sol)               # carries the recorded proof
            _hand_mint(sol, "signer@basin", ekey, include_proof=True)
            assert kernel.phase(sol) == "liquid", "a signature with no trust anchor is not solid"
            signers = os.path.join(d, "allowed_signers")
            with open(ekey + ".pub") as f:
                ktype, blob = f.read().split()[:2]
            with open(signers, "w") as f:
                f.write(f"signer@basin {ktype} {blob}\n")
            os.environ["RETICULI_SIGNERS"] = signers
            try:
                assert kernel.phase(sol) == "solid", "trusted + proven + coherent is solid"
                with open(os.path.join(sol, "g.txt")) as f:
                    g_bytes = f.read()
                with open(os.path.join(sol, "g.txt"), "w") as f:
                    f.write("hello, but drifted after the mint\n")   # free redo post-mint
                assert kernel.phase(sol) == "liquid", "drift demotes: the mint froze the crystal"
                with open(os.path.join(sol, "g.txt"), "w") as f:
                    f.write(g_bytes)
                assert kernel.phase(sol) == "solid", "the frozen bytes restored, solid again"
                # authorized (trusted) but NOT proven: no recorded proof -> not solid
                np = os.path.join(d, "noproof")
                shutil.copytree(m1, np)
                nm = kernel.read_manifest(np)
                nm.pop("proof", None)
                with open(os.path.join(np, kernel.STORE, "manifest.json"), "w") as f:
                    json.dump(nm, f)
                _hand_mint(np, "signer@basin", ekey, include_proof=False)
                assert kernel.phase(np) == "liquid", "authorized but not proven is not solid"
                # a signer NOT in the anchor is not solid (trust is relative)
                other = os.path.join(d, "otherkey")
                subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", other],
                               capture_output=True, check=True)
                sol_o = os.path.join(d, "sol-other")
                shutil.copytree(m1, sol_o)
                _hand_mint(sol_o, "stranger@elsewhere", other, include_proof=True)
                assert kernel.phase(sol_o) == "liquid", "an untrusted signer is not solid to you"

                # the stored packet FILE is authoritative, not disposable residue.
                # The signed statement binds the packet by digest, so the review
                # bundle on disk — what a human opens to see WHAT was authorized —
                # must match the signature. Swapping the packet file must demote,
                # even though the live record is untouched. A kernel that
                # RECONSTRUCTS the packet from current state and never reads the
                # file calls a forged packet solid (the reviewable artifact could
                # then be anything); solidity must verify the file, not just the
                # record. (Drift — the file honest but the record changed — is the
                # complementary direction, pinned by the g.txt edit above.)
                mint_dir = os.path.join(sol, kernel.MINT)
                pfile = next(f for f in sorted(os.listdir(mint_dir))
                             if f.endswith(".packet.json"))
                ppath = os.path.join(mint_dir, pfile)
                with open(ppath) as f:
                    honest_packet = f.read()
                tampered = json.loads(honest_packet)
                tampered["root"] = "f" * 64                # swap the stored packet
                with open(ppath, "w") as f:
                    json.dump(tampered, f, sort_keys=True)
                assert kernel.phase(sol) == "liquid", \
                    "a stored packet not matching the signed digest is not solid"
                with open(ppath, "w") as f:                # restore the honest bundle
                    f.write(honest_packet)
                assert kernel.phase(sol) == "solid", "the honest packet restored, solid again"

                # DOMAIN SEPARATION (confused deputy): a mint authorization and an
                # attestation are different acts, signed in different ssh
                # namespaces. A signature made in the ATTESTATION namespace must
                # NOT authorize a solid mint, even over byte-identical statement
                # content and a trusted key — the purposes are cryptographically
                # disjoint. Re-sign the solid record's mint statement under the
                # wrong (attestation) namespace: it must demote to liquid.
                cd = os.path.join(d, "confused-deputy")
                shutil.copytree(sol, cd)
                cd_stmt = next(os.path.join(cd, kernel.MINT, f)
                               for f in sorted(os.listdir(os.path.join(cd, kernel.MINT)))
                               if f.endswith(".mint.json"))
                os.remove(cd_stmt + ".sig")
                subprocess.run(["ssh-keygen", "-Y", "sign", "-f", ekey,
                                "-n", kernel.NAMESPACE, cd_stmt],   # attestation namespace, not mint
                               capture_output=True, check=True)
                assert kernel.phase(cd) == "liquid", \
                    "a signature in the attestation namespace must not authorize a mint"
                # and signed under the correct mint namespace, the same act is solid
                os.remove(cd_stmt + ".sig")
                subprocess.run(["ssh-keygen", "-Y", "sign", "-f", ekey,
                                "-n", kernel.MINT_NAMESPACE, cd_stmt],
                               capture_output=True, check=True)
                assert kernel.phase(cd) == "solid", \
                    "the mint namespace authorizes; the domains are separated, not broken"
            finally:
                os.environ.pop("RETICULI_SIGNERS", None)

        # cost: the redo's ledger accounts the oracle call — residue, outside
        # the root (m1 has no ledger, m3 does, and they share a root above)
        assert os.path.isfile(os.path.join(m3, kernel.LEDGER)), "ledger written"
        assert kernel.cost(m3)["calls"] == 1, "cost totals the ledger"
        assert kernel.cost(m1) is None, "no event, no cost"
        assert r["cost"]["comparable"] is None, "unmeasured is reported, not failed"

        # a producer runs with cwd=into and reports its cost through
        # RETICULI_USAGE; that cost must reach the ledger even when `into` is
        # RELATIVE — realize resolves the usage path absolutely, or the redo's
        # tokens/usd (the cost envelope) vanish silently.
        usrc = os.path.join(d, "usrc")
        os.makedirs(usrc)
        with open(os.path.join(usrc, "reticuli.toml"), "w") as f:
            f.write(FIXTURE)
        prod = os.path.join(d, "p.py")
        with open(prod, "w") as f:
            f.write("import os, json\n"
                    "open(os.environ['RETICULI_OUTPUT'], 'w').write('hello\\n')\n"
                    "u = os.environ.get('RETICULI_USAGE')\n"
                    "open(u, 'w').write(json.dumps({'tokens': 7, 'usd': 0.02})) if u else None\n")
        cwd0 = os.getcwd()
        os.chdir(d)
        try:
            kernel.realize(usrc, f"{sys.executable} {prod}", "relout")   # relative into
        finally:
            os.chdir(cwd0)
        uc = kernel.cost(os.path.join(d, "relout"))
        assert uc and uc.get("tokens") == 7 and uc.get("usd") == 0.02, \
            "producer-reported cost reaches the ledger (relative into)"
        with open(os.path.join(m1, kernel.LEDGER), "w") as f:
            f.write('{"event": "oracle", "calls": 4}\n')       # a 4-call original
        rr = kernel.three_machine(m1, m2, m3)                  # vs the 1-call redo
        assert rr["cost"]["comparable"] is False and not rr["satisfied"], "cost gates the test"

        # quarantine: a record's gates are not your shell. The ledger tells the
        # truth about the jail; where one exists, an escaping gate refuses.
        backend = kernel.jail("true", m3)[1]
        with open(os.path.join(m3, kernel.LEDGER)) as f:
            gate_line = [json.loads(x) for x in f if '"gate"' in x][-1]
        assert gate_line["quarantine"] == backend, "the ledger records the jail"
        m1e = os.path.join(d, "m1e")
        os.makedirs(m1e)
        with open(os.path.join(m1e, "reticuli.toml"), "w") as f:
            f.write(FIXTURE.replace("grep -qi hello g.txt && printf v > V",
                                    "printf pwn > ../escape.txt && printf v > V"))
        if backend in ("seatbelt", "bubblewrap"):
            try:
                kernel.realize(m1e, "printf 'hello jail\\n' > g.txt", os.path.join(d, "m4"))
                raise AssertionError("an escaping gate must refuse")
            except kernel.ReticuliError:
                pass
            assert not os.path.exists(os.path.join(d, "escape.txt")), "nothing escaped"
        else:                                                  # no jail here: recorded, not hidden
            kernel.realize(m1e, "printf 'hello jail\\n' > g.txt", os.path.join(d, "m4"))

        # comparability is a BAND ([1/tol, tol]), not equality: a redo that cost
        # 1.5x the original is comparable at the default tolerance. A kernel that
        # demands exact-equal cost passes the 4:1 case above yet fails here.
        # (last — it clobbers the ledgers it writes.)
        with open(os.path.join(m1, kernel.LEDGER), "w") as f:
            f.write('{"event": "oracle", "calls": 2}\n')       # a 2-call original
        with open(os.path.join(m3, kernel.LEDGER), "w") as f:
            f.write('{"event": "oracle", "calls": 3}\n')       # a 3-call redo -> 1.5x
        rb = kernel.three_machine(m1, m2, m3)
        assert rb["cost"]["comparable"] is True, "a 1.5x redo is comparable (a band, not equality)"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    _rejail()
    battery()
    with open("KERNEL_OK", "w") as f:
        f.write("kernel-ok\n")
    print("kernel-ok")

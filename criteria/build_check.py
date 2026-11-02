"""Kernel-build conformance gate — materialize, re-earn, rebuild.

`audit` re-runs a claim's gates against the bytes present, cold, and re-checks
that the claim still holds; a stored "passed" is never trusted. Writes BUILD_OK.

    python3 criteria/build_check.py        (from the repository root)
"""
import os
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
from reticuli._kernel import build, core, seal

CLAIM = ('[claim]\nname = "b"\ninputs = ["check.txt"]\n\n[[step]]\n'
         'kind = "produce"\noutput = "impl.txt"\nclass = "generated"\n'
         'request = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
         'class = "validated"\nrun = "grep -qx ok impl.txt && printf v > V"\n')

#: TWO generated outputs, on purpose: every other producer fixture in this
#: boundary has exactly one, and a conforming kernel was measured naming the
#: target only in that case (r8). A claim with a single output cannot tell a
#: kernel that forgets to name the target from one that names it.
MULTI = ('[claim]\nname = "m"\ninputs = ["check.txt"]\n\n[[step]]\n'
         'kind = "produce"\noutput = "a.txt"\nclass = "generated"\n\n'
         '[[step]]\nkind = "produce"\noutput = "b.txt"\nclass = "generated"\n\n'
         '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
         'run = "grep -qx ok a.txt && grep -qx ok b.txt && printf v > V"\n')

#: FORMAT 4 with guidance and deliberately unsorted steps, on purpose: every
#: rebuild fixture above is format 1, where the room receives the recipe
#: byte-for-byte — so the REWRITE path (format 3+: the room gets the
#: preimage recipe) ran under no pinned rebuild, and a conforming kernel was
#: measured writing the preimage's canonical JSON into the file named
#: reticuli.toml, then refusing its own file (r12): self-incompatible with
#: the entire migrated era. The steps are ordered gate-first so the
#: materialized room also witnesses the format-4 canonical sort.
F4 = ('[claim]\nname = "f4room"\ninputs = ["check.txt"]\nformat = 4\n\n'
      '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
      'run = "grep -qx ok impl.txt && printf v > V"\n\n'
      '[[step]]\nkind = "produce"\noutput = "impl.txt"\nclass = "generated"\n'
      'guidance = "words the room must not carry"\n')




# ==== seam block for build_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- _kernel/build.py: 8 seam names (0 value, 0 kind, 8 callable) ---
_SEAM__kernel_build_VALUES = {
}
_SEAM__kernel_build_KINDS = {}
_SEAM__kernel_build_CALLABLES = ('_authorized', '_compare_pin', '_materialize', '_produce', '_read_usage', '_ssh_verify', '_step_guidance', 'audit')

def _seam() -> None:
    from reticuli._kernel import build as _m__kernel_build
    for _n, _v in _SEAM__kernel_build_VALUES.items():
        assert getattr(_m__kernel_build, _n) == _v, f'_kernel/build.py seam {_n} changed'
    for _n in _SEAM__kernel_build_KINDS:
        assert hasattr(_m__kernel_build, _n), f'_kernel/build.py must export {_n}'
    for _n in _SEAM__kernel_build_CALLABLES:
        assert callable(getattr(_m__kernel_build, _n, None)), f'_kernel/build.py must export callable {_n}'


def battery() -> None:
    _seam()
    d = tempfile.mkdtemp()
    try:
        c = os.path.join(d, "c")
        os.makedirs(c)
        for name, body in {"claim.toml": CLAIM, "check.txt": "the impl says ok\n",
                           "impl.txt": "ok\n"}.items():
            with open(os.path.join(c, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx ok impl.txt && printf v > V",
                       shell=True, cwd=c, check=True)
        seal.seal(c)
        assert seal.verify(c)["ok"], "the claim seals and verifies"

        r = build.audit(c)
        assert r["ok"], f"a sealed claim re-earns its gate cold: {r.get('verdict')}"
        assert r["gates"] and r["gates"][0]["status"] in ("ok", "reproduced"), \
            f"the gate is reproduced: {r['gates']!r}"

        # THE SANDBOX SIGNAL IS PINNED (2026-10-05, keyholder-signed; the
        # pin-the-sandbox-signal proposal). A verdict's record
        # must SAY what jail earned it: the first cross-judging run found
        # both regrown kernels earning every verdict while reporting no
        # quarantine at all — and a transfer-acceptor pricing a signed earn
        # at thousands of times a local one needs exactly this provenance.
        # The vocabulary is closed, and `none` is the honest word for an
        # unsandboxed earn — an absent key is never a conforming answer.
        QUARANTINES = {"seatbelt", "bubblewrap", "inherited", "none"}
        for g in r["gates"]:
            assert g.get("quarantine") in QUARANTINES, \
                f"an audit's gate row names its jail: {g!r}"

        reb = os.path.join(d, "reb")
        rr = build.rebuild(c, "printf 'ok\\n' > impl.txt", reb)
        assert rr["root"], "the rebuild seals"
        assert rr.get("quarantine") in QUARANTINES, \
            f"a rebuild's result names its jail: {rr!r}"

        # THE PRODUCER INHERITS THE CALLER'S REACHABILITY (2026-10-05, the
        # free-the-producer proposal; HARDENED 2026-10-08, the
        # harden-the-producer-freedom-probe proposal). A producer is the
        # caller's oracle: it needs the network (model calls) and a real
        # process environment, and its output faces the jailed gate
        # regardless — so the kernel scrubs its environment but must not
        # CONFINE it beyond what the caller already is. The r4 regrown kernel
        # jailed producers (codex died on its stack guard page; any survivor
        # found the network denied — a descendant that judges but cannot
        # procreate).
        #
        # The property is INHERITANCE, not absolute network. An earlier form
        # asserted a socket bind simply succeeds, guarded by
        # sandbox_backend() != "inherited"; that conflated "the kernel adds
        # no jail" with "the ambient host has network", and fired falsely
        # whenever this check itself ran inside an outer confinement that did
        # not propagate RETICULI_JAILED (the succession per-layer gate; r14).
        # So first measure what the CALLER can do, then require the producer
        # to match it. If the caller is already confined, the property holds
        # vacuously and the probe is a no-op — robust in every environment.
        def _can_bind() -> bool:
            import socket
            try:
                s = socket.socket()
                s.bind(("127.0.0.1", 0))
                s.close()
                return True
            except OSError:
                return False

        if _can_bind():
            reb2 = os.path.join(d, "reb2")
            rr2 = build.rebuild(
                c,
                "python3 -c \"import socket; s = socket.socket(); "
                "s.bind(('127.0.0.1', 0)); s.close(); "
                "open('impl.txt', 'w').write('ok\\n')\"",
                reb2)
            assert rr2["root"], \
                "a producer inherits the caller's network reachability: " \
                "the caller can bind a socket, so the kernel's producer must " \
                "too — the kernel adds no jail of its own"

        # THE PRODUCER KEEPS THE CALLER'S HOME (2026-10-06,
        # keyholder-signed; the-producer-keeps-its-home proposal). Freedom
        # has two halves: the r6 kernel ran producers unjailed with the
        # network reachable — and every real producer died 401, because its
        # scrub handed producers a scratch HOME and the model CLI's
        # credential lives there. The producer is the caller's oracle,
        # working with the caller's standing; its HOME is the caller's. The
        # GATES' opposite contract (a scratch HOME, nothing inherited) is
        # pinned elsewhere and unchanged.
        reb3 = os.path.join(d, "reb3")
        home = os.environ.get("HOME", "")
        rr3 = build.rebuild(
            c,
            "python3 -c \"import os, sys; "
            f"sys.exit(0 if os.environ.get('HOME') == {home!r} else 7)\" "
            "&& printf 'ok\\n' > impl.txt",
            reb3)
        assert rr3["root"], \
            "the producer observes the caller's HOME, credentials and all"

        # AND IT IS TOLD WHICH OUTPUT TO WRITE (2026-10-06, keyholder-signed;
        # the name-the-next-output-always proposal). The kernel names the
        # target in RETICULI_OUTPUT — an absolute path, one of the claim's
        # own outputs — and lists them all in RETICULI_OUTPUTS, whether the
        # claim has one generated output or twenty. The r8 kernel named it
        # only when there was exactly one, and relatively at that, so it
        # could not drive a producer on any layer of this repository's chain
        # while satisfying every pinned fixture (all of which had a single
        # output). core_check pins the variables' SPELLING; this pins that
        # they are there and what they mean.
        multi = os.path.join(d, "multi")
        os.makedirs(multi)
        for name, body in {"claim.toml": MULTI, "check.txt": "two outputs\n",
                           "a.txt": "ok\n", "b.txt": "ok\n"}.items():
            with open(os.path.join(multi, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx ok a.txt && grep -qx ok b.txt && printf v > V",
                       shell=True, cwd=multi, check=True)       # warm, so it seals
        seal.seal(multi)
        prod = os.path.join(d, "named_target_producer.py")
        with open(prod, "w", encoding="utf-8") as f:
            f.write("import json, os\n"
                    "target = os.environ['RETICULI_OUTPUT']\n"
                    "assert os.path.isabs(target), f'not absolute: {target}'\n"
                    "outs = json.loads(os.environ['RETICULI_OUTPUTS'])\n"
                    "assert sorted(outs) == ['a.txt', 'b.txt'], outs\n"
                    "assert os.path.basename(target) in outs, target\n"
                    "for name in outs:\n"
                    "    with open(name, 'w') as fh:\n"
                    "        fh.write('ok\\n')\n")
        rr4 = build.rebuild(multi, f"{sys.executable} {prod}",
                            os.path.join(d, "multi-m3"))
        assert rr4["root"] == seal.verify(multi)["root"], \
            "a producer on a multi-output claim is told which output to " \
            "write, absolutely, and lands the claim's root"

        # THE ROOM RECIPE IS THE PREIMAGE, AS TOML (2026-10-07,
        # keyholder-signed; the-room-recipe-is-toml proposal). At format 3+
        # the room receives the recipe the root was computed from, and that
        # file must still BE a recipe: TOML that parses to the preimage
        # tables. The r12 kernel wrote the preimage's canonical JSON into
        # reticuli.toml and refused its own file — unable to rebuild or
        # audit anything of the migrated era — and no fixture here could
        # see it, because every rebuild above is format 1, the copy path.
        # The producer captures the room's recipe mid-rebuild so the room
        # itself is witnessed, not reconstructed.
        f4 = os.path.join(d, "f4room")
        os.makedirs(f4)
        for name, body in {"claim.toml": F4, "check.txt": "fmt4\n",
                           "impl.txt": "ok\n"}.items():
            with open(os.path.join(f4, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx ok impl.txt && printf v > V",
                       shell=True, cwd=f4, check=True)
        seal.seal(f4)
        grabbed = os.path.join(d, "room_recipe_copy.toml")
        prod4 = os.path.join(d, "f4_producer.py")
        with open(prod4, "w", encoding="utf-8") as f:
            f.write("import os, shutil\n"
                    "name = 'reticuli.toml' if os.path.isfile('reticuli.toml')"
                    " else 'claim.toml'\n"
                    f"shutil.copyfile(name, {grabbed!r})\n"
                    "with open('impl.txt', 'w') as fh:\n"
                    "    fh.write('ok\\n')\n")
        rr5 = build.rebuild(f4, f"{sys.executable} {prod4}",
                            os.path.join(d, "f4-m3"))
        assert rr5["root"] == seal.verify(f4)["root"], \
            "a format-4 claim rebuilds to its own root"
        import tomllib
        with open(grabbed, "rb") as f:
            room_recipe = tomllib.load(f)     # refuses JSON-in-toml loudly
        f4_steps = room_recipe.get("step", [])
        assert all("guidance" not in s and "request" not in s
                   for s in f4_steps), \
            "the room recipe is the PREIMAGE: guidance does not enter the room"
        # SUBSTANCE, NOT PRESENTATION (2026-10-08, keyholder-signed; the
        # the-room-is-substance-not-form proposal). The first draft of this
        # pin required the room's steps in format-4 CANONICAL order — but at
        # format 4 step order is authoring form, re-deriving the identical
        # root, so demanding one order refuses a conforming kernel that
        # materializes an honest, guidance-free room in file order (the r11
        # tree, caught by the outside-re-earn kit's smoke test). The room
        # recipe must carry the right STEPS, as a set; the order it writes
        # them in is as free in the room as it is in the sealed recipe.
        room_outputs = sorted(s["output"] for s in f4_steps)
        assert room_outputs == ["V", "impl.txt"], \
            f"the room recipe carries the preimage's steps: {room_outputs!r}"

        # A CARRIED FILE SHIPS WITHOUT BEING REGROWN (format 5, the APEIRON
        # campaign's item 4). The class vocabulary had regrowable and
        # pinned-as-criterion, and nothing for a file that is part of the
        # shipped artifact yet carries no behavior — deployment scripts,
        # prose — so a package swap silently deleted them. Carried bytes are
        # inside the root, OUTSIDE the producer's work list, and arrive in a
        # rebuild byte-identical; a producer that rewrites one is refused,
        # because changing a carried file is making a different claim.
        CARRIED = ('[claim]\nname = "ships"\nformat = 5\n'
                   'inputs = ["check.txt"]\n\n'
                   '[[step]]\nkind = "produce"\noutput = "impl.txt"\n'
                   'class = "generated"\n\n'
                   '[[step]]\nkind = "produce"\noutput = "NOTES.md"\n'
                   'class = "carried"\n\n'
                   '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
                   'run = "grep -qx ok impl.txt && printf v > V"\n')
        ship = os.path.join(d, "ship")
        os.makedirs(ship)
        for name, body in {"reticuli.toml": CARRIED, "check.txt": "crit\n",
                           "impl.txt": "ok\n",
                           "NOTES.md": "deploy notes, prose only\n"}.items():
            with open(os.path.join(ship, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx ok impl.txt && printf v > V",
                       shell=True, cwd=ship, check=True)
        seal.seal(ship)
        blind_prod = os.path.join(d, "carried_producer.py")
        with open(blind_prod, "w", encoding="utf-8") as f:
            f.write("import json, os\n"
                    "outs = json.loads(os.environ['RETICULI_OUTPUTS'])\n"
                    "assert outs == ['impl.txt'], outs  # carried is not work\n"
                    "assert os.path.isfile('NOTES.md')  # but it is present\n"
                    "open('impl.txt', 'w').write('ok\\n')\n")
        rr6 = build.rebuild(ship, f"{sys.executable} {blind_prod}",
                            os.path.join(d, "ship-m3"))
        assert rr6["root"] == seal.verify(ship)["root"], \
            "a carried claim rebuilds to its root, the producer never told " \
            "to write the carried file"
        with open(os.path.join(d, "ship-m3", "NOTES.md"), "rb") as f1, \
                open(os.path.join(ship, "NOTES.md"), "rb") as f2:
            assert f1.read() == f2.read(), "carried bytes arrive byte-identical"
        rewriter = os.path.join(d, "carried_rewriter.py")
        with open(rewriter, "w", encoding="utf-8") as f:
            f.write("open('impl.txt', 'w').write('ok\\n')\n"
                    "open('NOTES.md', 'w').write('improved prose\\n')\n")
        try:
            build.rebuild(ship, f"{sys.executable} {rewriter}",
                          os.path.join(d, "ship-m4"))
        except core.ClaimError as exc:
            assert "NOTES.md" in str(exc), \
                f"the refusal names the carried file: {exc!r}"
        else:
            raise AssertionError(
                "a producer that rewrites a carried file must be refused")

        # AN ASSEMBLY CLAIM JUDGES THE COMPOSITION (format 5, the campaign's
        # item 2). Five of its ledger entries were edges no per-component
        # criterion can express from inside its room — the import seam, call
        # signatures, what an inherited method must do at a boundary — each
        # one a rebuild that passed every gate and failed at assembly. An
        # `assembles` claim pins its members' ROOTS in its own recipe (so the
        # assembly moves when a member is re-pinned) and its gates run
        # against the members' shipped outputs; a member whose bytes no
        # longer recompute to the declared root refuses the fold, because a
        # moved member is a different composition.
        member = os.path.join(d, "member")
        os.makedirs(member)
        MEMBER = ('[claim]\nname = "member"\ninputs = ["check_m.txt"]\n\n'
                  '[[step]]\nkind = "produce"\noutput = "lib.txt"\n'
                  'class = "generated"\n\n'
                  '[[step]]\nkind = "gate"\noutput = "MV"\nclass = "validated"\n'
                  'run = "grep -qx two lib.txt && printf v > MV"\n')
        for name, body in {"reticuli.toml": MEMBER, "check_m.txt": "crit\n",
                           "lib.txt": "two\n"}.items():
            with open(os.path.join(member, name), "w", encoding="utf-8") as f:
                f.write(body)
        subprocess.run("grep -qx two lib.txt && printf v > MV",
                       shell=True, cwd=member, check=True)
        seal.seal(member)
        member_root = seal.read_manifest(member)["root"]
        assembly = os.path.join(d, "assembly")
        os.makedirs(assembly)
        ASSEMBLY = ('[claim]\nname = "assembly"\nformat = 5\n'
                    'inputs = ["check_a.txt"]\n'
                    f'assembles = ["member@{member_root}"]\n\n'
                    '[[step]]\nkind = "gate"\noutput = "AV"\n'
                    'class = "validated"\n'
                    # the composition edge: the assembly's gate reads the
                    # member's shipped output across the seam
                    'run = "grep -qx two lib.txt && printf v > AV"\n')
        for name, body in {"reticuli.toml": ASSEMBLY,
                           "check_a.txt": "crit\n",
                           # the pinned verdict, written warm: the gate's own
                           # bytes come from the ROOM, where lib.txt arrives
                           "AV": "v"}.items():
            with open(os.path.join(assembly, name), "w", encoding="utf-8") as f:
                f.write(body)
        import shutil as _sh
        _sh.copytree(member, os.path.join(assembly, ".reticuli", "sealed",
                                          "member"))
        seal.seal(assembly)
        assembly_root = seal.read_manifest(assembly)["root"]
        ra = build.audit(assembly)
        assert ra["ok"], \
            f"an assembly's gate judges the members' shipped outputs: {ra!r}"
        staged = os.path.join(assembly, ".reticuli", "sealed", "member",
                              "check_m.txt")
        with open(staged, "w", encoding="utf-8") as f:
            f.write("a stricter criterion\n")
        try:
            build.audit(assembly)
        except core.ClaimError:
            pass                        # the refusal, in band
        else:
            raise AssertionError("a member off its declared root must refuse "
                                 "the fold, not judge a different composition")
        with open(os.path.join(assembly, "reticuli.toml"), "w",
                  encoding="utf-8") as f:
            f.write(ASSEMBLY.replace(member_root, "f" * 64))
        seal.seal(assembly)
        assert seal.read_manifest(assembly)["root"] != assembly_root, \
            "re-pinning a member moves the assembly's own root: the member " \
            "roots are inside it"

        # editing the pinned input breaks the claim: audit is not fooled
        with open(os.path.join(c, "check.txt"), "w", encoding="utf-8") as f:
            f.write("a different criterion\n")
        assert not build.audit(c)["ok"], "a tampered pinned input fails audit"
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("BUILD_OK", "w", encoding="utf-8") as f:
            f.write("build-ok\n")
    print("build-ok")

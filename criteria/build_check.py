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
from reticuli._kernel import build, seal

CLAIM = ('[claim]\nname = "b"\ninputs = ["check.txt"]\n\n[[step]]\n'
         'kind = "produce"\noutput = "impl.txt"\nclass = "generated"\n'
         'request = "x"\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
         'class = "validated"\nrun = "grep -qx ok impl.txt && printf v > V"\n')




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

        # THE PRODUCER RUNS FREE (2026-10-05, keyholder-signed; the
        # free-the-producer proposal). A producer is the caller's oracle: it
        # needs the network (model calls) and a real process environment,
        # and its output faces the jailed gate regardless — so the kernel
        # scrubs its environment but must not confine it. The r4 regrown
        # kernel jailed producers: codex died allocating its stack guard
        # page, and any survivor would have found the network denied — a
        # descendant that judges but cannot procreate. The probe binds a
        # localhost socket, exactly what the gate quarantine refuses (the
        # run layer pins that side), and must succeed as a producer. Skipped
        # under an INHERITED jail (this check itself running inside a gate,
        # as in the self-claim chain): sandboxes do not nest, so there the
        # network is not the kernel's to grant — the pin binds the kernel's
        # own choice, not the host's.
        if build.sandbox_backend() != "inherited":
            reb2 = os.path.join(d, "reb2")
            rr2 = build.rebuild(
                c,
                "python3 -c \"import socket; s = socket.socket(); "
                "s.bind(('127.0.0.1', 0)); s.close(); "
                "open('impl.txt', 'w').write('ok\\n')\"",
                reb2)
            assert rr2["root"], \
                "a socket-binding producer succeeds: the kernel imposes no jail"

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

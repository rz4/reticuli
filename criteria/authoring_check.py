"""Authoring conformance gate — the acceptance check of the `authoring` layer.

The machinery that turns sessions into claims: authoring (propose from a trace,
certify cold, account the session's C1), feedback (sense what's sealable), pack
(a project as a self-claim: implementation generated, check claimed), and
render's recipe writer. Layers on exchange; knows nothing of the CLI. Writes
AUTHORING_OK iff the layer conforms. Stdlib only, so it runs in any clean
workspace.

    python3 checks/authoring_check.py        (from the repository root)
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib

sys.path.insert(0, "src" if os.path.isdir("src/reticuli") else ".")
from reticuli import authoring as authoring_mod
from reticuli import feedback, kernel, pack, render
from reticuli.authoring import build_claim


def _calls_sandbox_directly(path: str) -> bool:
    """True if the module reaches for kernel.sandbox itself (a Call to a
    `sandbox` attribute or name) — an authoring module must run gates only
    through kernel.run_gate, which owns the scrub, the bound, and the sandbox."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "sandbox":
                return True
            if isinstance(fn, ast.Name) and fn.id == "sandbox":
                return True
    return False




# ==== seam block for authoring_check.py ====
# Paste into the check; call _seam() from its battery()/main.

# --- render.py: 7 seam names (0 value, 0 kind, 7 callable) ---
_SEAM_render_VALUES = {
}
_SEAM_render_KINDS = {}
_SEAM_render_CALLABLES = ('ago', 'duration', 'paint', 'short', 'table', 'toml', 'tree')

def _seam() -> None:
    from reticuli import render as _m_render
    for _n, _v in _SEAM_render_VALUES.items():
        assert getattr(_m_render, _n) == _v, f'render.py seam {_n} changed'
    for _n in _SEAM_render_KINDS:
        assert hasattr(_m_render, _n), f'render.py must export {_n}'
    for _n in _SEAM_render_CALLABLES:
        assert callable(getattr(_m_render, _n, None)), f'render.py must export callable {_n}'


def battery() -> None:
    _seam()
    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws")
        os.makedirs(os.path.join(ws, ".reticuli"))
        with open(os.path.join(ws, "answer.txt"), "w") as f:
            f.write("42\n")
        gate = "grep -qx 42 answer.txt && printf ok > OK"
        events = [{"event": "prompt", "text": "write the answer", "ts": 5.0},
                  {"event": "write", "path": "answer.txt", "ts": 6.0},
                  {"event": "bash", "cmd": gate, "ts": 7.0}]
        with open(os.path.join(ws, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in events) + "\n")
        subprocess.run(gate, shell=True, cwd=ws, check=True)

        # the advisor senses a checked session as sealable
        assert feedback.advise(ws)["sealable"], "feedback"

        # IDENTITY MUST NOT DEPEND ON THE HOST FILESYSTEM. The gate above writes
        # `printf ok > OK`, so the shell token `ok` is a candidate input; on a
        # case-insensitive filesystem (macOS, Windows) it tests true against the
        # file `OK`. Pinning it would seal the SAME session to different roots on
        # different hosts, and name an input a case-sensitive host cannot find.
        # A candidate must match a real directory entry, case and all.
        cws = os.path.join(d, "case")
        os.makedirs(os.path.join(cws, ".reticuli"))
        with open(os.path.join(cws, "Note.txt"), "w") as f:
            f.write("hi\n")
        cgate = "grep -q hi Note.txt && printf ok > OK"
        with open(os.path.join(cws, ".reticuli", "draft.jsonl"), "w") as f:
            f.write(json.dumps({"event": "prompt", "text": "check it"}) + "\n")
            f.write(json.dumps({"event": "bash", "cmd": cgate}) + "\n")
        subprocess.run(cgate, shell=True, cwd=cws, check=True)
        cin = authoring_mod.propose(cws, ["OK"], "cased")["claim"]["inputs"]
        assert "ok" not in cin, \
            "a case-folded token is no input: identity must not follow the filesystem"
        assert "Note.txt" in cin, "the real input is pinned under its own name"
        assert "note.txt" not in cin, "and never under a folded one"

        # build_claim certifies cold; the claim verifies and carries the session's
        # cost as its C1 — one oracle call per prompt, the trace's span
        rec = os.path.join(ws, ".reticuli", "sealed", "answer")
        assert build_claim(ws, ["OK"], rec, name="answer")["ok"], "build_claim"
        assert kernel.verify(rec)["ok"], "verify"
        c1 = kernel.cost(rec)
        assert c1["calls"] == 1 and c1["seconds"] == 2.0, "build_claim accounts C1"

        # a redo with different work lands on the same root (the basin), and the
        # proposed recipe round-trips through the renderer byte-faithfully
        m3 = os.path.join(d, "m3")
        kernel.rebuild(rec, "printf '42\\n' > answer.txt", m3)
        assert kernel.verify(m3)["root"] == kernel.verify(rec)["root"], "basin"
        recipe = kernel.load_recipe(rec)
        assert tomllib.loads(render.dump_recipe(recipe)) == recipe, "recipe round-trip"

        # pack: the implementation is generated, the check is the claim
        proj = os.path.join(d, "proj")
        os.makedirs(os.path.join(proj, "pkg"))
        with open(os.path.join(proj, "pkg", "__init__.py"), "w") as f:
            f.write("VALUE = 42\n")
        with open(os.path.join(proj, "check.py"), "w") as f:
            f.write("import sys; sys.path.insert(0, '.')\n"
                    "from pkg import VALUE\nassert VALUE == 42\n"
                    "open('OK', 'w').write('ok\\n')\n")

        def repack():
            return pack.pack(proj, "proj", ["pkg/*.py"], ["check.py"],
                             "python3 check.py", "OK")["root"]

        r0 = repack()
        with open(os.path.join(proj, "pkg", "__init__.py"), "a") as f:
            f.write("# generated\n")
        assert repack() == r0, "editing the implementation keeps the root"
        with open(os.path.join(proj, "check.py"), "a") as f:
            f.write("# a stricter claim\n")
        assert repack() != r0, "editing the check moves the claim"

        # cold-certification: the trace has no authority. build_claim must rebuild
        # in a clean workspace and re-run every gate COLD; a pinned verdict that
        # does not reproduce from the bytes (a nondeterministic gate) must refuse
        # to seal — no claim forms from one the workspace cannot re-earn.
        ws2 = os.path.join(d, "ws2")
        os.makedirs(os.path.join(ws2, ".reticuli"))
        nd_gate = ("python3 -c \"import time; open('STAMP','w')"
                   ".write(str(time.time_ns()))\"")
        events2 = [{"event": "prompt", "text": "stamp the moment", "ts": 1.0},
                   {"event": "bash", "cmd": nd_gate, "ts": 2.0}]
        with open(os.path.join(ws2, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in events2) + "\n")
        subprocess.run(nd_gate, shell=True, cwd=ws2, check=True)   # warm STAMP
        rec2 = os.path.join(ws2, ".reticuli", "sealed", "stamp")
        try:
            build_claim(ws2, ["STAMP"], rec2, name="stamp")
            raise AssertionError("build_claim must refuse a verdict it cannot re-earn cold")
        except kernel.ClaimError:
            pass

        # the AUTHORING GATE CONTRACT: build_claim and pack run gates only through
        # kernel.run_gate (scrubbed env, bounded wall-clock, quarantine), never
        # kernel.sandbox directly — reaching for the sandbox runner bypasses the
        # declared bound. Enforced structurally, so a refactor cannot quietly
        # reopen the hole the reviewer found (pack sealing an inherited secret).
        for mod in (authoring_mod, pack):
            assert not _calls_sandbox_directly(mod.__file__), \
                f"{os.path.basename(mod.__file__)} must run gates via kernel.run_gate, not kernel.sandbox"

        # finding 1, behaviorally: pack runs the gate SCRUBBED, so an inherited
        # env secret cannot be sealed into the verdict.
        secret = "s3cr3t-" + "not-real"
        os.environ["AUTHORING_LEAK_PROBE"] = secret
        try:
            lp = os.path.join(d, "leakproj")
            os.makedirs(lp)
            with open(os.path.join(lp, "chk.py"), "w") as f:
                f.write("import os\n"
                        "open('OK','w').write(os.environ.get('AUTHORING_LEAK_PROBE','clean'))\n")
            with open(os.path.join(lp, "src.py"), "w") as f:
                f.write("# generated\n")
            pack.pack(lp, "leak", ["src.py"], ["chk.py"], "python3 chk.py", "OK")
            with open(os.path.join(lp, "OK")) as f:
                assert secret not in f.read(), "pack must run the gate scrubbed (secret reached the verdict)"
        finally:
            os.environ.pop("AUTHORING_LEAK_PROBE", None)

        # THE CLAIM BOUNDARY IS DECLARED, NOT INFERRED. The README flow — the
        # agent writes solver.py AND check.py — would make the check generated, so
        # a vacuous check over a wrong solver would seal at the same root as the
        # real thing. build_claim must refuse that gate as vacuous, seal it once
        # the check is claimed (`claim=`), and generate an implementation no hook
        # saw written (`generated=`). Provenance never decides class; declaration does.
        vs = os.path.join(d, "vacuous")
        os.makedirs(os.path.join(vs, ".reticuli"))
        with open(os.path.join(vs, "solver.py"), "w") as f:
            f.write("open('result.txt', 'w').write('42\\n')\n")
        with open(os.path.join(vs, "check.py"), "w") as f:
            f.write("assert open('result.txt').read().strip() == '42'\n")
        vgate = "python3 solver.py && python3 check.py && printf ok > VERIFIED"
        vevents = [{"event": "prompt", "text": "solve", "ts": 1.0},
                   {"event": "write", "path": "solver.py", "ts": 2.0},
                   {"event": "write", "path": "check.py", "ts": 3.0},
                   {"event": "bash", "cmd": vgate, "ts": 4.0}]
        with open(os.path.join(vs, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in vevents) + "\n")
        subprocess.run(vgate, shell=True, cwd=vs, check=True)
        try:
            build_claim(vs, ["VERIFIED"], os.path.join(d, "vac-rec"), name="vac")
            raise AssertionError("build_claim must refuse a gate whose every decider is generated")
        except kernel.ClaimError as e:
            assert "vacuous" in str(e), "and name the refusal"
        vr = build_claim(vs, ["VERIFIED"], os.path.join(d, "vac-rec"), name="vac", claim=["check.py"])
        vrec = kernel.load_recipe(os.path.join(d, "vac-rec"))
        assert vrec["claim"]["inputs"] == ["check.py"], "the claimed check is an input"
        assert [s["output"] for s in vrec["step"] if s["kind"] == "produce"] == ["solver.py"], \
            "the solver stays generated"
        with open(os.path.join(vs, "check.py"), "a") as f:
            f.write("# tightened\n")
        vr2 = build_claim(vs, ["VERIFIED"], os.path.join(d, "vac-rec2"), name="vac", claim=["check.py"])
        assert vr2["root"] != vr["root"], "the check is the claim: editing it moves the root"
        hs = os.path.join(d, "hookless")            # a human at a terminal: bash events only
        os.makedirs(os.path.join(hs, ".reticuli"))
        for name in ("solver.py", "check.py"):
            shutil.copyfile(os.path.join(vs, name), os.path.join(hs, name))
        with open(os.path.join(hs, ".reticuli", "draft.jsonl"), "w") as f:
            f.write(json.dumps({"event": "bash", "cmd": vgate, "ts": 1.0}) + "\n")
        subprocess.run(vgate, shell=True, cwd=hs, check=True)
        build_claim(hs, ["VERIFIED"], os.path.join(d, "hook-rec"), name="hl",
                    claim=["check.py"], generated=["solver.py"])
        hrec = kernel.load_recipe(os.path.join(d, "hook-rec"))
        assert hrec["claim"]["inputs"] == ["check.py"] and \
            any(s["output"] == "solver.py" and s["class"] == "generated" for s in hrec["step"]), \
            "--generated generates an untraced implementation; --claim claims the check"
        # pack applies the same rule: generated tests as the only decider are refused
        pp = os.path.join(d, "packproj")
        os.makedirs(pp)
        with open(os.path.join(pp, "x.py"), "w") as f:
            f.write("X = 1\n")
        with open(os.path.join(pp, "test_x.py"), "w") as f:
            f.write("from x import X\nassert X == 1\n")
        try:
            pack.pack(pp, "pp", ["*.py"], [], "python3 test_x.py && printf ok > OK", "OK")
            raise AssertionError("pack must refuse generated tests as the only decider")
        except kernel.ClaimError as e:
            assert "vacuous" in str(e)
        assert pack.pack(pp, "pp", ["x.py"], ["test_x.py"], "python3 test_x.py && printf ok > OK", "OK")["ok"]

        # finding 2: build_claim confines trace-derived paths BEFORE copying them.
        # A traced read of ../secret is an input that escapes the session;
        # build_claim must refuse it at the confinement boundary, not copy it out
        # of the .building workspace on the way to the seal that refuses it.
        cs = os.path.join(d, "confine-sess")
        os.makedirs(os.path.join(cs, ".reticuli"))
        with open(os.path.join(cs, "solver.py"), "w") as f:
            f.write("print('ok')\n")
        with open(os.path.join(d, "cs-secret.txt"), "w") as f:     # at the session's PARENT
            f.write("TOP SECRET\n")
        cs_events = [{"event": "prompt", "text": "solve", "ts": 1.0},
                     {"event": "write", "path": "solver.py", "ts": 2.0},
                     {"event": "read", "path": "../cs-secret.txt", "ts": 3.0},
                     {"event": "bash", "cmd": "python3 solver.py && printf ok > OK", "ts": 4.0}]
        with open(os.path.join(cs, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in cs_events) + "\n")
        subprocess.run("python3 solver.py && printf ok > OK", shell=True, cwd=cs, check=True)
        cs_rec = os.path.join(d, "confine-rec")
        try:
            build_claim(cs, ["OK"], cs_rec, name="confine")
            raise AssertionError("build_claim must refuse a trace-derived input that escapes the session")
        except kernel.ClaimError:
            pass
        stray = [os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs
                 if f == "cs-secret.txt" and os.path.join(r, f) != os.path.join(d, "cs-secret.txt")]
        assert not stray, f"build_claim copied the escaping input out of the workspace before refusing: {stray}"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    # A verdict is a claim's pinned OUTPUT, so write one only when this suite
    # is running as a claim's gate. Run from anywhere else it is just noise in
    # someone's working directory.
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("AUTHORING_OK", "w") as f:
            f.write("authoring-ok\n")
    print("authoring-ok")

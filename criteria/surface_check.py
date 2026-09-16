"""Surface conformance gate — the acceptance check of the `surface` layer.

The human handshake: drives the CLI end-to-end through the layers beneath it
(init -> run -> seal -> verify -> rebuild -> crosscheck) and claims the volatile
surface itself — argv grammar, exit codes, the shape of what a user sees (TOML
verdicts, the cost block, --json underneath). The functional depth is claimed by
the inner gates (kernel_check, exchange_check, authoring_check, agents_check,
launcher_check); above sits only contact — the README. Writes SURFACE_OK iff the
toolchain a *user* touches is conformant. Stdlib only, so it runs in any clean
workspace.

    python3 checks/surface_check.py        (from the repository root)
"""
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
import reticuli.__main__   # the CLI entrypoint
from reticuli import cli

# --help is organized by process phase, not a flat verb dump — a mental map the
# user reads top to bottom as the workflow itself. The census showed structure
# evaporates unless a gate demands it, so the sections and their membership are
# ratified here; the wording of each line stays free.
SECTIONS = ("session (draft):", "author (draft -> sealed, M1):",
            "transfer (sealed, M2):", "redo (sealed -> signed, M3):", "compose:")
LISTED = {"init", "hooks", "status", "run", "seal", "verify", "export",
          "import", "audit", "assess", "inspect", "rebuild", "crosscheck", "attest",
          "sign", "pack", "pull", "tree", "claims"}
# v1 carried a compatibility bridge that accepted its own vocabulary as aliases
# for the plain-CS names. In v2 the plain names ARE canonical, so the bridge is
# gone: these must be unknown verbs, not quiet synonyms.
RETIRED = ("condense", "realize", "prove", "mint", "records")


def _env() -> dict:
    """The package under test on a child interpreter's path — `python3 -m
    reticuli` must find the same `src/` tree this check imported."""
    env = dict(os.environ)
    path = [os.path.abspath(SRC)]
    if env.get("PYTHONPATH"):
        path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(path)
    return env


def _cli(*argv: str) -> str:
    r = subprocess.run([sys.executable, "-m", "reticuli", *argv],
                       capture_output=True, text=True, check=False, env=_env())
    assert r.returncode == 0, f"the CLI answers {' '.join(argv)}"
    return r.stdout


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, buf.getvalue()


def battery() -> None:
    assert reticuli.__main__.main is cli.main, "entrypoint"

    # the sectioned map: five phase groups in process order, every human verb
    # under exactly one, and `hook` present but unlisted (agent plumbing).
    help_out = _cli("--help")
    last = -1
    for s in SECTIONS:
        i = help_out.find(s)
        assert i > last, f"help section missing or out of order: {s!r}"
        last = i
    listed = set(re.findall(r"^\s{4}([a-z][a-z-]+)\s{2,}", help_out, re.MULTILINE))
    assert listed == LISTED, f"help verb map drifted: {listed ^ LISTED}"
    assert "hook" not in listed, "hook is internal — it must not be listed"
    # and the map is the WHOLE grammar: a verb cannot be dispatched without
    # being documented, nor documented without being dispatched.
    assert set(cli.verbs()) == LISTED | {"hook"}, \
        f"parser and help disagree: {set(cli.verbs()) ^ (LISTED | {'hook'})}"

    # no alias layer: v1's vocabulary is not a second spelling of v2's
    for gone in RETIRED:
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                cli.main([gone, "."])
        except SystemExit as exit_:
            assert exit_.code == 2, f"the v1 verb {gone!r} must be refused"
        else:
            raise AssertionError(f"the v1 verb {gone!r} is still accepted")

    d = tempfile.mkdtemp()
    try:
        ws = os.path.join(d, "ws")
        code, _ = _run(["init", ws])
        assert code == 0, "init exits 0"
        with open(os.path.join(ws, ".gitignore")) as f:
            assert "ledger.jsonl" in f.read(), "init is git-native"

        with open(os.path.join(ws, "answer.txt"), "w") as f:
            f.write("42\n")
        gate = "grep -qx 42 answer.txt && printf ok > OK"
        code, _ = _run(["run", gate, "-C", ws])
        assert code == 0 and os.path.isfile(os.path.join(ws, "OK")), "run authors a gate"
        events = [{"event": "prompt", "text": "write the answer", "ts": 5.0},
                  {"event": "write", "path": "answer.txt", "ts": 6.0},
                  {"event": "bash", "cmd": gate, "ts": 7.0}]
        with open(os.path.join(ws, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in events) + "\n")

        claim = os.path.join(ws, ".reticuli", "sealed", "answer")
        code, _ = _run(["seal", ws, "--accept", "OK", "--into", claim, "--name", "answer"])
        assert code == 0, "seal exits 0"
        code, out = _run(["verify", claim])
        assert code == 0 and "fresh" in out, "verify says fresh"
        code, out = _run(["verify", claim, "--json"])
        assert code == 0 and json.loads(out)["ok"], "--json underneath"

        m3 = os.path.join(d, "m3")
        code, out = _run(["rebuild", claim, "--producer", "printf '42\\n' > answer.txt",
                          "--into", m3])
        assert code == 0 and "calls" in out, "rebuild reports what it paid"
        m2 = os.path.join(d, "m2")
        shutil.copytree(claim, m2)
        code, out = _run(["crosscheck", claim, m2, m3])
        assert code == 0, "crosscheck exits 0"
        assert "satisfied = true" in out and "[cost]" in out, "the verdict and the bill"

        # the transfer and attestation verbs, end to end at the surface — the
        # census showed a redo can shrink the CLI to just what the gate drives,
        # so the whole README proof (export -> import -> audit -> attest) is
        # exercised here, not merely named.
        tar = os.path.join(d, "answer.tar")
        code, out = _run(["export", claim, tar])
        assert code == 0 and os.path.isfile(tar), "export writes the claim's tar"
        imp = os.path.join(d, "imported")
        code, out = _run(["import", tar, imp])
        assert code == 0 and "fresh" in out, "import verifies from bytes alone"
        code, out = _run(["audit", claim])
        assert code == 0 and "earned" in out, "audit re-earns the verdict"
        code, out = _run(["audit", claim, "--shallow"])
        assert code == 0 and "earned" in out, "the shallow lens is opt-in"
        code, out = _run(["audit", claim, "--mutants", "3"])
        assert code == 0 and "[mutation_score]" in out and "rate" in out, \
            "audit --mutants measures the check"
        vh = _cli("seal", "-h")
        assert "--claim" in vh and "--generated" in vh, \
            "the claim boundary is declared at the surface"
        ph = _cli("crosscheck", "-h")
        assert "--mutants" in ph, "crosscheck holds the redo to a declared mutation floor"
        key = os.path.join(d, "id")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", key], check=True)
        code, out = _run(["attest", m3, "--key", key, "--as", "you@lab"])
        assert code == 0, "attest signs a rebuild"
        code, out = _run(["attest", m3, "--check"])
        assert code == 0 and "attested" in out, "attest --check verifies the signature"

        # the signing ceremony at the surface: no key reviews the chain + packet,
        # a key authorizes it, --check verifies the authorization
        code, out = _run(["sign", m3])
        assert code == 0 and "[review]" in out and "sign_root" in out, \
            "sign (no key) emits the review packet"
        code, out = _run(["sign", m3, "--key", key, "--as", "you@lab"])
        assert code == 0 and "ceremony" in out, "sign --key authorizes the chain"
        code, out = _run(["sign", m3, "--check"])
        assert code == 0 and "authorized = true" in out, "sign --check verifies the authorization"

        code, out = _run(["claims", ws])
        assert code == 0 and "answer" in out, "the claim store renders"

        # two lenses, one verb: a session's tree is its files PLUS its claim
        # store's dependency graph (deps folded in); a claim's tree is its
        # structure — pinned inputs (the claim), generated strata, pinned verdicts
        code, out = _run(["tree", ws])
        assert code == 0 and "draft" in out, "the session lens"
        assert "answer" in out and "claim(s)" in out, "the dep graph rides in the session lens"
        code, out = _run(["tree", claim])
        assert code == 0 and "generated  answer.txt" in out and "pinned     OK" in out \
            and "layer(s)" in out, "the claim lens"

        # the agent handshake at the surface: `ret hook` is silent, `ret hooks` wires
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": "again", "cwd": ws}
        stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(payload))
        try:
            code, out = _run(["hook", "-C", ws])
        finally:
            sys.stdin = stdin
        assert code == 0 and out == "", "hook exits 0 and prints nothing"
        with open(os.path.join(ws, ".reticuli", "draft.jsonl")) as f:
            assert '"prompt"' in f.readlines()[-1], "the payload became a trace event"
        code, _ = _run(["hooks", ws])
        assert code == 0 and os.path.isfile(
            os.path.join(ws, ".claude", "settings.json")), "hooks wires the agent"
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    battery()
    # A verdict is a claim's pinned OUTPUT, so write one only when this suite
    # is running as a claim's gate. Run from anywhere else it is just noise in
    # someone's working directory.
    if os.path.isfile("reticuli.toml") or os.path.isfile("claim.toml"):
        with open("SURFACE_OK", "w") as f:
            f.write("surface-ok\n")
    print("surface-ok")

"""Surface conformance gate — the acceptance check of the `surface` layer.

The human handshake: drives the CLI end-to-end through the layers beneath it
and pins the command grammar itself. Fourteen verbs, one concept each
(observe -> declare -> test -> reconstruct -> compare -> preserve), grouped
in the help by concept; older spellings dispatch as aliases but are listed
only by `ret help -a`. Output is terse by default, explanatory under -v, and
a stable machine envelope {command, ok, status, root, data} under --json.
Exit codes: 0 the predicate held, 1 it failed, 2 the invocation was invalid.
The functional depth is claimed by the inner gates (kernel_check,
exchange_check, authoring_check, agents_check, launcher_check); this suite
claims the contact surface. Writes SURFACE_OK iff the toolchain a *user*
touches is conformant. Stdlib only, so it runs in any clean workspace.

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
import tarfile
import tempfile

SRC = "src" if os.path.isdir("src/reticuli") else "."
sys.path.insert(0, SRC)
import reticuli.__main__   # the CLI entrypoint
from reticuli import cli

# The help is organized by concept, not a flat verb dump — a mental map the
# user reads top to bottom as the workflow itself. The census showed structure
# evaporates unless a gate demands it, so the groups, their order, and their
# membership are ratified here; the wording of each line stays free.
GROUPS = ("Authoring", "Composition and transport", "Verification",
          "Reconstruction", "Evidence")
PORCELAIN = {"init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign"}
# Accepted older spellings: they dispatch (an existing invocation keeps
# working) but are aliases — the fourteen are the grammar, and the top help
# must not list them. `ret help -a` names every one.
ALIASES = {"seal", "hooks", "inspect", "tree", "claims", "attest"}
# v1's metaphor vocabulary stays retired: unknown verbs, not quiet synonyms.
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate")
ENVELOPE = {"command", "ok", "status", "root", "data"}


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
    assert r.returncode == 0, f"the CLI answers {' '.join(argv)}: {r.stderr[-200:]}"
    return r.stdout


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    return code, buf.getvalue()


def _run2(argv: list[str]) -> tuple[int, str, str]:
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, buf.getvalue(), err.getvalue()


def _envelope(argv: list[str]) -> dict:
    code, out = _run(argv)
    assert code in (0, 1), "an envelope verb exits by its predicate"
    e = json.loads(out)
    assert set(e) == ENVELOPE, f"envelope fields drifted: {set(e) ^ ENVELOPE}"
    assert e["command"] == argv[0], "the envelope names its command"
    assert isinstance(e["ok"], bool) and isinstance(e["status"], str)
    return e


def battery() -> None:
    assert reticuli.__main__.main is cli.main, "entrypoint"

    # the grouped map: five concept groups in workflow order, every porcelain
    # verb under exactly one, aliases and plumbing unlisted.
    help_out = _cli("-h")
    last = -1
    for s in GROUPS:
        i = help_out.find("\n" + s + "\n")
        assert i > last, f"help group missing or out of order: {s!r}"
        last = i
    listed = set(re.findall(r"^\s{4}([a-z][a-z-]+)\s{2,}", help_out, re.MULTILINE))
    assert listed == PORCELAIN, f"help verb map drifted: {listed ^ PORCELAIN}"
    for hidden in (*ALIASES, "hook", "help"):
        assert hidden not in listed, f"{hidden} must not be in the fourteen-verb map"
    # the map plus the aliases plus plumbing IS the parser: nothing dispatches
    # undocumented, and nothing documented fails to dispatch.
    assert set(cli.verbs()) == PORCELAIN | ALIASES | {"hook", "help"}, \
        f"parser and help disagree: {set(cli.verbs()) ^ (PORCELAIN | ALIASES | {'hook', 'help'})}"

    # two-level help: -h is concise usage; `ret help <verb>` (and --help) is
    # the fuller account; `ret help -a` lists everything, aliases included.
    vh = _cli("verify", "-h")
    assert "usage: ret verify" in vh, "verify -h is concise usage"
    fh = _cli("help", "verify")
    assert "Does not execute acceptance criteria" in fh, \
        "the verify/audit distinction is stated where a user learns the verb"
    assert _cli("help", "rebuild").find("withheld") > 0, \
        "rebuild's guarantee — generated sources are withheld — is stated"
    ha = _cli("help", "-a")
    for name in (*ALIASES, "hook"):
        assert name in ha, f"help -a lists {name}"
    assert "SYNOPSIS" in _cli("verify", "--help"), "--help is the full account"

    # the retired metaphor vocabulary stays retired
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
        # -- authoring: init (agent wiring rides it), run, status, pack
        ws = os.path.join(d, "ws")
        code, out = _run(["init", ws])
        assert code == 0 and out.startswith("initialized"), "init is terse"
        with open(os.path.join(ws, ".gitignore")) as f:
            assert "ledger.jsonl" in f.read(), "init is git-native"
        agent = os.path.join(d, "agent-proj")
        os.makedirs(agent)
        code, _ = _run(["init", agent, "--agent", "claude"])
        assert code == 0 and os.path.isfile(
            os.path.join(agent, ".claude", "settings.json")), \
            "init --agent wires the hooks: no separate concept to learn"
        code, _, err = _run2(["init", agent, "--agent", "acme"])
        assert code == 1 and "unsupported" in err, "an unknown agent refuses in words"

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

        code, out = _run(["status", ws])
        assert code == 0 and out.startswith("draft") and "observed=" in out, \
            "status shows the observation account in a draft"

        # pack is the single authoring boundary: a session declares acceptance
        claim = os.path.join(ws, ".reticuli", "sealed", "answer")
        code, _, err = _run2(["pack", ws, "--accept", "OK"])
        assert code == 2 and "-o" in err, "a session pack without -o refuses in words"
        code, out = _run(["pack", ws, "--accept", "OK", "-o", claim, "--name", "answer"])
        assert code == 0 and out.startswith("packed"), "pack seals the session"
        # the seal spelling still dispatches — an alias, not a concept
        try:
            code, _, _ = _run2(["seal"])
        except SystemExit as exit_:        # argparse: its required flags missing
            code = exit_.code
        assert code == 2, "seal (alias) still parses its own grammar"

        # -- verification: verify (identity only), audit (execution)
        code, out = _run(["verify", claim])
        assert code == 0 and out.startswith("fresh"), "verify says fresh, tersely"
        e = _envelope(["verify", claim, "--json"])
        assert e["ok"] and e["status"] == "fresh" and len(e["root"]) == 64, \
            "the envelope carries the stable fields"
        assert e["data"]["recomputed"], "verb detail lives under data"
        code, out = _run(["verify", claim, "-v"])
        assert code == 0 and "[verify]" in out, "-v is the explanatory account"

        broken = os.path.join(d, "broken")
        shutil.copytree(claim, broken)
        with open(os.path.join(broken, "OK"), "a") as f:
            f.write("tampered\n")
        code, out = _run(["verify", broken])
        assert code == 1 and out.startswith("broken"), \
            "a moved pinned byte: broken, exit 1"

        code, out = _run(["audit", claim])
        assert code == 0 and out.startswith("earned") and "gates=1/1" in out, \
            "audit re-earns the verdict, tersely"
        code, out = _run(["audit", claim, "--shallow"])
        assert code == 0 and out.startswith("earned"), "the shallow lens is opt-in"
        code, out = _run(["audit", claim, "--mutants", "3", "-v"])
        assert code == 0 and "[mutation_score]" in out and "rate" in out, \
            "audit --mutants measures the check"
        rec_via_audit = os.path.join(d, "audit.record.json")
        code, out = _run(["audit", claim, "--record", rec_via_audit])
        assert code == 0 and os.path.isfile(rec_via_audit), \
            "audit --record preserves the execution as a record"

        # -- reconstruction: rebuild, crosscheck (roles inferred, not named)
        m3 = os.path.join(d, "m3")
        code, out = _run(["rebuild", claim, "--producer", "printf '42\\n' > answer.txt",
                          "-o", m3])
        assert code == 0 and out.startswith("rebuilt") and "build=" in out, \
            "rebuild reports the build digest tersely (-o names the destination)"
        m2 = os.path.join(d, "m2")
        shutil.copytree(claim, m2)
        code, out = _run(["crosscheck", claim, m2, m3])
        assert code == 0 and out.startswith("accept") and "builds=3" in out, \
            "the three-machine test accepts, tersely"
        code, out = _run(["crosscheck", claim, m2, m3, "-v"])
        assert code == 0 and "satisfied = true" in out and "[cost]" in out, \
            "-v carries the verdict and the bill"
        # a pair invocation gets a REAL byte-copy leg, materialized here and
        # said so — never a silently weakened two-legged test
        e = _envelope(["crosscheck", claim, m3, "--json"])
        assert e["ok"] and e["status"] == "accept" and e["data"]["m2_materialized"], \
            "two realizations: M2 is materialized and disclosed"
        code, _, _ = _run2(["crosscheck", claim])
        assert code == 2, "one realization is not a comparison"

        # -- transport: export/import are inverses; --blind is the room
        tar = os.path.join(d, "answer.tar")
        code, out = _run(["export", claim, tar])
        assert code == 0 and os.path.isfile(tar), "export writes the claim's tar"
        imp = os.path.join(d, "imported")
        code, out = _run(["import", tar, imp])
        assert code == 0 and out.startswith("imported"), \
            "import verifies from bytes alone"
        eh = _cli("export", "-h")
        assert "--blind" in eh, "the room is one flag on the transfer verb"
        btar = os.path.join(d, "answer-room.tar")
        code, out = _run(["export", claim, btar, "--blind"])
        assert code == 0 and os.path.isfile(btar), "export --blind writes the room"
        with tarfile.open(btar) as t:
            names = set(t.getnames())
        assert "answer.txt" not in names, "the implementation stays home"
        assert "OK" in names and ".reticuli/manifest.json" in names, \
            "criteria and the verdict travel, and the manifest names the target root"
        room = os.path.join(d, "room")
        code, out = _run(["import", btar, room])
        assert code == 0 and out.startswith("imported"), \
            "a blind room verifies -- the claim is the identity"

        # -- authoring flags at the surface (the declaration language)
        ph = _cli("crosscheck", "-h")
        assert "--mutants" in ph, "crosscheck holds the redo to a declared mutation floor"
        kh = _cli("pack", "-h")
        assert "--pytest" in kh and "--environment" in kh and "--accept" in kh, \
            "one boundary, three sources: session, declared recipe, flags"
        code, _, err = _run2(["pack", os.path.join(d, "nothing-here")])
        assert code == 1 and "nothing to pack" in err, \
            "pack with nothing to pack refuses in words"
        # a declared project seals in place with no flags at all
        decl = os.path.join(d, "declared")
        shutil.copytree(claim, decl)
        shutil.rmtree(os.path.join(decl, ".reticuli"))
        code, out = _run(["pack", decl])
        assert code == 0 and out.startswith("packed"), \
            "reticuli.toml IS the declaration: zero-flag pack seals it"

        # -- evidence: record (machine), sign (human), and the distinction
        key = os.path.join(d, "id")
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-f", key], check=True)
        code, out = _run(["attest", m3, "--key", key, "--as", "you@lab"])
        assert code == 0, "attest (alias) signs a rebuild"
        code, out = _run(["attest", m3, "--check"])
        assert code == 0 and out.startswith("attested"), \
            "attest --check verifies the signature"

        rec = os.path.join(d, "answer.record.json")
        code, out = _run(["record", claim, "-o", rec, "--key", key])
        assert code == 0 and os.path.isfile(rec) and os.path.isfile(rec + ".sig"), \
            "record emits, writes, and signs"
        assert out.startswith("recorded") and "earned=true" in out and "signed" in out, \
            "the surface says what the record holds"
        e = _envelope(["record", claim, "-o", rec, "--json"])
        assert e["ok"] and e["data"]["digest"] and e["data"]["record"]["root"], \
            "--json underneath"
        # --sign without a configured identity refuses in words: a signature
        # must never appear from nowhere
        held = os.environ.pop("RETICULI_KEY", None)
        try:
            code, _, err = _run2(["record", claim, "-o", rec, "--sign"])
            assert code == 1 and "RETICULI_KEY" in err, \
                "record --sign names the missing identity"
        finally:
            if held:
                os.environ["RETICULI_KEY"] = held

        code, out = _run(["sign", m3])
        assert code == 0 and out.startswith("review"), \
            "sign (no key) emits the review packet"
        code, out = _run(["sign", m3, "-v"])
        assert code == 0 and "[review]" in out and "sign_root" in out, \
            "-v shows the packet a signer stands behind"
        code, out = _run(["sign", m3, "--key", key, "--as", "you@lab"])
        assert code == 0 and out.startswith("signed"), "sign --key authorizes the chain"
        code, out = _run(["sign", m3, "--check"])
        assert code == 0 and out.startswith("authorized"), \
            "sign --check verifies the authorization"

        # -- status is the one view; the old view verbs are lenses into it
        code, out = _run(["status", claim])
        assert code == 0 and "identity" in out and "fresh" in out \
            and "signed" in out, "status on a claim: the recorded state"
        code, out = _run(["status", claim, "--all"])
        assert code == 0 and "fixed --" in out and "unknown --" in out, \
            "status --all is the recipient's four blocks"
        code, out = _run(["status", claim, "--tree"])
        assert code == 0 and "layer(s)" in out, "status --tree: the claim lens"
        code, out = _run(["status", ws, "--tree"])
        assert code == 0 and "draft" in out, "status --tree: the session lens"
        code, out = _run(["inspect", claim])
        assert code == 0 and "fixed --" in out, "inspect (alias) still answers"
        code, out = _run(["claims", ws])
        assert code == 0 and "answer" in out, "claims (alias) lists the store"
        code, out = _run(["tree", claim])
        assert code == 0 and "generated  answer.txt" in out and "pinned     OK" in out, \
            "tree (alias): the claim lens"

        # the agent handshake: `ret hook` is plumbing, silent
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
            os.path.join(ws, ".claude", "settings.json")), "hooks (alias) wires the agent"
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

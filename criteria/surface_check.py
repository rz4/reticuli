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
from reticuli import cli, kernel

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
ALIASES = {"seal", "hooks", "tree", "claims", "attest"}
# v1's metaphor vocabulary stays retired — and `inspect` joined it: its
# strict-jail posture moved into audit's default, its report into status's
# recorded ledger and the ladder. Unknown verbs, not quiet synonyms.
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect")
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


#: Every default-mode output the battery sees, for the closing glyph ban:
#: the metaphor-era glyphs stay out of everything the CLI prints.
SEEN: list[str] = []
BANNED_GLYPHS = ("■", "✗", "⇐", "…", "·")


def _run(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(argv)
    SEEN.append(buf.getvalue())
    return code, buf.getvalue()


def _run2(argv: list[str]) -> tuple[int, str, str]:
    buf, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        code = cli.main(argv)
    SEEN.append(buf.getvalue())
    SEEN.append(err.getvalue())
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
    for hidden in (*ALIASES, "hook", "help", "completion"):
        assert hidden not in listed, f"{hidden} must not be in the fourteen-verb map"
    # the map plus the aliases plus plumbing IS the parser: nothing dispatches
    # undocumented, and nothing documented fails to dispatch.
    PLUMBING = {"hook", "help", "completion"}
    assert set(cli.verbs()) == PORCELAIN | ALIASES | PLUMBING, \
        f"parser and help disagree: {set(cli.verbs()) ^ (PORCELAIN | ALIASES | PLUMBING)}"

    # the tool names itself by its own claim
    code, out = _run(["--version"])
    assert code == 0 and out.startswith("ret "), "--version answers"
    # completion is generated from the parser, so it cannot drift from it
    code, out = _run(["completion", "bash"])
    assert code == 0 and "crosscheck" in out and "complete -F" in out, \
        "bash completion carries the grammar"

    # two-level help: -h is concise usage; `ret help <verb>` (and --help) is
    # the fuller account; `ret help -a` lists everything, aliases included.
    vh = _cli("verify", "-h")
    assert "usage: ret verify" in vh, "verify -h is concise usage"
    fh = _cli("help", "verify")
    assert "Does not execute acceptance criteria" in fh, \
        "the verify/audit distinction is stated where a user learns the verb"
    rh = _cli("help", "rebuild")
    assert "withheld" in rh, \
        "rebuild's guarantee — generated sources are withheld — is stated"
    assert "--producer openai" in rh and "any program" in rh, \
        "the shipped producers answer to their names; a producer stays any program"
    ha = _cli("help", "-a")
    for name in (*ALIASES, "hook"):
        assert name in ha, f"help -a lists {name}"
    assert "SYNOPSIS" in _cli("verify", "--help"), "--help is the full account"
    assert "RETICULI_KEY" in _cli("help", "environment"), \
        "every variable the tool reads is documented in one place"

    # the retired metaphor vocabulary stays retired -- and an unknown verb
    # gets the git answer: name the mistake, suggest the near miss, exit 2
    for gone in RETIRED:
        try:
            code, _, _ = _run2([gone, "."])
        except SystemExit as exit_:
            code = exit_.code
        assert code == 2, f"the v1 verb {gone!r} must be refused"
    code, _, err = _run2(["verfy", "."])
    assert code == 2 and "is not a ret command" in err and "verify" in err, \
        "a typo names the mistake and suggests the near miss"

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
        assert code == 2 and "unsupported" in err, \
            "an unknown agent value is an invalid invocation: words, exit 2"

        with open(os.path.join(ws, "answer.txt"), "w") as f:
            f.write("42\n")
        gate = "grep -qx 42 answer.txt && printf ok > OK"
        code, out, err = _run2(["run", gate, "-C", ws])
        assert code == 0 and os.path.isfile(os.path.join(ws, "OK")), "run authors a gate"
        assert out == "" and err == "", \
            "run is a silent wrapper: only the child's streams"
        # a traced write whose file was later DELETED must not crash pack, and
        # an untraced present file is observed nothing, declared nothing.
        # The session carries a transcript with a LARGE usage bill: the
        # discovery cost must ride the claim as reported testimony and must
        # never feed the cost band (the first real proof was rejected for
        # exactly that).
        transcript = os.path.join(d, "harness.jsonl")
        with open(transcript, "w") as f:
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-01-01T00:00:06Z",
                                "message": {"usage": {"input_tokens": 150000,
                                                      "output_tokens": 4075}}}) + "\n")
        events = [{"event": "session", "transcript": transcript, "ts": 5.0, "via": "hook"},
                  {"event": "prompt", "text": "write the answer", "ts": 5.0, "via": "hook"},
                  {"event": "write", "path": "answer.txt", "ts": 6.0, "via": "hook"},
                  {"event": "write", "path": "ghost.py", "ts": 6.5, "via": "hook"},
                  {"event": "bash", "cmd": gate, "ts": 7.0, "via": "hook"}]
        with open(os.path.join(ws, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in events) + "\n")
        with open(os.path.join(ws, "notes.md"), "w") as f:
            f.write("untraced\n")

        code, out = _run(["status", ws])
        assert code == 0 and out.startswith("draft") and "observed=" in out \
            and "declared=" in out and "unresolved=" in out, \
            "status counts the authoring triad: observed, declared, unresolved"
        code, out = _run(["status", ws, "--all"])
        for column in ("path", "observed", "declared", "evidence"):
            assert column in out, f"the --all account carries the {column} column"
        assert "gate" in out and "hook" in out, \
            "evidence names where each observation came from"
        assert "notes.md" in out and "-" in out, \
            "an untraced file is dashes: observation is not silently a declaration"
        # a status target that does not exist is a refusal, never an empty draft
        code, _, err = _run2(["status", os.path.join(d, "no-such-dir")])
        assert code == 1 and "no such directory" in err, \
            "status on a missing path refuses in words"

        # an uncovered generated file: the triad shows it, and pack refuses it
        ws3 = os.path.join(d, "ws3")
        code, _ = _run(["init", ws3, "--no-agent"])
        with open(os.path.join(ws3, "made.py"), "w") as f:
            f.write("# made\n")
        with open(os.path.join(ws3, ".reticuli", "draft.jsonl"), "w") as f:
            f.write(json.dumps({"event": "write", "path": "made.py",
                                "via": "hook", "ts": 1.0}) + "\n")
        code, out = _run(["status", ws3])
        assert code == 0 and "unresolved=1" in out and "undeclared" in out, \
            "an uncovered generated file is named as undeclared"

        # THE CANONICAL PYTHON SHAPE: the check reaches the implementation
        # through an import the command never names -- `python3 check.py`
        # where check.py says `from primes import ...`. Coverage must see
        # through one level of that, and the executed script itself must
        # read as a decider, never as the gate's output.
        ws4 = os.path.join(d, "ws4")
        code, _ = _run(["init", ws4, "--no-agent"])
        with open(os.path.join(ws4, "primes.py"), "w") as f:
            f.write("def is_prime(n):\n    return n == 2\n")
        with open(os.path.join(ws4, "check.py"), "w") as f:
            f.write("from primes import is_prime\nassert is_prime(2)\n")
        pygate = "python3 check.py && printf ok > PASSED"
        events4 = [{"event": "write", "path": "primes.py", "via": "hook", "ts": 1.0},
                   {"event": "write", "path": "check.py", "via": "hook", "ts": 2.0},
                   {"event": "bash", "cmd": pygate, "via": "shell", "ts": 3.0}]
        with open(os.path.join(ws4, ".reticuli", "draft.jsonl"), "w") as f:
            f.write("\n".join(json.dumps(e) for e in events4) + "\n")
        subprocess.run(pygate, shell=True, cwd=ws4, check=True)
        code, out = _run(["status", ws4, "--all"])
        assert code == 0 and "unresolved=0" not in out, "the --all view renders"
        assert re.search(r"primes\.py\s+write\s+generated", out), \
            "an imported implementation is covered: the canonical flow just works"
        assert re.search(r"check\.py\s+write\s+generated", out), \
            "the executed check is a decider, never misread as a gate output"
        code, out = _run(["status", ws4])
        assert "unresolved=0" in out and "packable" in out, \
            "the import-shaped session packs without --force"

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

        # -- verification: verify (identity only), audit (execution).
        # A passing check is SILENT: the exit code is the answer
        # (the silence rule; the style contract lives in the repository docs).
        code, out, err = _run2(["verify", claim])
        assert code == 0 and out == "" and err == "", "a passing verify is silent"
        code, _, err = _run2(["verify", os.path.join(d, "nowhere")])
        assert code == 1 and err.startswith("ret: verify:"), \
            "one voice for every refusal: ret: <verb>: <fact>"
        e = _envelope(["verify", claim, "--json"])
        assert e["ok"] and e["status"] == "fresh" and len(e["root"]) == 64, \
            "the envelope carries the stable fields"
        assert e["data"]["recomputed"], "verb detail lives under data"
        code, out = _run(["verify", claim, "-v"])
        assert code == 0 and "[verify]" in out, "-v is the explanatory account"
        assert re.search(r'root = "[0-9a-f]{64}"', out), "-v spells hashes in full"

        broken = os.path.join(d, "broken")
        shutil.copytree(claim, broken)
        with open(os.path.join(broken, "OK"), "a") as f:
            f.write("tampered\n")
        code, out, err = _run2(["verify", broken])
        assert code == 1 and out == "", "diagnostics never land on stdout"
        assert "broken" in err and "OK" in err, \
            "a broken verify NAMES the file that moved, from the parts residue"
        assert "hint:" in err, "and says what to do next"

        code, out, err = _run2(["audit", claim])
        assert code == 0 and out == "" and err == "", "a passing audit is silent"
        code, out = _run(["audit", claim, "-v"])
        assert code == 0 and "[audit]" in out and "reproduced" in out, \
            "-v carries the verdict table"
        code, out, err = _run2(["audit", broken])
        assert code == 1 and out == "" and "ret: audit:" in err, \
            "an audit failure is a stderr line, class-first"
        code, out = _run(["audit", claim, "--shallow"])
        assert code == 0 and out == "", "the shallow lens is opt-in"
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
        assert code == 0 and out.startswith("rebuilt"), \
            "rebuild prints the unknowable: the root it landed on"
        m2 = os.path.join(d, "m2")
        shutil.copytree(claim, m2)
        code, out, err = _run2(["crosscheck", claim, m2, m3])
        assert code == 0 and out == "" and err == "", \
            "an accepted three-machine test is silent"
        code, out = _run(["crosscheck", claim, m2, m3, "-v"])
        assert code == 0 and "satisfied = true" in out and "[cost]" in out, \
            "-v carries the verdict and the bill"
        assert "discovery" in out and "154075" in out, \
            "the discovery bill is reported beside the band, never inside it " \
            "-- a 154k-token session must not reject a one-call redo"
        # a NAMED producer preflights: a missing credential is one line on
        # stderr BEFORE any money moves, never a traceback from the room
        held_key = os.environ.pop("OPENAI_API_KEY", None)
        try:
            code, out, err = _run2(["rebuild", claim, "--producer", "openai",
                                    "-o", os.path.join(d, "never")])
            assert code == 1 and out == "" \
                and "the openai producer needs" in err, \
                "a named producer refuses in words before spending"
        finally:
            if held_key:
                os.environ["OPENAI_API_KEY"] = held_key
        m3bad = os.path.join(d, "m3bad")
        shutil.copytree(m3, m3bad)
        with open(os.path.join(m3bad, "OK"), "a") as f:
            f.write("tampered\n")
        code, out, err = _run2(["crosscheck", claim, m2, m3bad])
        assert code == 1 and out == "" and "reject" in err, \
            "a rejected test is a stderr line naming the cause"
        # a pair invocation gets a REAL byte-copy leg, materialized here and
        # said so — never a silently weakened two-legged test
        e = _envelope(["crosscheck", claim, m3, "--json"])
        assert e["ok"] and e["status"] == "accept" and e["data"]["m2_materialized"], \
            "two realizations: M2 is materialized and disclosed"
        code, _, _ = _run2(["crosscheck", claim])
        assert code == 2, "one realization is not a comparison"

        # -- transport: export/import are inverses; --blind is the room
        tar = os.path.join(d, "answer.tar")
        code, out, err = _run2(["export", claim, tar])
        assert code == 0 and out == "" and os.path.isfile(tar), \
            "export writes the tar you named, silently"
        imp = os.path.join(d, "imported")
        code, out, err = _run2(["import", tar, imp])
        assert code == 0 and out == "", "a verified import is silent"
        code, _, err = _run2(["import", os.path.join(d, "absent.tar"),
                              os.path.join(d, "nowhere")])
        assert code == 1 and "no archive" in err, \
            "a missing archive is a refusal with a reason, never a raw crash"
        # `-` is the standard stream: export | import round-trips through a
        # pipe — the oldest idiom tar has. Child processes, real pipes.
        piped = os.path.join(d, "piped")
        rt = subprocess.run(
            f"{sys.executable} -m reticuli export {claim} -o - | "
            f"{sys.executable} -m reticuli import - {piped}",
            shell=True, capture_output=True, text=True, check=False, env=_env())
        assert rt.returncode == 0 and rt.stdout == "", \
            f"export -o - | import - round-trips silently: {rt.stderr[-200:]}"
        code, _ = _run(["verify", piped])
        assert code == 0, "and the piped copy verifies"
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
        assert code == 0 and out == "", \
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
        assert code == 0 and out == "", "attest (alias) signs a rebuild, silently"
        code, out, err = _run2(["attest", m3, "--check"])
        assert code == 0 and out == "" and err == "", \
            "a verified attestation is silent"

        rec = os.path.join(d, "answer.record.json")
        code, out, err = _run2(["record", claim, "-o", rec, "--key", key])
        assert code == 0 and os.path.isfile(rec) and os.path.isfile(rec + ".sig"), \
            "record emits, writes, and signs"
        assert out == "", "the file you named appears; nothing else is said"
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
            "sign (no key) emits the review packet -- a view, so it speaks"
        code, out = _run(["sign", m3, "-v"])
        assert code == 0 and "[review]" in out and "sign_root" in out, \
            "-v shows the packet a signer stands behind"
        code, out = _run(["sign", m3, "--key", key, "--as", "you@lab"])
        assert code == 0 and out == "", "sign --key authorizes, silently"
        code, out, err = _run2(["sign", m3, "--check"])
        assert code == 0 and out == "" and err == "", \
            "a verified authorization is silent"
        # status counts BOTH drawers of statements — the attestation and the
        # signing ceremony's authorization live in different stores, and a
        # freshly signed claim once read `signed none` for looking in one
        code, out = _run(["status", m3])
        assert "2 statement(s)" in out and "signed" in out, \
            "an attested and signed claim counts both statements"

        # -- STATUS IS THE PURE VIEW: it reads and reports, never executes.
        # Every form is instant; every form ends with the ladder's `next` —
        # the first rung this claim has not yet earned.
        # The battery earned an audit above, so a receipt exists and the
        # ladder stands at "measure the tests".
        code, out = _run(["status", claim])
        assert code == 0 and "identity" in out and "fresh" in out \
            and "audited" in out and "on this machine" in out, \
            "status reports the audit receipt with its date"
        assert "discovery" in out and "154075" in out, \
            "the discovery bill shows where a reader orients"
        assert "next" in out and "ret assess" in out, \
            "the ladder: audited, so measuring the tests is next"
        # the DECIDING rung: assess leaves root-stamped residue; the ladder
        # advances exactly when the evidence appears
        code, _ = _run(["assess", claim, "--mutants", "2"])
        assert code == 0, "assess measures"
        code, out = _run(["status", claim])
        assert "ret assess" not in out and "crosscheck" in out, \
            "measured, so the ladder moves to proving it"
        code, out = _run(["status", claim, "--all"])
        assert code == 0, "--all is a view: exit 0, no execution"
        for word in ("fixed", "deciding", "free", "recorded", "unknown", "next"):
            assert word in out, f"the ledger carries the {word} group"
        assert "assess," in out and "a receipt, not a verdict" in out, \
            "recorded state is dated and named as testimony"
        # a broken claim: still a view, still exit 0 — the ladder says restore
        code, out = _run(["status", broken])
        assert code == 0 and "broken" in out and "restore" in out, \
            "a view never fails; it reports and points at the fix"
        code, out = _run(["status", claim, "--files"])
        assert code == 0 and re.search(r"answer\.txt\s+generated\s+free", out) \
            and re.search(r"OK\s+validated\s+verdict", out), \
            "--files lists EVERY declared file by role, hiding none"
        code, out = _run(["status", claim, "--tree"])
        assert code == 0 and "layers=" in out, "status --tree: the claim lens"
        code, out = _run(["status", ws, "--tree"])
        assert code == 0 and "draft" in out, "status --tree: the session lens"
        sh = _cli("status", "-h")
        assert "--files" in sh and "--no-strict" not in sh, \
            "status's flags are views; audit owns the jail choice"
        code, out = _run(["claims", ws])
        assert code == 0 and "answer" in out, "claims (alias) lists the store"
        code, out = _run(["tree", claim])
        assert "pinned     OK" in out, "tree (alias): the claim lens, labeled"

        # -- AUDIT IS THE JUDGE, and judging is done in the strict jail by
        # default: a claim's gates never read your files, --no-strict opts
        # down. Pinned by capture, deterministically on any host.
        seen_strict = []
        real_audit = kernel.audit

        def _capture(claimdir, *a, **kw):
            seen_strict.append(kw.get("strict"))
            return real_audit(claimdir, *a, **kw)
        kernel.audit = _capture
        try:
            code, _ = _run(["audit", claim, "--shallow"])
            code, _ = _run(["audit", claim, "--shallow", "--no-strict"])
        finally:
            kernel.audit = real_audit
        assert seen_strict == [True, False], \
            f"audit is strict by default, --no-strict opts down: {seen_strict}"

        # THE COLOR CONTRACT: auto means "a tty", so a
        # captured stream is plain; =always paints; =never restores every
        # label word -- information never lives only in a hue.
        assert not any("\x1b[" in s for s in SEEN), \
            "captured output (not a tty) carries no escape codes"
        held_color = os.environ.get("RETICULI_COLOR")
        try:
            os.environ["RETICULI_COLOR"] = "always"
            code, out = _run(["status", claim])
            assert code == 0 and "\x1b[" in out, "=always paints the status block"
            code, out = _run(["status", claim, "--tree"])
            assert "\x1b[" in out and "pinned     OK" not in out, \
                "on color, the class IS the color: the label word yields"
            os.environ["RETICULI_COLOR"] = "never"
            code, out = _run(["status", claim, "--tree"])
            assert "\x1b[" not in out and "pinned     OK" in out, \
                "with color off, the label word returns"
        finally:
            if held_color is None:
                os.environ.pop("RETICULI_COLOR", None)
            else:
                os.environ["RETICULI_COLOR"] = held_color

        # the agent handshake: `ret hook` is plumbing, silent — and a payload
        # naming its transcript leaves session meta, so pack can later price
        # the discovery from the harness's own usage records
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": "again",
                   "cwd": ws, "transcript_path": os.path.join(d, "t.jsonl")}
        stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(payload))
        try:
            code, out = _run(["hook", "-C", ws])
        finally:
            sys.stdin = stdin
        assert code == 0 and out == "", "hook exits 0 and prints nothing"
        with open(os.path.join(ws, ".reticuli", "draft.jsonl")) as f:
            trace_text = f.read()
        assert '"prompt"' in trace_text.splitlines()[-1], \
            "the payload became a trace event"
        assert '"event": "session"' in trace_text and "t.jsonl" in trace_text, \
            "the harness transcript is remembered as session meta"
        code, _ = _run(["hooks", ws])
        assert code == 0 and os.path.isfile(
            os.path.join(ws, ".claude", "settings.json")), "hooks (alias) wires the agent"

        # the closing sweep: no output anywhere carried a metaphor-era glyph
        for glyph in BANNED_GLYPHS:
            hits = [s for s in SEEN if glyph in s]
            assert not hits, f"the glyph {glyph!r} appeared in CLI output: {hits[0][:120]!r}"
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

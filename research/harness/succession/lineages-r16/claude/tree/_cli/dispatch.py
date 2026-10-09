"""The surface dispatcher: argv grammar, verb handlers, and human/--json
rendering (`spec/layers.md`'s surface layer).

Fourteen porcelain verbs (`spec/verification.md`'s vocabulary, grouped by
workflow concept) plus three plumbing verbs (`hook`, `help`, `completion`).
Every porcelain verb shares `--json` / `--verbose` / `--color`; the
envelope on `--json` is always exactly `{command, ok, status, root, data}`.
A refusal (`kernel.ClaimError`) speaks once: as the JSON envelope's
`data.error` under `--json`, or as a single `ret: <verb>: <fact>` stderr
line otherwise -- never both, never a raw traceback. An invalid
invocation (an unknown verb, a malformed flag combination) is a different
seam: exit 2, a stderr line, never an envelope even under `--json`.

Each verb's body is a thin call into the layer that actually does the
work (`kernel`, `registry`, `attest`, `record`, `transfer`, `pack`,
`authoring`, `hooks`, `assess`); this module's job is argument plumbing
and presentation.
"""
import argparse
import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from reticuli import (assess, attest, authoring, hooks, kernel, pack,
                       record, registry, render, transfer)
from reticuli._cli import output

PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")
PLUMBING = ("hook", "help", "completion")

_SUPPORTED_AGENTS = ("claude",)

_DESC = ('Reticuli records and reproduces software claims.\n\n'
         'Authoring\n'
         '    init        initialize a workspace\n'
         '    run         run and observe a command\n'
         '    status      show work, claims, and unresolved inputs\n'
         '    pack        create a claim from a project\n\n'
         'Composition and transport\n'
         '    pull        add another claim as a dependency\n'
         '    export      write a portable claim archive\n'
         '    import      restore a claim archive\n\n'
         'Verification\n'
         '    verify      verify claim identity\n'
         '    audit       rerun acceptance criteria\n'
         '    assess      measure specification strength\n\n'
         'Reconstruction\n'
         '    rebuild     rebuild an implementation from a claim\n'
         '    crosscheck  compare independent realizations\n\n'
         'Evidence\n'
         '    record      write an execution record\n'
         '    sign        authorize a claim or proof')

_EPILOG = ("See 'ret <command> -h' for command usage.\n"
           "See 'ret help <command>' for detailed help; 'ret help -a' lists "
           "everything,\nincluding accepted older spellings.")

_VERSION = "0.1"

# -------------------------------------------------------------- per-verb help
_HELP = {
    "init": (
        "SYNOPSIS\n    ret init [dir] [--agent NAME]\n\n"
        "Mark a directory as a session workspace: create its .reticuli "
        "store, a git-native .gitignore, and -- with --agent -- wire a "
        "coding agent's hook handshake into it."
    ),
    "run": (
        "SYNOPSIS\n    ret run <command> [-C dir]\n\n"
        "Run one shell command and return its exit code UNCHANGED: a "
        "transparent boundary, so a session can use `ret run` as a "
        "predicate the way it uses any command."
    ),
    "status": (
        "SYNOPSIS\n    ret status [dir] [--all] [--files] [--tree] [--claims]\n\n"
        "A pure view: reads and reports a workspace's draft triad or a "
        "claim's documented state, never executes a gate."
    ),
    "pack": (
        "SYNOPSIS\n    ret pack [dir] [--accept OUTPUT...] -o DEST --name NAME\n\n"
        "The single authoring boundary: seal a project, or a traced "
        "session's acceptance (--accept), into a claim. --pytest is sugar "
        "for a pytest-shaped gate; --environment names a hash-pinned "
        "requirements file."
    ),
    "pull": "SYNOPSIS\n    ret pull <src> <dest>\n\nMaterialize a claim as a dependency.",
    "export": (
        "SYNOPSIS\n    ret export [dir] [tar] [-o out] [--blind]\n\n"
        "Write a portable, deterministic claim archive. --blind withholds "
        "the implementation: criteria and verdicts travel, the room stays home."
    ),
    "import": "SYNOPSIS\n    ret import <tar> [dest]\n\nRestore a claim archive; verifies on arrival.",
    "verify": (
        "SYNOPSIS\n    ret verify [dir]\n\n"
        "Recompute a claim's identity from the bytes present and compare "
        "it with the sealed root. Does not execute acceptance criteria; "
        "audit does."
    ),
    "audit": (
        "SYNOPSIS\n    ret audit [dir] [--shallow] [--no-strict] [--mutants N] [--record path]\n\n"
        "Re-earn every gate, cold, composed claims included by default "
        "(--shallow opts out). Judged in a sandboxed jail by default; "
        "--no-strict opts down."
    ),
    "assess": (
        "SYNOPSIS\n    ret assess [dir] [--mutants N]\n\n"
        "Measure how much of a claim its own gates actually pin down, via "
        "deterministic mutation testing."
    ),
    "rebuild": (
        "SYNOPSIS\n    ret rebuild [dir] [--producer NAME|COMMAND] [-o into]\n\n"
        "Regrow a claim's generated outputs until its gates pass. The "
        "claim's own generated sources are withheld from the room a "
        "producer sees -- rebuild measures whether the pinned criteria "
        "and fixtures alone are enough.\n\n"
        "The shipped producers answer to their own names (--producer "
        "openai, --producer anthropic, --producer codex); a producer "
        "stays any program -- any shell command that writes the declared "
        "outputs."
    ),
    "crosscheck": (
        "SYNOPSIS\n    ret crosscheck <m1> [m2] [m3] [--mutants N]\n\n"
        "The three-machine test: M1 (origin), M2 (transfer), M3 "
        "(independent rebuild). Given only M1 and M3, M2 is materialized "
        "here, as a real byte copy, and that fact is disclosed."
    ),
    "record": (
        "SYNOPSIS\n    ret record [dir] [-o out] [--key K] [--as IDENTITY] [--check]\n\n"
        "Without --as: emit, write, and (with --key) sign a record "
        "(spec/record.md). With --as: notarize the build in place "
        "(attestation). --check reads attestations back."
    ),
    "sign": (
        "SYNOPSIS\n    ret sign [dir] [--key K] [--as IDENTITY] [--check]\n\n"
        "Without a key: print the review packet a signer would stand "
        "behind. With --key/--as: authorize the claim's whole lineage, "
        "detached signature. --check reads authorizations back."
    ),
    "hook": "SYNOPSIS\n    ret hook [-C dir]\n\nClassify one coding-agent hook payload from stdin. Plumbing: silent.",
    "help": "SYNOPSIS\n    ret help [topic] [-a]\n\nShow detailed help for one command, or every command with -a.",
    "completion": "SYNOPSIS\n    ret completion [bash|zsh]\n\nPrint a shell completion script generated from the grammar.",
}

_BRIEF = {
    "init": "initialize a workspace", "run": "run and observe a command",
    "status": "show work, claims, and unresolved inputs",
    "pack": "create a claim from a project",
    "pull": "add another claim as a dependency",
    "export": "write a portable claim archive",
    "import": "restore a claim archive",
    "verify": "verify claim identity", "audit": "rerun acceptance criteria",
    "assess": "measure specification strength",
    "rebuild": "rebuild an implementation from a claim",
    "crosscheck": "compare independent realizations",
    "record": "write an execution record", "sign": "authorize a claim or proof",
    "hook": "classify one coding-agent hook payload (plumbing)",
    "help": "show detailed help for one command, or every command with -a",
    "completion": "print a shell completion script",
}

_ENVIRONMENT_HELP = """\
Environment variables ret reads:

RETICULI_PRODUCER     default --producer for `ret rebuild`
RETICULI_KEY          default signing key path for `record --sign`
RETICULI_SIGNERS      an ssh allowed_signers file, the trust anchor for
                      signature verification (`record --check`, `sign --check`,
                      status's signature view)
RETICULI_COLOR        auto (default, tty-based) / always / never
RETICULI_CACHE        where the verdict-reuse cache lives
RETICULI_GATE_TIMEOUT host override for a gate's wall-clock ceiling
RETICULI_JAILED       internal: already-inside-a-sandbox signal
OPENAI_API_KEY        credential for --producer openai / codex
ANTHROPIC_API_KEY     credential for --producer anthropic
"""


# ============================================================== plumbing
def _add_common(sub) -> None:
    sub.add_argument("--json", action="store_true",
                      help="print the machine-readable envelope instead of a human summary")
    sub.add_argument("--verbose", "-v", action="store_true",
                      help="show extra detail in human-readable mode")
    sub.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                      help="colorize human-mode output (default: auto)")


def _add_parser(sub, name, **kw):
    kw.setdefault("description", _HELP.get(name, ""))
    kw.setdefault("epilog", None)
    kw.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
    return sub.add_parser(name, **kw)


def build_parser():
    """The top-level parser and every registered subparser, keyed by verb."""
    p = argparse.ArgumentParser(
        prog="ret", description=_DESC, epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="store_true", help="print the version and exit")
    sub = p.add_subparsers(dest="verb", metavar="<command>")
    registered = {}

    def add(name):
        s = _add_parser(sub, name)
        registered[name] = s
        return s

    s = add("init")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--agent", default=None)
    s.add_argument("--no-agent", action="store_true",
                    help="withhold the coding-agent handshake (the default)")
    _add_common(s)

    s = add("run")
    s.add_argument("cmd")
    s.add_argument("-C", "--dir", dest="dir", default=None)

    s = add("status")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--all", action="store_true")
    s.add_argument("--files", action="store_true")
    s.add_argument("--tree", action="store_true")
    s.add_argument("--claims", action="store_true")
    _add_common(s)

    s = add("pack")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--name")
    s.add_argument("--gate")
    s.add_argument("--gate-output", default="gate")
    s.add_argument("--generated", action="append", default=[])
    s.add_argument("--inputs", action="append", default=[])
    s.add_argument("--component")
    s.add_argument("--format", type=int, default=None)
    s.add_argument("--envelope", action="append", default=[])
    s.add_argument("--mutation-floor", type=float, default=None)
    s.add_argument("--requires", action="append", default=[])
    s.add_argument("--by")
    s.add_argument("--inputs-manifest")
    s.add_argument("--environment")
    s.add_argument("--pytest", action="store_true")
    s.add_argument("--accept", nargs="+", default=None)
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    _add_common(s)

    s = add("pull")
    s.add_argument("src")
    s.add_argument("dest")
    _add_common(s)

    s = add("export")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("tar", nargs="?", default=None)
    s.add_argument("-o", "--out", default=None)
    s.add_argument("--blind", action="store_true")
    _add_common(s)

    s = add("import")
    s.add_argument("tar")
    s.add_argument("dest", nargs="?", default=None)
    _add_common(s)

    s = add("verify")
    s.add_argument("dir", nargs="?", default=".")
    _add_common(s)

    s = add("audit")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--shallow", action="store_true")
    s.add_argument("--no-strict", action="store_true")
    s.add_argument("--mutants", type=int, default=None)
    s.add_argument("--record", default=None)
    _add_common(s)

    s = add("assess")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--mutants", type=int, default=None)
    _add_common(s)

    s = add("rebuild")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--producer", default=None)
    s.add_argument("-o", "--out", "--into", dest="out", default=None)
    s.add_argument("--ws", default=None)
    s.add_argument("--reuse", action="store_true")
    s.add_argument("--without-guidance", action="store_true")
    _add_common(s)

    s = add("crosscheck")
    s.add_argument("m1", nargs="?", default=".")
    s.add_argument("m2", nargs="?", default=None)
    s.add_argument("m3", nargs="?", default=None)
    s.add_argument("--mutants", type=int, default=None)
    _add_common(s)

    s = add("record")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("-o", "--out", default=None)
    s.add_argument("--key", default=None)
    s.add_argument("--as", dest="identity", default=None)
    s.add_argument("--check", action="store_true")
    s.add_argument("--sign", action="store_true")
    s.add_argument("--signers", default=None)
    _add_common(s)

    s = add("sign")
    s.add_argument("dir", nargs="?", default=".")
    s.add_argument("--key", default=None)
    s.add_argument("--as", dest="identity", default=None)
    s.add_argument("--check", action="store_true")
    s.add_argument("--ws", default=None)
    _add_common(s)

    s = add("hook")
    s.add_argument("-C", "--project-dir", default=None)

    s = add("help")
    s.add_argument("topic", nargs="?", default=None)
    s.add_argument("-a", "--all", action="store_true")

    s = add("completion")
    s.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p, registered


def verbs() -> tuple:
    """Every verb the grammar registers: the fourteen porcelain verbs plus
    the three plumbing verbs."""
    _, registered = build_parser()
    return tuple(registered)


def _completion_text(shell: str) -> str:
    names = " ".join(sorted(verbs()))
    if shell == "zsh":
        return (f"#compdef ret\n_ret() {{ compadd {names}; }}\ncompdef _ret ret")
    return ("_ret_completion() {\n"
            '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
            f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
            "}\n"
            "complete -F _ret_completion ret")


def _environment_doc() -> str:
    return _ENVIRONMENT_HELP


def _help_all(registered) -> None:
    names = tuple(registered)
    width = max(len(n) for n in names)
    for name in sorted(names):
        print(f"{name:<{width}}  {_BRIEF.get(name, '')}")


def _help_topic(registered, topic: str) -> None:
    if topic == "environment":
        print(_environment_doc())
        return
    s = registered.get(topic)
    if s is None:
        print(f"ret: help: no such command: {topic!r}")
        return
    print(s.format_help())


# ================================================================ rendering
def _emit(cmd: str, args, *, ok: bool, status: str, root, data: dict) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"command": cmd, "ok": ok, "status": status,
                           "root": root, "data": data}, sort_keys=True))
    return 0 if ok else 1


def _fail(cmd: str, args, reason: str, *, hints=None) -> int:
    if getattr(args, "json", False):
        return _emit(cmd, args, ok=False, status="error", root=None,
                     data={"error": reason})
    output._err(cmd, reason)
    for h in hints or ():
        print(f"hint: {h}", file=sys.stderr)
    return 1


def _invalid(cmd: str, reason: str) -> int:
    print(f"ret: {cmd}: {reason}", file=sys.stderr)
    return 2


def _verbose_block(args, title: str, pairs: list) -> None:
    out = [f"[{title}]"]
    for k, v in pairs:
        if isinstance(v, bool):
            out.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, str):
            out.append(f'{k} = "{v}"')
        else:
            out.append(f"{k} = {v}")
    output._line(args, "\n".join(out))


def _dir(args) -> str:
    for attr in ("dir", "m1"):
        v = getattr(args, attr, None)
        if v:
            return v
    return "."


def _rel(path: str) -> str:
    try:
        r = os.path.relpath(path)
    except ValueError:
        return path
    return path if r.startswith("..") else r


_GATE_WORDS = {"ok": "reproduced", "mismatch": "wrong bytes", "failed": "crashed",
               "timeout": "timed out", "environment": "host can't judge"}


def _gate_word(status) -> str:
    return _GATE_WORDS.get(status, str(status))


# ================================================================== init
def _handle_init(args) -> int:
    ws = args.dir
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    gi_path = os.path.join(ws, ".gitignore")
    existing = ""
    if os.path.isfile(gi_path):
        with open(gi_path, "r", encoding="utf-8") as f:
            existing = f.read()
    if "ledger.jsonl" not in existing:
        with open(gi_path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(".reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n.reticuli/run/\n")

    agent = getattr(args, "agent", None)
    wired = None
    if agent:
        if agent not in _SUPPORTED_AGENTS:
            return _invalid("init", f"unsupported agent: {agent!r}")
        wired = hooks.install(ws)

    data = {"ws": ws, "agent": agent, "wired": wired}
    if not getattr(args, "json", False):
        output._line(args, f"initialized {_rel(ws)}")
    return _emit("init", args, ok=True, status="ok", root=None, data=data)


# =================================================================== run
def _handle_run(args) -> int:
    ws = args.dir or os.getcwd()
    proc = subprocess.run(args.cmd, shell=True, cwd=ws)
    return proc.returncode


# ================================================================== pull
def _handle_pull(args) -> int:
    def fn():
        return registry.pull(args.src, args.dest)
    try:
        data = fn()
    except kernel.ClaimError as e:
        return _fail("pull", args, str(e))
    if not getattr(args, "json", False):
        output._line(args, f"pulled {data.get('name')}  {render.short(data.get('root') or '')}")
    return _emit("pull", args, ok=True, status="ok", root=data.get("root"), data=data)


# ================================================================ verify
def _handle_verify(args) -> int:
    d = _dir(args)
    try:
        v = kernel.verify(d)
    except kernel.ClaimError as e:
        return _fail("verify", args, str(e))

    manifest_name = v.get("name")
    try:
        ph = kernel.phase(d)
    except kernel.ClaimError:
        ph = None
    data = {"name": manifest_name, "root": v["root"], "recomputed": v["recomputed"],
            "phase": ph, "ok": v["ok"]}

    if not v["ok"]:
        if getattr(args, "json", False):
            return _emit("verify", args, ok=False, status="mismatch", root=v["root"], data=data)
        declared = _declared_paths(d)
        reason = (f"identity mismatch in {d!r}: the bytes present no longer "
                  f"recompute the sealed root; check these declared file(s) "
                  f"for drift: {', '.join(declared) if declared else '(none declared)'}")
        return _fail("verify", args, reason,
                     hints=["restore the sealed bytes, or reseal if the change is intended"])

    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        _verbose_block(args, "verify", [("name", manifest_name), ("root", v["root"]),
                                         ("recomputed", v["recomputed"]), ("ok", v["ok"])])
    return _emit("verify", args, ok=True, status="fresh", root=v["root"], data=data)


def _declared_paths(d: str) -> list:
    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError:
        return []
    claim = recipe.get("claim", {})
    out = list(claim.get("inputs", []))
    for step in recipe.get("step", []):
        default = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default) != "generated":
            out.append(step["output"])
    return out


# =================================================================== audit
def _audit_status_word(gates: list) -> str:
    if not gates:
        return "broken"
    statuses = {g.get("status") for g in gates}
    for word in ("environment", "timeout", "mismatch", "failed"):
        if word in statuses:
            return word
    return "broken"


def _handle_audit(args) -> int:
    d = _dir(args)
    deep = not bool(getattr(args, "shallow", False))
    strict = not bool(getattr(args, "no_strict", False))
    mutants = getattr(args, "mutants", None)
    record_path = getattr(args, "record", None)

    try:
        start = time.monotonic()
        if deep:
            outer = registry.audit_deep(d)
            own = outer.get("own", {}) or {}
            gates = own.get("gates", []) or []
            environment = own.get("environment", []) or []
            layers = outer.get("layers", []) or []
            ok = bool(outer["ok"])
            recomputed = outer.get("root")
        else:
            own = kernel.audit(d, strict=strict)
            gates = own.get("gates", []) or []
            environment = own.get("environment", []) or []
            layers = []
            ok = bool(own["ok"])
            recomputed = own.get("root")
        elapsed = time.monotonic() - start
    except kernel.ClaimError as e:
        return _fail("audit", args, str(e))

    try:
        manifest = kernel.read_manifest(d)
        name, sealed_root = manifest.get("name"), manifest.get("root")
    except kernel.ClaimError:
        name, sealed_root = None, recomputed

    extra = {}
    if mutants is not None:
        try:
            extra["mutation_score"] = kernel.mutation_score(d, max_mutants=mutants)
        except kernel.ClaimError:
            pass
    if record_path:
        try:
            doc = record.emit(d)
            record.write(doc, record_path)
            extra["record"] = record_path
        except kernel.ClaimError:
            pass

    if ok:
        try:
            kernel.ledger(d, {"event": "audit", "ok": True})
        except OSError:
            pass
        status = "earned"
    else:
        status = _audit_status_word(gates)

    data = {"name": name, "root": sealed_root, "recomputed": recomputed,
            "elapsed": elapsed, "environment": environment, "layers": layers,
            "gates": gates, "ok": ok}
    data.update(extra)

    if not ok:
        if not getattr(args, "json", False):
            output._err("audit", f"{status}: {d!r}")
            return 1
        return _emit("audit", args, ok=False, status=status, root=sealed_root, data=data)

    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        lines = [f"[audit]", f"root = \"{sealed_root}\"", f"elapsed = {elapsed:.3f}"]
        for g in gates:
            lines.append(f"  gate {g.get('output')}: {_gate_word(g.get('status'))}")
        if "mutation_score" in extra:
            ms = extra["mutation_score"]
            lines.append(f"[mutation_score]\nmutants = {ms.get('mutants')}\nrate = {ms.get('rate')}")
        output._line(args, "\n".join(lines))
    return _emit("audit", args, ok=True, status="earned", root=sealed_root, data=data)


# ================================================================== assess
def _handle_assess(args) -> int:
    d = _dir(args)
    mutants = getattr(args, "mutants", None)
    try:
        result = assess.assess(d, mutants=mutants)
    except kernel.ClaimError as e:
        return _fail("assess", args, str(e))

    try:
        recipe = kernel.load_recipe(d)
        claim = recipe.get("claim", {})
    except kernel.ClaimError:
        claim = {}

    try:
        kernel.ledger(d, {"event": "assess", "ok": True})
    except OSError:
        pass

    data = dict(result)
    data["declared"] = claim.get("mutation_floor")
    data["gate"] = "ok" if not result.get("not_measured") else "gap"

    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        _verbose_block(args, "assess", [("measured", result["measured"]),
                                         ("not_measured", result["not_measured"]),
                                         ("not_applicable", result["not_applicable"])])
    return _emit("assess", args, ok=True, status="measured", root=None, data=data)


# ================================================================= rebuild
_PRODUCERS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
              "codex": "OPENAI_API_KEY"}


def _handle_rebuild(args) -> int:
    d = _dir(args)
    producer = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    into = getattr(args, "out", None) or tempfile.mkdtemp(prefix="reticuli-rebuild-")
    ws = getattr(args, "ws", None)
    reuse = bool(getattr(args, "reuse", False))

    if producer in _PRODUCERS:
        credential = _PRODUCERS[producer]
        if not os.environ.get(credential):
            return _fail("rebuild", args, f"the {producer} producer needs {credential} set")

    try:
        result = dict(registry.rebuild_chain(d, producer, into, ws=ws, reuse=reuse))
    except kernel.ClaimError as e:
        return _fail("rebuild", args, str(e))

    result["into"] = into
    if not getattr(args, "json", False):
        output._line(args, f"rebuilt {_rel(into)}  {render.short(result.get('root') or '')}")
    return _emit("rebuild", args, ok=True, status="rebuilt", root=result.get("root"), data=result)


# =============================================================== crosscheck
def _ledger_discovery(d: str):
    try:
        events = kernel.ledger_events(d)
    except OSError:
        return None
    for e in reversed(events):
        if e.get("event") == "discovery" and "discovery_tokens" in e:
            return e["discovery_tokens"]
    return None


def _handle_crosscheck(args) -> int:
    m1 = args.m1
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    mutants = getattr(args, "mutants", None)

    if not m2 and not m3:
        return _invalid("crosscheck", "one realization is not a comparison")

    materialized_m2 = False
    scratch = None
    if m2 and not m3:
        m3 = m2
        m2 = None
    if not m2:
        scratch = tempfile.mkdtemp(prefix="reticuli-crosscheck-m2-")
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.copytree(m1, scratch)
        m2 = scratch
        materialized_m2 = True

    try:
        result = dict(registry.crosscheck_deep(m1, m2, m3, mutants=mutants))
    except kernel.ClaimError as e:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
        return _fail("crosscheck", args, str(e))

    result["m2_materialized"] = materialized_m2
    status = result.get("verdict", "reject")
    ok = bool(result.get("satisfied"))

    if not ok:
        reasons = (result.get("rejected") or []) + (result.get("incomplete") or [])
        return _fail("crosscheck", args, f"{status}: " + (", ".join(reasons) or status))

    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        lines = [f"[crosscheck]", f"satisfied = {'true' if ok else 'false'}",
                 f'verdict = "{status}"', f"roots = {result.get('roots')}",
                 "[cost]", f"comparable = {result.get('cost', {}).get('comparable')}"]
        tokens = _ledger_discovery(m1)
        if tokens is not None:
            lines.append(f"discovery: {tokens} tokens (reported, not in cost band)")
        output._line(args, "\n".join(lines))
    return _emit("crosscheck", args, ok=True, status=status, root=result.get("roots", {}).get("M1"),
                 data=result)


# ================================================================== export
def _handle_export(args) -> int:
    d = _dir(args)
    dest = getattr(args, "out", None) or getattr(args, "tar", None)
    blind = bool(getattr(args, "blind", False))
    if not dest:
        return _fail("export", args, "export requires a destination (a path, or -o)")

    try:
        if dest == "-":
            tmp = tempfile.mktemp(prefix="reticuli-export-")
            transfer.export(d, tmp, blind=blind)
            with open(tmp, "rb") as f:
                sys.stdout.buffer.write(f.read())
            sys.stdout.buffer.flush()
            os.remove(tmp)
        else:
            transfer.export(d, dest, blind=blind)
    except kernel.ClaimError as e:
        return _fail("export", args, str(e))

    data = {"tar": dest, "blind": blind}
    return _emit("export", args, ok=True, status="ok", root=None, data=data)


def _handle_import(args) -> int:
    tar_path = args.tar
    dest = getattr(args, "dest", None) or "."

    try:
        if tar_path == "-":
            tmp = tempfile.mktemp(prefix="reticuli-import-")
            with open(tmp, "wb") as f:
                f.write(sys.stdin.buffer.read())
            tar_path = tmp
        elif not os.path.isfile(tar_path):
            return _fail("import", args, f"no archive at {tar_path!r}")
        data = transfer.import_(tar_path, dest)
    except kernel.ClaimError as e:
        return _fail("import", args, str(e))

    ok = bool(data.get("ok"))
    if not ok:
        return _fail("import", args, data.get("error") or "import failed to verify")
    return _emit("import", args, ok=True, status="ok", root=data.get("root"), data=data)


# ================================================================== record
def _handle_record(args) -> int:
    d = _dir(args)
    identity = getattr(args, "identity", None)
    key = getattr(args, "key", None)
    sign_flag = bool(getattr(args, "sign", False))
    check = bool(getattr(args, "check", False))
    out_path = getattr(args, "out", None) or os.path.join(d, "record.json")
    signers = getattr(args, "signers", None) or os.environ.get("RETICULI_SIGNERS")

    try:
        if check:
            result = attest.check(d, signers=signers)
            ok = bool(result.get("attestations")) and all(
                a["verdict"] in ("signed", "unanchored") for a in result["attestations"])
            return _emit("record", args, ok=ok, status="checked" if ok else "unanchored",
                         root=None, data=result)

        if identity:
            if not key:
                return _fail("record", args, "record --as requires --key")
            result = attest.attest(d, key, identity)
            return _emit("record", args, ok=True, status="attested", root=None, data=result)

        if sign_flag and not key:
            key = os.environ.get("RETICULI_KEY")
            if not key:
                return _fail("record", args,
                             "record --sign requires RETICULI_KEY to name a signing key")
            identity = identity or os.environ.get("RETICULI_IDENTITY") or "unknown"

        doc = record.emit(d)
        record.write(doc, out_path)
        if key:
            record.sign(out_path, key)
        data = {"path": out_path, "name": doc["name"], "root": doc["root"],
                "digest": record.digest(doc), "record": doc, "signed": bool(key)}
    except kernel.ClaimError as e:
        return _fail("record", args, str(e))

    return _emit("record", args, ok=True, status="ok", root=data.get("root"), data=data)


# =================================================================== sign
def _handle_sign(args) -> int:
    d = _dir(args)
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    ws = getattr(args, "ws", None)
    check = bool(getattr(args, "check", False))

    try:
        if check:
            result = attest.sign_check(d, ws=ws)
            ok = any(a.get("packet_holds") for a in result.get("authorizations", []))
            return _emit("sign", args, ok=ok, status="checked" if ok else "unsigned",
                         root=None, data=result)

        if key and identity:
            result = attest.sign(d, key, identity, ws=ws)
            return _emit("sign", args, ok=True, status="signed", root=None, data=result)

        pkt = attest.review_packet(d, ws=ws)
    except kernel.ClaimError as e:
        return _fail("sign", args, str(e))

    if getattr(args, "verbose", False) and not getattr(args, "json", False):
        _verbose_block(args, "review", [("root", pkt.get("root")),
                                         ("build_digest", pkt.get("build_digest")),
                                         ("sign_root", pkt.get("sign_root")),
                                         ("audit_ok", pkt.get("audit", {}).get("ok"))])
    elif not getattr(args, "json", False):
        output._line(args, f"review  {render.short(pkt.get('root') or '')}")
    return _emit("sign", args, ok=True, status="review", root=pkt.get("root"), data=pkt)


# ==================================================================== pack
def _read_discovery_tokens(ws: str):
    trace_path = os.path.join(ws, hooks.TRACE)
    if not os.path.isfile(trace_path):
        return None
    total, found = 0, False
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "session" and e.get("transcript"):
                tpath = e["transcript"]
                if not os.path.isfile(tpath):
                    continue
                with open(tpath, "r", encoding="utf-8") as tf:
                    for tline in tf:
                        tline = tline.strip()
                        if not tline:
                            continue
                        try:
                            rec = json.loads(tline)
                        except json.JSONDecodeError:
                            continue
                        usage = (rec.get("message") or {}).get("usage") or {}
                        it = usage.get("input_tokens") or 0
                        ot = usage.get("output_tokens") or 0
                        if it or ot:
                            total += it + ot
                            found = True
    return total if found else None


def _dispatch_pack(args) -> int:
    path = args.dir
    accept = getattr(args, "accept", None)
    output_dir = getattr(args, "output", None)
    name = getattr(args, "name", None)
    gate = getattr(args, "gate", None)

    if accept and not output_dir:
        output._err("pack", "--accept requires -o/--output to know where to "
                             "seal the accepted claim")
        return 2

    try:
        if accept:
            into = output_dir
            if os.path.exists(into) and os.listdir(into):
                return _fail("pack", args, f"refused non-empty pack target: {into!r}")
            result = authoring.build_claim(path, accept, into, name=name)
            tokens = _read_discovery_tokens(path)
            if tokens is not None:
                try:
                    kernel.ledger(into, {"event": "discovery", "discovery_tokens": tokens})
                except OSError:
                    pass
        elif name or gate:
            use_pytest = bool(getattr(args, "pytest", False))
            gate_output = getattr(args, "gate_output", None) or "gate"
            if use_pytest and not gate:
                gate = f"python3 -m pytest -q && printf ok > {gate_output}"
            if not name or not gate:
                raise kernel.ClaimError("pack requires --name and --gate")
            dest = output_dir or path
            if dest != path:
                shutil.copytree(path, dest, dirs_exist_ok=True)
            result = pack.pack(
                dest, name, getattr(args, "generated", None) or [],
                getattr(args, "inputs", None) or [], gate, gate_output,
                claim_format=getattr(args, "format", None),
                envelope=_parse_envelope(getattr(args, "envelope", None)),
                mutation_floor=getattr(args, "mutation_floor", None),
                requires=getattr(args, "requires", None) or None,
                by=getattr(args, "by", None),
                inputs_manifest=getattr(args, "inputs_manifest", None),
                environment=getattr(args, "environment", None))
        else:
            try:
                kernel.load_recipe(path)
            except kernel.ClaimError:
                raise kernel.ClaimError(f"nothing to pack in {path!r}")
            result = registry.seal_with(path)
    except kernel.ClaimError as e:
        return _fail("pack", args, str(e))

    if not getattr(args, "json", False):
        output._line(args, f"packed {result.get('name')}  {render.short(result.get('root') or '')}")
    return _emit("pack", args, ok=True, status="packed", root=result.get("root"), data=result)


def _parse_envelope(items):
    if not items:
        return None
    out = {}
    for item in items:
        unit, _, val = item.partition("=")
        if unit and val:
            out[unit] = float(val)
    return out or None


# ================================================================== status
def _real_files(ws: str) -> set:
    out = set()
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d != kernel.STORE.lstrip("./")
                       and d != ".reticuli"]
        rel_dir = os.path.relpath(dirpath, ws)
        for fname in filenames:
            rel = fname if rel_dir in (".", "") else f"{rel_dir}/{fname}"
            out.add(rel.replace(os.sep, "/"))
    return out


def _one_level_imports(ws: str, pyfile: str, real: set) -> set:
    found = set()
    path = os.path.join(ws, pyfile)
    try:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return found
    for m in re.finditer(r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))',
                          src, re.MULTILINE):
        mod = m.group(1) or m.group(2)
        if mod:
            candidate = mod.split(".")[0] + ".py"
            if candidate in real:
                found.add(candidate)
    return found


def _draft_sense(ws: str) -> dict:
    events = []
    trace_path = os.path.join(ws, hooks.TRACE)
    if os.path.isfile(trace_path):
        with open(trace_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    real = _real_files(ws)
    written, read_paths, bash_cmds = {}, {}, []
    for e in events:
        et = e.get("event")
        if et == "write" and "path" in e:
            written.setdefault(e["path"], e.get("via"))
        elif et == "read" and "path" in e:
            read_paths.setdefault(e["path"], e.get("via"))
        elif et == "bash" and "cmd" in e:
            bash_cmds.append(e["cmd"])

    bash_literal = set()
    for cmd in bash_cmds:
        try:
            toks = shlex.split(cmd)
        except ValueError:
            toks = cmd.split()
        for t in toks:
            if t in real:
                bash_literal.add(t)

    covered = set(bash_literal)
    for cmd in bash_cmds:
        try:
            deciders = kernel.gate_deciders(cmd)
        except Exception:
            deciders = []
        for dec in deciders:
            if dec in real:
                covered.add(dec)
                if dec.endswith(".py"):
                    covered |= _one_level_imports(ws, dec, real)

    rows = {}
    for p in sorted(set(written) | set(read_paths) | bash_literal | covered):
        if p in written:
            via = written[p] or "hook"
            role = "generated" if p in covered else "undeclared"
            rows[p] = {"path": p, "observed": "write", "declared": role, "evidence": via}
        elif p in covered:
            rows[p] = {"path": p, "observed": "bash", "declared": "pinned", "evidence": "gate"}
        elif p in read_paths:
            via = read_paths[p] or "hook"
            rows[p] = {"path": p, "observed": "read", "declared": "pinned", "evidence": via}

    for p in sorted(real):
        if p not in rows:
            rows[p] = {"path": p, "observed": "-", "declared": "-", "evidence": "-"}

    observed_n = sum(1 for r in rows.values() if r["observed"] != "-")
    declared_n = sum(1 for r in rows.values() if r["declared"] not in ("-", "undeclared"))
    unresolved_n = sum(1 for r in rows.values() if r["declared"] == "undeclared")
    return {"rows": rows, "observed": observed_n, "declared": declared_n,
            "unresolved": unresolved_n}


_SIGN_DISPLAY = {"attest": "attested", "sign": "signed"}


def _statements(d: str) -> list:
    out = []
    attest_dir = os.path.join(d, attest.ATTEST)
    if os.path.isdir(attest_dir):
        for fname in sorted(os.listdir(attest_dir)):
            if fname.endswith(".statement.json"):
                out.append({"kind": "attest", "display": "attested"})
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if fname.endswith(".sign.json"):
                out.append({"kind": "sign", "display": "signed"})
    return out


def _claim_status_view(d: str) -> dict:
    try:
        manifest = kernel.read_manifest(d)
        name, sealed_root = manifest.get("name"), manifest.get("root")
    except kernel.ClaimError:
        name, sealed_root = None, None

    try:
        v = kernel.verify(d)
        identity_ok = v["ok"]
    except kernel.ClaimError:
        identity_ok = False

    try:
        ph = kernel.phase(d)
    except kernel.ClaimError:
        ph = "sealed"
    phase_display = ph if identity_ok else "broken"

    events = []
    try:
        events = kernel.ledger_events(d)
    except OSError:
        pass
    audited = None
    assessed = None
    for e in reversed(events):
        if audited is None and e.get("event") == "audit":
            audited = {"when": e.get("when")}
        if assessed is None and e.get("event") == "assess":
            assessed = {"when": e.get("when")}
    discovery = _ledger_discovery(d)

    try:
        manifest_full = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest_full = {}
    proof = manifest_full.get("proof")

    signatures = _statements(d)

    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError:
        recipe = None

    if not identity_ok:
        nxt = "restore the original bytes, or reseal if the change is intended (ret verify)"
    elif audited is None:
        nxt = "earn a verdict fresh: ret audit"
    elif assessed is None:
        nxt = "measure the tests: ret assess"
    else:
        nxt = "prove it independently: ret crosscheck"

    return {"name": name, "root": sealed_root, "phase": phase_display,
            "identity_ok": identity_ok, "audited": audited, "deciding": [],
            "proof": proof, "signatures": signatures, "next": nxt,
            "discovery": discovery, "assessed": assessed, "recipe": recipe}


def _files_claim(recipe: dict) -> list:
    if recipe is None:
        return []
    claim = recipe.get("claim", {})
    rows, seen = [], set()
    for path in claim.get("inputs", []):
        rows.append((path, "pinned", "fixed"))
        seen.add(path)
    for step in recipe.get("step", []):
        path = step.get("output")
        if not path or path in seen:
            continue
        default = "generated" if step.get("kind") == "produce" else "pinned"
        role = step.get("class", default)
        descriptor = {"generated": "free", "pinned": "fixed", "validated": "verdict"}.get(role, role)
        rows.append((path, role, descriptor))
        seen.add(path)
    return rows


def _dispatch_status(args) -> int:
    d = args.dir
    if not os.path.isdir(d):
        return _fail("status", args, f"no such directory: {d!r}")

    as_json = bool(getattr(args, "json", False))

    if getattr(args, "claims", False):
        rows = registry.claims(d)
        if not as_json:
            text = render.table([[c["name"], render.short(c["root"]), c["phase"]] for c in rows])
            if text:
                output._line(args, text)
        return _emit("status", args, ok=True, status="ok", root=None, data={"claims": rows})

    if getattr(args, "tree", False):
        sealed = os.path.isfile(os.path.join(d, kernel.MANIFEST))
        if not sealed:
            if not as_json:
                output._line(args, "draft (workspace)")
            return _emit("status", args, ok=True, status="draft", root=None, data={"phase": "draft"})

        try:
            manifest = kernel.read_manifest(d)
            recipe = kernel.load_recipe(d)
        except kernel.ClaimError as e:
            return _fail("status", args, str(e))
        comps = manifest.get("components") or []
        files = _files_claim(recipe)
        if not as_json:
            colored = output._color_enabled(args)
            rows = []
            for path, role, _desc in files:
                bucket = "generated" if role == "generated" else "pinned"
                if colored:
                    color = "cyan" if bucket == "generated" else "green"
                    rows.append([output._paint(path, color, args)])
                else:
                    rows.append([bucket, path])
            text = f"layers={len(comps)}"
            table_text = render.table(rows)
            if table_text:
                text += "\n" + table_text
            output._line(args, text)
        return _emit("status", args, ok=True, status="ok", root=manifest.get("root"),
                     data={"layers": comps})

    sealed = os.path.isfile(os.path.join(d, kernel.MANIFEST))

    if not sealed:
        sense = _draft_sense(d)
        try:
            readiness = {"sealable": bool([r for r in sense["rows"].values()
                                           if r["observed"] == "bash"])}
        except Exception:
            readiness = {"sealable": False}
        packable = sense["unresolved"] == 0 and sense["observed"] > 0

        if getattr(args, "files", False) or getattr(args, "all", False):
            header = ["path", "observed", "declared", "evidence"]
            rows = [header]
            for p in sorted(sense["rows"]):
                r = sense["rows"][p]
                rows.append([r["path"], r["observed"], r["declared"], r["evidence"]])
            if not as_json:
                output._line(args, render.table(rows))
            data = {"phase": "draft", "files": list(sense["rows"].values())}
            return _emit("status", args, ok=True, status="draft", root=None, data=data)

        if not as_json:
            word = "packable" if packable else "not yet packable"
            undeclared = [p for p, r in sense["rows"].items() if r["declared"] == "undeclared"]
            tail = f"  undeclared: {', '.join(sorted(undeclared))}" if undeclared else ""
            output._line(args, f"draft  observed={sense['observed']} "
                                f"declared={sense['declared']} "
                                f"unresolved={sense['unresolved']}  {word}{tail}")
        data = {"phase": "draft", "observed": sense["observed"],
                "declared": sense["declared"], "unresolved": sense["unresolved"]}
        return _emit("status", args, ok=True, status="draft", root=None, data=data)

    view = _claim_status_view(d)

    if getattr(args, "files", False):
        rows = [["path", "role", "note"]]
        for path, role, descriptor in _files_claim(view["recipe"]):
            rows.append([path, role, descriptor])
        if not as_json:
            output._line(args, render.table(rows))
        return _emit("status", args, ok=True, status="fresh", root=view["root"],
                     data={"files": _files_claim(view["recipe"])})

    if getattr(args, "all", False):
        files = _files_claim(view["recipe"])
        fixed = [p for p, r, _ in files if r == "pinned"]
        free = [p for p, r, _ in files if r == "generated"]
        deciding = [p for p, r, _ in files if r == "validated"]
        lines = []
        lines.append("fixed:")
        lines.append("  " + (", ".join(fixed) if fixed else "(none declared)"))
        lines.append("deciding:")
        lines.append("  " + (", ".join(deciding) if deciding else "(none declared)"))
        lines.append("free:")
        lines.append("  " + (", ".join(free) if free else "(none declared)"))
        lines.append("recorded:")
        if view["audited"]:
            lines.append(f"  audit, {view['audited'].get('when')} -- on this machine")
        if view["assessed"]:
            lines.append(f"  assess, {view['assessed'].get('when')} -- a receipt, not a verdict")
        if not view["audited"] and not view["assessed"]:
            lines.append("  (nothing recorded yet)")
        lines.append("unknown:")
        lines.append("  (nothing declared awaiting measurement)")
        lines.append(f"next: {view['next']}")
        if not as_json:
            output._line(args, "\n".join(lines))
        return _emit("status", args, ok=True, status="fresh", root=view["root"], data=view)

    if not as_json:
        short_root = render.short(view["root"] or "") or "-" * 8
        colored = output._color_enabled(args)
        head = f"{view['name']}  {short_root}  {view['phase']}"
        head = output._paint(head, "cyan", args) if colored else head
        lines = [head]
        if not view["identity_ok"]:
            lines.append("identity: broken")
            lines.append(f"next: {view['next']}")
        else:
            lines.append("identity: fresh")
            if view["audited"]:
                lines.append(f"audited: {view['audited'].get('when')} on this machine")
            else:
                lines.append("audited: never")
            if view["discovery"] is not None:
                lines.append(f"discovery: {view['discovery']} tokens "
                              f"(reported, not in cost band)")
            if view["signatures"]:
                kinds = ", ".join(sorted({s["display"] for s in view["signatures"]}))
                lines.append(f"{len(view['signatures'])} statement(s): {kinds}")
            lines.append(f"next: {view['next']}")
        output._line(args, "\n".join(lines))

    status_word = "fresh" if view["identity_ok"] else "claim"
    return _emit("status", args, ok=True, status=status_word, root=view["root"], data=view)


# ============================================================ hook/help/etc
def _handle_hook(args) -> int:
    payload = json.load(sys.stdin)
    project_dir = getattr(args, "project_dir", None)
    cwd = payload.get("cwd") or project_dir or os.getcwd()
    if "cwd" not in payload:
        payload["cwd"] = cwd
    transcript = payload.get("transcript_path")
    if transcript and os.path.isdir(os.path.join(payload["cwd"], kernel.STORE)):
        trace_path = os.path.join(payload["cwd"], hooks.TRACE)
        os.makedirs(os.path.dirname(trace_path), exist_ok=True)
        with open(trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "session", "transcript": transcript,
                                 "ts": time.time()}) + "\n")
    hooks.event(payload)
    return 0


def _handle_help(registered, args) -> int:
    topic = getattr(args, "topic", None)
    if getattr(args, "all", False) or (topic == "-a"):
        _help_all(registered)
        return 0
    if topic:
        _help_topic(registered, topic)
        return 0
    _help_all(registered)
    return 0


def _handle_completion(args) -> int:
    print(_completion_text(getattr(args, "shell", None) or "bash"))
    return 0


# =================================================================== main
_ROUTE = {
    "init": _handle_init, "run": _handle_run, "pull": _handle_pull,
    "verify": _handle_verify, "audit": _handle_audit, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "crosscheck": _handle_crosscheck,
    "export": _handle_export, "import": _handle_import,
    "record": _handle_record, "sign": _handle_sign,
    "pack": _dispatch_pack, "status": _dispatch_status,
    "completion": _handle_completion, "hook": _handle_hook,
}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)

    if argv and argv[0] == "--version":
        print(f"ret {_VERSION}")
        return 0

    parser, registered = build_parser()

    if not argv:
        parser.print_help()
        return 0

    verb = argv[0]
    if verb in ("-h", "--help"):
        parser.print_help()
        return 0
    if verb == "--version":
        print(f"ret {_VERSION}")
        return 0

    all_verbs = set(registered)
    if verb not in all_verbs:
        close = difflib.get_close_matches(verb, all_verbs, n=1)
        suggestion = f" Did you mean {close[0]!r}?" if close else ""
        print(f"ret: {verb!r} is not a ret command.{suggestion}", file=sys.stderr)
        return 2

    sub = registered[verb]
    try:
        ns = sub.parse_args(argv[1:])
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    if getattr(ns, "color", "auto") == "auto" and os.environ.get("RETICULI_COLOR"):
        ns.color = os.environ["RETICULI_COLOR"]

    if verb == "help":
        return _handle_help(registered, ns)

    fn = _ROUTE.get(verb)
    if fn is None:
        print(f"ret: {verb!r} is not a ret command.", file=sys.stderr)
        return 2
    return fn(ns)

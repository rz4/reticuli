"""cli-verbs: the verb handlers and the assembled `ret` entry point.

Each porcelain verb (`spec/layers.md`'s CLI table) gets one `_handle_*`
function here, except the four whose behavior branches on more than one
shape of invocation (`pack` plain vs. `--accept`, `audit` deep vs.
`--shallow`, `status`'s claim/draft/registry views, `crosscheck`'s legs),
which get a `_dispatch_*` function instead; `main()` parses argv with
`_build_parser()` and routes the result to whichever of the two handles
that verb. A handler's body is a thin call into the layer that actually
does the work (`kernel`, `registry`, `attest`, `record`, `transfer`,
`pack`, `hooks`, `assess`, `feedback`) -- this module's own job is
argument plumbing and the `output.py` envelope.

`_contract` is that plumbing, factored once (the pattern `_cli/report.py`
already uses under a different name): a verb's body raises
`kernel.ClaimError` for a clean refusal -- rendered through `output._err`
and `output._finish` rather than a raw traceback -- or returns a result
dict whose `ok`/`satisfied` flag and `status`/`verdict` word drive the
envelope. `pack --accept` without `-o` is refused even earlier than that,
in words, before a single byte is touched: there is nowhere to seal the
accepted claim, so the check happens before `_contract` ever calls into
`pack.pack`.

`_dir` reads the claim/workspace directory a verb operates on from
whichever attribute its own grammar gives it (`path`, falling back to
`dir` or `workspace`), defaulting to `.`; `run`'s own `workspace` is read
directly, since the whole point of `run` is that it returns the child's
exit code UNCHANGED rather than going through the three-valued envelope
every other verb shares.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

from reticuli import assess, attest, feedback, hooks, kernel, pack, record, registry, render, transfer
from reticuli._cli import handlers, output, statusview, views

PORCELAIN = ("init", "run", "status", "pack", "pull", "export", "import",
             "verify", "audit", "assess", "rebuild", "crosscheck",
             "record", "sign")
_PLUMBING = ("hook", "help", "completion")

_FULL_HELP = {
    "init": "initialize a workspace",
    "run": "run and observe a command",
    "status": "show work, claims, and unresolved inputs",
    "pack": "create a claim from a project",
    "pull": "add another claim as a dependency",
    "export": "write a portable claim archive",
    "import": "restore a claim archive",
    "verify": "verify claim identity",
    "audit": "rerun acceptance criteria",
    "assess": "measure specification strength",
    "rebuild": "rebuild an implementation from a claim",
    "crosscheck": "compare independent realizations",
    "record": "write an execution record",
    "sign": "authorize a claim or proof",
    "hook": "classify one coding-agent hook payload (plumbing)",
    "help": "show detailed help for one command, or every command with -a",
    "completion": "print a shell completion script",
}


def _all_verbs() -> tuple:
    return PORCELAIN + _PLUMBING


def _dir(args) -> str:
    """The claim/workspace directory a verb operates on: whichever of
    `path`/`dir`/`workspace` its own grammar set, defaulting to `.`."""
    for attr in ("path", "dir", "workspace"):
        value = getattr(args, attr, None)
        if value:
            return value
    return "."


def _contract(cmd: str, args, fn) -> int:
    """Run one verb's body (`fn`, taking no arguments) through the CLI's
    shared contract: a `kernel.ClaimError` becomes a clean refusal rather
    than a traceback, and every outcome -- pass or refusal -- ends through
    `output._finish`'s envelope."""
    try:
        data = fn()
    except kernel.ClaimError as e:
        output._err(cmd, str(e))
        output._finish(cmd, {"error": str(e)}, False, "error", args, None)
        return 1

    ok = data.get("ok")
    if ok is None:
        ok = data.get("satisfied", True)
    ok = bool(ok)
    status = data.get("status") or data.get("verdict") or ("ok" if ok else "failed")
    output._finish(cmd, data, ok, str(status), args, data.get("root"))
    return 0 if ok else 1


# ------------------------------------------------------------------- help
def _help_all() -> None:
    names = _all_verbs()
    width = max(len(name) for name in names)
    for name in sorted(names):
        print(f"{name:<{width}}  {_FULL_HELP.get(name, '')}")


def _help_topic(topic: str) -> None:
    if topic not in _all_verbs():
        print(f"ret: help: no such command: {topic!r}")
        return
    print(f"ret {topic}: {_FULL_HELP.get(topic, '')}")


def _handle_help(args) -> int:
    topic = getattr(args, "topic", None)
    if topic:
        _help_topic(topic)
    else:
        _help_all()
    return 0


# ------------------------------------------------------------- completion
def _handle_completion(args) -> int:
    shell = getattr(args, "shell", None) or "bash"
    names = " ".join(sorted(_all_verbs()))
    if shell == "zsh":
        print(f"#compdef ret\n_ret() {{ compadd {names}; }}\ncompdef _ret ret")
    else:
        print(
            "_ret_completion() {\n"
            '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
            f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
            "}\n"
            "complete -F _ret_completion ret"
        )
    return 0


# -------------------------------------------------------------------- hook
def _handle_hook(args) -> int:
    """Classify one coding-agent hook payload from stdin (`hooks.event`);
    nothing is ever printed back to the agent."""
    payload = json.load(sys.stdin)
    project_dir = getattr(args, "project_dir", None)
    if project_dir and "cwd" not in payload:
        payload["cwd"] = project_dir
    hooks.event(payload)
    return 0


# -------------------------------------------------------------------- init
def _handle_init(args) -> int:
    ws = _dir(args)
    no_agent = bool(getattr(args, "no_agent", False))
    data = handlers.init(ws, no_agent=no_agent)
    output._finish("init", data, True, "ok", args, None)
    return 0


# --------------------------------------------------------------------- run
def _handle_run(args) -> int:
    """Run one shell command inside `args.workspace` and return the
    child's exit code UNCHANGED, so a caller can use a run's result as its
    own predicate -- the one verb the shared `_contract` envelope does not
    wrap, since wrapping it would swallow the exact exit code this verb
    promises to pass through."""
    ws = getattr(args, "workspace", None) or getattr(args, "dir", None) or os.getcwd()
    command = getattr(args, "command", None)
    if command is None:
        command = [getattr(args, "cmd", "")]
    cmd = command if isinstance(command, str) else " && ".join(command)

    rc = handlers.run(cmd, ws=ws)
    output._finish("run", {"command": cmd, "workspace": ws, "exit_code": rc},
                    rc == 0, "ok" if rc == 0 else "failed", args, None)
    return rc


# ------------------------------------------------------------------ verify
def _handle_verify(args) -> int:
    d = _dir(args)
    return _contract("verify", args, lambda: kernel.verify(d))


# ----------------------------------------------------------------- assess
def _handle_assess(args) -> int:
    d = _dir(args)
    mutants = getattr(args, "mutants", None)
    return _contract("assess", args, lambda: assess.assess(d, mutants=mutants))


# ---------------------------------------------------------------- rebuild
def _handle_rebuild(args) -> int:
    d = _dir(args)
    into = getattr(args, "into", None) or tempfile.mkdtemp(prefix="reticuli-rebuild-")
    producer = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    ws = getattr(args, "workspace", None)
    reuse = bool(getattr(args, "reuse", False))

    def fn():
        result = dict(registry.rebuild_chain(d, producer, into, ws=ws, reuse=reuse))
        result["into"] = into
        return result

    return _contract("rebuild", args, fn)


# ------------------------------------------------------------------- pull
def _handle_pull(args) -> int:
    src = getattr(args, "src", None)
    dest = getattr(args, "dest", None)

    def fn():
        if not src or not dest:
            raise kernel.ClaimError("pull requires a source and a destination")
        return registry.pull(src, dest)

    return _contract("pull", args, fn)


# ------------------------------------------------------------------- sign
def _handle_sign(args) -> int:
    d = _dir(args)
    key = getattr(args, "key", None)
    identity = getattr(args, "identity", None)
    ws = getattr(args, "workspace", None)

    def fn():
        if not key or not identity:
            raise kernel.ClaimError("sign requires --key and --identity")
        return attest.sign(d, key, identity, ws=ws)

    return _contract("sign", args, fn)


# ----------------------------------------------------------------- export
def _handle_export(args) -> int:
    d = _dir(args)
    tar_path = getattr(args, "out", None)
    blind = bool(getattr(args, "blind", False))

    def fn():
        if not tar_path:
            raise kernel.ClaimError("export requires --out")
        transfer.export(d, tar_path, blind=blind)
        return {"ok": True, "tar": tar_path, "blind": blind}

    return _contract("export", args, fn)


# ----------------------------------------------------------------- import
def _handle_import(args) -> int:
    tar_path = getattr(args, "tar", None)
    dest = getattr(args, "dest", None) or _dir(args)

    def fn():
        if not tar_path:
            raise kernel.ClaimError("import requires a tar path")
        return transfer.import_(tar_path, dest)

    return _contract("import", args, fn)


# ----------------------------------------------------------------- record
def _handle_record(args) -> int:
    d = _dir(args)
    path = getattr(args, "out", None) or os.path.join(d, "record.json")
    key = getattr(args, "key", None)

    def fn():
        doc = record.emit(d)
        record.write(doc, path)
        if key:
            record.sign(path, key)
        return {"ok": True, "path": path, "name": doc["name"], "root": doc["root"],
                "signed": bool(key)}

    return _contract("record", args, fn)


# ------------------------------------------------------------------- pack
def _dispatch_pack(args) -> int:
    """`pack`: seal a project directory as a claim. `--accept` names the
    gate output(s) to take as the earned verdict and finalize immediately
    (the folded `seal` verb) into `-o`/`--output`; given with no `-o`
    there is nowhere to seal the accepted claim, so this refuses in words
    with exit 2 before anything is built -- the one behavior this
    module's own gate pins directly."""
    path = _dir(args)
    name = getattr(args, "name", None)
    expected_root = getattr(args, "root", None)
    generated = getattr(args, "generated", None) or []
    gate = getattr(args, "gate", None)
    output_dir = getattr(args, "output", None)
    use_pytest = bool(getattr(args, "pytest", False))
    accept = getattr(args, "accept", None)
    into = getattr(args, "into", None)
    force = bool(getattr(args, "force", False))

    if accept and not output_dir:
        output._err("pack", "--accept needs -o/--output to know where to "
                             "seal the accepted claim")
        output._finish("pack", {"error": "--accept requires -o"}, False,
                        "error", args, None)
        return 2

    gate_output = accept[0] if accept else "gate"
    if use_pytest and not gate:
        gate = f"python3 -m pytest -q && printf ok > {gate_output}"

    def fn():
        if not name or not gate:
            raise kernel.ClaimError("pack requires --name and --gate")

        dest = output_dir or path
        if dest != path:
            if os.path.isdir(dest) and os.listdir(dest) and not force:
                raise kernel.ClaimError(
                    f"refused non-empty pack target: {dest!r} (use --force)")
            shutil.copytree(path, dest, dirs_exist_ok=True)
            work_dir = dest
        else:
            work_dir = path

        result = pack.pack(work_dir, name, generated, [], gate, gate_output)

        if expected_root and result["root"] != expected_root:
            raise kernel.ClaimError(
                f"pack sealed to {result['root']!r}, not the expected "
                f"{expected_root!r}")

        if into and into != work_dir:
            if os.path.isdir(into) and os.listdir(into) and not force:
                raise kernel.ClaimError(
                    f"refused non-empty pack destination: {into!r} (use --force)")
            shutil.copytree(work_dir, into, dirs_exist_ok=True)
            result = dict(result)
            result["into"] = into

        return result

    return _contract("pack", args, fn)


# ------------------------------------------------------------------ audit
def _dispatch_audit(args) -> int:
    """`audit`: re-earn every gate, cold -- the deep (whole-lineage) form
    by default (`registry.audit_deep`); `--shallow` opts out to the
    kernel's own single-claim audit (`spec/verification.md`)."""
    d = _dir(args)
    deep = not bool(getattr(args, "shallow", False))
    fn = (lambda: registry.audit_deep(d)) if deep else (lambda: kernel.audit(d))
    return _contract("audit", args, fn)


# ----------------------------------------------------------------- status
def _dispatch_status(args) -> int:
    """`status`: a claim's documented state (phase, gates, signatures,
    residue, the next ladder rung) -- or, with `--claims`/`--tree`/
    `--deps`, the registry-wide views over a workspace's store. A claim
    still in `draft` has no root or gate history yet, so it gets its own
    rendering rather than forcing a verdict that cannot exist until it is
    sealed."""
    d = _dir(args)
    as_json = bool(getattr(args, "json", False))

    if getattr(args, "claims", False):
        rows = registry.claims(d)
        if not as_json:
            text = render.table([[c["name"], render.short(c["root"]), c["phase"]]
                                  for c in rows])
            if text:
                output._line(args, text)
        output._finish("status", {"claims": rows}, True, "ok", args, None)
        return 0

    if getattr(args, "tree", False) or getattr(args, "deps", False):
        graph = registry.deps(d)
        if getattr(args, "tree", False):
            node = {}
            for c in graph.get("claims", []):
                children = [f"{dep['component']} ({dep['status']})"
                            for dep in c.get("depends_on", [])]
                node[c["name"]] = children or None
            if not as_json:
                text = render.tree(node)
                if text:
                    output._line(args, text)
        else:
            rows = [[c["name"], dep["component"], dep["status"]]
                    for c in graph.get("claims", []) for dep in c.get("depends_on", [])]
            if not as_json:
                text = render.table(rows)
                if text:
                    output._line(args, text)
        output._finish("status", graph, True, "ok", args, None)
        return 0

    if not os.path.isfile(os.path.join(d, kernel.MANIFEST)):
        try:
            files = statusview._files_claim(d)
        except kernel.ClaimError as e:
            output._err("status", str(e))
            output._finish("status", {"error": str(e)}, False, "error", args, None)
            return 1
        readiness = feedback.advise(d)
        data = {"phase": "draft", "files": files, "sealable": readiness["sealable"]}
        if not as_json:
            word = "sealable" if readiness["sealable"] else "not yet sealable"
            output._line(args, f"draft  ({len(files)} declared file(s), {word})")
        output._finish("status", data, True, "draft", args, None)
        return 0

    view = views._claim_view(d)
    if not as_json:
        text = (statusview._v_status_claim(d) if getattr(args, "verbose", False)
                else statusview._t_status_claim(d))
        output._line(args, text)
    output._finish("status", view, True, view.get("phase") or "ok", args, view.get("root"))
    return 0


# -------------------------------------------------------------- crosscheck
def _dispatch_crosscheck(args) -> int:
    """`crosscheck`: the three-machine test, folded with the deep audit on
    every directory leg (`registry.crosscheck_deep`) so a forged ancestor
    cannot hide behind an honest parent. Each of M2/M3 may be a claim
    directory or a signed record (`spec/record.md`); the lower layer mixes
    the two transports freely."""
    d = _dir(args)
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    mutants = getattr(args, "mutants", None)

    def fn():
        if not m2 or not m3:
            raise kernel.ClaimError(
                "crosscheck requires a second and third machine (--m2, --m3)")
        return registry.crosscheck_deep(d, m2, m3, mutants=mutants)

    return _contract("crosscheck", args, fn)


# -------------------------------------------------------------------- argv
def _add_common(sub) -> None:
    sub.add_argument("--json", action="store_true",
                      help="print the machine-readable envelope instead of a human summary")
    sub.add_argument("--verbose", "-v", action="store_true",
                      help="show extra detail in human-readable mode")
    sub.add_argument("--color", choices=("auto", "always", "never"), default="auto",
                      help="colorize human-mode output (default: auto)")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ret", description="Reticuli records and reproduces software claims.")
    p.add_argument("--version", action="store_true", help="print the version and exit")
    sub = p.add_subparsers(dest="verb", metavar="<command>")

    s = sub.add_parser("help", help=_FULL_HELP["help"])
    s.add_argument("topic", nargs="?", help="a command to show detailed help for")
    s.add_argument("-a", "--all", action="store_true",
                    help="list everything, including plumbing verbs")

    s = sub.add_parser("completion", help=_FULL_HELP["completion"])
    s.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    s = sub.add_parser("hook", help=_FULL_HELP["hook"])
    s.add_argument("--project-dir", help="the project to wire the handshake into (default: cwd)")

    s = sub.add_parser("init", help=_FULL_HELP["init"])
    s.add_argument("path", nargs="?", default=".", help="the workspace directory (default: .)")
    s.add_argument("--no-agent", action="store_true",
                    help="withhold the coding-agent handshake")
    _add_common(s)

    s = sub.add_parser("run", help=_FULL_HELP["run"])
    s.add_argument("command", nargs="+", help="the shell command to run and observe")
    s.add_argument("--workspace", "-w", help="the workspace to run inside (default: cwd)")
    _add_common(s)

    s = sub.add_parser("verify", help=_FULL_HELP["verify"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    _add_common(s)

    s = sub.add_parser("assess", help=_FULL_HELP["assess"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--mutants", type=int, help="how many deterministic mutants to draw")
    _add_common(s)

    s = sub.add_parser("rebuild", help=_FULL_HELP["rebuild"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--into", help="the room to regrow into (default: a fresh scratch directory)")
    s.add_argument("--producer", help="the producer to regrow with (default: $RETICULI_PRODUCER)")
    s.add_argument("--workspace", help="a session workspace whose trace guides the producer")
    s.add_argument("--reuse", action="store_true", help="resume into a non-empty target")
    _add_common(s)

    s = sub.add_parser("pull", help=_FULL_HELP["pull"])
    s.add_argument("src", help="the claim to add as a dependency")
    s.add_argument("dest", help="the workspace to add it into")
    _add_common(s)

    s = sub.add_parser("sign", help=_FULL_HELP["sign"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--key", help="an ssh private key to sign the root with")
    s.add_argument("--identity", help="the identity to sign as")
    s.add_argument("--workspace", help="a session workspace to record the signature under")
    _add_common(s)

    s = sub.add_parser("export", help=_FULL_HELP["export"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--out", help="the archive path to write")
    s.add_argument("--blind", action="store_true", help="exclude generated bytes from the archive")
    _add_common(s)

    s = sub.add_parser("import", help=_FULL_HELP["import"])
    s.add_argument("tar", help="the archive to restore")
    s.add_argument("dest", nargs="?", help="where to restore it (default: cwd)")
    _add_common(s)

    s = sub.add_parser("record", help=_FULL_HELP["record"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--out", help="the record path to write (default: <path>/record.json)")
    s.add_argument("--key", help="an ssh private key to sign the record with")
    _add_common(s)

    s = sub.add_parser("pack", help=_FULL_HELP["pack"])
    s.add_argument("path", nargs="?", default=".", help="the project directory (default: .)")
    s.add_argument("--name", help="the claim's name")
    s.add_argument("--root", help="assert the sealed claim recomputes exactly this root")
    s.add_argument("--generated", action="append", help="a generated (regrowable) output pattern; repeatable")
    s.add_argument("--gate", help="the gate command")
    s.add_argument("--output", "-o", help="where to seal an accepted claim (default: --path in place)")
    s.add_argument("--pytest", action="store_true", help="sugar: the gate is a pytest run")
    s.add_argument("--accept", nargs="+", help="gate output name(s) to accept as the earned verdict")
    s.add_argument("--into", help="also copy the sealed claim here")
    s.add_argument("--force", action="store_true", help="overwrite a non-empty --output/--into target")
    _add_common(s)

    s = sub.add_parser("audit", help=_FULL_HELP["audit"])
    s.add_argument("path", nargs="?", default=".", help="the claim directory (default: .)")
    s.add_argument("--shallow", action="store_true", help="opt out of the recursive deep audit")
    _add_common(s)

    s = sub.add_parser("status", help=_FULL_HELP["status"])
    s.add_argument("path", nargs="?", default=".", help="the claim/workspace directory (default: .)")
    s.add_argument("--tree", action="store_true", help="show the dependency DAG")
    s.add_argument("--claims", action="store_true", help="list every sealed claim")
    s.add_argument("--deps", action="store_true", help="show the flat dependency report")
    _add_common(s)

    s = sub.add_parser("crosscheck", help=_FULL_HELP["crosscheck"])
    s.add_argument("path", nargs="?", default=".", help="M1, the original claim directory (default: .)")
    s.add_argument("--m2", help="M2: a transfer leg (a claim directory or a record)")
    s.add_argument("--m3", help="M3: an independent-rebuild leg (a claim directory or a record)")
    s.add_argument("--mutants", type=int, help="how many deterministic mutants M3 must re-earn")
    _add_common(s)

    return p


_ROUTE = {
    "help": _handle_help, "completion": _handle_completion, "hook": _handle_hook,
    "init": _handle_init, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import, "pack": _dispatch_pack, "audit": _dispatch_audit,
    "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        print(handlers._version_line())
        return 0
    if not getattr(args, "verb", None):
        parser.print_help()
        return 0

    fn = _ROUTE.get(args.verb)
    if fn is None:
        output._err("ret", f"no such command: {args.verb!r}")
        return 2
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())

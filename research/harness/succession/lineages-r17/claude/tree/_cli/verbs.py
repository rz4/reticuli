"""The verb handlers (`spec/layers.md`: surface, `_cli/verbs.py`).

Each porcelain verb (`_cli/parser.py`'s `PORCELAIN`) has one `_handle_*`
function here, except the four whose behavior is actually a small choice
among several lower-layer calls (`pack`, `audit`, `status`, `crosscheck`),
which get a `_dispatch_*` instead. Every one of these takes the parsed
`argparse.Namespace` and returns the process exit code: `0` on success,
`1` on a refusal the claim itself raised (`kernel.ClaimError`), `2` on a
usage error caught before anything is built or run. `main()` builds the
argument grammar on top of `_cli/parser.py`'s verb/alias table and routes
to these functions.

No handler here does its own judging or filesystem work beyond what the
layer it calls already does -- `kernel`, `registry`, `attest`, `transfer`,
`pack`, `record`, `assess`, `heldout`, `hooks`, `handlers` do the work;
`report`/`statusview`/`views`/`output` render the result and close the verb
out through the shared `--json` envelope / one-voice-error contract.

Stdlib only.
"""
import json
import os
import shlex
import sys

from reticuli import assess, attest, registry, transfer, heldout, hooks, kernel
from reticuli import feedback
from reticuli import pack as pack_mod
from reticuli import record as record_mod
from reticuli._cli import handlers, output, parser, report, statusview, views


# =============================================================================
# small shared helpers
# =============================================================================

def _kv_pairs(items) -> dict:
    """`["k=v", ...]` -> `{"k": "v", ...}`; `{}` for `None`/empty."""
    out = {}
    for item in items or []:
        key, _, value = item.partition("=")
        out[key] = value
    return out


def _join_command(command) -> str:
    """A `run`/`rebuild` command argument as one shell string: already a
    string, or the words of a captured argv joined with spaces."""
    if isinstance(command, str):
        return command
    return " ".join(command)


# =============================================================================
# handlers: one verb, one lower-layer call
# =============================================================================

def _handle_help(args) -> int:
    """`ret help [topic|-a]`, or `ret -h`'s own text with no topic given."""
    if getattr(args, "all", False):
        parser._help_all()
    elif getattr(args, "topic", None):
        parser._help_topic(args.topic)
    else:
        top, _sub = parser._parser()
        top.print_help()
    return 0


def _handle_init(args) -> int:
    """`ret init [workspace]`: mark a workspace, wire the agent hook."""
    result = handlers.init(args.workspace, no_agent=getattr(args, "no_agent", False))
    return 0 if report._r_init(args, result) else 1


def _handle_completion(args) -> int:
    """`ret completion [shell]`: print a shell completion script."""
    try:
        parser._completion(getattr(args, "shell", None) or "bash")
    except ValueError as e:
        output._err("completion", str(e))
        return 2
    return 0


def _handle_hook(args) -> int:
    """`ret hook`: one Claude Code hook payload on stdin -> one traced event."""
    payload = json.load(sys.stdin)
    hooks.event(payload)
    return 0


def _handle_run(args) -> int:
    """`ret run -- <command>`: the child's exit code, unchanged."""
    cmd = _join_command(args.command)
    return handlers.run(cmd, args.workspace)


def _handle_verify(args) -> int:
    """`ret verify [path]`: identity only, no gate run."""
    try:
        result = kernel.verify(args.path)
    except kernel.ClaimError as e:
        output._err("verify", str(e))
        return 1
    return 0 if report._r_verify(args, result) else 1


def _handle_assess(args) -> int:
    """`ret assess [path]`: mutation-coverage measurement."""
    try:
        result = assess.assess(args.path, mutants=getattr(args, "mutants", None))
    except kernel.ClaimError as e:
        output._err("assess", str(e))
        return 1
    return 0 if report._r_assess(args, result) else 1


def _handle_rebuild(args) -> int:
    """`ret rebuild <path> <producer> <into>`: regrow until the gates pass.

    `--blind` measures what the criteria alone carry (`heldout.held_out`,
    guidance withheld); `--deep` walks a composed claim's whole DAG
    (`registry.rebuild_chain`); plain `rebuild` is `kernel.rebuild`.
    """
    produce_from = _kv_pairs(getattr(args, "produce_from", None)) or None
    input_from = _kv_pairs(getattr(args, "input_from", None)) or None
    producer_env = _kv_pairs(getattr(args, "env", None)) or None
    guidance = not getattr(args, "without_guidance", False)

    try:
        if getattr(args, "blind", False):
            result = heldout.held_out(
                args.path, args.producer, args.into,
                produce_from=produce_from, input_from=input_from,
                producer_env=producer_env)
        elif getattr(args, "deep", False):
            result = registry.rebuild_chain(
                args.path, args.producer, args.into,
                reuse=getattr(args, "reuse", False), guidance=guidance,
                input_from=input_from, producer_env=producer_env)
        else:
            result = kernel.rebuild(
                args.path, args.producer, args.into, guidance=guidance,
                produce_from=produce_from, input_from=input_from,
                producer_env=producer_env)
    except kernel.ClaimError as e:
        output._err("rebuild", str(e))
        return 1
    return 0 if report._r_rebuild(args, result) else 1


def _handle_pull(args) -> int:
    """`ret pull <path> --into <ws>`: materialize a plain dependency."""
    try:
        result = registry.pull(args.path, args.into)
    except kernel.ClaimError as e:
        output._err("pull", str(e))
        return 1
    return 0 if report._r_pull(args, result) else 1


def _handle_sign(args) -> int:
    """`ret sign <path>`: the authorization ceremony, or `--check` its read-back."""
    try:
        if getattr(args, "check", False):
            result = attest.sign_check(
                args.path, ws=getattr(args, "workspace", None),
                signers=getattr(args, "signers", None))
            return 0 if report._r_sign_check(args, result) else 1
        result = attest.sign(
            args.path, args.key, args.identity, ws=getattr(args, "workspace", None))
    except kernel.ClaimError as e:
        output._err("sign", str(e))
        return 1
    return 0 if report._r_sign(args, result) else 1


def _handle_export(args) -> int:
    """`ret export <path> -o <tar>`: a deterministic archive of declared content."""
    try:
        transfer.export(args.path, args.output, blind=getattr(args, "blind", False))
    except kernel.ClaimError as e:
        output._err("export", str(e))
        return 1
    return 0 if report._r_export(args, {"ok": True, "path": args.output}) else 1


def _handle_import(args) -> int:
    """`ret import <archive> --into <dest>`: extract, then verify identity."""
    try:
        result = transfer.import_(args.archive, args.into)
    except kernel.ClaimError as e:
        output._err("import", str(e))
        return 1
    return 0 if report._r_import(args, result) else 1


def _handle_record(args) -> int:
    """`ret record [path] [-o out] [--key k]`: earn and state a signed record."""
    try:
        doc = record_mod.emit(args.path)
    except kernel.ClaimError as e:
        output._err("record", str(e))
        return 1
    out_path = getattr(args, "output", None)
    if out_path:
        record_mod.write(doc, out_path)
        if getattr(args, "key", None):
            record_mod.sign(out_path, args.key)
    return 0 if report._r_record(args, doc) else 1


# =============================================================================
# dispatches: a verb whose behavior is a small choice among lower-layer calls
# =============================================================================

def _dispatch_pack(args) -> int:
    """`ret pack [path]`: write a recipe into `path` and seal it in place.

    The gate command comes from exactly one of `--gate CMD` (verbatim),
    `--pytest [target]` (a pytest shorthand), or `--accept FILE...`
    (acceptance scripts, which also become pinned inputs) -- and every one
    of them needs `-o/--output` to name the gate's verdict file; pack never
    guesses that name. Refuses in words, before anything is built, if none
    of the three is given, or if `-o` is missing.
    """
    command = "pack"
    accept = list(args.accept or [])
    gate_cmd = args.gate
    use_pytest = bool(args.pytest)

    if not (accept or use_pytest or gate_cmd):
        output._err(command, "nothing to run: give --gate, --pytest, or --accept")
        return 2
    if not args.output:
        output._err(command,
                     "-o/--output is required to name the gate's verdict file")
        return 2

    path = args.path or "."
    name = args.name or os.path.basename(os.path.abspath(path))
    output_name = args.output

    if gate_cmd:
        run_cmd = gate_cmd
        inputs = []
    elif accept:
        checks = " && ".join(f"python3 {shlex.quote(a)}" for a in accept)
        run_cmd = f"{checks} && printf ok > {shlex.quote(output_name)}"
        inputs = list(accept)
    else:
        target = args.pytest if isinstance(args.pytest, str) else ""
        prefix = f"python3 -m pytest -q {target}".rstrip()
        run_cmd = f"{prefix} && printf ok > {shlex.quote(output_name)}"
        inputs = []

    if os.path.isfile(os.path.join(path, kernel.RECIPE)) and not args.force:
        output._err(command,
                     f"a claim already exists at {path!r}; use --force to overwrite")
        return 1

    try:
        result = pack_mod.pack(path, name, generated=args.generated or [],
                                inputs=inputs, gate=run_cmd, gate_output=output_name)
    except kernel.ClaimError as e:
        output._err(command, str(e))
        return 1
    return 0 if report._r_pack(args, result) else 1


def _dispatch_audit(args) -> int:
    """`ret audit [path]`: re-earn every gate; `--deep` walks a composed DAG."""
    if getattr(args, "deep", False):
        result = registry.audit_deep(args.path)
        result.setdefault("verdict", "accept" if result["ok"] else "reject")
        result.setdefault("gates", [])
    else:
        result = kernel.audit(args.path)
    return 0 if report._r_audit(args, result) else 1


def _dispatch_status(args) -> int:
    """`ret status [path]`: a sealed claim's state, a draft's sealability
    probe (`--draft`), or the workspace's claims as a table, tree, or
    dependency listing (`--tree`/`--deps`/`--structure`)."""
    path = getattr(args, "path", None) or "."

    if getattr(args, "draft", False):
        result = feedback.advise(path)
        return 0 if statusview._r_status_draft(args, result) else 1
    if getattr(args, "deps", False):
        statusview._r_deps(args, registry.deps(path))
        return 0
    if getattr(args, "structure", False):
        statusview._r_structure(args, registry.deps(path))
        return 0
    if getattr(args, "tree", False):
        statusview._r_tree(args, registry.claims(path))
        return 0

    if os.path.isfile(os.path.join(path, kernel.MANIFEST)):
        view = views._claim_view(path)
        text = (statusview._v_status_claim(view) if getattr(args, "verbose", False)
                else statusview._t_status_claim(view))
        ok = view.get("verified") is not False
        output._finish("status", view, ok, view.get("phase", ""), args)
        output._line(args, text)
        output._line(args, statusview._ledger_status_claim(path))
        return 0 if ok else 1

    statusview._r_claims(args, registry.claims(path))
    return 0


def _dispatch_crosscheck(args) -> int:
    """`ret crosscheck <m1> <m2> <m3>`: the three-machine test, over
    directories or frozen records; `--deep` walks each leg's whole DAG;
    `--record` also seals the proof onto M1 when it is satisfied."""
    try:
        if getattr(args, "record", False):
            proof = kernel.record_proof(args.m1, args.m2, args.m3)
            result = proof["crosscheck"]
        elif getattr(args, "deep", False):
            result = registry.crosscheck_deep(args.m1, args.m2, args.m3)
        else:
            result = kernel.crosscheck(
                args.m1, args.m2, args.m3, mutants=getattr(args, "mutants", None))
    except kernel.ClaimError as e:
        output._err("crosscheck", str(e))
        return 1
    return 0 if report._r_crosscheck(args, result) else 1


# =============================================================================
# main: the argument grammar, built on `_cli/parser.py`'s verb/alias table
# =============================================================================

_HANDLERS = {
    "help": _handle_help,
    "init": _handle_init,
    "completion": _handle_completion,
    "hook": _handle_hook,
    "run": _handle_run,
    "verify": _handle_verify,
    "assess": _handle_assess,
    "rebuild": _handle_rebuild,
    "pull": _handle_pull,
    "sign": _handle_sign,
    "export": _handle_export,
    "record": _handle_record,
    "import": _handle_import,
}
_DISPATCHES = {
    "pack": _dispatch_pack,
    "audit": _dispatch_audit,
    "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def _build_parser():
    """`_cli/parser.py`'s verb/alias grammar, with each verb's own arguments
    added onto its subparser."""
    top, sub = parser._parser()
    choices = sub.choices

    choices["init"].add_argument("workspace", nargs="?", default=".")
    choices["init"].add_argument("--no-agent", dest="no_agent", action="store_true")

    run_p = choices["run"]
    run_p.add_argument("command", nargs="+")
    run_p.add_argument("--workspace", default=".")

    choices["verify"].add_argument("path", nargs="?", default=".")

    assess_p = choices["assess"]
    assess_p.add_argument("path", nargs="?", default=".")
    assess_p.add_argument("--mutants", type=int, default=None)

    rebuild_p = choices["rebuild"]
    rebuild_p.add_argument("path", nargs="?", default=".")
    rebuild_p.add_argument("producer")
    rebuild_p.add_argument("into")
    rebuild_p.add_argument("--without-guidance", action="store_true")
    rebuild_p.add_argument("--blind", action="store_true")
    rebuild_p.add_argument("--deep", action="store_true")
    rebuild_p.add_argument("--reuse", action="store_true")
    rebuild_p.add_argument("--produce-from", dest="produce_from", action="append")
    rebuild_p.add_argument("--input-from", dest="input_from", action="append")
    rebuild_p.add_argument("--env", action="append")

    pull_p = choices["pull"]
    pull_p.add_argument("path", nargs="?", default=".")
    pull_p.add_argument("--into", required=True)

    sign_p = choices["sign"]
    sign_p.add_argument("path", nargs="?", default=".")
    sign_p.add_argument("--key")
    sign_p.add_argument("--identity")
    sign_p.add_argument("--check", action="store_true")
    sign_p.add_argument("--signers")
    sign_p.add_argument("--workspace")

    export_p = choices["export"]
    export_p.add_argument("path", nargs="?", default=".")
    export_p.add_argument("-o", "--output", required=True)
    export_p.add_argument("--blind", action="store_true")

    import_p = choices["import"]
    import_p.add_argument("archive")
    import_p.add_argument("--into", required=True)

    record_p = choices["record"]
    record_p.add_argument("path", nargs="?", default=".")
    record_p.add_argument("-o", "--output")
    record_p.add_argument("--key")

    pack_p = choices["pack"]
    pack_p.add_argument("path", nargs="?", default=".")
    pack_p.add_argument("--name")
    pack_p.add_argument("--root")
    pack_p.add_argument("--generated", action="append")
    pack_p.add_argument("--gate")
    pack_p.add_argument("-o", "--output")
    pack_p.add_argument("--pytest", nargs="?", const=True, default=None)
    pack_p.add_argument("--accept", action="append")
    pack_p.add_argument("--into")
    pack_p.add_argument("--force", action="store_true")

    audit_p = choices["audit"]
    audit_p.add_argument("path", nargs="?", default=".")
    audit_p.add_argument("--deep", action="store_true")

    status_p = choices["status"]
    status_p.add_argument("path", nargs="?", default=".")
    status_p.add_argument("--tree", action="store_true")
    status_p.add_argument("--deps", action="store_true")
    status_p.add_argument("--structure", action="store_true")
    status_p.add_argument("--draft", action="store_true")

    crosscheck_p = choices["crosscheck"]
    crosscheck_p.add_argument("m1")
    crosscheck_p.add_argument("m2")
    crosscheck_p.add_argument("m3")
    crosscheck_p.add_argument("--deep", action="store_true")
    crosscheck_p.add_argument("--record", action="store_true")
    crosscheck_p.add_argument("--mutants", type=int, default=None)

    choices["completion"].add_argument("shell", nargs="?", default="bash")
    choices["help"].add_argument("topic", nargs="?", default=None)
    choices["help"].add_argument("-a", "--all", action="store_true")

    return top, sub


def main(argv=None) -> int:
    """Parse `argv` (default `sys.argv[1:]`) and run the named verb."""
    top, _sub = _build_parser()
    args = top.parse_args(argv)

    if not args.verb:
        top.print_help()
        return 2

    canon = parser.ALIASES.get(args.verb, args.verb)
    func = _HANDLERS.get(canon) or _DISPATCHES.get(canon)
    if func is None:
        output._err("ret", f"unknown command {args.verb!r}")
        return 2

    try:
        return func(args)
    except kernel.ClaimError as e:
        output._err(canon, str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())

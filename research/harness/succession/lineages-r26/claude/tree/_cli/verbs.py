"""The verb handlers and composite dispatches -- see `spec/layers.md`.

Every `ret <verb>` the parser can produce ends up here as one function
taking the parsed `argparse.Namespace` and returning the process's exit
code. A plain `_handle_*` is a thin translation of one verb onto its
business logic in `reticuli._cli.handlers` (or, for `assess`/`record`,
onto `reticuli.assess`/`reticuli.record` directly -- neither has a
`handlers.py` wrapper because neither needs session/producer plumbing).
A `_dispatch_*` is a verb whose CLI-level behavior is more than a single
call: `pack` validates its own invocation before touching disk, `status`
picks among four different views by which flag was given, and `audit`/
`crosscheck` compose a chain's dependencies by default, with `--shallow`
the explicit, honest opt-down to a claim's own gates alone.

Every refusal speaks through `output._err` (`ret: <verb>: <fact>`, to
stderr) and returns a non-zero code: 2 for a usage error caught before
anything was built or spent, 1 for a refusal business logic itself
raised. `run` is the one handler whose return value is not a verdict:
it is the child process's own exit code, unchanged, so a session can use
it as a predicate.

Reaches only `reticuli.kernel`'s pinned public surface, `reticuli.assess`/
`reticuli.record`'s own public functions, and this package's own
`handlers`/`output`/`report`/`statusview`/`parser` modules -- never a
`reticuli._kernel` private. Stdlib only.
"""
import json
import os
import sys

from reticuli import assess as _assess
from reticuli import kernel
from reticuli import record as _record
from . import handlers as _handlers
from . import output as _output
from . import parser as _parser
from . import report as _report
from . import statusview as _statusview


def _usage(verb: str, message: str) -> int:
    """A usage error: the one-voice refusal, to stderr, exit code 2."""
    _output._err(verb, message)
    return 2


def _status_ok(view: dict) -> bool:
    """Whether a status view's claim holds -- a draft is never broken;
    anything sealed or signed must have its identity hold."""
    if view.get("phase", "draft") == "draft":
        return True
    return bool((view.get("verified") or {}).get("ok"))


def _kv_dict(pairs) -> dict:
    """Every `KEY=VALUE` string in `pairs`, parsed into a dict -- an
    entry with no `=` is dropped rather than raising; the grammar that
    collects these is free to validate the shape, this is just the read."""
    out = {}
    for item in pairs or []:
        if "=" in item:
            key, value = item.split("=", 1)
            out[key] = value
    return out


# ==============================================================================
# plain handlers: one verb, one call into the business logic beneath
# ==============================================================================


def _handle_help(args) -> int:
    """`help [topic] [-a]`: one command's own usage, or the grouped
    overview with every accepted older spelling."""
    topic = getattr(args, "topic", None)
    if not topic:
        _parser._help_all()
        return 0
    _, subparsers = _parser._parser()
    if topic not in subparsers and topic not in _parser._FULL_HELP:
        _parser._help_topic(topic)
        return 1
    _parser._help_topic(topic)
    return 0


def _handle_init(args) -> int:
    """`init [ws] [--name NAME] [--no-agent]`."""
    ws = getattr(args, "ws", None) or "."
    name = getattr(args, "name", None)
    no_agent = getattr(args, "no_agent", False)
    try:
        data = _handlers.init(ws, name, no_agent=no_agent)
    except kernel.ClaimError as e:
        _output._err("init", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("init", data, True, "initialized", args)
    else:
        print(_report._r_init(data))
    return 0


def _handle_completion(args) -> int:
    """`completion [shell]`: a completion script generated from the live
    grammar, so it can never drift from what was actually registered."""
    shell = getattr(args, "shell", None) or "bash"
    try:
        _parser._completion(shell)
    except ValueError as e:
        _output._err("completion", str(e))
        return 2
    return 0


def _handle_hook(args) -> int:
    """`hook [payload]`: one agent-handshake payload, mapped to a trace
    event -- the payload defaults to stdin, the old pipe-a-JSON-blob
    convention the agent side's own handshake uses."""
    raw = getattr(args, "payload", None)
    if raw is None:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as e:
        _output._err("hook", f"invalid JSON payload: {e}")
        return 2
    try:
        entry = _handlers.hook(payload)
    except kernel.ClaimError as e:
        _output._err("hook", str(e))
        return 1
    print(json.dumps(entry))
    return 0


def _handle_run(args) -> int:
    """`run CMD [--ws WS]`: a traced command, returning the child's own
    exit code UNCHANGED -- the predicate contract every caller depends
    on. Accepts either a single command string (`cmd`/`ws`) or a
    pre-split argv (`command`/`workspace`)."""
    command = getattr(args, "command", None)
    if command is None:
        command = getattr(args, "cmd", None)
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    ws = getattr(args, "workspace", None)
    if ws is None:
        ws = getattr(args, "ws", None) or "."
    return _handlers.run(command, ws)


def _handle_verify(args) -> int:
    """`verify [d]`: identity only, no gate runs."""
    d = getattr(args, "d", None) or getattr(args, "claim", None) or "."
    try:
        data = _handlers.verify(d)
    except kernel.ClaimError as e:
        _output._err("verify", str(e))
        return 1
    ok = bool(data.get("ok"))
    if getattr(args, "json", False):
        _output._finish("verify", data, ok, "ok" if ok else "broken", args)
    else:
        print(_report._r_verify(data))
    return 0 if ok else 1


def _handle_assess(args) -> int:
    """`assess [d] [--mutants N]`: how much of the claim's generated
    output the gates actually interrogate, by mutation testing."""
    d = getattr(args, "d", None) or getattr(args, "claim", None) or "."
    mutants = getattr(args, "mutants", None)
    if mutants is None:
        mutants = 50
    try:
        data = _assess.assess(d, mutants=mutants)
    except kernel.ClaimError as e:
        _output._err("assess", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("assess", data, True, "assessed", args)
    else:
        print(_report._r_assess(data))
    return 0


def _handle_rebuild(args) -> int:
    """`rebuild d PRODUCER INTO [--produce-from ...] [--input-from ...]
    [--without-guidance]`: the producer-preflighted regrow."""
    d = getattr(args, "d", None)
    producer = getattr(args, "producer", None)
    into = getattr(args, "into", None)
    produce_from = _kv_dict(getattr(args, "produce_from", None))
    input_from = _kv_dict(getattr(args, "input_from", None))
    guidance = not getattr(args, "without_guidance", False)
    try:
        data = _handlers.rebuild(d, producer, into, produce_from=produce_from,
                                  input_from=input_from, guidance=guidance)
    except kernel.ClaimError as e:
        _output._err("rebuild", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("rebuild", data, True, "rebuilt", args)
    else:
        print(_report._r_rebuild(data))
    return 0


def _handle_pull(args) -> int:
    """`pull SRC DEST [--ws WS]`: a claim becomes a dependency, whole
    closure included, in one copy."""
    src = getattr(args, "src", None)
    dest = getattr(args, "dest", None)
    ws = getattr(args, "ws", None)
    try:
        data = _handlers.pull(src, dest, ws=ws)
    except kernel.ClaimError as e:
        _output._err("pull", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("pull", data, True, "pulled", args)
    else:
        print(_report._r_pull(data))
    return 0


def _handle_sign(args) -> int:
    """`sign d --key KEY --principal PRINCIPAL [--ws WS]`: the signing
    ceremony -- accountable authorization over the claim's whole chain."""
    d = getattr(args, "d", None)
    key = getattr(args, "key", None)
    principal = getattr(args, "principal", None)
    ws = getattr(args, "ws", None)
    try:
        data = _handlers.sign(d, key, principal, ws=ws)
    except kernel.ClaimError as e:
        _output._err("sign", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("sign", data, True, "signed", args)
    else:
        print(_report._r_sign(data))
    return 0


def _handle_export(args) -> int:
    """`export d path [--blind]`: a portable, byte-deterministic archive
    of the claim's declared content."""
    d = getattr(args, "d", None)
    tar_path = getattr(args, "tar_path", None) or getattr(args, "path", None)
    blind = getattr(args, "blind", False)
    try:
        data = _handlers.export(d, tar_path, blind=blind)
    except kernel.ClaimError as e:
        _output._err("export", str(e))
        return 1
    if getattr(args, "json", False):
        _output._finish("export", data, True, "exported", args)
    else:
        print(_report._r_export(data))
    return 0


def _handle_record(args) -> int:
    """`record [d] [--out PATH] [--key KEY --as PRINCIPAL] [--check]
    [--signers PATH]`: write a signed statement of this machine's
    results; `--key`/`--as` fold the old `attest` verb's job in as the
    signing step, `--check` verifies an existing one instead of writing."""
    d = getattr(args, "d", None) or "."
    out = getattr(args, "out", None)
    key = getattr(args, "key", None)
    principal = getattr(args, "as_", None) or getattr(args, "as", None)
    check = getattr(args, "check", False)
    signers = getattr(args, "signers", None)
    path = out or os.path.join(d, "record.json")

    try:
        if check:
            doc = _record.read(path)
            ok = True
            if signers:
                ok = _record.signer(path, signers) is not None
            data = {"ok": ok, "root": doc.get("root")}
            status = "checked"
        elif key and principal:
            data = dict(_handlers.attest(d, key, principal))
            data.setdefault("ok", True)
            status = "attested"
        else:
            doc = _record.emit(d)
            _record.write(doc, path)
            data = {"name": doc.get("name"), "root": doc.get("root"),
                     "build_digest": doc.get("build_digest"), "when": doc.get("when"),
                     "gates": doc.get("gates"), "path": path}
            status = "recorded"
    except kernel.ClaimError as e:
        _output._err("record", str(e))
        return 1

    ok = bool(data.get("ok", True))
    if getattr(args, "json", False):
        _output._finish("record", data, ok, status, args)
    elif check:
        print(_report._row("ok", data.get("ok")))
    elif key and principal:
        print(_report._r_attest(data))
    else:
        print(_report._r_record(data))
    return 0 if ok else 1


def _handle_import(args) -> int:
    """`import path dest`: extract and reverify -- identity, not trust,
    is what travels."""
    tar_path = getattr(args, "tar_path", None) or getattr(args, "path", None)
    dest = getattr(args, "dest", None)
    try:
        data = _handlers.import_(tar_path, dest)
    except kernel.ClaimError as e:
        _output._err("import", str(e))
        return 1
    ok = bool(data.get("ok", True))
    if getattr(args, "json", False):
        _output._finish("import", data, ok, "imported" if ok else "failed", args)
    else:
        print(_report._r_import(data))
    return 0 if ok else 1


# ==============================================================================
# dispatches: a verb whose CLI-level behavior is more than one call
# ==============================================================================


def _dispatch_pack(args) -> int:
    """`pack [path] --name NAME ... [--accept] [-o OUTPUT]`: turn a
    project directory into a sealed claim in place. `--accept` seals an
    already-authored recipe (the old `seal` verb's job) without
    expanding any new generated/input patterns -- and REQUIRES `-o` to
    name the gate output being accepted, refused in words, with exit 2,
    before anything is built."""
    accept = getattr(args, "accept", None)
    output = getattr(args, "output", None) or getattr(args, "gate_output", None)
    if accept and not output:
        return _usage("pack", "--accept needs -o/--output naming the gate output to accept")

    path = getattr(args, "path", None) or "."
    name = getattr(args, "name", None)
    gate = getattr(args, "gate", None)
    if getattr(args, "pytest", False) and not gate:
        gate = "python3 -m pytest"
    expected_root = getattr(args, "root", None)
    force = getattr(args, "force", False)

    recipe_path = os.path.join(path, kernel.RECIPE)
    if not accept and not force and os.path.isfile(recipe_path):
        return _usage("pack", f"{recipe_path!r} already exists; pass --force to overwrite "
                               "or --accept to seal it as-is")

    try:
        if accept:
            manifest = kernel.seal(path)
            data = {"ok": True, "name": manifest.get("name"), "root": manifest.get("root")}
        else:
            if not name:
                return _usage("pack", "pack needs --name")
            if not gate or not output:
                return _usage("pack", "pack needs --gate and -o/--output")
            generated = list(getattr(args, "generated", None) or [])
            inputs = list(getattr(args, "inputs", None) or [])
            data = dict(_handlers.pack(path, name, generated, inputs, gate, output))
            data.setdefault("ok", True)
        if expected_root and data.get("root") != expected_root:
            raise kernel.ClaimError(
                f"pack: sealed root {data.get('root')} does not match expected {expected_root}")
    except kernel.ClaimError as e:
        _output._err("pack", str(e))
        return 1

    ok = bool(data.get("ok", True))
    if getattr(args, "json", False):
        _output._finish("pack", data, ok, "sealed", args)
    else:
        print(_report._r_pack(data))
    return 0 if ok else 1


def _dispatch_status(args) -> int:
    """`status [d] [--workspace] [--tree] [--claims] [-v]`: one claim's
    full state, every claim a workspace holds, a claim's declared files,
    or a workspace's sealed-claims table -- four views, one verb."""
    d = getattr(args, "d", None) or getattr(args, "claim", None) or "."
    as_json = getattr(args, "json", False)
    try:
        if getattr(args, "claims", False):
            data = {"claims": _handlers.claims(d)}
            if as_json:
                _output._finish("status", data, True, "claims", args)
            else:
                print(_statusview._r_claims(d))
            return 0

        if getattr(args, "tree", False):
            data = {"files": _handlers.tree(d)}
            if as_json:
                _output._finish("status", data, True, "tree", args)
            else:
                print(_statusview._r_tree(d))
            return 0

        if getattr(args, "workspace", False):
            data = _handlers.status(d, workspace=True)
            ok = all(_status_ok(v) for v in data.get("claims", []))
            if as_json:
                _output._finish("status", data, ok, "workspace", args)
            else:
                for view in data.get("claims", []):
                    print(_statusview._t_status_claim(view))
            return 0 if ok else 1

        view = _handlers.status(d)
        ok = _status_ok(view)
        if as_json:
            _output._finish("status", view, ok, view.get("phase", "draft"), args)
        elif getattr(args, "verbose", False):
            print(_statusview._v_status_claim(view, d))
        else:
            print(_statusview._t_status_claim(view))
        return 0 if ok else 1
    except kernel.ClaimError as e:
        _output._err("status", str(e))
        return 1


def _dispatch_audit(args) -> int:
    """`audit [d] [--shallow]`: re-execute every gate, cold and
    sandboxed. Composed claims audit recursively UNLESS `--shallow`
    opts down to the claim's own gates alone -- the deep form is the
    default because a verdict that silently stops composing at the
    first dependency is the strongest everyday case quietly going dark."""
    d = getattr(args, "claim", None) or getattr(args, "d", None) or "."
    shallow = getattr(args, "shallow", False)
    try:
        data = _handlers.audit(d, shallow=shallow)
    except kernel.ClaimError as e:
        _output._err("audit", str(e))
        return 1
    ok = bool(data.get("ok"))
    if not getattr(args, "quiet", False):
        if getattr(args, "json", False):
            verdict = data.get("verdict") or ("accept" if ok else "reject")
            _output._finish("audit", data, ok, verdict, args)
        else:
            print(_report._r_audit(data))
    return 0 if ok else 1


def _dispatch_crosscheck(args) -> int:
    """`crosscheck m1 m2 m3 [--shallow] [--mutants N]`: the three-machine
    test. Each directory leg re-earns its own deep audit too, unless
    `--shallow` opts down."""
    m1 = getattr(args, "m1", None)
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    shallow = getattr(args, "shallow", False)
    mutants = getattr(args, "mutants", None)
    try:
        data = _handlers.crosscheck(m1, m2, m3, shallow=shallow, mutants=mutants)
    except kernel.ClaimError as e:
        _output._err("crosscheck", str(e))
        return 1
    ok = bool(data.get("satisfied"))
    if not getattr(args, "quiet", False):
        if getattr(args, "json", False):
            _output._finish("crosscheck", data, ok, data.get("verdict", "?"), args)
        else:
            print(_report._r_crosscheck(data))
    return 0 if ok else 1


# ==============================================================================
# main: the one place argv becomes an exit code
# ==============================================================================

_HANDLERS = {
    "help": _handle_help, "init": _handle_init, "completion": _handle_completion,
    "hook": _handle_hook, "run": _handle_run, "verify": _handle_verify,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "pull": _handle_pull,
    "sign": _handle_sign, "export": _handle_export, "record": _handle_record,
    "import": _handle_import,
}

_DISPATCHES = {
    "pack": _dispatch_pack, "audit": _dispatch_audit, "status": _dispatch_status,
    "crosscheck": _dispatch_crosscheck,
}


def main(argv=None) -> int:
    """Parse `argv` and route to the one handler or dispatch registered
    for the verb named -- the single place argv becomes an exit code."""
    parser, _subparsers = _parser._parser()
    args = parser.parse_args(argv)
    verb = getattr(args, "verb", None)
    if not verb:
        parser.print_help()
        return 1
    fn = _HANDLERS.get(verb) or _DISPATCHES.get(verb)
    if fn is None:
        _output._err("ret", f"no such command: {verb!r}")
        return 2
    return fn(args)

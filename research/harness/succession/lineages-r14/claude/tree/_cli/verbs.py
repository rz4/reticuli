"""reticuli._cli.verbs -- the verb handlers and composite dispatches
(spec/layers.md: surface).

Each porcelain verb (spec/layers.md's CLI table) gets one function here: a
plain `_handle_*` for a verb that is always one behavior, and a `_dispatch_*`
for a verb that picks among several behaviors by flag -- `pack` (glob-based
packing versus certifying a session's own trace cold), `audit` (deep by
default, `--shallow` opts out), `status` (plain / `--tree` / `--claims` /
`--ledger` / `--structure`), and `crosscheck` (the three-machine test,
optionally recording its proof). `main()` builds this module's own argv
grammar and routes a parsed command to the function above, folding every
verb's outcome through `output._finish`/`_err` except the two whose own
contract is a bare exit code: `run` (the child's exit code, unchanged) and
`pack` (a usage error is refused in words before anything is built, exit 2).
"""
import argparse
import os
import re
import shutil
import sys

from reticuli import kernel, registry, transfer, attest, record as record_mod
from reticuli import pack as pack_mod, hooks, assess, authoring
from reticuli._cli import output, parser as cli_parser, report, statusview, handlers

_REDIRECT = re.compile(r">>?\s*([^\s&|;]+)")


# -- init / hooks / run: before anything is a claim --------------------------

def _handle_init(args) -> dict:
    """`init`: mark a workspace as a session -- its `.reticuli/` store, and
    (unless `--no-agent`) the coding-agent handshake wired into it
    (`handlers.init`)."""
    def run():
        return handlers.init(getattr(args, "workspace", "."), getattr(args, "no_agent", False))
    return report._generic_contract("init", args, run)


def _handle_run(args) -> int:
    """`run`: run a shell command inside a workspace and return the
    child's exit code UNCHANGED (`handlers.run`) -- the one handler whose
    own contract is a bare exit code, never an envelope."""
    command = args.command
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    return handlers.run(command, getattr(args, "workspace", "."))


def _handle_hook(args) -> int:
    """`hook`: the coding-agent event receiver -- read one payload from
    stdin and trace it (`hooks.main`)."""
    return hooks.main()


# -- plumbing: help / completion ---------------------------------------------

def _handle_help(args) -> int:
    """`help [-a] [topic]`: everything (`-a`/no topic), or one command's
    detailed help."""
    if getattr(args, "all", False) or not getattr(args, "topic", None):
        cli_parser._help_all()
        return 0
    return cli_parser._help_topic(args.topic)


def _handle_completion(args) -> int:
    """`completion [shell]`: a shell completion script, generated from the
    grammar (`parser._completion`)."""
    cli_parser._completion(getattr(args, "shell", "bash"))
    return 0


# -- the kernel's own verbs ---------------------------------------------

def _handle_verify(args) -> dict:
    """`verify`: identity + gates re-run on present bytes (`kernel.verify`)."""
    return report._r_verify(args)


def _handle_assess(args) -> dict:
    """`assess`: how much the gates would have caught, by mutation testing
    (`assess.assess`)."""
    return report._r_assess(args)


def _dispatch_audit(args) -> dict:
    """`audit [--shallow]`: deep re-earning over the whole composed chain
    by default (`registry.audit_deep`); `--shallow` opts out to a single
    claim's own gates (`kernel.audit`, spec/verification.md)."""
    def run():
        if getattr(args, "shallow", False):
            return kernel.audit(args.claim)
        return registry.audit_deep(args.claim)
    return report._generic_contract("audit", args, run)


# -- rebuilding, pulling, crosschecking ---------------------------------

def _handle_rebuild(args) -> dict:
    """`rebuild`: regrow a claim's generated outputs, its declared
    components rebuilt first (`registry.rebuild_chain`)."""
    return report._r_rebuild(args)


def _handle_pull(args) -> dict:
    """`pull`: materialize a claim as a dependency of a fresh workspace
    (`registry.pull`)."""
    return report._r_pull(args)


def _dispatch_crosscheck(args) -> dict:
    """`crosscheck [--record]`: the three-machine test, deep over every
    ancestor (`registry.crosscheck_deep`); `--record` additionally seals a
    passing verdict onto M1 as a recorded proof (`kernel.record_proof`,
    spec/record.md)."""
    def run():
        if getattr(args, "record", False):
            res = kernel.record_proof(args.m1, args.m2, args.m3)
            out = dict(res["crosscheck"])
            out["proof_recorded"] = res["proof_recorded"]
            return out
        return registry.crosscheck_deep(args.m1, args.m2, args.m3)
    return report._generic_contract("crosscheck", args, run)


# -- evidence: records, attestation, authorization ---------------------

def _handle_record(args) -> dict:
    """`record [--check]`: emit this machine's signed statement of a
    claim's current results (`record.emit`); `--check` instead checks
    existing attestations for intactness and drift (`attest.check`)."""
    if getattr(args, "check", False):
        return report._r_attest_check(args)
    return report._r_record(args)


def _handle_sign(args) -> dict:
    """`sign [--check]`: the accountable authorization ceremony over a
    reviewed claim (`attest.sign`); `--check` instead checks each
    authorization's own integrity (`attest.sign_check`)."""
    if getattr(args, "check", False):
        return report._r_sign_check(args)
    return report._r_sign(args)


# -- moving a claim between places ---------------------------------------

def _handle_export(args) -> dict:
    """`export`: a deterministic tar of a claim's declared content
    (`transfer.export`)."""
    return report._r_export(args)


def _handle_import(args) -> dict:
    """`import`: extract a tar's declared content and verify the claim's
    identity holds from the received bytes alone (`transfer.import_`)."""
    return report._r_import(args)


# -- status: plain / tree / claims / ledger / structure ------------------

def _dispatch_status(args) -> dict:
    """`status [--tree|--claims|--ledger|--structure]`: a sealed claim's
    state, a not-yet-sealed session's draft state, or one of the
    registry-wide readings a flag selects (spec/layers.md: `tree`/`claims`
    folded in as flags)."""
    target = getattr(args, "target", None) or "."

    def run():
        if getattr(args, "tree", False):
            return statusview._r_deps(target)
        if getattr(args, "claims", False):
            return {"claims": registry.claims(target)}
        if getattr(args, "ledger", False):
            return statusview._ledger_status_claim(target)
        if getattr(args, "structure", False):
            return statusview._r_structure(target)
        if os.path.isfile(os.path.join(target, kernel.MANIFEST)):
            return statusview._v_status_claim(target)
        return statusview._r_status_draft(target)
    return report._generic_contract("status", args, run)


# -- pack: glob-based, or certifying a session's own trace cold ----------

def _dispatch_pack(args) -> int:
    """`pack <path> [--accept OUTPUT...] -o DEST [--gate CMD] [--generated
    PAT...] [--root PAT...]`: seal `path` as a self-claim from declared glob
    patterns naming the implementation (`--generated`) and the pinned
    inputs (`--root`); `--accept` instead certifies the workspace's own
    session trace cold (`authoring.build_claim`) against the named output(s),
    in which case `-o/--output` must name where the certified claim is
    written -- refused as a usage error, in words, before anything is built,
    rather than failing partway through."""
    command = "pack"
    path = getattr(args, "path", None) or "."
    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(path))
    accept = list(getattr(args, "accept", None) or ())
    out = getattr(args, "output", None)
    force = bool(getattr(args, "force", False))

    if accept and not out:
        output._err(command, "pack --accept needs -o/--output to name where the certified claim is written")
        return 2

    try:
        if accept:
            if os.path.isdir(out) and os.listdir(out):
                if not force:
                    raise kernel.ClaimError(f"refuses to build into a non-empty directory: {out!r}")
                shutil.rmtree(out)
            result = authoring.build_claim(path, accept, out, name)
        else:
            gate = getattr(args, "gate", None)
            pytest_arg = getattr(args, "pytest", None)
            if not gate and pytest_arg:
                gate = "python3 -m pytest" + (f" {pytest_arg}" if isinstance(pytest_arg, str) else "")
            if not gate:
                output._err(command, "pack needs --gate (or --pytest) to name the verdict command")
                return 2

            gate_output = out
            if not gate_output:
                matches = list(_REDIRECT.finditer(gate))
                gate_output = matches[-1].group(1) if matches else None
            if not gate_output:
                output._err(command,
                             "pack needs -o/--output (or a redirect in --gate) to name the gate's verdict file")
                return 2

            manifest_path = os.path.join(path, kernel.STORE, "manifest.json")
            if os.path.isfile(manifest_path) and not force:
                raise kernel.ClaimError(f"refuses to pack over an already-sealed claim: {path!r}")

            result = pack_mod.pack(
                path, name,
                generated=getattr(args, "generated", None) or (),
                inputs=getattr(args, "root", None) or (),
                gate=gate, gate_output=gate_output,
            )
    except kernel.ClaimError as e:
        output._err(command, str(e))
        return 1

    output._finish(command, result, True, result.get("status", "ok"), args)
    return 0


# -- main(): this module's own argv grammar, routed to the verbs above -------

def _add_common(sp) -> None:
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--verbose", action="store_true")
    sp.add_argument("--color", choices=("auto", "always", "never"), default="auto")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ret")
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="verb", metavar="command")

    def add(name):
        sp = sub.add_parser(name)
        _add_common(sp)
        return sp

    s_init = add("init")
    s_init.add_argument("workspace", nargs="?", default=".")
    s_init.add_argument("--no-agent", dest="no_agent", action="store_true")

    s_run = add("run")
    s_run.add_argument("command", nargs="+")
    s_run.add_argument("--workspace", default=".")

    s_status = add("status")
    s_status.add_argument("target", nargs="?", default=".")
    s_status.add_argument("--tree", action="store_true")
    s_status.add_argument("--claims", action="store_true")
    s_status.add_argument("--ledger", action="store_true")
    s_status.add_argument("--structure", action="store_true")

    s_pack = add("pack")
    s_pack.add_argument("path", nargs="?", default=".")
    s_pack.add_argument("--name")
    s_pack.add_argument("--root", nargs="*", default=())
    s_pack.add_argument("--generated", nargs="*", default=())
    s_pack.add_argument("--gate")
    s_pack.add_argument("--pytest")
    s_pack.add_argument("--accept", nargs="+")
    s_pack.add_argument("-o", "--output")
    s_pack.add_argument("--into")
    s_pack.add_argument("--force", action="store_true")

    s_pull = add("pull")
    s_pull.add_argument("claim")
    s_pull.add_argument("dest")

    s_export = add("export")
    s_export.add_argument("claim")
    s_export.add_argument("out")
    s_export.add_argument("--blind", action="store_true")

    s_import = add("import")
    s_import.add_argument("tar")
    s_import.add_argument("dest")

    s_verify = add("verify")
    s_verify.add_argument("claim", nargs="?", default=".")

    s_audit = add("audit")
    s_audit.add_argument("claim", nargs="?", default=".")
    s_audit.add_argument("--shallow", action="store_true")

    s_assess = add("assess")
    s_assess.add_argument("claim", nargs="?", default=".")
    s_assess.add_argument("--mutants", type=int, default=50)

    s_rebuild = add("rebuild")
    s_rebuild.add_argument("claim")
    s_rebuild.add_argument("producer")
    s_rebuild.add_argument("into")
    s_rebuild.add_argument("--workspace")
    s_rebuild.add_argument("--reuse", action="store_true")

    s_crosscheck = add("crosscheck")
    s_crosscheck.add_argument("m1")
    s_crosscheck.add_argument("m2")
    s_crosscheck.add_argument("m3")
    s_crosscheck.add_argument("--record", action="store_true")

    s_record = add("record")
    s_record.add_argument("claim", nargs="?", default=".")
    s_record.add_argument("--out")
    s_record.add_argument("--key")
    s_record.add_argument("--as", dest="identity")
    s_record.add_argument("--check", action="store_true")
    s_record.add_argument("--signers")

    s_sign = add("sign")
    s_sign.add_argument("claim")
    s_sign.add_argument("--key")
    s_sign.add_argument("--as", dest="identity")
    s_sign.add_argument("--workspace", default=".")
    s_sign.add_argument("--check", action="store_true")
    s_sign.add_argument("--signers")

    add("hook")

    s_help = add("help")
    s_help.add_argument("topic", nargs="?")
    s_help.add_argument("-a", "--all", action="store_true")

    s_completion = add("completion")
    s_completion.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p


_HANDLERS = {
    "init": _handle_init, "verify": _handle_verify, "assess": _handle_assess,
    "rebuild": _handle_rebuild, "pull": _handle_pull, "sign": _handle_sign,
    "export": _handle_export, "record": _handle_record, "import": _handle_import,
}
_DISPATCHES = {
    "audit": _dispatch_audit, "status": _dispatch_status, "crosscheck": _dispatch_crosscheck,
}


def main(argv=None) -> int:
    """Parse argv against this module's own grammar and route to the verb
    above it names -- the only place a verb's dispatch and its exit-code
    contract are joined."""
    p = _build_parser()
    args = p.parse_args(sys.argv[1:] if argv is None else argv)

    if getattr(args, "version", False):
        print(handlers._version_line())
        return 0
    verb = getattr(args, "verb", None)
    if not verb:
        p.print_help()
        return 1

    if verb == "help":
        return _handle_help(args)
    if verb == "completion":
        return _handle_completion(args)
    if verb == "hook":
        return _handle_hook(args)
    if verb == "run":
        return _handle_run(args)
    if verb == "pack":
        return _dispatch_pack(args)

    fn = _DISPATCHES.get(verb) or _HANDLERS.get(verb)
    if fn is None:
        output._err("ret", f"unknown command: {verb!r}")
        return 2
    envelope = fn(args)
    return 0 if envelope.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

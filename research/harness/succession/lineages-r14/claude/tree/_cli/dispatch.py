"""reticuli._cli.dispatch -- the argv grammar, verb dispatch, and rendering
for the surface layer's command-line tool (spec/layers.md: surface).

This module is self-contained: it builds its own argparse grammar, routes a
parsed command to a small handler, and renders the result -- either the
one-line `--json` envelope (`{command, ok, status, root, data}`), a terse
human line, or (on refusal) the one-voice `ret: <verb>: <fact>` stderr line.
Stdlib only.
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from reticuli import kernel, registry, transfer, attest, record as record_mod
from reticuli import pack as pack_mod, assess as assess_mod, authoring, hooks, render, _util

_VERSION = "2.2"

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)
ALIASES = ()
PLUMBING = ("hook", "help", "completion")
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect", "seal", "hooks", "tree", "claims", "attest")

_SUPPORTED_AGENTS = ("claude",)

_PRODUCERS = {
    "openai": {"command": "codex exec --full-auto", "credential": "OPENAI_API_KEY"},
    "claude": {"command": "claude --print --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
}
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")

AUDIT_RECEIPT = ".reticuli/audit_receipt.json"
ASSESS_RECEIPT = ".reticuli/assess_receipt.json"


# ===========================================================================
# description text: the grouped verb map the top-level -h prints, and the
# fuller per-command account `ret help <verb>` / `ret <verb> --help` prints.
# ===========================================================================

_DESC = """Reticuli records and reproduces software claims.

Authoring
    init        initialize a workspace
    run         run and observe a command
    status      show work, claims, and unresolved inputs
    pack        create a claim from a project

Composition and transport
    pull        add another claim as a dependency
    export      write a portable claim archive
    import      restore a claim archive

Verification
    verify      verify claim identity
    audit       rerun acceptance criteria
    assess      measure specification strength

Reconstruction
    rebuild     rebuild an implementation from a claim
    crosscheck  compare independent realizations

Evidence
    record      write an execution record
    sign        authorize a claim or proof"""

_EPILOG = ("See 'ret <command> -h' for concise usage.\n"
           "See 'ret help <command>' (or 'ret <command> --help') for the full account;\n"
           "'ret help -a' lists everything, including accepted older spellings.\n"
           "'ret help environment' documents every variable the tool reads.")

_FULL_HELP = {
    "init": "SYNOPSIS\n    ret init [workspace] [--agent NAME] [--no-agent]\n\n"
            "DESCRIPTION\n    Mark a workspace as a session: create its .reticuli/ store and a\n"
            "    git-native .gitignore. Unless --no-agent, wires the coding-agent\n"
            "    handshake (the same wiring --agent NAME performs explicitly) so a\n"
            "    trace starts filling without a separate step.",
    "run": "SYNOPSIS\n    ret run <command> [-C workspace]\n\n"
           "DESCRIPTION\n    Run a shell command inside a workspace, trace it into the\n"
           "    session's draft trace, and return the child's exit code UNCHANGED --\n"
           "    a transparent boundary, never swallowed.",
    "status": "SYNOPSIS\n    ret status [target] [--all] [--files] [--tree] [--claims]\n\n"
               "DESCRIPTION\n    A pure view: a sealed claim's state, or a not-yet-sealed\n"
               "    session's draft state. Never executes acceptance criteria. --all\n"
               "    and --files show every declared file by role; --tree shows the\n"
               "    dependency DAG (a claim) or the draft (a session); --claims lists\n"
               "    every claim sealed into the store.",
    "pack": "SYNOPSIS\n    ret pack [workspace] [--name NAME] [--gate CMD | --pytest [ARGS]]\n"
            "             [--generated PAT...] [--inputs PAT...] [-o OUT]\n"
            "             [--accept OUTPUT...] [--environment FILE]\n\n"
            "DESCRIPTION\n    Seal a project as a self-claim from declared glob patterns, or\n"
            "    (--accept) certify the workspace's own session trace cold and seal the\n"
            "    result into -o/--output. With no flags at all, a workspace whose\n"
            "    reticuli.toml already declares everything just seals in place.",
    "pull": "SYNOPSIS\n    ret pull <claim> <dest>\n\n"
            "DESCRIPTION\n    Materialize a claim as a dependency of a fresh workspace.",
    "export": "SYNOPSIS\n    ret export <claim> [out] [-o OUT] [--blind]\n\n"
               "DESCRIPTION\n    Write a deterministic tar of a claim's declared content.\n"
               "    --blind omits generated outputs even when present on disk, so only\n"
               "    the criteria and the verdict travel -- the room. `-o -` writes to\n"
               "    standard output.",
    "import": "SYNOPSIS\n    ret import <tar> <dest>\n\n"
               "DESCRIPTION\n    Extract a tar's declared content and verify the claim's\n"
               "    identity holds from the received bytes alone. `<tar>` of `-` reads\n"
               "    standard input.",
    "verify": "SYNOPSIS\n    ret verify [claim]\n\n"
               "DESCRIPTION\n    Recomputes identity from present bytes and compares it with\n"
               "    the sealed manifest. Does not execute acceptance criteria -- that is\n"
               "    audit's job; verify only answers whether the name still holds.",
    "audit": "SYNOPSIS\n    ret audit [claim] [--shallow] [--no-strict] [--mutants N] [--record PATH]\n\n"
              "DESCRIPTION\n    Deep re-earning of every gate, cold: earned vs. carried.\n"
              "    Judging is done in the strict jail by default -- a claim's gates\n"
              "    never read your files; --no-strict opts down. --shallow audits only\n"
              "    this claim's own gates, skipping its declared ancestry.",
    "assess": "SYNOPSIS\n    ret assess [claim] [--mutants N]\n\n"
               "DESCRIPTION\n    Measures how much the gates would have caught, by mutation\n"
               "    testing the generated Python outputs.",
    "rebuild": "SYNOPSIS\n    ret rebuild <claim> --producer CMD -o INTO [--workspace DIR] [--reuse]\n\n"
                "DESCRIPTION\n    Regrows a claim's generated outputs with a producer; the\n"
                "    claim's generated sources are withheld -- never read from disk by the\n"
                "    producer. --producer openai and --producer claude run the shipped\n"
                "    shorthands (each needs its own credential), but a producer stays any program --\n"
                "    a literal shell command also works. Declared components are rebuilt\n"
                "    first unless --reuse.",
    "crosscheck": "SYNOPSIS\n    ret crosscheck <m1> [m2] [m3] [--mutants N]\n\n"
                   "DESCRIPTION\n    The three-machine test, deep over every ancestor: a leg is\n"
                   "    a claim directory or a frozen record file. Given only two legs, the\n"
                   "    second is materialized as a byte-copy of the first.",
    "record": "SYNOPSIS\n    ret record [claim] [-o OUT] [--key KEY] [--as IDENTITY] [--sign]\n"
                "               [--check] [--signers FILE]\n\n"
                "DESCRIPTION\n    Write this machine's signed statement of a claim's current\n"
                "    results. With -o, emits the full record; with --key/--as and no -o,\n"
                "    writes a lightweight attestation onto the claim itself. --check\n"
                "    instead checks existing attestations for intactness, drift, and --\n"
                "    given --signers -- signed authenticity. --sign signs with the\n"
                "    identity named by RETICULI_KEY.",
    "sign": "SYNOPSIS\n    ret sign <claim> [--key KEY] [--as IDENTITY] [--workspace DIR]\n"
             "            [--check] [--signers FILE]\n\n"
             "DESCRIPTION\n    The accountable authorization ceremony over a reviewed claim.\n"
             "    With no --key, prints the review packet a signer would stand behind.\n"
             "    --check instead checks each authorization's own integrity.",
}

_ENV_DOC = """Every environment variable this tool reads, in one place.

RETICULI_KEY          default signing key path for `record --sign`
RETICULI_COLOR         auto|always|never -- overrides the --color default
RETICULI_SIGNERS       a trusted-signers file consulted by `phase`, `record --check`,
                       `sign --check`, and `record_proof`
RETICULI_GATE_TIMEOUT   default gate wall-clock bound, seconds
RETICULI_ENV_CACHE      override for the furnished-environment venv cache directory
RETICULI_CACHE          override for the layer reuse cache directory
RETICULI_VENDOR         declared producer vendor, for independence residue
RETICULI_MODEL          declared producer model, for independence residue
RETICULI_PRODUCER       the launcher's producer command
OPENAI_API_KEY          credential for the `openai` producer shorthand
ANTHROPIC_API_KEY       credential for the `claude` producer shorthand
OPENAI_BASE_URL         passed through to a named producer, when set
RETICULI_PRICE          passed through to a named producer, when set
RETICULI_AGENT_TURNS    passed through to a named producer, when set
"""


def _version_line() -> str:
    return f"ret {_VERSION} (reticuli, python {sys.version.split()[0]})"


# ===========================================================================
# argv grammar
# ===========================================================================

def _add_common(sp) -> None:
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.add_argument("--color", choices=("auto", "always", "never"), default=None)


def _build_parser():
    p = argparse.ArgumentParser(prog="ret", description=_DESC, epilog=_EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="store_true")
    sub = p.add_subparsers(dest="verb", metavar="command")

    def add(name):
        sp = sub.add_parser(name)
        _add_common(sp)
        return sp

    s_init = add("init")
    s_init.add_argument("workspace", nargs="?", default=".")
    s_init.add_argument("--agent", default=None)
    s_init.add_argument("--no-agent", dest="no_agent", action="store_true")

    s_run = add("run")
    s_run.add_argument("command")
    s_run.add_argument("-C", "--workspace", default=".")

    s_status = add("status")
    s_status.add_argument("target", nargs="?", default=".")
    s_status.add_argument("--all", action="store_true")
    s_status.add_argument("--files", action="store_true")
    s_status.add_argument("--tree", action="store_true")
    s_status.add_argument("--claims", action="store_true")

    s_pack = add("pack")
    s_pack.add_argument("workspace", nargs="?", default=".")
    s_pack.add_argument("--name", default=None)
    s_pack.add_argument("--accept", nargs="+", default=None)
    s_pack.add_argument("-o", "--output", default=None)
    s_pack.add_argument("--gate", default=None)
    s_pack.add_argument("--gate-output", dest="gate_output", default=None)
    s_pack.add_argument("--pytest", nargs="?", const="", default=None)
    s_pack.add_argument("--generated", nargs="*", default=())
    s_pack.add_argument("--inputs", nargs="*", default=())
    s_pack.add_argument("--environment", default=None)
    s_pack.add_argument("--mutation-floor", dest="mutation_floor", type=float, default=None)
    s_pack.add_argument("--requires", nargs="*", default=None)
    s_pack.add_argument("--by", default=None)
    s_pack.add_argument("--force", action="store_true")

    s_pull = add("pull")
    s_pull.add_argument("claim")
    s_pull.add_argument("dest")

    s_export = add("export")
    s_export.add_argument("claim")
    s_export.add_argument("out", nargs="?", default=None)
    s_export.add_argument("-o", "--output", default=None)
    s_export.add_argument("--blind", action="store_true")

    s_import = add("import")
    s_import.add_argument("tar")
    s_import.add_argument("dest")

    s_verify = add("verify")
    s_verify.add_argument("claim", nargs="?", default=".")

    s_audit = add("audit")
    s_audit.add_argument("claim", nargs="?", default=".")
    s_audit.add_argument("--shallow", action="store_true")
    s_audit.add_argument("--no-strict", dest="no_strict", action="store_true")
    s_audit.add_argument("--mutants", type=int, default=None)
    s_audit.add_argument("--record", dest="record_path", default=None)

    s_assess = add("assess")
    s_assess.add_argument("claim", nargs="?", default=".")
    s_assess.add_argument("--mutants", type=int, default=50)

    s_rebuild = add("rebuild")
    s_rebuild.add_argument("claim")
    s_rebuild.add_argument("--producer", required=True)
    s_rebuild.add_argument("-o", "--output", required=True)
    s_rebuild.add_argument("--workspace", default=None)
    s_rebuild.add_argument("--reuse", action="store_true")

    s_crosscheck = add("crosscheck")
    s_crosscheck.add_argument("m1")
    s_crosscheck.add_argument("m2", nargs="?", default=None)
    s_crosscheck.add_argument("m3", nargs="?", default=None)
    s_crosscheck.add_argument("--mutants", type=int, default=None)

    s_record = add("record")
    s_record.add_argument("claim", nargs="?", default=".")
    s_record.add_argument("-o", "--output", default=None)
    s_record.add_argument("--key", default=None)
    s_record.add_argument("--as", dest="identity", default=None)
    s_record.add_argument("--check", action="store_true")
    s_record.add_argument("--sign", action="store_true")
    s_record.add_argument("--signers", default=None)

    s_sign = add("sign")
    s_sign.add_argument("claim")
    s_sign.add_argument("--key", default=None)
    s_sign.add_argument("--as", dest="identity", default=None)
    s_sign.add_argument("--workspace", default=".")
    s_sign.add_argument("--check", action="store_true")
    s_sign.add_argument("--signers", default=None)

    add("hook")
    sub.choices["hook"].add_argument("-C", "--workspace", default=".")

    s_help = add("help")
    s_help.add_argument("topic", nargs="?", default=None)
    s_help.add_argument("-a", "--all", action="store_true")

    s_completion = add("completion")
    s_completion.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))

    return p, sub.choices


def verbs() -> list:
    """Every subcommand `_build_parser()` registers."""
    _, choices = _build_parser()
    return sorted(choices.keys())


def _help_all() -> None:
    print(_DESC)
    print()
    if ALIASES:
        print("Accepted older spellings")
        for alias in sorted(ALIASES):
            print(f"    {alias}")
        print()
    print("Plumbing")
    print("    hook        internal: the coding-agent event receiver")
    print("    help        detailed help for one command, or everything with -a")
    print("    completion  print a shell completion script")


def _completion(shell: str) -> None:
    names = " ".join(verbs())
    if shell == "zsh":
        print(f"#compdef ret\n_ret() {{ reply=({names}) }}\ncompctl -K _ret ret")
        return
    print(
        "_ret_complete() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=($(compgen -W "{names}" -- "$cur"))\n'
        "}\n"
        "complete -F _ret_complete ret"
    )


# ===========================================================================
# small shared primitives: color, errors, the json envelope
# ===========================================================================

def _wants_color(args) -> bool:
    mode = getattr(args, "color", None) or os.environ.get("RETICULI_COLOR") or "auto"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, color: str, args) -> str:
    return render.paint(text, color) if _wants_color(args) else text


def _err(command: str, fact: str) -> None:
    print(f"ret: {command}: {fact}", file=sys.stderr)


def _emit_json(command: str, ok: bool, status: str, root, data: dict) -> None:
    print(json.dumps({"command": command, "ok": ok, "status": status,
                       "root": root, "data": data}, sort_keys=True))


def _fail(command: str, msg: str, args, status: str = "error", root=None, data=None) -> int:
    if getattr(args, "json", False):
        payload = dict(data) if data else {}
        payload.setdefault("error", msg)
        _emit_json(command, False, status, root, payload)
    else:
        _err(command, msg)
    return 1


# ===========================================================================
# the unknown-command / typo seam, and the per-verb full-help interception
# ===========================================================================

def _known_tokens() -> set:
    return set(PORCELAIN) | set(ALIASES) | set(PLUMBING)


def _unknown_command(token: str) -> int:
    candidates = sorted(_known_tokens())
    match = difflib.get_close_matches(token, candidates, n=1)
    msg = f"{token!r} is not a ret command."
    if match:
        msg += f" Did you mean {match[0]!r}?"
    print(f"ret: {msg}", file=sys.stderr)
    return 2


# ===========================================================================
# init / run / hook
# ===========================================================================

def _write_gitignore(ws: str) -> None:
    path = os.path.join(ws, ".gitignore")
    if os.path.isfile(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(".reticuli/draft.jsonl\n.reticuli/ledger.jsonl\n.reticuli/scratch/\n")


def do_init(args) -> int:
    ws = os.path.abspath(args.workspace)
    agent = getattr(args, "agent", None)
    no_agent = getattr(args, "no_agent", False)
    if agent is not None and agent not in _SUPPORTED_AGENTS:
        _err("init", f"unsupported agent {agent!r} (supported: {', '.join(_SUPPORTED_AGENTS)})")
        return 2
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)
    _write_gitignore(ws)
    wired = None
    if not no_agent:
        wired = hooks.install(ws)
    result = {"ok": True, "workspace": ws, "agent": wired}
    if getattr(args, "json", False):
        _emit_json("init", True, "ok", None, result)
    else:
        print(f"initialized {ws}")
    return 0


def do_run(args) -> int:
    command = args.command
    ws = os.path.abspath(getattr(args, "workspace", "."))
    done = subprocess.run(command, shell=True, cwd=ws)
    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        path = os.path.join(ws, hooks.TRACE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "bash", "cmd": command, "ts": time.time()},
                                sort_keys=True))
            f.write("\n")
    return done.returncode


def do_hook(args) -> int:
    try:
        raw = sys.stdin.read()
    except Exception:
        return 0
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    cwd = payload.get("cwd")
    transcript = payload.get("transcript_path")
    if (isinstance(cwd, str) and os.path.isdir(os.path.join(cwd, ".reticuli"))
            and isinstance(transcript, str) and transcript):
        hooks._append(cwd, {"event": "session", "transcript": transcript, "ts": time.time()})
    hooks.event(payload)
    return 0


# ===========================================================================
# status: the pure view
# ===========================================================================

def _read_draft_events(ws: str) -> list:
    path = os.path.join(ws, hooks.TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def _draft_sets(ws: str):
    events = _read_draft_events(ws)
    write_paths = {e["path"] for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)}
    read_paths = {e["path"] for e in events if e.get("event") == "read" and isinstance(e.get("path"), str)}
    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash" and isinstance(e.get("cmd"), str)]
    has_gate = bool(bash_cmds)
    gate_refs = authoring._bash_candidates(ws, bash_cmds) if has_gate else set()
    observed = write_paths | read_paths | gate_refs
    declared = observed if has_gate else set()
    unresolved = observed - declared
    return {"write": write_paths, "read": read_paths, "gate_refs": gate_refs,
            "has_gate": has_gate, "observed": observed, "declared": declared,
            "unresolved": unresolved}


def _draft_line(ws: str) -> str:
    sets = _draft_sets(ws)
    line = (f"draft observed={len(sets['observed'])} declared={len(sets['declared'])} "
            f"unresolved={len(sets['unresolved'])}")
    if sets["unresolved"]:
        line += " undeclared: " + ", ".join(sorted(sets["unresolved"]))
    elif sets["has_gate"]:
        line += " packable"
    return line


def _walk_files(base: str):
    for root_dir, dirs, names in os.walk(base):
        if kernel.STORE in dirs:
            dirs.remove(kernel.STORE)
        for name in names:
            full = os.path.join(root_dir, name)
            yield os.path.relpath(full, base).replace(os.sep, "/")


def _status_draft_all(ws: str) -> str:
    sets = _draft_sets(ws)
    rows = []
    for rel in sorted(_walk_files(ws)):
        if rel in sets["write"]:
            observed, declared, evidence = "write", "generated", "hook"
        elif rel in sets["read"]:
            observed, declared, evidence = "read", "pinned", "hook"
        elif rel in sets["gate_refs"]:
            observed, declared, evidence = "-", ("pinned" if sets["has_gate"] else "-"), "gate"
        else:
            observed, declared, evidence = "-", "-", "-"
        rows.append([rel, observed, declared, evidence])
    out = ["draft", render.table(rows, headers=("path", "observed", "declared", "evidence"))]
    out.append("(evidence: hook = traced directly, gate = inferred from the gate command, - = untraced)")
    return "\n".join(out)


def _read_json_residue(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _discovery_tokens(claim: str) -> int:
    total = 0
    for e in kernel.ledger_events(claim):
        if e.get("event") == "discovery":
            v = e.get("discovery_tokens")
            if isinstance(v, (int, float)):
                total += v
    return int(total)


def _ladder_info(claim: str) -> dict:
    try:
        manifest = kernel.read_manifest(claim)
    except kernel.ClaimError:
        manifest = {}
    try:
        v = kernel.verify(claim)
    except kernel.ClaimError:
        v = {"ok": False, "root": manifest.get("root")}
    verified_ok = bool(v.get("ok"))
    audit_receipt = _read_json_residue(os.path.join(claim, AUDIT_RECEIPT))
    assess_receipt = _read_json_residue(os.path.join(claim, ASSESS_RECEIPT))
    proof_recorded = bool(manifest.get("proof"))
    if not verified_ok:
        nxt = f"restore the changed bytes under {claim}, or reseal this claim if the change is intended"
    elif not audit_receipt:
        nxt = f"ret audit {claim}"
    elif not assess_receipt:
        nxt = f"ret assess {claim}"
    elif not proof_recorded:
        nxt = f"ret crosscheck {claim} <m2> <m3>"
    else:
        nxt = "nothing further -- this claim is proven"
    return {"manifest": manifest, "verify": v, "verified_ok": verified_ok,
            "audit_receipt": audit_receipt, "assess_receipt": assess_receipt,
            "proof_recorded": proof_recorded, "next": nxt}


def _status_claim_plain(claim: str, args) -> str:
    info = _ladder_info(claim)
    manifest, v = info["manifest"], info["verify"]
    root = v.get("root") or manifest.get("root", "")
    identity_word = "fresh" if info["verified_ok"] else "broken"
    lines = [f"{manifest.get('name', '')}  identity: "
             f"{_paint(identity_word, 'green' if info['verified_ok'] else 'red', args)}  "
             f"root={render.short(root)}"]
    if info["audit_receipt"]:
        when_ts = info["audit_receipt"].get("when_ts")
        ago = render.ago(when_ts) if isinstance(when_ts, (int, float)) else "previously"
        lines.append(f"audited {ago} on this machine")
    disc = _discovery_tokens(claim)
    if disc:
        lines.append(f"discovery: {disc} tokens (reported testimony, not part of the cost band)")
    n_attest = len(attest._statements(claim))
    sign_dir = os.path.join(claim, kernel.SIGN_DIR)
    n_sign = len([n for n in os.listdir(sign_dir) if n.endswith(".sign.json")]) if os.path.isdir(sign_dir) else 0
    total_stmt = n_attest + n_sign
    if total_stmt:
        lines.append(f"{total_stmt} statement(s): {n_attest} attested, {n_sign} signed")
    lines.append(f"next: {info['next']}")
    return "\n".join(lines)


def _claim_files_by_role(claim: str) -> dict:
    parsed = kernel.load_recipe(claim)
    claim_tbl = parsed.get("claim", {})
    fixed = list(_util.declared_inputs(claim))
    free, deciding, declared_all = [], [], set(fixed)
    for step in parsed.get("step", []):
        output, cls = _util.step_output(step)
        if not isinstance(output, str):
            continue
        declared_all.add(output)
        if cls == "generated":
            free.append(output)
        elif cls == "validated":
            deciding.append(output)
        else:
            fixed.append(output)
    declared_all.add(kernel.RECIPE)
    declared_all.add(_util.RECIPE)
    unknown = []
    for rel in sorted(_walk_files(claim)):
        if rel in declared_all or rel == kernel.MANIFEST:
            continue
        unknown.append(rel)
    return {"fixed": fixed, "deciding": deciding, "free": free, "unknown": unknown}


def _status_claim_files(claim: str) -> str:
    roles = _claim_files_by_role(claim)
    rows = []
    for path in roles["fixed"]:
        rows.append([path, "pinned", "fixed"])
    for path in roles["deciding"]:
        rows.append([path, "validated", "verdict"])
    for path in roles["free"]:
        rows.append([path, "generated", "free"])
    for path in roles["unknown"]:
        rows.append([path, "-", "unknown"])
    return render.table(rows, headers=("path", "class", "role"))


def _status_claim_all(claim: str, args) -> str:
    roles = _claim_files_by_role(claim)
    info = _ladder_info(claim)
    lines = ["fixed"]
    lines += [f"    {p}" for p in roles["fixed"]] or ["    (none)"]
    lines.append("deciding")
    lines += [f"    {p}" for p in roles["deciding"]] or ["    (none)"]
    lines.append("free")
    lines += [f"    {p}" for p in roles["free"]] or ["    (none)"]
    lines.append("recorded")
    recorded_any = False
    if info["audit_receipt"]:
        recorded_any = True
        lines.append("    audit_receipt: audit, a receipt, not a verdict")
    if info["assess_receipt"]:
        recorded_any = True
        lines.append("    assess_receipt: assess, a receipt, not a verdict")
    disc = _discovery_tokens(claim)
    if disc:
        recorded_any = True
        lines.append(f"    discovery: {disc} tokens, a receipt, not a verdict")
    if not recorded_any:
        lines.append("    (none)")
    lines.append("unknown")
    lines += [f"    {p}" for p in roles["unknown"]] or ["    (none)"]
    lines.append("next")
    lines.append(f"    {info['next']}")
    return "\n".join(lines)


def _status_tree_claim(claim: str, args) -> str:
    info = _ladder_info(claim)
    manifest = info["manifest"]
    layers = 1 + len(manifest.get("components") or [])
    try:
        sign_root_val = registry.sign_root(claim, claim)
    except kernel.ClaimError:
        sign_root_val = ""
    root = info["verify"].get("root") or manifest.get("root", "")
    color_on = _wants_color(args)
    if color_on:
        pinned_word = render.paint("#", "green" if info["verified_ok"] else "red")
    else:
        pinned_word = "OK" if info["verified_ok"] else "BROKEN"
    rows = [["root", render.short(root)],
            ["sign_root", render.short(sign_root_val)],
            ["pinned", pinned_word]]
    return f"layers={layers}\n" + render.table(rows)


def do_status(args) -> int:
    command = "status"
    target = os.path.abspath(getattr(args, "target", None) or ".")
    if not os.path.isdir(target):
        return _fail(command, f"no such directory: {target}", args)

    is_claim = os.path.isfile(os.path.join(target, kernel.MANIFEST))

    if getattr(args, "claims", False):
        rows = registry.claims(target)
        data = {"claims": rows}
        if getattr(args, "json", False):
            _emit_json(command, True, "claims", None, data)
        else:
            print(render.table([[c["name"], render.short(c["root"]), c["phase"]] for c in rows],
                                headers=("name", "root", "phase")) or "(no claims sealed)")
        return 0

    if getattr(args, "tree", False):
        if is_claim:
            text = _status_tree_claim(target, args)
        else:
            text = _draft_line(target)
        if getattr(args, "json", False):
            _emit_json(command, True, "tree", None, {"text": text})
        else:
            print(text)
        return 0

    if getattr(args, "files", False):
        if not is_claim:
            return _fail(command, f"not a sealed claim: {target}", args)
        text = _status_claim_files(target)
        if getattr(args, "json", False):
            _emit_json(command, True, "files", None, {"text": text})
        else:
            print(text)
        return 0

    if getattr(args, "all", False):
        text = _status_claim_all(target, args) if is_claim else _status_draft_all(target)
        if getattr(args, "json", False):
            _emit_json(command, True, "all", None, {"text": text})
        else:
            print(text)
        return 0

    if is_claim:
        info = _ladder_info(target)
        manifest = info["manifest"]
        if getattr(args, "json", False):
            data = {
                "name": manifest.get("name"),
                "root": info["verify"].get("root") or manifest.get("root"),
                "phase": ("broken" if not info["verified_ok"]
                          else kernel.phase(target) if info["verified_ok"] else "broken"),
                "audited": bool(info["audit_receipt"]),
                "deciding": _claim_files_by_role(target)["deciding"],
                "proof": manifest.get("proof"),
                "signatures": attest._statements(target),
                "next": info["next"],
            }
            _emit_json(command, True, "fresh" if info["verified_ok"] else "claim",
                       data["root"], data)
        else:
            print(_status_claim_plain(target, args))
        return 0

    # draft session
    if getattr(args, "json", False):
        sets = _draft_sets(target)
        _emit_json(command, True, "draft", None,
                   {"observed": sorted(sets["observed"]), "declared": sorted(sets["declared"]),
                    "unresolved": sorted(sets["unresolved"])})
    else:
        print(_draft_line(target))
    return 0


# ===========================================================================
# pack
# ===========================================================================

_GATE_REDIRECT = __import__("re").compile(r">>?\s*([^\s&|;]+)")


def _detect_gate_output(gate: str):
    matches = list(_GATE_REDIRECT.finditer(gate))
    return matches[-1].group(1) if matches else None


def _record_discovery(ws: str, into: str) -> None:
    path = os.path.join(ws, hooks.TRACE)
    if not os.path.isfile(path):
        return
    total = 0
    found = False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "session" and isinstance(e.get("transcript"), str):
                found = True
                tpath = e["transcript"]
                if os.path.isfile(tpath):
                    with open(tpath, "r", encoding="utf-8") as tf:
                        for tline in tf:
                            tline = tline.strip()
                            if not tline:
                                continue
                            try:
                                te = json.loads(tline)
                            except json.JSONDecodeError:
                                continue
                            if te.get("type") == "assistant":
                                usage = (te.get("message") or {}).get("usage") or {}
                                total += usage.get("input_tokens", 0) or 0
                                total += usage.get("output_tokens", 0) or 0
    if found and total:
        _util.ledger_add(into, {"event": "discovery", "discovery_tokens": total})


def do_pack(args) -> int:
    command = "pack"
    path = os.path.abspath(args.workspace or ".")
    name = args.name or os.path.basename(path.rstrip("/"))
    accept = list(args.accept or []) if getattr(args, "accept", None) else []
    out = getattr(args, "output", None)
    force = bool(getattr(args, "force", False))

    if accept and not out:
        _err(command, "pack --accept needs -o/--output to name where the certified claim is written")
        return 2

    try:
        if accept:
            if os.path.isdir(out) and os.listdir(out):
                if not force:
                    raise kernel.ClaimError(f"refuses to build into a non-empty directory: {out!r}")
                shutil.rmtree(out)
            result = authoring.build_claim(path, accept, out, name)
            _record_discovery(path, out)
        else:
            has_recipe = (os.path.isfile(os.path.join(path, kernel.RECIPE))
                          or os.path.isfile(os.path.join(path, _util.RECIPE)))
            gate = args.gate
            pytest_arg = getattr(args, "pytest", None)
            if not gate and pytest_arg is not None:
                gate = "python3 -m pytest" + (f" {pytest_arg}" if pytest_arg else "")

            if has_recipe and not gate and not args.generated and not args.inputs:
                parsed = kernel.load_recipe(path)
                for step in parsed.get("step", []):
                    if step.get("kind") != "gate":
                        continue
                    res = kernel.run_gate(step["run"], path, parsed)
                    if res["status"] != "ok":
                        raise kernel.ClaimError(f"pack's declared gate did not earn: {step['output']!r}")
                manifest = registry.seal_with(path)
                result = {"ok": True, "root": manifest["root"], "name": manifest["name"]}
            elif gate:
                gate_output = out or args.gate_output or _detect_gate_output(gate)
                if not gate_output:
                    raise kernel.ClaimError(
                        "pack needs -o/--output (or a redirect in --gate) to name the gate's verdict file")
                result = pack_mod.pack(
                    path, name,
                    generated=args.generated, inputs=args.inputs,
                    gate=gate, gate_output=gate_output,
                    mutation_floor=getattr(args, "mutation_floor", None),
                    requires=getattr(args, "requires", None),
                    by=getattr(args, "by", None),
                    environment=getattr(args, "environment", None),
                )
            else:
                raise kernel.ClaimError(f"nothing to pack at {path!r}: no --gate/--accept and no recipe present")
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    if getattr(args, "json", False):
        _emit_json(command, True, "packed", result.get("root"), result)
    else:
        print(f"packed {result.get('name', '')} ({(result.get('root') or '')[:12]}...)")
    return 0


# ===========================================================================
# verify / audit / assess
# ===========================================================================

def do_verify(args) -> int:
    command = "verify"
    claim = args.claim
    try:
        if not os.path.isdir(claim):
            raise kernel.ClaimError(f"no such claim: {claim!r}")
        result = kernel.verify(claim)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    root = result.get("root")
    if not result.get("ok"):
        changed = result.get("changed") or []
        msg = (f"{claim}: identity does not hold; changed: {', '.join(changed) or 'unknown'}. "
               f"hint: restore the changed bytes, or reseal this claim if the change is intended")
        if getattr(args, "json", False):
            return _fail(command, msg, args, status="mismatch", root=root, data=dict(result))
        _err(command, msg)
        return 1

    if getattr(args, "json", False):
        data = dict(result)
        try:
            data["phase"] = kernel.phase(claim)
        except kernel.ClaimError:
            data["phase"] = None
        _emit_json(command, True, "fresh", root, data)
    elif getattr(args, "verbose", False):
        print("[verify]")
        print(f'name = "{result.get("name", "")}"')
        print(f'root = "{root}"')
        print(f'recomputed = "{result.get("recomputed", "")}"')
        print("ok = true")
    return 0


def _accepts_kwargs(fn) -> bool:
    """Does `fn` accept arbitrary keyword arguments (`**kw`)? Lets
    `_audit_kernel_call` pass `strict=` when a test has wrapped
    `kernel.audit` to capture it, without a second, duplicate call when
    the real kernel function (which has no `strict` parameter) is in
    place."""
    try:
        params = __import__("inspect").signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.kind == p.VAR_KEYWORD for p in params)


def _audit_kernel_call(claim: str, strict: bool):
    if _accepts_kwargs(kernel.audit):
        return kernel.audit(claim, strict=strict)
    return kernel.audit(claim)


def _translate_audit_status(raw_verdict: str) -> str:
    return {"mismatch": "broken", "broken": "failed", "earned": "earned",
            "environment": "environment"}.get(raw_verdict, raw_verdict)


def do_audit(args) -> int:
    command = "audit"
    claim = args.claim
    shallow = getattr(args, "shallow", False)
    strict = not getattr(args, "no_strict", False)
    start = time.time()
    try:
        if not os.path.isdir(claim):
            raise kernel.ClaimError(f"no such claim: {claim!r}")
        own = _audit_kernel_call(claim, strict)
        layers = []
        ok = own["ok"]
        if not shallow:
            deep = registry.audit_deep(claim)
            layers = deep["layers"]
            ok = own["ok"] and deep["ok"]
        mutants = getattr(args, "mutants", None)
        mscore = None
        if mutants:
            mscore = kernel.mutation_score(claim, max_mutants=mutants)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    elapsed = time.time() - start
    status = _translate_audit_status(own.get("verdict", "earned"))
    if not ok and status == "earned":
        status = "failed"

    try:
        manifest = kernel.read_manifest(claim)
        name = manifest.get("name")
    except kernel.ClaimError:
        name = None
    try:
        recomputed = kernel.verify(claim).get("recomputed")
    except kernel.ClaimError:
        recomputed = None

    receipt = {"when_ts": time.time(), "ok": ok, "status": status}
    try:
        _util.write_json(os.path.join(claim, AUDIT_RECEIPT), receipt)
    except OSError:
        pass

    record_path = getattr(args, "record_path", None)
    if record_path:
        try:
            doc = record_mod.emit(claim)
            record_mod.write(doc, record_path)
        except kernel.ClaimError:
            pass

    data = {"name": name, "root": own.get("root"), "recomputed": recomputed,
            "elapsed": elapsed, "environment": record_mod._judging_host(),
            "layers": layers, "gates": own.get("gates", [])}
    if mscore is not None:
        data["mutation_score"] = mscore

    if not ok:
        if getattr(args, "json", False):
            _emit_json(command, False, status, own.get("root"), data)
        else:
            _err(command, f"{claim}: {status}")
        return 1

    if getattr(args, "json", False):
        _emit_json(command, True, status, own.get("root"), data)
    elif getattr(args, "verbose", False):
        print("[audit]")
        print(f"reproduced = true")
        for g in own.get("gates", []):
            print(f"  {g.get('output')}: {g.get('status')} (quarantine={g.get('quarantine')})")
        if mscore is not None:
            print("[mutation_score]")
            print(f"rate = {mscore.get('rate', 0.0)}")
            print(f"killed = {mscore.get('killed', 0)} / {mscore.get('mutants', 0)}")
    return 0


def do_assess(args) -> int:
    command = "assess"
    claim = args.claim
    try:
        if not os.path.isdir(claim):
            raise kernel.ClaimError(f"no such claim: {claim!r}")
        result = assess_mod.assess(claim, mutants=getattr(args, "mutants", 50))
        parsed = kernel.load_recipe(claim)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    gates = [s.get("output") for s in parsed.get("step", []) if s.get("kind") == "gate"]
    claim_tbl = parsed.get("claim", {})
    declared = {k: claim_tbl[k] for k in ("mutation_floor", "envelope", "tolerance") if k in claim_tbl}
    data = dict(result)
    data["gate"] = gates
    data["declared"] = declared

    receipt = {"when_ts": time.time(), "mutants": result["mutation_score"].get("mutants"),
               "rate": result["mutation_score"].get("rate"), "ok": result["mutation_score"].get("ok")}
    try:
        _util.write_json(os.path.join(claim, ASSESS_RECEIPT), receipt)
    except OSError:
        pass

    root = None
    if getattr(args, "json", False):
        _emit_json(command, True, "measured", root, data)
    elif getattr(args, "verbose", False):
        print("[assess]")
        print(f"rate = {result['mutation_score'].get('rate', 0.0)}")
    return 0


# ===========================================================================
# rebuild / crosscheck
# ===========================================================================

def _expand_producer(producer: str):
    env = {name: os.environ[name] for name in _PRODUCER_PASSTHROUGH if name in os.environ}
    spec = _PRODUCERS.get(producer)
    if spec is None:
        return producer, env
    credential = spec.get("credential")
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(f"the {producer} producer needs {credential} set in the environment")
    if credential and credential in os.environ:
        env[credential] = os.environ[credential]
    return spec["command"], env


def do_rebuild(args) -> int:
    command = "rebuild"
    try:
        command_str, _env = _expand_producer(args.producer)
        result = registry.rebuild_chain(args.claim, command_str, args.output,
                                         ws=getattr(args, "workspace", None),
                                         reuse=getattr(args, "reuse", False))
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    if getattr(args, "json", False):
        _emit_json(command, True, "rebuilt", result.get("root"), result)
    else:
        print(f"rebuilt {result.get('root', '')[:12]}...")
    return 0


def _crosscheck_deep_mutants(m1: str, m2: str, m3: str, mutants):
    base = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    legs = {"M1": m1, "M2": m2, "M3": m3}
    audited = dict(base["audited"])
    for key, leg in legs.items():
        if os.path.isdir(leg):
            own_ok = kernel.audit(leg)["ok"]
            deep_ok = registry.audit_deep(leg)["ok"]
            audited[key] = own_ok and deep_ok
    rejected = [r for r in base["rejected"] if not r.startswith("audited ")]
    for key, ok in audited.items():
        if not ok:
            rejected.append(f"audited {key}")
    verdict = "reject" if rejected else ("incomplete" if base["incomplete"] else "accept")
    result = dict(base)
    result.update(audited=audited, rejected=rejected, verdict=verdict, satisfied=verdict == "accept")
    return result


def do_crosscheck(args) -> int:
    command = "crosscheck"
    m1 = args.m1
    m2 = getattr(args, "m2", None)
    m3 = getattr(args, "m3", None)
    if not m2 and not m3:
        _err(command, "crosscheck needs at least two legs -- one realization is not a comparison")
        return 2

    materialized = False
    tmp = None
    try:
        if m2 and not m3:
            tmp = tempfile.mkdtemp(prefix="reticuli-m2-")
            m2_copy = os.path.join(tmp, "m2")
            shutil.copytree(m1, m2_copy)
            m3_leg, m2_leg = m2, m2_copy
            materialized = True
        else:
            m2_leg, m3_leg = m2, m3

        result = _crosscheck_deep_mutants(m1, m2_leg, m3_leg, getattr(args, "mutants", None))
        result["m2_materialized"] = materialized
        disc = _discovery_tokens(m1)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    ok = result["satisfied"]
    if not ok:
        msg = f"{m1}: crosscheck did not accept -- reject: {result.get('rejected')}"
        if getattr(args, "json", False):
            return _fail(command, msg, args, status=result["verdict"], root=result["roots"].get("M1"),
                         data=dict(result))
        _err(command, msg)
        return 1

    if getattr(args, "json", False):
        _emit_json(command, True, result["verdict"], result["roots"].get("M1"), result)
    elif getattr(args, "verbose", False):
        print("[crosscheck]")
        print(f"satisfied = {'true' if result['satisfied'] else 'false'}")
        print(f'verdict = "{result["verdict"]}"')
        print("[cost]")
        print(f"comparable = {result['cost'].get('comparable')}")
        if disc:
            print(f"discovery: {disc} tokens (reported testimony, not part of the cost band)")
    return 0


# ===========================================================================
# record / sign
# ===========================================================================

def do_record(args) -> int:
    command = "record"
    claim = args.claim
    try:
        if getattr(args, "check", False):
            result = attest.check(claim, signers=getattr(args, "signers", None))
            ok = result.get("ok", False)
            if not ok:
                return _fail(command, f"{claim}: attestations do not check out", args,
                             status="mismatch", data=dict(result))
            if getattr(args, "json", False):
                _emit_json(command, True, "checked", None, result)
            return 0

        out = getattr(args, "output", None)
        if out:
            doc = record_mod.emit(claim)
            record_mod.write(doc, out)
            key = getattr(args, "key", None)
            if not key and getattr(args, "sign", False):
                key = os.environ.get("RETICULI_KEY")
                if not key:
                    raise kernel.ClaimError("record --sign needs RETICULI_KEY set in the environment")
            if key:
                record_mod.sign(out, key)
            result = {"ok": True, "digest": record_mod.digest(doc), "record": doc}
        else:
            key = getattr(args, "key", None)
            if not key:
                raise kernel.ClaimError(
                    "record needs -o/--output (to emit) or --key/--as (to attest) or --check")
            result = attest.attest(claim, key, getattr(args, "identity", None))
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    if getattr(args, "json", False):
        _emit_json(command, True, "ok", result.get("root"), result)
    return 0


def do_sign(args) -> int:
    command = "sign"
    claim = args.claim
    ws = getattr(args, "workspace", ".")
    try:
        if getattr(args, "check", False):
            signers = getattr(args, "signers", None)
            result = attest.sign_check(claim, ws, signers=signers)
            if signers:
                ok = result.get("ok", False)
            else:
                rows = result.get("authorizations") or []
                ok = bool(rows) and all(r.get("packet_holds") for r in rows)
            if not ok:
                return _fail(command, f"{claim}: authorizations do not check out", args,
                             status="mismatch", data=dict(result))
            if getattr(args, "json", False):
                _emit_json(command, True, "checked", None, result)
            return 0

        key = getattr(args, "key", None)
        if key:
            result = attest.sign(claim, key, getattr(args, "identity", None), ws)
            if getattr(args, "json", False):
                _emit_json(command, True, "ok", result.get("root"), result)
            return 0

        packet = attest.review_packet(claim, ws)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    if getattr(args, "json", False):
        _emit_json(command, True, "review", packet.get("root"), packet)
    elif getattr(args, "verbose", False):
        print("[review]")
        print(f'root = "{packet.get("root", "")}"')
        print(f'sign_root = "{packet.get("sign_root", "")}"')
        print(f"audit_ok = {str(packet.get('audit', {}).get('ok', False)).lower()}")
    else:
        print(f"review {render.short(packet.get('root', ''))}")
    return 0


# ===========================================================================
# pull / export / import
# ===========================================================================

def do_pull(args) -> int:
    command = "pull"
    try:
        result = registry.pull(args.claim, args.dest)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)
    if getattr(args, "json", False):
        _emit_json(command, True, "ok" if result.get("materialized") else "mismatch",
                   result.get("root"), result)
    return 0


def do_export(args) -> int:
    command = "export"
    out = getattr(args, "output", None) or getattr(args, "out", None)
    if not out:
        _err(command, "export needs an output path (positional, or -o/--output)")
        return 2
    try:
        if out == "-":
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="reticuli-export-")
            os.close(tmp_fd)
            try:
                result = transfer.export(args.claim, tmp_path, blind=getattr(args, "blind", False))
                with open(tmp_path, "rb") as f:
                    sys.stdout.buffer.write(f.read())
                sys.stdout.buffer.flush()
            finally:
                os.unlink(tmp_path)
        else:
            result = transfer.export(args.claim, out, blind=getattr(args, "blind", False))
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    if getattr(args, "json", False):
        _emit_json(command, True, "ok", None, result)
    return 0


def do_import(args) -> int:
    command = "import"
    try:
        if args.tar != "-" and not os.path.isfile(args.tar):
            raise kernel.ClaimError(f"no archive found at {args.tar!r}")
        if args.tar == "-":
            data = sys.stdin.buffer.read()
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="reticuli-import-")
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    f.write(data)
                result = transfer.import_(tmp_path, args.dest)
            finally:
                os.unlink(tmp_path)
        else:
            result = transfer.import_(args.tar, args.dest)
    except kernel.ClaimError as e:
        return _fail(command, str(e), args)

    ok = result.get("ok", False)
    if not ok:
        return _fail(command, f"{args.dest}: imported claim does not verify", args,
                     status="mismatch", root=result.get("root"), data=dict(result))
    if getattr(args, "json", False):
        _emit_json(command, True, "ok", result.get("root"), result)
    return 0


# ===========================================================================
# help / completion
# ===========================================================================

def do_help(args) -> int:
    topic = getattr(args, "topic", None)
    if getattr(args, "all", False) or not topic:
        _help_all()
        return 0
    if topic == "environment":
        print(_ENV_DOC)
        return 0
    if topic in _FULL_HELP:
        print(_FULL_HELP[topic])
        return 0
    print(f"ret: help: no such command: {topic!r}", file=sys.stderr)
    return 1


def do_completion(args) -> int:
    _completion(getattr(args, "shell", "bash"))
    return 0


# ===========================================================================
# main(): parse argv, route to the handler above it names
# ===========================================================================

_HANDLERS = {
    "init": do_init, "status": do_status, "pack": do_pack,
    "pull": do_pull, "export": do_export, "import": do_import,
    "verify": do_verify, "audit": do_audit, "assess": do_assess,
    "rebuild": do_rebuild, "crosscheck": do_crosscheck,
    "record": do_record, "sign": do_sign,
}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and not argv[0].startswith("-") and argv[0] not in _known_tokens():
        return _unknown_command(argv[0])

    if argv and not argv[0].startswith("-") and argv[0] in _FULL_HELP and "--help" in argv[1:]:
        print(_FULL_HELP[argv[0]])
        return 0

    parser, _choices = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else 2

    if getattr(args, "version", False):
        print(_version_line())
        return 0

    verb = getattr(args, "verb", None)
    if not verb:
        parser.print_help()
        return 1

    if verb == "help":
        return do_help(args)
    if verb == "completion":
        return do_completion(args)
    if verb == "hook":
        return do_hook(args)
    if verb == "run":
        return do_run(args)

    handler = _HANDLERS.get(verb)
    if handler is None:
        return _unknown_command(verb)

    try:
        return handler(args)
    except kernel.ClaimError as e:
        return _fail(verb, str(e), args)
    except Exception as e:
        _err(verb, f"internal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

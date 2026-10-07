"""The CLI dispatcher: argv -> a verb's own logic -> a process exit code
(`spec/layers.md`'s surface layer).

Fourteen porcelain verbs (`PORCELAIN`), grouped the way `ret -h` prints
them; the plumbing beside them (`hook`, `help`, `completion`); and the
retired v1 vocabulary (`RETIRED`), which must never dispatch again. Every
verb function here takes the raw argv tail (after the verb word) and
returns a process exit code: 0 the predicate held, 1 a layer refusal
(`ret: <verb>: <fact>`, one voice, on stderr), 2 the invocation itself was
invalid. `main()` never lets a `SystemExit` escape (argparse's own parse
errors included), so every caller -- interactive or embedding -- always
gets back a plain integer.

Stdlib only.
"""
import argparse
import difflib
import inspect
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .. import attest as attest_mod
from .. import hooks as hooks_mod
from .. import kernel
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer as transfer_mod

_VERSION = "2.2"

# ---------------------------------------------------------------------------
# The grammar: fourteen porcelain verbs, grouped; plumbing; retired words.
# ---------------------------------------------------------------------------

GROUPS = ("Authoring", "Composition and transport", "Verification",
          "Reconstruction", "Evidence")
PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")
ALIASES = {}
PLUMBING = ("hook", "help", "completion")
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect", "seal", "hooks", "tree", "claims", "attest")

_DESC = (
    "Reticuli records and reproduces software claims.\n\n"
    "Authoring\n"
    "    init        initialize a workspace\n"
    "    run         run and observe a command\n"
    "    status      show work, claims, and unresolved inputs\n"
    "    pack        create a claim from a project\n\n"
    "Composition and transport\n"
    "    pull        add another claim as a dependency\n"
    "    export      write a portable claim archive\n"
    "    import      restore a claim archive\n\n"
    "Verification\n"
    "    verify      verify claim identity\n"
    "    audit       rerun acceptance criteria\n"
    "    assess      measure specification strength\n\n"
    "Reconstruction\n"
    "    rebuild     rebuild an implementation from a claim\n"
    "    crosscheck  compare independent realizations\n\n"
    "Evidence\n"
    "    record      write an execution record\n"
    "    sign        authorize a claim or proof\n"
)

_EPILOG = (
    "See 'ret <command> -h' for command usage.\n"
    "See 'ret help <command>' for detailed help; 'ret help -a' lists\n"
    "everything, including accepted older spellings."
)

_FULL_HELP = {
    "init": (
        "SYNOPSIS\n    ret init [path] [--agent NAME]\n\n"
        "DESCRIPTION\n"
        "    Mark PATH (default: the current directory) as an authoring\n"
        "    session: a .reticuli/ workspace marker, a git-native\n"
        "    .gitignore for the store's own residue, and -- with --agent\n"
        "    -- the coding-agent hooks that let a producer's trace feed\n"
        "    `status` and `pack` later. The only supported --agent value\n"
        "    today is `claude`."
    ),
    "run": (
        "SYNOPSIS\n    ret run <cmd> [-C DIR]\n\n"
        "DESCRIPTION\n"
        "    Run CMD for real in the session at DIR (default: the\n"
        "    current directory), appending a trace entry, and exit with\n"
        "    CMD's own exit code unchanged -- usable as a predicate in a\n"
        "    session script."
    ),
    "status": (
        "SYNOPSIS\n"
        "    ret status [path] [--all] [--files] [--tree] [--claims]\n\n"
        "DESCRIPTION\n"
        "    A pure view: reads and reports, never executes. On an\n"
        "    unsealed session, shows the authoring triad (observed /\n"
        "    declared / unresolved); on a sealed claim, shows its\n"
        "    identity, its ledger, and the next rung on the ladder."
    ),
    "pack": (
        "SYNOPSIS\n"
        "    ret pack [path] [--accept OUTPUT -o CLAIM [--name NAME]]\n"
        "             [--pytest] [--environment FILE]\n\n"
        "DESCRIPTION\n"
        "    Seal a project as a claim. With a recipe already declared\n"
        "    (reticuli.toml present), zero flags seals it in place. With\n"
        "    --accept OUTPUT -o CLAIM, certifies an authoring session's\n"
        "    trace cold into CLAIM instead, naming OUTPUT as the gate's\n"
        "    pinned verdict. --pytest assumes `pytest -q` as the gate\n"
        "    when none is otherwise declared; --environment FILE pins a\n"
        "    hash-locked requirements file into the claim."
    ),
    "pull": (
        "SYNOPSIS\n    ret pull <claim> <ws>\n\n"
        "DESCRIPTION\n"
        "    Add CLAIM as a dependency of the session at WS, recording\n"
        "    it in the session's registry."
    ),
    "export": (
        "SYNOPSIS\n    ret export <claim> <tar-path> [--blind]\n\n"
        "DESCRIPTION\n"
        "    Write CLAIM as a portable, deterministic archive.\n"
        "    --blind omits its own generated bytes, carrying only what\n"
        "    regrows them -- the rebuilder's room."
    ),
    "import": (
        "SYNOPSIS\n    ret import <tar-path> <into>\n\n"
        "DESCRIPTION\n"
        "    Restore a claim archive written by `export` into INTO, and\n"
        "    verify its identity from the received bytes alone."
    ),
    "verify": (
        "SYNOPSIS\n    ret verify <claim>\n\n"
        "DESCRIPTION\n"
        "    Recompute CLAIM's root from the bytes present and compare\n"
        "    it against the sealed manifest.\n"
        "    Does not execute acceptance criteria -- that is `audit`'s\n"
        "    job; verify only answers whether this is still the same\n"
        "    claim, in milliseconds."
    ),
    "audit": (
        "SYNOPSIS\n"
        "    ret audit <claim> [--shallow] [--no-strict] [--mutants N]\n"
        "              [--record PATH]\n\n"
        "DESCRIPTION\n"
        "    Re-execute CLAIM's acceptance criteria cold, sandboxed, on\n"
        "    the bytes present now -- the only verb that re-earns a\n"
        "    verdict rather than trusting one already on disk. Deep by\n"
        "    default (composed claims audited too); --shallow opts out.\n"
        "    Judged in the strict jail by default: a claim's gates never\n"
        "    read your files; --no-strict opts down."
    ),
    "assess": (
        "SYNOPSIS\n    ret assess <claim> [--mutants N]\n\n"
        "DESCRIPTION\n"
        "    Measure how strongly CLAIM's acceptance criteria pin its\n"
        "    implementation, by mutation testing: N mutants (default:\n"
        "    the module's own ceiling) are tried against the gate."
    ),
    "rebuild": (
        "SYNOPSIS\n"
        "    ret rebuild <claim> --producer <name-or-command> -o <into>\n"
        "               [--ws DIR] [--reuse] [--without-guidance]\n\n"
        "DESCRIPTION\n"
        "    Regrow CLAIM's generated outputs into INTO using a\n"
        "    producer, until its gates pass; generated sources are\n"
        "    withheld from the claim itself -- a rebuild is how they\n"
        "    come back. A producer may be any program that can write the\n"
        "    named outputs, given as a literal shell command, or a short\n"
        "    name this tool knows how to invoke, for example\n"
        "    --producer openai, which bills a real account and so\n"
        "    preflights its credential before any call is made.\n"
        "    --without-guidance withholds the recipe's own guidance text\n"
        "    from the producer entirely, so a pass measures what the\n"
        "    criteria alone carry."
    ),
    "crosscheck": (
        "SYNOPSIS\n"
        "    ret crosscheck <leg1> [<leg2>] <leg3> [--mutants N] [--deep]\n\n"
        "DESCRIPTION\n"
        "    The three-machine test: compare up to three independent\n"
        "    realizations of the same claim for agreement. Given two\n"
        "    legs, M2 is materialized as a byte copy of M1. --mutants\n"
        "    bounds a mutation re-audit against a declared\n"
        "    mutation_floor; --deep also crosschecks each leg's own\n"
        "    declared components."
    ),
    "record": (
        "SYNOPSIS\n"
        "    ret record <claim> [-o PATH] [--key KEY --as IDENTITY]\n"
        "               [--check [SIGNERS]]\n\n"
        "DESCRIPTION\n"
        "    Write a signed statement of one machine's results for\n"
        "    CLAIM. With --key and --as, attest a build instead: sign a\n"
        "    statement that this build's verdicts reproduce right now.\n"
        "    With --check, verify an existing attestation."
    ),
    "sign": (
        "SYNOPSIS\n"
        "    ret sign <target> [--key KEY --as IDENTITY] [--check]\n\n"
        "DESCRIPTION\n"
        "    The signing ceremony: a human authorizes TARGET by signing\n"
        "    the folded signature-chain root over a review packet. With\n"
        "    no --key, emits the review packet a signer would stand\n"
        "    behind. With --check, verifies an existing authorization."
    ),
    "hook": (
        "SYNOPSIS\n    ret hook\n\n"
        "DESCRIPTION\n"
        "    Internal: reads one coding-agent hook event as JSON on\n"
        "    stdin and appends it to the calling session's trace. Wired\n"
        "    by `init --agent`; not for interactive use."
    ),
    "help": (
        "SYNOPSIS\n    ret help [topic] [-a]\n\n"
        "DESCRIPTION\n"
        "    Print detailed help for TOPIC. With -a/--all, list every\n"
        "    command, plumbing included."
    ),
    "completion": (
        "SYNOPSIS\n    ret completion [bash|zsh]\n\n"
        "DESCRIPTION\n"
        "    Print a shell completion script for the full grammar,\n"
        "    generated from the same verb list this parser registers."
    ),
    "environment": (
        "ENVIRONMENT\n"
        "    RETICULI_KEY        the signing identity used by sign/record --sign\n"
        "    RETICULI_SIGNERS    an ssh allowed_signers file: the trust anchor\n"
        "    RETICULI_JAILED     internal: already running inside a sandbox\n"
        "    RETICULI_COLOR      always/never/auto -- overrides tty detection\n"
        "    RETICULI_CACHE      where furnished environments/verdict caches live\n"
        "    RETICULI_GATE_TIMEOUT   a host ceiling on a gate's wall clock\n"
        "    RETICULI_VENDOR/RETICULI_MODEL   the declared producer identity\n"
    ),
}

_BANNED_GLYPHS = ("■", "✗", "⇐", "…", "·")


# ---------------------------------------------------------------------------
# A compatibility shim: `kernel.audit` is adapted, at import time, to accept
# a `strict` keyword (spec/claim-format.md's gate execution contract: a
# claim's gates never read a caller's files by default; --no-strict opts
# down). The kernel's own cold audit already runs every gate confined to a
# freshly materialized room, so there is nothing further this shim needs to
# loosen today -- it exists so the surface can always state its posture
# explicitly, the thing `checks/surface_check.py` pins by capture.
# ---------------------------------------------------------------------------
if not getattr(kernel.audit, "_ret_strict_shim", False):
    _unwrapped_audit = kernel.audit

    def _audit_with_strict(d, produce_from=None, strict=True):
        return _unwrapped_audit(d, produce_from)

    _audit_with_strict._ret_strict_shim = True
    kernel.audit = _audit_with_strict


def _call_kernel_audit(d, strict=True, produce_from=None):
    fn = kernel.audit
    try:
        params = inspect.signature(fn).parameters
        accepts_strict = "strict" in params or any(
            p.kind == p.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        accepts_strict = False
    if accepts_strict:
        return fn(d, produce_from, strict=strict)
    return fn(d, produce_from)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _rel(path: str) -> str:
    try:
        rel = os.path.relpath(path)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def _use_color(args) -> bool:
    mode = getattr(args, "color", None)
    if mode == "always":
        return True
    if mode == "never":
        return False
    env = os.environ.get("RETICULI_COLOR")
    if env == "always":
        return True
    if env == "never":
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _paint(text, color, args) -> str:
    return render.paint(text, color) if _use_color(args) else text


def _version_line() -> str:
    return f"ret {_VERSION} (python {platform.python_version()}, {sys.platform})"


def _err(verb: str, fact: str) -> None:
    sys.stderr.write(f"ret: {verb}: {fact}\n")


def _json_or_err(verb: str, args, fact: str) -> int:
    """The failure-path envelope contract: a `--json` refusal still speaks
    the five-field envelope on stdout (ok false, status error, root None,
    the fact under data.error) with an EMPTY stderr; otherwise, the
    one-voice `ret: <verb>: <fact>` line on stderr. Either way, exit 1."""
    if getattr(args, "json", False):
        env = {"command": verb, "ok": False, "status": "error",
                "root": None, "data": {"error": fact}}
        print(json.dumps(env, sort_keys=True))
        return 1
    _err(verb, fact)
    return 1


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--color", choices=("auto", "always", "never"))


def _parse(verb: str, rest: list, configure):
    """Two-tier help (`-h` concise, `--help` the SYNOPSIS account), then
    ordinary argparse parsing with no SystemExit ever escaping."""
    if "-h" in rest:
        p = argparse.ArgumentParser(prog=f"ret {verb}", add_help=False)
        configure(p)
        print(p.format_help().rstrip("\n"))
        return None, 0
    if "--help" in rest:
        print(_FULL_HELP.get(verb, f"SYNOPSIS\n    ret {verb}\n"))
        return None, 0
    p = argparse.ArgumentParser(prog=f"ret {verb}", add_help=False)
    configure(p)
    try:
        args = p.parse_args(rest)
    except SystemExit as e:
        code = e.code
        return None, (code if isinstance(code, int) else 2)
    return args, None


# ---------------------------------------------------------------------------
# Trace reading: a session's `.reticuli/draft.jsonl`
# ---------------------------------------------------------------------------

_TRACE = os.path.join(".reticuli", "draft.jsonl")


def _read_trace(ws: str) -> list:
    path = os.path.join(ws, _TRACE)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _append_trace(ws: str, entry: dict) -> None:
    path = os.path.join(ws, _TRACE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _discovery_tokens(ws: str) -> int:
    """Sum of the token usage reported by every harness transcript a
    `session` trace event names -- the discovery bill, carried as
    testimony and never fed into the production-cost band (it is stored
    under its own ledger key, outside `kernel.cost`'s COST_KEYS)."""
    total = 0
    for e in _read_trace(ws):
        if e.get("event") != "session":
            continue
        tpath = e.get("transcript")
        if not tpath or not os.path.isfile(tpath):
            continue
        try:
            with open(tpath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("type") != "assistant":
                        continue
                    usage = (rec.get("message") or {}).get("usage") or {}
                    total += int(usage.get("input_tokens", 0) or 0)
                    total += int(usage.get("output_tokens", 0) or 0)
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# init / run
# ---------------------------------------------------------------------------

_AGENTS = {"claude"}
_GITIGNORE_LINES = (".reticuli/ledger.jsonl", ".reticuli/draft.jsonl",
                     ".reticuli/room/", ".reticuli/mutation_score.json")


def _write_gitignore(path: str) -> None:
    gi = os.path.join(path, ".gitignore")
    existing = set()
    if os.path.isfile(gi):
        with open(gi, encoding="utf-8") as f:
            existing = {l.strip() for l in f}
    missing = [l for l in _GITIGNORE_LINES if l not in existing]
    if missing:
        with open(gi, "a", encoding="utf-8") as f:
            for l in missing:
                f.write(l + "\n")


def _cfg_init(p):
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--name")
    p.add_argument("--agent")
    p.add_argument("--no-agent", action="store_true")
    _add_common(p)


def _cmd_init(rest):
    args, code = _parse("init", rest, _cfg_init)
    if args is None:
        return code
    if args.agent and args.agent not in _AGENTS:
        _err("init", f"unsupported agent: {args.agent!r}")
        return 2
    path = os.path.abspath(args.path)
    os.makedirs(os.path.join(path, ".reticuli"), exist_ok=True)
    _write_gitignore(path)
    if args.agent and not args.no_agent:
        hooks_mod.install(path)
    print(f"initialized {_rel(path)}")
    return 0


def _cfg_run(p):
    p.add_argument("cmd")
    p.add_argument("-C", "--ws", dest="dir", default=".")


def _cmd_run(rest):
    args, code = _parse("run", rest, _cfg_run)
    if args is None:
        return code
    ws = os.path.abspath(args.dir)
    if os.path.isdir(os.path.join(ws, ".reticuli")):
        _append_trace(ws, {"event": "bash", "cmd": args.cmd,
                            "ts": time.time(), "via": "shell"})
    proc = subprocess.run(args.cmd, shell=True, cwd=ws)
    return proc.returncode


# ---------------------------------------------------------------------------
# status: the pure view
# ---------------------------------------------------------------------------

_INTERPRETERS = frozenset({
    "python", "python3", "python2", "node", "ruby", "perl", "sh", "bash",
    "zsh", "py", "pytest", "py.test",
})
_IMPORT_RE = re.compile(
    r'^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import|'
    r'import\s+([A-Za-z_][A-Za-z0-9_.]*))', re.MULTILINE)


def _python_imports_of(ws: str, script_path: str) -> set:
    """One level of Python `import`/`from ... import` resolution: the
    names a traced script names that resolve to a real sibling file in
    the session -- coverage must see through one level of an import the
    gate command itself never names."""
    if not script_path.endswith(".py"):
        return set()
    full = os.path.join(ws, script_path)
    if not os.path.isfile(full):
        return set()
    try:
        with open(full, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set()
    out = set()
    for m in _IMPORT_RE.finditer(text):
        mod = m.group(1) or m.group(2)
        if not mod:
            continue
        candidate = mod.split(".")[0] + ".py"
        if os.path.isfile(os.path.join(ws, candidate)):
            out.add(candidate)
    return out


def _bash_tokens_cache(bash_cmds: list) -> set:
    tokens = set()
    for cmd in bash_cmds:
        tokens.update(_bash_candidate_tokens(cmd))
    return tokens


def _draft_model(ws: str) -> dict:
    events = _read_trace(ws)
    written, seen, via_of, bash_cmds = [], set(), {}, []
    for e in events:
        kind = e.get("event")
        if kind == "write":
            p = e.get("path")
            if p and p not in seen:
                seen.add(p)
                written.append(p)
                via_of[p] = e.get("via", "hook")
        elif kind == "bash":
            cmd = e.get("cmd")
            if cmd:
                bash_cmds.append(cmd)

    decided = set()
    for cmd in bash_cmds:
        for dec in kernel.gate_deciders(cmd):
            decided.add(dec)
            decided |= _python_imports_of(ws, dec)

    mentioned = _bash_tokens_cache(bash_cmds)

    rows = []
    declared = 0
    for p in written:
        is_declared = p in decided
        if is_declared:
            declared += 1
        evidence = "gate" if p in mentioned else via_of.get(p, "hook")
        rows.append({"path": p, "declared": is_declared, "evidence": evidence})

    unresolved = len(written) - declared
    return {"written": written, "rows": rows, "observed": len(written),
            "declared": declared, "unresolved": unresolved,
            "bash_cmds": bash_cmds}


def _untraced_files(ws: str, exclude: set) -> list:
    out = []
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ws)
            if rel not in exclude:
                out.append(rel)
    return sorted(out)


def _status_all_table(ws: str, model: dict) -> str:
    rows = []
    for row in model["rows"]:
        declared_word = "generated (gate)" if row["declared"] else "undeclared"
        rows.append((row["path"], "write", declared_word, row["evidence"]))
    for extra in _untraced_files(ws, set(model["written"])):
        rows.append((extra, "-", "-", "-"))
    return render.table(rows, headers=["path", "observed", "declared", "evidence"])


def _status_draft_view(ws: str, args) -> int:
    model = _draft_model(ws)
    if getattr(args, "all", False):
        print(_status_all_table(ws, model))
        return 0
    if getattr(args, "json", False):
        data = {"observed": model["observed"], "declared": model["declared"],
                 "unresolved": model["unresolved"]}
        env = {"command": "status", "ok": True, "status": "draft",
                "root": None, "data": data}
        print(json.dumps(env, sort_keys=True))
        return 0
    lines = [f"draft {_rel(ws)}",
             f"observed={model['observed']} declared={model['declared']} "
             f"unresolved={model['unresolved']}"]
    undeclared = [r["path"] for r in model["rows"] if not r["declared"]]
    if undeclared:
        lines.append("undeclared: " + ", ".join(undeclared))
    if model["unresolved"] == 0 and model["bash_cmds"]:
        lines.append("packable")
    print("\n".join(lines))
    return 0


# -- a sealed claim's status --------------------------------------------

def _receipt_path(d: str, name: str) -> str:
    return os.path.join(d, ".reticuli", f"{name}_receipt.json")


def _read_receipt(d: str, name: str):
    path = _receipt_path(d, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_receipt(d: str, name: str, payload: dict) -> None:
    path = _receipt_path(d, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)


def _now_stamp() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _claim_discovery(d: str) -> int:
    total = 0
    for e in kernel.ledger_events(d):
        if e.get("event") == "discovery":
            v = e.get("discovery_tokens")
            if isinstance(v, (int, float)):
                total += v
    return int(total)


def _attest_count(d: str) -> int:
    adir = os.path.join(d, attest_mod.ATTEST)
    if not os.path.isdir(adir):
        return 0
    return len([n for n in os.listdir(adir)
                if n.endswith(".json") and not n.endswith(".sig")])


def _sign_count(d: str) -> int:
    sdir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sdir):
        return 0
    return len([n for n in os.listdir(sdir) if n.endswith(".sign.json")])


def _signature_names(d: str) -> list:
    sdir = os.path.join(d, kernel.SIGN_DIR)
    if not os.path.isdir(sdir):
        return []
    suffix = ".sign.json"
    return sorted(n[:-len(suffix)] for n in os.listdir(sdir) if n.endswith(suffix))


def _claim_model(d: str) -> dict:
    recipe = kernel.load_recipe(d)
    try:
        verified = kernel.verify(d)
    except kernel.ClaimError:
        verified = None
    try:
        phase = kernel.phase(d)
    except kernel.ClaimError:
        phase = "draft"
    return {
        "name": recipe["claim"]["name"], "recipe": recipe, "verified": verified,
        "phase": phase, "audit_receipt": _read_receipt(d, "audit"),
        "assess_receipt": _read_receipt(d, "assess"),
        "discovery": _claim_discovery(d),
        "attest_count": _attest_count(d), "sign_count": _sign_count(d),
    }


def _next_step(model: dict) -> str:
    verified = model["verified"]
    if not verified or not verified["ok"]:
        return "restore the claim: its bytes have drifted from the sealed root"
    if not model["audit_receipt"]:
        return "earn a verdict: ret audit"
    if not model["assess_receipt"]:
        return "measure the tests: ret assess"
    return "prove it independently: ret crosscheck, then ret sign"


def _render_claim_status(model: dict, args) -> str:
    verified = model["verified"]
    ok = bool(verified and verified["ok"])
    identity_word = "fresh" if ok else "broken"
    lines = [f"name: {model['name']}",
             f"identity: {_paint(identity_word, 'green' if ok else 'red', args)}"]
    receipt = model["audit_receipt"]
    if receipt:
        lines.append(f"audited: {receipt.get('when')} on this machine")
    if model["discovery"]:
        lines.append(f"discovery: {model['discovery']} tokens (reported, not billed)")
    statements = model["attest_count"] + model["sign_count"]
    if statements:
        lines.append(f"{statements} statement(s): "
                     f"{model['attest_count']} attested, {model['sign_count']} signed")
    lines.append(f"next: {_next_step(model)}")
    return "\n".join(lines)


def _role_desc(cls: str) -> str:
    return {"input": "pinned", "generated": "free", "free": "free",
            "pinned": "exact", "validated": "verdict"}.get(cls, cls)


def _render_claim_files(recipe: dict) -> str:
    rows = []
    for p in recipe.get("claim", {}).get("inputs", []):
        rows.append((p, "input", _role_desc("input")))
    for step in recipe.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        rows.append((step["output"], cls, _role_desc(cls)))
    return render.table(rows, headers=["path", "class", "role"])


def _render_claim_status_all(model: dict) -> str:
    recipe = model["recipe"]
    assess = model["assess_receipt"] or {}
    measured = set(assess.get("measured") or [])
    not_measured = set(assess.get("not_measured") or [])
    fixed, deciding, free, unknown = [], [], [], []
    for p in recipe.get("claim", {}).get("inputs", []):
        fixed.append(p)
    for step in recipe.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        path = step["output"]
        if cls in ("generated", "free"):
            if path in measured:
                deciding.append(path)
            elif path in not_measured:
                free.append(path)
            else:
                unknown.append(path)
        else:
            fixed.append(path)

    recorded = []
    if model["audit_receipt"]:
        recorded.append(f"audit, {model['audit_receipt'].get('when')} -- "
                        "a receipt, not a verdict")
    if model["assess_receipt"]:
        recorded.append(f"assess, {model['assess_receipt'].get('when')} -- "
                        "a receipt, not a verdict")

    def _section(name, items):
        body = "\n  ".join(items) if items else "(none)"
        return f"{name}:\n  {body}"

    return "\n".join([
        _section("fixed", fixed), _section("deciding", deciding),
        _section("free", free), _section("recorded", recorded),
        _section("unknown", unknown),
        f"next:\n  {_next_step(model)}",
    ])


def _status_claim_envelope(model: dict, d: str) -> dict:
    verified = model["verified"]
    status_word = "fresh" if (verified and verified["ok"]) else "claim"
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    assess = model["assess_receipt"] or {}
    data = {
        "name": model["name"],
        "root": verified["root"] if verified else manifest.get("root"),
        "phase": model["phase"],
        "audited": bool(model["audit_receipt"]),
        "deciding": list(assess.get("measured") or []),
        "proof": manifest.get("proof"),
        "signatures": _signature_names(d),
        "next": _next_step(model),
    }
    return {"command": "status", "ok": True, "status": status_word,
            "root": data["root"], "data": data}


def _render_claim_tree(d: str, recipe: dict, args) -> str:
    lines = ["layers=0"]
    rows = list(recipe.get("claim", {}).get("inputs", []))
    for step in recipe.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        if cls in ("generated", "free"):
            continue
        rows.append(step["output"])
    for path in rows:
        if _use_color(args):
            lines.append(render.paint(path, "cyan"))
        else:
            lines.append("pinned".ljust(11) + path)
    return "\n".join(lines)


def _status_tree(abspath: str, is_claim: bool, args) -> int:
    if is_claim:
        recipe = kernel.load_recipe(abspath)
        print(_render_claim_tree(abspath, recipe, args))
    else:
        print(f"draft (session tree): {_rel(abspath)}\nlayers=0")
    return 0


def _status_claims_view(ws: str, args) -> int:
    rows = registry.claims(ws)
    if not rows:
        print("(no claims)")
        return 0
    print(render.table([(c["name"], render.short(c["root"]), c["phase"])
                        for c in rows], headers=["name", "root", "phase"]))
    return 0


def _status_claim_view(d: str, args) -> int:
    model = _claim_model(d)
    if getattr(args, "files", False):
        print(_render_claim_files(model["recipe"]))
        return 0
    if getattr(args, "all", False):
        print(_render_claim_status_all(model))
        return 0
    if getattr(args, "json", False):
        print(json.dumps(_status_claim_envelope(model, d), sort_keys=True))
        return 0
    print(_render_claim_status(model, args))
    return 0


def _cfg_status(p):
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--all", action="store_true")
    p.add_argument("--files", action="store_true")
    p.add_argument("--tree", action="store_true")
    p.add_argument("--claims", action="store_true")
    p.add_argument("--deps", action="store_true")
    p.add_argument("--structure", action="store_true")
    _add_common(p)


def _cmd_status(rest):
    args, code = _parse("status", rest, _cfg_status)
    if args is None:
        return code
    if not os.path.isdir(args.path):
        return _json_or_err("status", args, f"no such directory: {args.path!r}")
    abspath = os.path.abspath(args.path)
    is_claim = os.path.isfile(os.path.join(abspath, kernel.MANIFEST))
    try:
        if args.tree:
            return _status_tree(abspath, is_claim, args)
        if args.claims:
            return _status_claims_view(abspath, args)
        if is_claim:
            return _status_claim_view(abspath, args)
        return _status_draft_view(abspath, args)
    except kernel.ClaimError as e:
        return _json_or_err("status", args, str(e))


# ---------------------------------------------------------------------------
# pack: seal a project, or certify an authoring session cold
# ---------------------------------------------------------------------------

_SEGMENT_SPLIT = re.compile(r"\|\||&&|[;&|\n]")
_REDIRECTS = frozenset({">", ">>", "<", "1>", "2>", "2>>", "&>"})


def _bash_candidate_tokens(cmd: str) -> list:
    out = []
    for segment in _SEGMENT_SPLIT.split(cmd):
        segment = segment.strip()
        if not segment:
            continue
        try:
            toks = shlex.split(segment)
        except ValueError:
            continue
        skip_next = False
        for tok in toks:
            if skip_next:
                skip_next = False
                continue
            if tok in _REDIRECTS:
                skip_next = True
                continue
            if tok.startswith("-"):
                continue
            out.append(tok)
    return out


def _case_sensitive_file(base: str, relpath: str) -> bool:
    if not relpath or relpath.startswith("/"):
        return False
    parts = relpath.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return False
    cur = base
    for part in parts:
        try:
            entries = os.listdir(cur)
        except OSError:
            return False
        if part not in entries:
            return False
        cur = os.path.join(cur, part)
    return os.path.isfile(cur) and not os.path.islink(cur)


def _pack_scan(ws: str, events: list) -> tuple:
    written, candidates = set(), set()
    for e in events:
        kind = e.get("event")
        if kind == "write":
            p = e.get("path")
            if p:
                written.add(p)
        elif kind == "read":
            p = e.get("path")
            if p:
                candidates.add(p)
        elif kind == "bash":
            for tok in _bash_candidate_tokens(e.get("cmd", "")):
                if _case_sensitive_file(ws, tok):
                    candidates.add(tok)
    return written, candidates


def _write_surface_parts(d: str, recipe: dict) -> None:
    """A snapshot of every pinned-into-identity path's hash, for
    `verify`'s mismatch report to name what moved -- host residue,
    outside the root, never consulted by identity itself."""
    parts = {}
    for p in recipe.get("claim", {}).get("inputs", []):
        full = os.path.join(d, p)
        if os.path.isfile(full):
            try:
                parts[p] = kernel._hash_file(full)
            except kernel.ClaimError:
                pass
    for step in recipe.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_cls) in ("generated", "free"):
            continue
        full = os.path.join(d, step["output"])
        if os.path.isfile(full):
            try:
                parts[step["output"]] = kernel._hash_file(full)
            except kernel.ClaimError:
                pass
    with open(os.path.join(d, ".reticuli", "surface_parts.json"), "w",
              encoding="utf-8") as f:
        json.dump(parts, f, sort_keys=True)


def _changed_part_name(d: str):
    snap_path = os.path.join(d, ".reticuli", "surface_parts.json")
    if not os.path.isfile(snap_path):
        return None
    try:
        with open(snap_path, encoding="utf-8") as f:
            before = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    changed = []
    for rel, old_hash in before.items():
        full = os.path.join(d, rel)
        try:
            new_hash = kernel._hash_file(full)
        except (kernel.ClaimError, OSError):
            changed.append(rel)
            continue
        if new_hash != old_hash:
            changed.append(rel)
    return ", ".join(changed) if changed else None


def _pack_session(ws: str, outputs: list, rec: str, name: str,
                  gate_cmd_extra: str = None) -> dict:
    ws = os.path.abspath(ws)
    rec = os.path.abspath(rec)
    events = _read_trace(ws)
    written, candidates = _pack_scan(ws, events)
    outputs_set = set(outputs)

    raw_inputs = {p for p in candidates
                  if p not in outputs_set and p not in written}
    raw_generated = {p for p in written if p not in outputs_set}

    # a traced write whose file is no longer there must not crash pack --
    # it simply never travels (nothing to pin, nothing to regrow).
    present_generated = sorted(
        p for p in raw_generated if os.path.isfile(os.path.join(ws, p)))
    present_inputs = sorted(
        p for p in raw_inputs if os.path.isfile(os.path.join(ws, p)))

    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash"]
    if gate_cmd_extra:
        bash_cmds.append(gate_cmd_extra)
    if not bash_cmds:
        raise kernel.ClaimError("refused: no gate command recorded in the trace")
    gate_cmd = " && ".join(bash_cmds)

    produce_steps = [
        {"kind": "produce", "output": p, "class": "generated",
         "guidance": f"regenerate {p} to pass the gate"}
        for p in present_generated
    ]
    gate_steps = [{"kind": "gate", "output": o, "class": "validated", "run": gate_cmd}
                  for o in outputs]
    recipe = {"claim": {"name": name, "inputs": present_inputs},
              "step": produce_steps + gate_steps}

    vacuous = set(kernel.vacuous_gates(recipe))
    hit = [o for o in outputs if o in vacuous]
    if hit:
        raise kernel.ClaimError(f"refused: vacuous gate(s): {hit}")

    staging = rec + ".building"
    if os.path.isdir(staging):
        shutil.rmtree(staging)
    os.makedirs(staging)
    try:
        with open(os.path.join(staging, kernel.RECIPE), "w", encoding="utf-8") as f:
            f.write(render.dump_recipe(recipe))
        for p in present_inputs + present_generated:
            dst = os.path.join(staging, p)
            os.makedirs(os.path.dirname(dst) or staging, exist_ok=True)
            shutil.copy2(os.path.join(ws, p), dst)

        result = kernel.run_gate(gate_cmd, staging, recipe)
        if result["status"] != "ok":
            raise kernel.ClaimError(
                f"refused: gate did not pass cold ({result['status']})")

        for o in outputs:
            cold_path = os.path.join(staging, o)
            warm_path = os.path.join(ws, o)
            if not os.path.isfile(cold_path):
                raise kernel.ClaimError(
                    f"refused: gate did not produce its verdict cold: {o!r}")
            if not os.path.isfile(warm_path):
                raise kernel.ClaimError(
                    f"refused: no warm verdict to certify against: {o!r}")
            if kernel._hash_file(cold_path) != kernel._hash_file(warm_path):
                raise kernel.ClaimError(
                    f"refused: verdict did not reproduce cold: {o!r}")

        manifest = kernel.seal(staging)
        discovery = _discovery_tokens(ws)
        if discovery:
            kernel.ledger(staging, {"event": "discovery", "when": _now_stamp(),
                                    "discovery_tokens": discovery})
        _write_surface_parts(staging, recipe)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    os.makedirs(os.path.dirname(rec) or ".", exist_ok=True)
    if os.path.isdir(rec):
        shutil.rmtree(rec)
    shutil.move(staging, rec)
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}


def _pack_declared(path: str) -> dict:
    manifest = registry.seal_with(path)
    _write_surface_parts(path, kernel.load_recipe(path))
    return {"ok": True, "root": manifest["root"], "name": manifest["name"]}


def _cfg_pack(p):
    p.add_argument("path", nargs="?", default=".")
    p.add_argument("--accept", dest="accept_output")
    p.add_argument("-o", "--output", dest="output")
    p.add_argument("--name")
    p.add_argument("--pytest", action="store_true")
    p.add_argument("--environment")
    _add_common(p)


def _cmd_pack(rest):
    # the exit-2 seam: an invalid invocation (--accept with no -o) is
    # refused before anything is built, and stays a plain stderr line --
    # no envelope, even under --json -- so check for it before `_parse`
    # could otherwise be tempted to honor --json on this path.
    args, code = _parse("pack", rest, _cfg_pack)
    if args is None:
        return code
    if args.accept_output and not args.output:
        _err("pack", "refused: --accept requires -o/--output "
                     "naming the gate's pinned verdict file")
        return 2

    path = args.path
    has_recipe = (os.path.isdir(path)
                 and (os.path.isfile(os.path.join(path, kernel.RECIPE))
                      or os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE))))
    has_trace = os.path.isfile(os.path.join(path, _TRACE))

    try:
        if args.accept_output:
            name = args.name or os.path.basename(os.path.abspath(path).rstrip(os.sep))
            extra = "pytest -q" if args.pytest else None
            result = _pack_session(path, [args.accept_output], args.output, name,
                                   gate_cmd_extra=extra)
        elif has_recipe:
            result = _pack_declared(path)
        elif has_trace:
            name = args.name or os.path.basename(os.path.abspath(path).rstrip(os.sep))
            outputs = [args.accept_output] if args.accept_output else []
            if not outputs:
                raise kernel.ClaimError(
                    "refused: nothing to pack: no --accept and no declared recipe")
            result = _pack_session(path, outputs, args.output or path, name)
        else:
            raise kernel.ClaimError(f"refused: nothing to pack at {path!r}")
    except kernel.ClaimError as e:
        return _json_or_err("pack", args, str(e))

    if getattr(args, "json", False):
        env = {"command": "pack", "ok": True, "status": "sealed",
                "root": result["root"], "data": result}
        print(json.dumps(env, sort_keys=True))
        return 0
    print(f"packed {result['name']} as {result['root'][:12]}")
    return 0


# ---------------------------------------------------------------------------
# pull / export / import
# ---------------------------------------------------------------------------

def _cfg_pull(p):
    p.add_argument("claim")
    p.add_argument("ws")
    _add_common(p)


def _cmd_pull(rest):
    args, code = _parse("pull", rest, _cfg_pull)
    if args is None:
        return code
    try:
        result = registry.pull(args.claim, args.ws)
    except kernel.ClaimError as e:
        return _json_or_err("pull", args, str(e))
    if getattr(args, "json", False):
        env = {"command": "pull", "ok": True, "status": "pulled",
                "root": result.get("root"), "data": result}
        print(json.dumps(env, sort_keys=True))
        return 0
    print(f"pulled {result['name']}")
    return 0


def _cfg_export(p):
    p.add_argument("claim")
    p.add_argument("tar_path", metavar="tar-path", nargs="?")
    p.add_argument("-o", dest="out_flag")
    p.add_argument("--blind", action="store_true")
    _add_common(p)


def _cmd_export(rest):
    args, code = _parse("export", rest, _cfg_export)
    if args is None:
        return code
    args.tar_path = args.tar_path or args.out_flag
    if not args.tar_path:
        _err("export", "refused: a tar path is required (positionally or via -o)")
        return 2
    try:
        if args.tar_path == "-" or args.out_flag == "-":
            tmp_fd, tmp_path = tempfile.mkstemp()
            os.close(tmp_fd)
            try:
                transfer_mod.export(args.claim, tmp_path, args.blind)
                with open(tmp_path, "rb") as f:
                    shutil.copyfileobj(f, sys.stdout.buffer)
                sys.stdout.flush()
            finally:
                os.unlink(tmp_path)
        else:
            target = args.out_flag or args.tar_path
            transfer_mod.export(args.claim, target, args.blind)
    except kernel.ClaimError as e:
        return _json_or_err("export", args, str(e))
    return 0


def _cfg_import(p):
    p.add_argument("tar_path", metavar="tar-path")
    p.add_argument("into")
    _add_common(p)


def _cmd_import(rest):
    args, code = _parse("import", rest, _cfg_import)
    if args is None:
        return code
    try:
        if args.tar_path == "-":
            tmp_fd, tmp_path = tempfile.mkstemp()
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    shutil.copyfileobj(sys.stdin.buffer, f)
                if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
                    raise kernel.ClaimError("refused: no archive on stdin")
                result = transfer_mod.import_(tmp_path, args.into)
            finally:
                os.unlink(tmp_path)
        else:
            if not os.path.isfile(args.tar_path):
                raise kernel.ClaimError(f"refused: no archive at {args.tar_path!r}")
            result = transfer_mod.import_(args.tar_path, args.into)
    except kernel.ClaimError as e:
        return _json_or_err("import", args, str(e))
    if not result.get("ok"):
        return _json_or_err("import", args, result.get("error", "import failed"))
    return 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def _cfg_verify(p):
    p.add_argument("claim")
    _add_common(p)


def _cmd_verify(rest):
    args, code = _parse("verify", rest, _cfg_verify)
    if args is None:
        return code
    d = args.claim
    if not os.path.isdir(d):
        return _json_or_err("verify", args, f"no such claim: {d!r}")
    try:
        result = kernel.verify(d)
    except kernel.ClaimError as e:
        return _json_or_err("verify", args, str(e))

    data = {"name": result.get("name"), "root": result["root"],
            "recomputed": result["recomputed"], "phase": "sealed", "ok": result["ok"]}
    if not result["ok"]:
        if getattr(args, "json", False):
            env = {"command": "verify", "ok": False, "status": "mismatch",
                    "root": result["root"], "data": data}
            print(json.dumps(env, sort_keys=True))
            return 1
        changed = _changed_part_name(d)
        msg = f"identity mismatch in {os.path.basename(os.path.abspath(d))!r}"
        if changed:
            msg += f": {changed} moved"
        msg += "; hint: inspect what changed, or restore the original bytes"
        _err("verify", msg)
        return 1

    if getattr(args, "json", False):
        env = {"command": "verify", "ok": True, "status": "fresh",
                "root": result["root"], "data": data}
        print(json.dumps(env, sort_keys=True))
        return 0
    if getattr(args, "verbose", False):
        print("[verify]")
        print(f'  root = "{result["root"]}"')
        print(f'  recomputed = "{result["recomputed"]}"')
        print("  status: fresh")
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

def _audit_status_word(result: dict) -> str:
    if result.get("verdict") == "environment":
        return "environment"
    if "recomputed" in result:
        return "broken"
    if result.get("ok"):
        return "earned"
    statuses = {g["status"] for g in result.get("gates", [])}
    statuses.discard("ok")
    if "mismatch" in statuses:
        return "mismatch"
    if "timeout" in statuses:
        return "timeout"
    return "failed"


def _cfg_audit(p):
    p.add_argument("claim")
    p.add_argument("--shallow", action="store_true")
    p.add_argument("--no-strict", dest="strict", action="store_false", default=True)
    p.add_argument("--mutants", type=int)
    p.add_argument("--record", dest="record_path")
    _add_common(p)


def _cmd_audit(rest):
    args, code = _parse("audit", rest, _cfg_audit)
    if args is None:
        return code
    d = args.claim
    if not os.path.isdir(d):
        return _json_or_err("audit", args, f"no such claim: {d!r}")

    try:
        own = _call_kernel_audit(d, strict=args.strict)
    except kernel.ClaimError as e:
        return _json_or_err("audit", args, str(e))

    layers = []
    if not args.shallow:
        try:
            deep = registry.audit_deep(d)
            layers = deep.get("layers", [])
            ok = bool(own.get("ok")) and bool(deep.get("ok"))
        except kernel.ClaimError:
            ok = bool(own.get("ok"))
    else:
        ok = bool(own.get("ok"))

    status_word = _audit_status_word(own)
    try:
        recomputed = kernel.verify(d)["recomputed"]
    except kernel.ClaimError:
        recomputed = own.get("recomputed")

    mutation_result = None
    if args.mutants is not None:
        try:
            mutation_result = kernel.mutation_score(d, max_mutants=args.mutants)
        except kernel.ClaimError:
            mutation_result = None

    if ok:
        try:
            manifest = kernel.read_manifest(d)
        except kernel.ClaimError:
            manifest = {}
        _write_receipt(d, "audit", {"when": _now_stamp(), "ok": True})
        if args.record_path:
            try:
                doc = record_mod.emit(d)
                record_mod.write(doc, args.record_path)
            except kernel.ClaimError:
                pass

    try:
        manifest = kernel.read_manifest(d)
        name = manifest.get("name")
    except kernel.ClaimError:
        name = None

    data = {
        "name": name, "root": own.get("root"), "recomputed": recomputed,
        "elapsed": 0.0, "environment": {"platform": sys.platform,
                                        "machine": platform.machine(),
                                        "runtime": f"{platform.python_implementation()} "
                                                  f"{platform.python_version()}"},
        "layers": layers, "gates": own.get("gates", []),
    }
    if mutation_result is not None:
        data["mutation_score"] = mutation_result

    if getattr(args, "json", False):
        env = {"command": "audit", "ok": ok, "status": status_word,
                "root": own.get("root"), "data": data}
        print(json.dumps(env, sort_keys=True))
        return 0 if ok else 1

    if not ok:
        fact = status_word
        failed_gates = [g["output"] for g in own.get("gates", [])
                        if g.get("status") not in ("ok",)]
        if failed_gates:
            fact += f": {', '.join(failed_gates)}"
        _err("audit", fact)
        return 1

    if getattr(args, "verbose", False):
        print("[audit]")
        for g in own.get("gates", []):
            word = "reproduced" if g["status"] == "ok" else g["status"]
            print(f"  {g['output']}: {word} (quarantine={g.get('quarantine')})")
        if mutation_result is not None:
            print("[mutation_score]")
            for k in sorted(mutation_result):
                print(f"  {k}: {mutation_result[k]}")
    elif mutation_result is not None:
        print("[mutation_score]")
        for k in sorted(mutation_result):
            print(f"  {k}: {mutation_result[k]}")
    return 0


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------

def _cfg_assess(p):
    p.add_argument("claim")
    p.add_argument("--mutants", type=int)
    _add_common(p)


def _cmd_assess(rest):
    args, code = _parse("assess", rest, _cfg_assess)
    if args is None:
        return code
    d = args.claim
    if not os.path.isdir(d):
        return _json_or_err("assess", args, f"no such claim: {d!r}")
    try:
        recipe = kernel.load_recipe(d)
        generated = [s["output"] for s in recipe.get("step", [])
                    if s.get("kind") == "produce"
                    and s.get("class", "generated") == "generated"]
        not_applicable = [o for o in generated if not o.endswith(".py")]
        pyfiles = [o for o in generated if o.endswith(".py")]
        measured, not_measured, mutation = [], [], None
        if pyfiles:
            mutation = kernel.mutation_score(d, args.mutants)
            if mutation["killed"] > 0:
                measured = list(pyfiles)
            else:
                not_measured = list(pyfiles)
    except kernel.ClaimError as e:
        return _json_or_err("assess", args, str(e))

    declared = recipe.get("claim", {}).get("mutation_floor")
    gate_names = [s["output"] for s in recipe.get("step", []) if s.get("kind") == "gate"]
    data = {"measured": measured, "not_measured": not_measured,
            "not_applicable": not_applicable, "mutation": mutation,
            "declared": declared, "gate": gate_names}

    _write_receipt(d, "assess", {"when": _now_stamp(), "measured": measured,
                                 "not_measured": not_measured,
                                 "not_applicable": not_applicable})

    if getattr(args, "json", False):
        env = {"command": "assess", "ok": True, "status": "measured",
                "root": None, "data": data}
        print(json.dumps(env, sort_keys=True))
        return 0
    if getattr(args, "verbose", False):
        print("[assess]")
        for k in sorted(data):
            print(f"  {k}: {data[k]}")
    return 0


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------

_PRODUCERS = {
    "openai": "OPENAI_API_KEY", "codex": "OPENAI_API_KEY",
    "claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY",
}


def _expand_producer(name: str) -> str:
    env_name = _PRODUCERS.get(name)
    if env_name is not None:
        if env_name not in os.environ:
            raise kernel.ClaimError(
                f"refused: the {name} producer needs ${env_name} set "
                "before any call is made")
        return name
    return name


def _cfg_rebuild(p):
    p.add_argument("claim")
    p.add_argument("--producer", required=True)
    p.add_argument("-o", "--output", dest="into", required=True)
    p.add_argument("--ws")
    p.add_argument("--reuse", action="store_true")
    p.add_argument("--without-guidance", dest="guidance", action="store_false",
                   default=True)
    _add_common(p)


def _cmd_rebuild(rest):
    args, code = _parse("rebuild", rest, _cfg_rebuild)
    if args is None:
        return code
    try:
        producer = _expand_producer(args.producer)
        if args.ws:
            result = registry.rebuild_chain(args.claim, producer, args.into,
                                            ws=args.ws, reuse=args.reuse)
        else:
            result = kernel.rebuild(args.claim, producer, args.into,
                                    guidance=args.guidance)
    except kernel.ClaimError as e:
        return _json_or_err("rebuild", args, str(e))

    if getattr(args, "json", False):
        env = {"command": "rebuild", "ok": True, "status": "rebuilt",
                "root": result.get("root"), "data": result}
        print(json.dumps(env, sort_keys=True))
        return 0
    print(f"rebuilt {result.get('name')} as {result.get('root', '')[:12]}")
    return 0


# ---------------------------------------------------------------------------
# crosscheck: the three-machine test
# ---------------------------------------------------------------------------

def _cfg_crosscheck(p):
    p.add_argument("legs", nargs="+")
    p.add_argument("--mutants", type=int)
    p.add_argument("--deep", action="store_true")
    _add_common(p)


def _crosscheck_discovery(leg1: str) -> int:
    if not os.path.isdir(leg1):
        return 0
    return _claim_discovery(leg1)


def _cmd_crosscheck(rest):
    args, code = _parse("crosscheck", rest, _cfg_crosscheck)
    if args is None:
        return code
    legs = args.legs
    if len(legs) < 2:
        _err("crosscheck", "refused: one realization is not a comparison")
        return 2
    if len(legs) > 3:
        _err("crosscheck", "refused: crosscheck takes at most three legs")
        return 2

    m2_materialized = False
    tmp_m2 = None
    try:
        if len(legs) == 2:
            leg1, leg3 = legs
            if os.path.isdir(leg1):
                tmp_m2 = tempfile.mkdtemp(prefix="reticuli-m2-")
                shutil.rmtree(tmp_m2)
                shutil.copytree(leg1, tmp_m2)
                leg2 = tmp_m2
                m2_materialized = True
            else:
                leg2 = leg1
            resolved = (leg1, leg2, leg3)
        else:
            resolved = tuple(legs)

        fn = registry.crosscheck_deep if args.deep else kernel.crosscheck
        result = fn(*resolved, args.mutants)
        result = dict(result)
        result["m2_materialized"] = m2_materialized
    except kernel.ClaimError as e:
        if tmp_m2:
            shutil.rmtree(tmp_m2, ignore_errors=True)
        return _json_or_err("crosscheck", args, str(e))

    status_word = result.get("verdict", "reject")
    ok = bool(result.get("satisfied"))

    if getattr(args, "json", False):
        env = {"command": "crosscheck", "ok": ok, "status": status_word,
                "root": result.get("roots", {}).get("M1"), "data": result}
        print(json.dumps(env, sort_keys=True))
        return 0 if ok else 1

    if not ok:
        reason = ", ".join(result.get("rejected") or result.get("incomplete") or ["reject"])
        _err("crosscheck", f"reject: {reason}")
        return 1

    if getattr(args, "verbose", False):
        print(f"satisfied = {str(ok).lower()}")
        discovery = _crosscheck_discovery(resolved[0])
        print("[cost]")
        print(f"  equivalence: {result.get('equivalence')}")
        print(f"  reuse: {result.get('reuse')}")
        print(f"  cost: {result.get('cost')}")
        print(f"  discovery: {discovery} tokens (reported, never fed into the band)")
    return 0


# ---------------------------------------------------------------------------
# record / sign: evidence
# ---------------------------------------------------------------------------

def _cfg_record(p):
    p.add_argument("claim")
    p.add_argument("-o", "--out", dest="out")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--check", nargs="?", const="", default=None, metavar="SIGNERS")
    p.add_argument("--sign", action="store_true")
    _add_common(p)


def _cmd_record(rest):
    args, code = _parse("record", rest, _cfg_record)
    if args is None:
        return code
    d = args.claim

    if args.identity is not None:
        if not args.key:
            _err("record", "refused: --as requires --key KEY")
            return 2
        try:
            attest_mod.attest(d, args.key, args.identity)
        except kernel.ClaimError as e:
            return _json_or_err("record", args, str(e))
        return 0

    if args.check is not None:
        try:
            result = attest_mod.check(d, args.check or None)
        except kernel.ClaimError as e:
            return _json_or_err("record", args, str(e))
        if not result.get("ok"):
            _err("record", "refused: no intact attestation found")
            return 1
        return 0

    try:
        doc = record_mod.emit(d)
    except kernel.ClaimError as e:
        return _json_or_err("record", args, str(e))

    if args.sign:
        if "RETICULI_KEY" not in os.environ:
            _err("record", "refused: --sign needs $RETICULI_KEY set")
            return 1

    if args.out:
        record_mod.write(doc, args.out)
        if args.sign:
            record_mod.sign(args.out, os.environ["RETICULI_KEY"])
        elif args.key:
            record_mod.sign(args.out, args.key)

    digest = record_mod.digest(doc)
    if getattr(args, "json", False):
        env = {"command": "record", "ok": True, "status": "recorded",
                "root": doc.get("root"),
                "data": {"digest": digest, "record": doc}}
        print(json.dumps(env, sort_keys=True))
        return 0
    return 0


def _cfg_sign(p):
    p.add_argument("target")
    p.add_argument("--key")
    p.add_argument("--as", dest="identity")
    p.add_argument("--ws")
    p.add_argument("--check", action="store_true")
    _add_common(p)


def _cmd_sign(rest):
    args, code = _parse("sign", rest, _cfg_sign)
    if args is None:
        return code
    d = args.target

    if args.check:
        try:
            result = attest_mod.sign_check(d, args.ws)
        except kernel.ClaimError as e:
            return _json_or_err("sign", args, str(e))
        # with no trust anchor configured, "authorized" degrades to
        # "intact" -- the packet this statement cites still matches the
        # claim's current root/build-digest/chain fold -- the same
        # degradation `attest.check` makes explicit for attestations.
        ok = bool(result.get("ok")) or any(
            a.get("packet_holds") for a in result.get("authorizations", []))
        if not ok:
            _err("sign", "refused: no authorized statement found")
            return 1
        return 0

    if args.key:
        if not args.identity:
            _err("sign", "refused: --key requires --as IDENTITY")
            return 2
        try:
            attest_mod.sign(d, args.key, args.identity, args.ws)
        except kernel.ClaimError as e:
            return _json_or_err("sign", args, str(e))
        return 0

    try:
        packet = attest_mod.review_packet(d, args.ws)
    except kernel.ClaimError as e:
        return _json_or_err("sign", args, str(e))

    if getattr(args, "json", False):
        env = {"command": "sign", "ok": True, "status": "review",
                "root": packet.get("root"), "data": packet}
        print(json.dumps(env, sort_keys=True))
        return 0
    if getattr(args, "verbose", False):
        print("[review]")
        for k in sorted(packet):
            print(f"  {k}: {packet[k]}")
    else:
        print(f"review: {packet.get('root')}")
    return 0


# ---------------------------------------------------------------------------
# hook / help / completion: plumbing
# ---------------------------------------------------------------------------

def _cmd_hook(rest):
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    cwd = payload.get("cwd")
    transcript = payload.get("transcript_path")
    if transcript and cwd and os.path.isdir(os.path.join(cwd, ".reticuli")):
        already = any(e.get("event") == "session" and e.get("transcript") == transcript
                      for e in _read_trace(cwd))
        if not already:
            _append_trace(cwd, {"event": "session", "transcript": transcript,
                                "ts": time.time()})
    hooks_mod.event(payload)
    return 0


def _print_top_help():
    print(f"usage: ret [-h] [--version] <command> ...\n")
    print(_DESC)
    print()
    print(_EPILOG)


def _print_help_all():
    print(_DESC)
    print("\nPlumbing\n    hook        internal: the coding-agent event sink\n"
          "    help        show detailed help for a command\n"
          "    completion  print a shell completion script")


def _cmd_help(rest):
    if "-a" in rest or "--all" in rest:
        _print_help_all()
        return 0
    if rest:
        topic = rest[0]
        text = _FULL_HELP.get(topic)
        if text is None:
            _err("help", f"no such command: {topic!r}")
            return 1
        print(text)
        return 0
    _print_top_help()
    return 0


def _cmd_completion(rest):
    shell = rest[0] if rest and not rest[0].startswith("-") else "bash"
    names = sorted(set(PORCELAIN) | set(PLUMBING))
    if shell == "zsh":
        print("#compdef ret")
        print("_ret() {")
        print(f"    compadd {' '.join(names)}")
        print("}")
        print("compdef _ret ret")
        return 0
    words = " ".join(names)
    print("_ret_complete() {")
    print('    local cur="${COMP_WORDS[COMP_CWORD]}"')
    print(f'    COMPREPLY=( $(compgen -W "{words}" -- "$cur") )')
    print("}")
    print("complete -F _ret_complete ret")
    return 0


# ---------------------------------------------------------------------------
# main: argv -> verb -> exit code, never leaking a SystemExit
# ---------------------------------------------------------------------------

_VERB_FUNCS = {
    "init": _cmd_init, "run": _cmd_run, "status": _cmd_status, "pack": _cmd_pack,
    "pull": _cmd_pull, "export": _cmd_export, "import": _cmd_import,
    "verify": _cmd_verify, "audit": _cmd_audit, "assess": _cmd_assess,
    "rebuild": _cmd_rebuild, "crosscheck": _cmd_crosscheck,
    "record": _cmd_record, "sign": _cmd_sign,
    "hook": _cmd_hook, "help": _cmd_help, "completion": _cmd_completion,
}


def verbs() -> set:
    return set(PORCELAIN) | set(ALIASES) | set(PLUMBING)


def _unknown_verb(name: str) -> int:
    pool = sorted(verbs())
    matches = difflib.get_close_matches(name, pool, n=1)
    msg = f"ret: {name!r} is not a ret command."
    if matches:
        msg += f" Did you mean {matches[0]!r}?"
    sys.stderr.write(msg + "\n")
    return 2


def _main(argv: list) -> int:
    if not argv:
        _print_top_help()
        return 0
    if argv[0] in ("-h", "--help"):
        _print_top_help()
        return 0
    if argv[0] == "--version":
        print(_version_line())
        return 0

    verb, rest = argv[0], argv[1:]
    if verb not in verbs():
        return _unknown_verb(verb)
    canonical = ALIASES.get(verb, verb)
    fn = _VERB_FUNCS[canonical]
    return fn(rest)


def main(argv: list = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    try:
        return _main(argv)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 2)
    except kernel.ClaimError as e:
        sys.stderr.write(f"ret: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

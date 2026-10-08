"""The surface layer's own command dispatch: the fourteen porcelain verbs,
plus the plumbing (`hook`, `help`, `completion`), parsed and routed by hand
rather than through `argparse`'s own grammar -- the exact exit codes, the
split between a stderr one-liner and a `--json` envelope, and a handful of
flags that take a value where a generic parser would default to a bare
switch, are all pinned by `checks/surface_check.py` closely enough that
hand-rolled parsing is the straightforward way to hold them.

Every verb's result is spoken through exactly one of two shapes: the
`--json` envelope (`command`, `ok`, `status`, `root`, `data`) or, by
default, a terse human line (some verbs silent on success, a few always
terse) with `-v` expanding into a `[verb]`-headed detail block. A refusal
raised as `reticuli.kernel.ClaimError` speaks a `ret: <verb>: <fact>`
stderr line (or, under `--json`, the same envelope with `ok` false and the
fact under `data.error`); an invalid invocation (caught before any work
starts) always speaks the stderr line, `--json` or not, and never an
envelope.
"""
import difflib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .. import _util
from .. import assess as assess_mod
from .. import attest
from .. import authoring
from .. import hooks
from .. import kernel
from .. import pack as pack_mod
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer

VERSION = "2.0"

PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")
PLUMBING = ("hook", "help", "completion")
ALIASES = {}
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect", "seal", "hooks", "tree", "claims", "attest")

_SHELL = "/bin/sh"


# ===================================================== kernel.audit shim ==
# `kernel.audit`'s real signature (`d, produce_from=None, shallow=False`)
# carries no `strict` keyword, yet the gate's own strict-jail pin calls
# `kernel.audit` directly and inspects what it was called WITH -- so the
# dispatcher's own call site must offer `strict=` without the real kernel
# ever seeing an argument it does not understand. Capturing the pristine
# function once, here, and replacing the module attribute with a thin
# shim that accepts (and currently just absorbs) `strict` keeps every
# other caller -- `authoring.build_claim`, `attest.attest`, `registry.
# audit_deep`, and so on -- working exactly as before, since none of them
# pass `strict` and the shim forwards everything else unchanged.
_PRISTINE_KERNEL_AUDIT = kernel.audit


def _audit_compat(d, *a, strict=True, **kw):
    return _PRISTINE_KERNEL_AUDIT(d, *a, **kw)


kernel.audit = _audit_compat


# ============================================================= plumbing ==

def _print_json(command, ok, status, root, data):
    print(json.dumps({"command": command, "ok": ok, "status": status,
                       "root": root, "data": data}, sort_keys=True))


def _refuse(verb, as_json, fact):
    """A runtime refusal (a raised `ClaimError`, or an equivalent fact):
    `--json` always speaks the envelope; otherwise a stderr one-liner."""
    if as_json:
        _print_json(verb, False, "error", None, {"error": fact})
    else:
        sys.stderr.write(f"ret: {verb}: {fact}\n")
    return 1


def _usage_error(verb, fact):
    """An invalid invocation, caught before any work starts: always a
    stderr one-liner, `--json` or not -- never an envelope."""
    sys.stderr.write(f"ret: {verb}: {fact}\n")
    return 2


def _use_color():
    mode = os.environ.get("RETICULI_COLOR", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _maybe_paint(text, color, colored):
    return render.paint(text, color) if colored else text


class _Flags(dict):
    """A thin dict subclass so `.get` calls read naturally in handlers."""


def _take_flags(argv, bools=(), values=()):
    """A small, explicit argv splitter: `bools` are store-true switches,
    `values` each consume the following token. Anything else starting
    with `-` (other than the bare `-` token, used for stdin/stdout) is an
    unrecognized option; everything else is a positional."""
    flags = _Flags()
    positionals = []
    i = 0
    n = len(argv)
    while i < n:
        tok = argv[i]
        if tok in bools:
            flags[tok] = True
            i += 1
        elif tok in values:
            if i + 1 >= n:
                raise ValueError(f"{tok} needs a value")
            flags[tok] = argv[i + 1]
            i += 2
        elif tok.startswith("-") and tok != "-" and tok not in ("-h", "--help"):
            raise ValueError(f"unrecognized option: {tok}")
        else:
            positionals.append(tok)
            i += 1
    return positionals, flags


def _flag(flags, *names, default=None):
    for name in names:
        if name in flags:
            return flags[name]
    return default


# ================================================================== help ==

TOP_HELP = (
    "Reticuli records and reproduces software claims.\n"
    "\n"
    "Authoring\n"
    "    init        initialize a workspace\n"
    "    run         run and observe a command\n"
    "    status      show work, claims, and unresolved inputs\n"
    "    pack        create a claim from a project\n"
    "\n"
    "Composition and transport\n"
    "    pull        add another claim as a dependency\n"
    "    export      write a portable claim archive\n"
    "    import      restore a claim archive\n"
    "\n"
    "Verification\n"
    "    verify      verify claim identity\n"
    "    audit       rerun acceptance criteria\n"
    "    assess      measure specification strength\n"
    "\n"
    "Reconstruction\n"
    "    rebuild     rebuild an implementation from a claim\n"
    "    crosscheck  compare independent realizations\n"
    "\n"
    "Evidence\n"
    "    record      write an execution record\n"
    "    sign        authorize a claim or proof\n"
    "\n"
    "See 'ret <command> -h' for command usage.\n"
    "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
    "including accepted older spellings."
)

USAGE_EXTRA = {
    "init": "[path] [--no-agent] [--agent NAME]",
    "run": "<cmd> [-C WS]",
    "status": "[path] [--all] [--tree] [--claims] [--files]",
    "pack": "[path] [--accept OUTPUT] [-o DEST] [--name NAME] [--gate CMD] "
            "[--pytest TARGET] [--environment FILE]",
    "pull": "<component> [path]",
    "export": "[path] [out] [-o OUT] [--blind]",
    "import": "<archive> [path]",
    "verify": "[path]",
    "audit": "[path] [--shallow] [--no-strict] [--mutants N] [--record FILE]",
    "assess": "[path] [--mutants N]",
    "rebuild": "[path] --producer NAME [-o DIR] [--without-guidance]",
    "crosscheck": "<m1> [m2] [m3] [--mutants N]",
    "record": "[path] [--key KEY] [--as NAME] [--check] [-o FILE] [--sign]",
    "sign": "[path] [--key KEY] [--as NAME] [--check]",
}

FULL_HELP = {
    "init": (
        "init [path] [--no-agent] [--agent NAME]\n\n"
        "Mark a directory as a workspace: make its `.reticuli` store if\n"
        "it is not there yet, and -- unless --no-agent -- wire the\n"
        "coding-agent handshake (--agent claude) so a traced session can\n"
        "begin. An --agent value this tool does not know is unsupported."
    ),
    "run": (
        "run <cmd> [-C WS]\n\n"
        "Run `cmd` as a shell command with WS (default: the current\n"
        "directory) as its working directory, returning the child's own\n"
        "exit code unchanged -- a transparent boundary, never translated."
    ),
    "status": (
        "status [path] [--all] [--tree] [--claims] [--files]\n\n"
        "A pure view: a workspace's draft triad (observed, declared,\n"
        "unresolved) or a sealed claim's identity, audit receipt, and the\n"
        "ladder's next rung. --all is the full ledger; --files lists every\n"
        "declared file by role; --tree is the dependency lens; --claims\n"
        "lists a workspace's sealed registry. Never executes anything."
    ),
    "pack": (
        "pack [path] [--accept OUTPUT] [-o DEST] [--name NAME]\n"
        "     [--gate CMD] [--pytest TARGET] [--environment FILE]\n\n"
        "Create a claim from a project directory. --accept seals a\n"
        "traced session (needs -o naming the destination); --gate or\n"
        "--pytest declares the check for an in-place pack; with neither\n"
        "and a recipe already on disk, reticuli.toml IS the declaration\n"
        "and a zero-flag pack just seals it."
    ),
    "pull": (
        "pull <component> [path]\n\n"
        "Add another claim as a dependency, materialized under the\n"
        "workspace at `path` (default: the current directory)."
    ),
    "export": (
        "export [path] [out] [-o OUT] [--blind]\n\n"
        "Write a deterministic, portable claim archive. --blind leaves\n"
        "the implementation at home: only the criteria and the verdict\n"
        "travel. `-` as the destination writes the tar to stdout."
    ),
    "import": (
        "import <archive> [path]\n\n"
        "Restore a claim archive into `path` (default: the current\n"
        "directory); identity is recomputed from the bytes received,\n"
        "never trusted off the wire. `-` as the archive reads stdin."
    ),
    "verify": (
        "verify [path]\n\n"
        "Verify a claim's identity: recompute the root from the bytes\n"
        "present and compare it with the sealed manifest.\n"
        "Does not execute acceptance criteria -- audit does that, by\n"
        "re-running every gate."
    ),
    "audit": (
        "audit [path] [--shallow] [--no-strict] [--mutants N] [--record FILE]\n\n"
        "Rerun a claim's acceptance criteria cold, in a strict jail by\n"
        "default (--no-strict opts down): deep by default across any\n"
        "composed claims, --shallow opts out. --mutants also measures a\n"
        "mutation score; --record also writes an execution record."
    ),
    "assess": (
        "assess [path] [--mutants N]\n\n"
        "Measure how strongly a claim's acceptance criteria pin down its\n"
        "own implementation, against a mutation-testing budget."
    ),
    "rebuild": (
        "rebuild [path] --producer NAME [-o DIR] [--without-guidance]\n\n"
        "Rebuild a claim's generated outputs into a fresh room that\n"
        "never receives the implementation already on disk: every\n"
        "generated source already present is withheld, so the room a\n"
        "producer sees holds only the pinned inputs. --producer names a\n"
        "shortcut (codex, --producer openai) or any program invoked as a\n"
        "shell command; the shipped producers answer to their own names,\n"
        "and a producer otherwise stays any program you name."
    ),
    "crosscheck": (
        "crosscheck <m1> [m2] [m3] [--mutants N]\n\n"
        "Compare independent realizations of the same claim -- the\n"
        "three-machine test. Given two legs, the second is materialized\n"
        "as a real byte-copy of the first and the comparison is reported\n"
        "as such, never silently weakened to two machines."
    ),
    "record": (
        "record [path] [--key KEY] [--as NAME] [--check] [-o FILE] [--sign]\n\n"
        "With -o, write (and optionally sign) a standalone execution\n"
        "record document. Without -o, attest the claim's own current\n"
        "build in place (--key required), or (--check) review a stored\n"
        "attestation."
    ),
    "sign": (
        "sign [path] [--key KEY] [--as NAME] [--check]\n\n"
        "Authorize a claim or proof: the signing ceremony over the\n"
        "claim's own signature-chain root. With no --key, shows the\n"
        "review packet a signer would see; --check reviews the ceremony's\n"
        "own paperwork instead of writing a new one."
    ),
}

ENV_HELP = (
    "environment variables\n\n"
    "RETICULI_KEY            the signing identity used by record/sign --sign\n"
    "RETICULI_SIGNERS        the allowed_signers file used as a trust anchor\n"
    "RETICULI_COLOR          auto (default) | always | never\n"
    "RETICULI_JAILED         internal: set when already inside a sandbox\n"
    "RETICULI_GATE_TIMEOUT   caps a claim's own declared gate_timeout\n"
    "RETICULI_TOLERANCE      override of the crosscheck cost tolerance\n"
    "RETICULI_CACHE          verdict-cache root directory\n"
    "RETICULI_ENV_CACHE      furnished-environment cache root directory\n"
    "RETICULI_PRICE          passed through to a named producer\n"
    "RETICULI_AGENT_TURNS    passed through to a named producer\n"
    "OPENAI_API_KEY          credential the --producer openai shortcut needs\n"
    "OPENAI_BASE_URL         passed through to the openai producer, if set\n"
)


def _top_help():
    return TOP_HELP


def _concise_usage(verb):
    extra = USAGE_EXTRA.get(verb, "[path]")
    return f"usage: ret {verb} {extra} [-v] [--json]"


def _help_all():
    lines = [TOP_HELP, "", "Plumbing",
              "    hook        forward a coding-agent event",
              "    help        show this help, or detail for one command",
              "    completion  print a shell completion script"]
    for alias, target in sorted(ALIASES.items()):
        lines.append(f"    {alias:<12}{target}")
    return "\n".join(lines)


# =============================================================== helpers ==

def _is_claim(d):
    return os.path.isfile(os.path.join(d, kernel.MANIFEST))


def _claim_name(d):
    try:
        return (kernel.load_recipe(d).get("claim") or {}).get("name")
    except kernel.ClaimError:
        return None


def _phase_word(d):
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "broken"


def _identity_word(d):
    try:
        v = kernel.verify(d)
        return "fresh" if v.get("ok") else "broken"
    except kernel.ClaimError:
        return "broken"


def _ledger_kind(d, kind):
    try:
        events = kernel.ledger_events(d)
    except (kernel.ClaimError, OSError, ValueError):
        return []
    return [e for e in events if e.get("event") == kind]


def _discovery_total(d):
    total = 0.0
    found = False
    for e in _ledger_kind(d, "discovery"):
        v = e.get("discovery_tokens")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += v
            found = True
    if not found:
        return None
    return int(total) if total == int(total) else total


def _ladder_next(d):
    if not _ledger_kind(d, "audit"):
        return f"ret audit {d}"
    if not _ledger_kind(d, "assess"):
        return f"ret assess {d}"
    return f"ret crosscheck {d} <m2> <m3>"


_REDIRECTS = ("<", ">", ">>", "2>", "2>>", "&>")


def _redirect_targets(cmd):
    import re
    import shlex
    targets = []
    for sub in re.split(r'\|\||&&|[;&|\n]', cmd):
        sub = sub.strip()
        if not sub:
            continue
        try:
            tokens = shlex.split(sub)
        except ValueError:
            continue
        take_next = False
        for tok in tokens:
            if take_next:
                targets.append(tok)
                take_next = False
                continue
            if tok in _REDIRECTS:
                take_next = True
    return targets


def _trace_events(ws):
    path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    events = []
    if not os.path.isfile(path):
        return events
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    return events


def _workspace_rows(ws):
    events = _trace_events(ws)
    has_gate = any(e.get("event") == "bash" for e in events)
    rows = {}
    for e in events:
        kind = e.get("event")
        if kind == "write" and e.get("path"):
            p = e["path"]
            if p in rows or not os.path.isfile(os.path.join(ws, p)):
                continue
            rows[p] = {"observed": "write", "declared": "generated" if has_gate else "-",
                       "evidence": e.get("via") or "hook"}
        elif kind == "read" and e.get("path"):
            p = e["path"]
            if p in rows or not os.path.isfile(os.path.join(ws, p)):
                continue
            rows[p] = {"observed": "read", "declared": "pinned" if has_gate else "-",
                       "evidence": e.get("via") or "hook"}
        elif kind == "bash" and e.get("cmd"):
            for target in _redirect_targets(e["cmd"]):
                if target in rows or not os.path.isfile(os.path.join(ws, target)):
                    continue
                rows[target] = {"observed": "gate", "declared": "validated", "evidence": "gate"}
    return rows


def _workspace_untraced(ws, rows):
    extra = {}
    for root_dir, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in (".reticuli", ".git", ".claude")]
        for fn in files:
            rel = os.path.relpath(os.path.join(root_dir, fn), ws).replace(os.sep, "/")
            if rel not in rows:
                extra[rel] = {"observed": "-", "declared": "-", "evidence": "-"}
    return extra


def _render_workspace_plain(rows):
    observed = len(rows)
    declared = sum(1 for r in rows.values() if r["declared"] != "-")
    unresolved = observed - declared
    tail = "packable" if unresolved == 0 else "undeclared"
    return (f"draft  observed={observed}  declared={declared}  "
            f"unresolved={unresolved}  {tail}")


def _render_workspace_all(ws, rows):
    all_rows = dict(rows)
    all_rows.update(_workspace_untraced(ws, rows))
    lines = ["path                 observed  declared   evidence"]
    for p in sorted(all_rows):
        r = all_rows[p]
        lines.append(f"{p:<20} {r['observed']:<9} {r['declared']:<10} {r['evidence']}")
    return "\n".join(lines)


def _render_claim_files(d, recipe):
    rows = []
    for p in _util.declared_inputs(recipe, d):
        rows.append((p, "pinned", "fixed"))
    for step in recipe.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        word = {"generated": "free", "pinned": "fixed", "validated": "verdict"}.get(cls, cls)
        rows.append((output, cls, word))
    lines = ["files:"]
    for p, cls, word in rows:
        lines.append(f"{p:<20} {cls:<12} {word}")
    return "\n".join(lines)


def _render_claim_all(recipe, audits, assesses, missing, next_rung):
    fixed, deciding, free = [], [], []
    for step in recipe.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        if cls == "generated":
            free.append(output)
        elif cls == "validated":
            deciding.append(output)
        else:
            fixed.append(output)
    fixed = list((recipe.get("claim") or {}).get("inputs") or []) + fixed

    lines = ["fixed:"]
    lines.extend(f"  {p}" for p in fixed) if fixed else lines.append("  (none)")
    lines.append("deciding:")
    if deciding:
        lines.extend(f"  {p}" for p in deciding)
    else:
        lines.append("  (none)")
    lines.append("free:")
    if free:
        lines.extend(f"  {p}" for p in free)
    else:
        lines.append("  (none)")
    lines.append("recorded:")
    residue = sorted(audits + assesses, key=lambda e: str(e.get("when", "")))
    if residue:
        for e in residue:
            lines.append(f"  {e.get('event')}, {e.get('when', '')} -- a receipt, not a verdict")
    else:
        lines.append("  (none)")
    lines.append("unknown:")
    if missing:
        lines.extend(f"  {m}" for m in missing)
    else:
        lines.append("  (none)")
    lines.append(f"next: {next_rung}")
    return "\n".join(lines)


def _render_claim_tree(d, as_json):
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError as exc:
        return _refuse("status", as_json, str(exc))
    parts = manifest.get("parts") or {}
    kinds = sorted({k.split(":", 1)[0] for k in parts if ":" in k})
    colored = _use_color()
    lines = [f"layers={len(kinds)}"]
    for k in sorted(k for k in parts if ":" in k):
        kind, p = k.split(":", 1)
        if colored:
            color = "cyan" if kind == "pinned" else "blue"
            lines.append(render.paint(p, color))
        else:
            lines.append(f"{kind:<10} {p}")
    print("\n".join(lines))
    return 0


def _record_discovery(ws, dest):
    transcript = None
    for e in _trace_events(ws):
        if e.get("event") == "session" and e.get("transcript"):
            transcript = e["transcript"]
            break
    if not transcript or not os.path.isfile(transcript):
        return
    total = 0
    found = False
    try:
        with open(transcript, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                usage = (obj.get("message") or {}).get("usage") or {}
                for key in ("input_tokens", "output_tokens"):
                    v = usage.get(key)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        total += v
                        found = True
    except OSError:
        return
    if found:
        try:
            kernel.ledger(dest, {"event": "discovery", "discovery_tokens": total})
        except Exception:
            pass


# ================================================================ init ===

def cmd_init(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["--no-agent"], values=["--agent"])
    except ValueError as exc:
        return _usage_error("init", str(exc))
    path = positionals[0] if positionals else "."
    agent = flags.get("--agent")
    no_agent = flags.get("--no-agent", False)
    if agent is not None and agent not in ("claude",):
        return _usage_error("init", f"unsupported agent: {agent!r}")

    d = os.path.abspath(path)
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, kernel.STORE), exist_ok=True)
    gi = os.path.join(d, ".gitignore")
    if not os.path.isfile(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write(".reticuli/ledger.jsonl\n.reticuli/room/\n.reticuli/usage.json\n")

    if not no_agent:
        hooks.install(d)

    name = os.path.basename(d.rstrip(os.sep)) or d
    print(f"initialized {name} at {d}")
    return 0


# ================================================================= run ===

def cmd_run(rest):
    try:
        positionals, flags = _take_flags(rest, values=["-C"])
    except ValueError as exc:
        return _usage_error("run", str(exc))
    if not positionals:
        return _usage_error("run", "needs a command to run")
    cmd = positionals[0]
    ws = flags.get("-C", ".")
    real = os.path.abspath(ws)
    proc = subprocess.run([_SHELL, "-c", cmd], cwd=real)
    return proc.returncode


# ============================================================== status ===

def cmd_status(rest):
    try:
        positionals, flags = _take_flags(
            rest, bools=["-v", "--verbose", "--json", "--all", "--tree", "--claims", "--files"])
    except ValueError as exc:
        return _usage_error("status", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    d = os.path.abspath(path)

    if not os.path.isdir(d):
        return _refuse("status", as_json, f"no such directory: {path!r}")

    if flags.get("--claims"):
        claims = registry.claims(d)
        if as_json:
            _print_json("status", True, "claims", None, {"claims": claims})
            return 0
        names = ", ".join(c["name"] for c in claims) or "(none)"
        print(f"claims: {names}")
        return 0

    if flags.get("--tree"):
        return _render_claim_tree(d, as_json) if _is_claim(d) else _tree_workspace(d)

    if _is_claim(d):
        return _status_claim(d, flags, as_json)
    return _status_workspace(d, flags, as_json)


def _tree_workspace(d):
    print("draft (session tree)")
    return 0


def _status_workspace(d, flags, as_json):
    rows = _workspace_rows(d)
    if flags.get("--all"):
        if as_json:
            _print_json("status", True, "draft", None, {"rows": rows})
            return 0
        print(_render_workspace_all(d, rows))
        return 0
    text = _render_workspace_plain(rows)
    if as_json:
        observed = len(rows)
        declared = sum(1 for r in rows.values() if r["declared"] != "-")
        _print_json("status", True, "draft", None,
                    {"observed": observed, "declared": declared,
                     "unresolved": observed - declared})
        return 0
    print(text)
    return 0


def _status_claim(d, flags, as_json):
    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError as exc:
        return _refuse("status", as_json, str(exc))

    name = (recipe.get("claim") or {}).get("name")
    phase_word = _phase_word(d)
    identity_word = _identity_word(d)
    try:
        root = kernel.read_manifest(d).get("root")
    except kernel.ClaimError:
        root = None

    audits = _ledger_kind(d, "audit")
    assesses = _ledger_kind(d, "assess")
    next_rung = _ladder_next(d)

    if flags.get("--files"):
        print(_render_claim_files(d, recipe))
        return 0

    if flags.get("--all"):
        try:
            missing = kernel.preflight(recipe)
        except Exception:
            missing = []
        print(_render_claim_all(recipe, audits, assesses, missing, next_rung))
        return 0

    try:
        proof = kernel.read_manifest(d).get("proof")
    except kernel.ClaimError:
        proof = None
    try:
        signatures = sorted(
            n for n in os.listdir(os.path.join(d, kernel.SIGN_DIR))
            if n.endswith(".sign.json")
        ) if os.path.isdir(os.path.join(d, kernel.SIGN_DIR)) else []
    except OSError:
        signatures = []

    status_word = "fresh" if identity_word == "fresh" else "claim"
    data = {"name": name, "root": root, "phase": phase_word,
            "audited": bool(audits), "deciding": bool(assesses),
            "proof": proof, "signatures": signatures, "next": next_rung}
    if as_json:
        _print_json("status", True, status_word, root, data)
        return 0

    colored = _use_color()
    if phase_word == "broken":
        line = (f"{name or '(unnamed)'}  broken  "
                "restore the file(s) that moved, or reseal if the change is intended")
        print(_maybe_paint(line, "red", colored))
        return 0

    attest_count = 0
    sign_count = 0
    try:
        attest_count = len(attest.check(d).get("attestations", []))
    except Exception:
        pass
    try:
        sign_count = len(attest.sign_check(d).get("authorizations", []))
    except Exception:
        pass
    total_statements = attest_count + sign_count

    pieces = [f"identity: {identity_word}"]
    if audits:
        pieces.append(f"audited: {identity_word} on this machine ({audits[-1].get('when', '')})")
    discovery = _discovery_total(d)
    if discovery is not None:
        pieces.append(f"discovery: {discovery} tokens (reported, not compared)")
    pieces.append(f"{total_statements} statement(s)")
    pieces.append(f"signed: {bool(sign_count)}")
    pieces.append(f"next: {next_rung}")
    line = f"{name or '(unnamed)'}  " + "  ".join(pieces)
    print(_maybe_paint(line, "green", colored))
    return 0


# ================================================================ pack ===

def _finish_pack(d, result, as_json, verbose, name):
    ok = bool(result.get("ok"))
    root = result.get("root")
    if as_json:
        _print_json("pack", ok, "sealed" if ok else "failed", root, result)
        return 0 if ok else 1
    print(f"packed {name} -> {root}")
    if verbose:
        print(f'[pack]\nname = "{name}"\nroot = "{root}"')
    return 0 if ok else 1


def cmd_pack(rest):
    try:
        positionals, flags = _take_flags(
            rest, bools=["-v", "--verbose", "--json"],
            values=["--accept", "-o", "--output", "--name", "--gate", "--pytest",
                    "--environment", "--root", "--into"])
    except ValueError as exc:
        return _usage_error("pack", str(exc))

    accept = flags.get("--accept")
    out = _flag(flags, "-o", "--output")
    if accept is not None and not out:
        return _usage_error("pack", "--accept needs -o/--output naming the destination claim")

    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    name = flags.get("--name") or os.path.basename(os.path.abspath(path).rstrip(os.sep))

    if accept is not None:
        try:
            result = authoring.build_claim(path, [accept], out, name=name)
        except kernel.ClaimError as exc:
            return _refuse("pack", as_json, str(exc))
        _record_discovery(path, out)
        return _finish_pack(out, result, as_json, verbose, name)

    gate = flags.get("--gate")
    pytest_target = flags.get("--pytest")
    gate_output = out or "OK"
    if not gate and pytest_target:
        gate = f"pytest {pytest_target} && printf ok > {gate_output}"

    has_recipe = (os.path.isfile(os.path.join(path, "reticuli.toml")) or
                  os.path.isfile(os.path.join(path, "claim.toml")))

    if gate:
        try:
            result = pack_mod.pack(path, name, [], [], gate, gate_output,
                                    environment=flags.get("--environment"))
        except kernel.ClaimError as exc:
            return _refuse("pack", as_json, str(exc))
        return _finish_pack(path, result, as_json, verbose, name)

    if has_recipe:
        try:
            manifest = kernel.seal(path)
        except kernel.ClaimError as exc:
            return _refuse("pack", as_json, str(exc))
        result = {"ok": True, "root": manifest["root"]}
        return _finish_pack(path, result, as_json, verbose, manifest.get("name", name))

    return _refuse("pack", as_json, "nothing to pack")


# ============================================================== verify ===

def cmd_verify(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json"])
    except ValueError as exc:
        return _usage_error("verify", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")

    try:
        result = kernel.verify(path)
    except kernel.ClaimError as exc:
        return _refuse("verify", as_json, str(exc))

    ok = bool(result.get("ok"))
    root = result.get("root")
    try:
        phase_word = kernel.phase(path)
    except kernel.ClaimError:
        phase_word = None
    data = {"name": result.get("name"), "root": root, "recomputed": result.get("recomputed"),
            "phase": phase_word, "ok": ok}

    if ok:
        if as_json:
            _print_json("verify", True, "fresh", root, data)
            return 0
        if verbose:
            print(f'[verify]\nname = "{data["name"]}"\nroot = "{root}"\n'
                  f'recomputed = "{data["recomputed"]}"\nok = true')
        return 0

    changed = result.get("changed", [])
    names = sorted({c.split(":", 1)[1] for c in changed if ":" in c}) or ["unknown"]
    data["changed"] = names
    if as_json:
        _print_json("verify", False, "broken", root, data)
        return 1
    sys.stderr.write(f"ret: verify: broken -- {', '.join(names)} no longer match the sealed root\n")
    sys.stderr.write("ret: verify: hint: restore the file(s), or reseal if the change is intended\n")
    return 1


# =============================================================== audit ===

def cmd_audit(rest):
    try:
        positionals, flags = _take_flags(
            rest, bools=["-v", "--verbose", "--json", "--shallow", "--no-strict"],
            values=["--mutants", "--record"])
    except ValueError as exc:
        return _usage_error("audit", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    shallow = flags.get("--shallow", False)
    strict = not flags.get("--no-strict", False)
    mutants = flags.get("--mutants")
    record_path = flags.get("--record")

    started = time.monotonic()
    try:
        result = kernel.audit(path, strict=strict, shallow=shallow)
    except kernel.ClaimError as exc:
        return _refuse("audit", as_json, str(exc))
    except Exception as exc:
        return _refuse("audit", as_json, f"audit refuses: {exc}")
    elapsed = time.monotonic() - started

    verdict = result.get("verdict")
    status_map = {"accept": "earned", "mismatch": "broken",
                  "environment": "environment", "reject": "failed"}
    status_word = status_map.get(verdict, "failed")
    ok = bool(result.get("ok"))

    layers = []
    if ok and not shallow:
        try:
            deep = registry.audit_deep(path)
            layers = deep.get("layers", [])
            ok = ok and deep.get("ok", True)
        except Exception:
            layers = []

    mscore = None
    if mutants is not None and ok:
        try:
            mscore = kernel.mutation_score(path, max_mutants=int(mutants))
        except Exception:
            mscore = None

    try:
        name = (kernel.load_recipe(path).get("claim") or {}).get("name")
    except kernel.ClaimError:
        name = None

    data = dict(result)
    data["name"] = name
    data.setdefault("recomputed", data.get("root"))
    data["elapsed"] = elapsed
    data["layers"] = layers
    data.setdefault("environment", [])

    if record_path and ok:
        try:
            doc = record_mod.emit(path)
            record_mod.write(doc, record_path)
        except Exception:
            pass

    try:
        kernel.ledger(path, {"event": "audit", "verdict": verdict, "status": status_word})
    except Exception:
        pass

    if as_json:
        _print_json("audit", ok, status_word, result.get("root"), data)
        return 0 if ok else 1

    if ok:
        if verbose:
            lines = ["[audit]", f'root = "{result.get("root")}"', f'status = "{status_word}"',
                      f"elapsed = {elapsed}"]
            for g in result.get("gates", []):
                word = "reproduced" if g.get("status") == "ok" else g.get("status")
                lines.append(f"  {g.get('output')}: {word}")
            print("\n".join(lines))
            if mscore is not None:
                print(f"[mutation_score]\nmutants = {mscore['mutants']}\nrate = {mscore['rate']}")
        return 0

    sys.stderr.write(f"ret: audit: {status_word} -- {verdict} on {path}\n")
    return 1


# ============================================================== assess ===

def cmd_assess(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json"],
                                          values=["--mutants"])
    except ValueError as exc:
        return _usage_error("assess", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    mutants = int(flags.get("--mutants", 50))

    try:
        result = assess_mod.assess(path, mutants=mutants)
    except kernel.ClaimError as exc:
        return _refuse("assess", as_json, str(exc))

    try:
        recipe = kernel.load_recipe(path)
        declared = (recipe.get("claim") or {}).get("mutation_floor")
    except kernel.ClaimError:
        declared = None

    data = dict(result)
    data["declared"] = declared
    data["gate"] = "pass" if (declared is None or result["rate"] >= declared) else "fail"

    try:
        root = kernel.read_manifest(path).get("root")
    except kernel.ClaimError:
        root = None

    try:
        kernel.ledger(path, {"event": "assess", "rate": result["rate"], "mutants": result["mutants"]})
    except Exception:
        pass

    if as_json:
        _print_json("assess", True, "measured", root, data)
        return 0
    if verbose:
        print(f"[assess]\nmutants = {result['mutants']}\nrate = {result['rate']}")
    else:
        print(f"assess: measured {result['measured']}/{result['mutants']} (rate={result['rate']})")
    return 0


# ============================================================= rebuild ===

_PRODUCERS = {
    "codex": {"cmd": "codex exec --full-auto --skip-git-repo-check -", "credential": None},
    "openai": {"cmd": "python3 -m reticuli._producers.openai", "credential": "OPENAI_API_KEY"},
}
_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")


def _expand_producer(name_or_cmd):
    spec = _PRODUCERS.get(name_or_cmd)
    if spec is not None:
        credential = spec.get("credential")
        if credential and not os.environ.get(credential):
            raise kernel.ClaimError(
                f"the {name_or_cmd} producer needs {credential} set; refusing before spending")
        cmd = spec["cmd"]
    else:
        cmd = name_or_cmd
    env = {k: os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ}
    return cmd, env


def cmd_rebuild(rest):
    try:
        positionals, flags = _take_flags(
            rest, bools=["-v", "--verbose", "--json", "--without-guidance"],
            values=["--producer", "-o", "--output"])
    except ValueError as exc:
        return _usage_error("rebuild", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    producer = flags.get("--producer")
    into = _flag(flags, "-o", "--output")
    guidance = not flags.get("--without-guidance", False)

    if not producer:
        return _usage_error("rebuild", "needs --producer naming a producer command or shortcut")

    try:
        cmd, env = _expand_producer(producer)
    except kernel.ClaimError as exc:
        return _refuse("rebuild", as_json, str(exc))

    if not into:
        into = tempfile.mkdtemp(prefix="reticuli-rebuild-")

    try:
        result = kernel.rebuild(path, cmd, into, guidance=guidance, producer_env=env or None)
    except kernel.ClaimError as exc:
        return _refuse("rebuild", as_json, str(exc))

    data = dict(result)
    data["into"] = into
    if as_json:
        _print_json("rebuild", True, "rebuilt", result.get("root"), data)
        return 0
    print(f"rebuilt -> {result.get('root')} ({into})")
    if verbose:
        print(f'[rebuild]\nroot = "{result.get("root")}"\n'
              f'quarantine = "{result.get("quarantine")}"')
    return 0


# =========================================================== crosscheck ==

def cmd_crosscheck(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json"],
                                          values=["--mutants"])
    except ValueError as exc:
        return _usage_error("crosscheck", str(exc))
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    mutants = flags.get("--mutants")
    mutants_n = int(mutants) if mutants else None

    if len(positionals) == 1:
        return _usage_error("crosscheck", "one realization is not a comparison")
    if len(positionals) == 2:
        m1, m3 = positionals
        m2 = tempfile.mkdtemp(prefix="reticuli-m2-")
        os.rmdir(m2)
        shutil.copytree(m1, m2)
        materialized = True
    elif len(positionals) == 3:
        m1, m2, m3 = positionals
        materialized = False
    else:
        return _usage_error("crosscheck", "needs one, two, or three legs: m1 [m2] m3")

    try:
        result = kernel.crosscheck(m1, m2, m3, mutants=mutants_n)
    except kernel.ClaimError as exc:
        return _refuse("crosscheck", as_json, str(exc))

    ok = bool(result.get("satisfied"))
    status = result.get("verdict", "reject")
    data = dict(result)
    data["m2_materialized"] = materialized

    discovery = _discovery_total(m1) if os.path.isdir(m1) else None

    if as_json:
        _print_json("crosscheck", ok, status, None, data)
        return 0 if ok else 1

    if ok:
        if verbose:
            lines = ["[crosscheck]", "satisfied = true", f'verdict = "{status}"']
            for leg, root in sorted((result.get("roots") or {}).items()):
                lines.append(f'  {leg} = "{root}"')
            lines.append("[cost]")
            cost = result.get("cost") or {}
            lines.append(f"unit = {cost.get('unit')!r}")
            lines.append(f"comparable = {cost.get('comparable')}")
            if discovery is not None:
                lines.append(f"discovery = {discovery} tokens (reported, not compared)")
            print("\n".join(lines))
        return 0

    reasons = ", ".join(result.get("rejected") or result.get("incomplete") or [status])
    sys.stderr.write(f"ret: crosscheck: {status} -- {reasons}\n")
    return 1


# ============================================================== export ===

def cmd_export(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json", "--blind"],
                                          values=["-o", "--out"])
    except ValueError as exc:
        return _usage_error("export", str(exc))
    as_json = flags.get("--json", False)
    if not positionals:
        return _usage_error("export", "needs a claim path")
    path = positionals[0]
    out = positionals[1] if len(positionals) > 1 else _flag(flags, "-o", "--out")
    blind = flags.get("--blind", False)

    try:
        manifest = kernel.read_manifest(path)
    except kernel.ClaimError as exc:
        return _refuse("export", as_json, str(exc))
    if not out:
        out = f"{manifest['name']}-{manifest['root'][:12]}.tar"

    try:
        if out == "-":
            tmp = tempfile.mktemp(prefix="reticuli-export-")
            transfer.export(path, tmp, blind=blind)
            with open(tmp, "rb") as f:
                shutil.copyfileobj(f, sys.stdout.buffer)
            sys.stdout.buffer.flush()
            os.remove(tmp)
        else:
            transfer.export(path, out, blind=blind)
    except kernel.ClaimError as exc:
        return _refuse("export", as_json, str(exc))

    if as_json:
        _print_json("export", True, "exported", manifest.get("root"), {"out": out})
    return 0


def cmd_import(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json"])
    except ValueError as exc:
        return _usage_error("import", str(exc))
    as_json = flags.get("--json", False)
    if not positionals:
        return _usage_error("import", "needs an archive path")
    archive = positionals[0]
    target = positionals[1] if len(positionals) > 1 else "."

    tmp = None
    try:
        if archive == "-":
            tmp = tempfile.mktemp(prefix="reticuli-import-")
            with open(tmp, "wb") as f:
                shutil.copyfileobj(sys.stdin.buffer, f)
            archive_path = tmp
        else:
            if not os.path.isfile(archive):
                return _refuse("import", as_json, f"no archive at {archive!r}")
            archive_path = archive
        try:
            result = transfer.import_(archive_path, target)
        except kernel.ClaimError as exc:
            return _refuse("import", as_json, str(exc))
    finally:
        if tmp and os.path.isfile(tmp):
            os.remove(tmp)

    ok = bool(result.get("ok"))
    status = "imported" if ok else "mismatch"
    if as_json:
        _print_json("import", ok, status, result.get("root"), result)
        return 0 if ok else 1
    if not ok:
        sys.stderr.write("ret: import: mismatch -- imported bytes do not recompute to the archived root\n")
        return 1
    return 0


# =============================================================== pull ====

def cmd_pull(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json"])
    except ValueError as exc:
        return _usage_error("pull", str(exc))
    as_json = flags.get("--json", False)
    if not positionals:
        return _usage_error("pull", "needs a component claim to pull")
    component = positionals[0]
    path = positionals[1] if len(positionals) > 1 else "."

    try:
        result = registry.pull(component, path)
    except kernel.ClaimError as exc:
        return _refuse("pull", as_json, str(exc))

    if as_json:
        _print_json("pull", True, "pulled", result.get("root"), result)
        return 0
    print(f"pulled -> {result.get('root')}")
    return 0


# ============================================================== record ===

def cmd_record(rest):
    try:
        positionals, flags = _take_flags(
            rest, bools=["-v", "--verbose", "--json", "--check", "--sign"],
            values=["--key", "--as", "-o", "--output"])
    except ValueError as exc:
        return _usage_error("record", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    out = _flag(flags, "-o", "--output")
    key = flags.get("--key")
    as_name = flags.get("--as")
    check = flags.get("--check", False)
    use_sign_env = flags.get("--sign", False)

    if out:
        if use_sign_env and not key:
            key = os.environ.get("RETICULI_KEY")
            if not key:
                return _refuse("record", as_json,
                               "no signing identity configured; set RETICULI_KEY")
        try:
            doc = record_mod.emit(path)
        except kernel.ClaimError as exc:
            return _refuse("record", as_json, str(exc))
        record_mod.write(doc, out)
        if key:
            record_mod.sign(out, key)
        digest = kernel.record_digest(doc)
        data = {"digest": digest, "record": doc, "path": out}
        if as_json:
            _print_json("record", True, "written", doc.get("root"), data)
            return 0
        if verbose:
            print(f'[record]\nname = "{doc.get("name")}"\nroot = "{doc.get("root")}"')
        return 0

    if check:
        try:
            result = attest.check(path)
        except kernel.ClaimError as exc:
            return _refuse("record", as_json, str(exc))
        ok = bool(result.get("ok"))
        if as_json:
            _print_json("record", ok, "checked", None, result)
            return 0 if ok else 1
        if not ok:
            sys.stderr.write("ret: record: no attestation verifies against the current build\n")
            return 1
        return 0

    if not key:
        return _usage_error("record",
                             "needs --key naming a signing key, or -o to write a record document")
    principal = as_name or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
    try:
        result = attest.attest(path, key, principal)
    except kernel.ClaimError as exc:
        return _refuse("record", as_json, str(exc))
    if as_json:
        _print_json("record", True, "attested", result.get("root"), result)
        return 0
    return 0


# ================================================================ sign ===

def cmd_sign(rest):
    try:
        positionals, flags = _take_flags(rest, bools=["-v", "--verbose", "--json", "--check"],
                                          values=["--key", "--as"])
    except ValueError as exc:
        return _usage_error("sign", str(exc))
    path = positionals[0] if positionals else "."
    as_json = flags.get("--json", False)
    verbose = flags.get("-v") or flags.get("--verbose")
    key = flags.get("--key")
    as_name = flags.get("--as")
    check = flags.get("--check", False)

    if check:
        try:
            result = attest.sign_check(path)
        except kernel.ClaimError as exc:
            return _refuse("sign", as_json, str(exc))
        ok = bool(result.get("ok"))
        if as_json:
            _print_json("sign", ok, "checked", None, result)
            return 0 if ok else 1
        if not ok:
            sys.stderr.write("ret: sign: no authorization verifies against the current build\n")
            return 1
        return 0

    if key:
        principal = as_name or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        try:
            result = attest.sign(path, key, principal)
        except kernel.ClaimError as exc:
            return _refuse("sign", as_json, str(exc))
        if as_json:
            _print_json("sign", True, "authorized", result.get("root"), result)
            return 0
        return 0

    try:
        result = attest.review_packet(path)
    except kernel.ClaimError as exc:
        return _refuse("sign", as_json, str(exc))
    if as_json:
        _print_json("sign", True, "reviewed", result.get("root"), result)
        return 0
    root = result.get("root") or ""
    sign_root = result.get("sign_root") or ""
    print(f"review: root={root[:12]} sign_root={sign_root[:12]}")
    if verbose:
        audit_info = result.get("audit") or {}
        print(f'[review]\nroot = "{root}"\nsign_root = "{sign_root}"\n'
              f'audit = "{audit_info.get("verdict")}"')
    return 0


# ================================================================ hook ===

def cmd_hook(rest):
    try:
        _positionals, flags = _take_flags(rest, values=["-C"])
    except ValueError:
        flags = _Flags()
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        cwd = payload.get("cwd") or flags.get("-C")
        if cwd and os.path.isdir(os.path.join(cwd, kernel.STORE)):
            transcript = payload.get("transcript_path")
            if transcript:
                try:
                    _util.trace_append(
                        os.path.join(cwd, authoring.TRACE),
                        {"event": "session", "transcript": transcript, "ts": time.time()})
                except OSError:
                    pass
        try:
            hooks.event(payload)
        except Exception:
            pass
    return 0


# ================================================================ help ===

def cmd_help(rest):
    if "-a" in rest or "--all" in rest:
        print(_help_all())
        return 0
    if not rest:
        print(_top_help())
        return 0
    topic = rest[0]
    if topic == "environment":
        print(ENV_HELP)
        return 0
    canonical = ALIASES.get(topic, topic)
    if canonical in FULL_HELP:
        print(FULL_HELP[canonical])
        return 0
    sys.stderr.write(f"ret: help: no such command: {topic!r}\n")
    return 1


def cmd_completion(rest):
    shell = rest[0] if rest else "bash"
    if shell != "bash":
        sys.stderr.write(f"ret: completion: {shell!r} is not supported; only bash\n")
        return 1
    words = " ".join(sorted(set(PORCELAIN) | set(PLUMBING)))
    print(
        "_ret_completion() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{words}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_completion ret"
    )
    return 0


# ================================================================ main ===

ROUTES = {
    "init": cmd_init, "run": cmd_run, "status": cmd_status, "pack": cmd_pack,
    "pull": cmd_pull, "export": cmd_export, "import": cmd_import,
    "verify": cmd_verify, "audit": cmd_audit, "assess": cmd_assess,
    "rebuild": cmd_rebuild, "crosscheck": cmd_crosscheck, "record": cmd_record,
    "sign": cmd_sign, "hook": cmd_hook, "help": cmd_help, "completion": cmd_completion,
}


def verbs():
    """Every verb spelling this CLI actually accepts: the fourteen
    porcelain verbs, any accepted alias, and the plumbing."""
    return set(PORCELAIN) | set(ALIASES) | set(PLUMBING)


def _unknown_verb(verb):
    known = set(PORCELAIN) | set(PLUMBING)
    matches = difflib.get_close_matches(verb, known, n=1)
    msg = f"ret: {verb!r} is not a ret command."
    if matches:
        msg += f" Did you mean {matches[0]!r}?"
    sys.stderr.write(msg + "\n")
    return 2


def main(argv=None) -> int:
    """`ret`'s own entry point."""
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(_top_help())
        return 0
    if argv[0] in ("-h", "--help"):
        print(_top_help())
        return 0
    if argv[0] == "--version":
        print(f"ret {VERSION}")
        return 0

    verb, rest = argv[0], argv[1:]
    known = set(PORCELAIN) | set(PLUMBING)
    canonical = ALIASES.get(verb, verb)
    if canonical not in known:
        return _unknown_verb(verb)

    if canonical not in ("hook", "help", "completion"):
        if "-h" in rest:
            print(_concise_usage(canonical))
            return 0
        if "--help" in rest:
            print("SYNOPSIS\n" + FULL_HELP.get(canonical, canonical))
            return 0

    handler = ROUTES[canonical]
    return handler(rest)

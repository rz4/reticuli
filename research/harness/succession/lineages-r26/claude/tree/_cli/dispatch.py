"""The dispatch entry point: argv in, exit code out -- see `spec/layers.md`.

A self-contained implementation of the `ret` command surface, built
directly on the layers beneath the CLI (`reticuli.kernel`, `.registry`,
`.transfer`, `.attest`, `.pack`, `.hooks`, `.assess`, `.record`,
`.authoring`, `.render`, `._util`) -- never a `reticuli._kernel` private.
`main` is the single place argv becomes an exit code; `verbs()` names
every registered subcommand. Stdlib only.
"""
import argparse
import ast
import difflib
import inspect
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

from reticuli import kernel, _util
from reticuli import authoring as authoring_mod
from reticuli import hooks as hooks_mod
from reticuli import assess as assess_mod
from reticuli import record as record_mod
from reticuli import attest as attest_mod
from reticuli import transfer as transfer_mod
from reticuli import registry as registry_mod

VERSION = "2.2"

PORCELAIN = frozenset({
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
})
ALIASES = frozenset()
PLUMBING = ("hook", "help", "completion")

_DESC = (
    'Reticuli records and reproduces software claims.\n\n'
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
    '    sign        authorize a claim or proof'
)

_EPILOG = (
    "See 'ret <command> -h' for command usage.\n"
    "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
    "including accepted older spellings."
)

_USAGE = {
    "init": "usage: ret init [ws] [--agent NAME] [--no-agent] [--name NAME] "
            "[--json] [-v] [--color {auto,always,never}]",
    "run": "usage: ret run CMD [-C WS]",
    "status": "usage: ret status [d] [--all] [--tree] [--claims] [--files] "
               "[-v] [--json] [--color {auto,always,never}]",
    "pack": "usage: ret pack [root] [--accept OUTPUT [OUTPUT ...]] [-o DEST] "
            "[--name NAME] [--pytest] [--environment PATH] [--json]",
    "pull": "usage: ret pull src dest [--ws WS] [--json]",
    "export": "usage: ret export d [tar_path] [-o PATH] [--blind] [--json]",
    "import": "usage: ret import tar_path dest [--json]",
    "verify": "usage: ret verify [d] [-v] [--json] [--color {auto,always,never}]",
    "audit": "usage: ret audit [d] [--shallow] [--no-strict] [--mutants N] "
             "[--record PATH] [-v] [--json]",
    "assess": "usage: ret assess [d] [--mutants N] [--json]",
    "rebuild": "usage: ret rebuild d --producer PRODUCER -o INTO "
               "[--without-guidance] [--json]",
    "crosscheck": "usage: ret crosscheck m1 [m2] m3 [--shallow] [--mutants N] "
                  "[-v] [--json]",
    "record": "usage: ret record [d] [-o PATH] [--key KEY] [--as PRINCIPAL] "
              "[--sign] [--check] [--json]",
    "sign": "usage: ret sign d [--key KEY] [--as PRINCIPAL] [--check] [-v] [--json]",
}

_FULL_ACCOUNT = {
    "verify": (
        "SYNOPSIS\n"
        "    ret verify [d]\n\n"
        "DESCRIPTION\n"
        "    Recompute the claim's root from the bytes present and compare\n"
        "    it with the sealed manifest. Does not execute acceptance criteria\n"
        "    -- identity only, no gate runs. That is audit's job."
    ),
    "rebuild": (
        "SYNOPSIS\n"
        "    ret rebuild d --producer PRODUCER -o INTO\n\n"
        "DESCRIPTION\n"
        "    Regrow d's generated outputs with PRODUCER into INTO, until\n"
        "    every gate passes. Generated sources are withheld from a\n"
        "    blind room -- a guarantee a rebuild can be measured against.\n\n"
        "PRODUCERS\n"
        "    A producer is any program: a literal shell command, or one of\n"
        "    the shipped names this build answers to by credential --\n"
        "        --producer openai   (needs $OPENAI_API_KEY)\n"
        "        --producer claude   (needs $ANTHROPIC_API_KEY)\n"
        "    Any other value passes straight through as the command to run."
    ),
    "audit": (
        "SYNOPSIS\n"
        "    ret audit [d] [--shallow] [--mutants N] [--record PATH]\n\n"
        "DESCRIPTION\n"
        "    Re-execute every gate, cold and sandboxed, earning each\n"
        "    verdict fresh. Judging runs in the strict jail by default --\n"
        "    a claim's gates never read your files; --no-strict opts down."
    ),
    "status": (
        "SYNOPSIS\n"
        "    ret status [d] [--all] [--tree] [--claims] [--files]\n\n"
        "DESCRIPTION\n"
        "    A pure view: reads a claim or a session and reports it, never\n"
        "    executes anything."
    ),
    "pack": (
        "SYNOPSIS\n"
        "    ret pack [root] --accept OUTPUT -o DEST [--name NAME]\n\n"
        "DESCRIPTION\n"
        "    Turn a project directory or a session into a sealed claim."
    ),
}


# ==============================================================================
# small shared helpers
# ==============================================================================


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _ago(when_iso) -> str:
    if not when_iso:
        return "unknown"
    try:
        parsed = time.strptime(when_iso, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return str(when_iso)
    import calendar
    secs = max(0.0, time.time() - calendar.timegm(parsed))
    return f"{int(secs)}s ago"


def _read_json_safe(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _err(verb: str, msg: str) -> None:
    print(f"ret: {verb}: {msg}", file=sys.stderr)


def _usage(verb: str, msg: str) -> int:
    _err(verb, msg)
    return 2


def _refuse(verb: str, args, msg: str) -> int:
    if getattr(args, "json", False):
        envelope = {"command": verb, "ok": False, "status": "error",
                    "root": None, "data": {"error": msg}}
        print(json.dumps(envelope))
    else:
        _err(verb, msg)
    return 1


def _print_envelope(command: str, data, ok: bool, status: str, args, root=None) -> None:
    if root is None and isinstance(data, dict):
        root = data.get("root")
    envelope = {"command": command, "ok": ok, "status": status, "root": root, "data": data}
    print(json.dumps(envelope, default=str))


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--color", choices=("auto", "always", "never"), default=None)


def _wants_full_help(rest) -> bool:
    return bool(rest) and rest[0] == "--help"


def _wants_concise_help(rest) -> bool:
    return bool(rest) and rest[0] == "-h"


def _color_active(args) -> bool:
    mode = getattr(args, "color", None) or os.environ.get("RETICULI_COLOR") or "auto"
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


_COLOR_CODES = {"green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
                "reset": "\033[0m"}


def _paint(text: str, color: str, active: bool) -> str:
    if not active:
        return text
    code = _COLOR_CODES.get(color)
    return f"{code}{text}{_COLOR_CODES['reset']}" if code else text


def _version_line() -> str:
    return f"ret {VERSION} (reticuli {VERSION}, python {platform.python_version()})"


# ==============================================================================
# help system
# ==============================================================================


def _print_top_help() -> None:
    print(f"usage: ret [-h] [--version] <command> ...\n\n{_DESC}\n\n{_EPILOG}")


def _print_help_all() -> None:
    print(_DESC)
    print()
    print("Plumbing")
    for name in PLUMBING:
        print(f"    {name}")
    if ALIASES:
        print()
        print("Accepted older spellings")
        for old in sorted(ALIASES):
            print(f"    {old}")
    print()
    print(_EPILOG)


def _print_environment_doc() -> None:
    print(
        "ENVIRONMENT VARIABLES\n\n"
        "    RETICULI_KEY          default signing key path for record --sign\n"
        "    RETICULI_SIGNERS      allowed_signers anchor file for --check\n"
        "    RETICULI_COLOR        auto|always|never -- overrides tty detection\n"
        "    RETICULI_CACHE        verdict-cache directory override\n"
        "    RETICULI_JAILED       internal: already-inside-a-sandbox signal\n"
        "    OPENAI_API_KEY        credential for --producer openai\n"
        "    ANTHROPIC_API_KEY     credential for --producer claude\n"
        "    RETICULI_PRICE        producer pricing override, passed through\n"
        "    RETICULI_AGENT_TURNS  producer turn-count override, passed through\n"
        "    OPENAI_BASE_URL       producer endpoint override, passed through"
    )


def _print_full_account(topic: str) -> None:
    text = _FULL_ACCOUNT.get(topic)
    if text is None:
        text = (f"SYNOPSIS\n    ret {topic} ...\n\n"
                 f"DESCRIPTION\n    See 'ret {topic} -h' for the option grammar.")
    print(text)


def _handle_help(rest, verb) -> int:
    if rest and rest[0] in ("-a", "--all"):
        _print_help_all()
        return 0
    if not rest:
        _print_top_help()
        return 0
    topic = rest[0]
    if topic == "environment":
        _print_environment_doc()
        return 0
    _print_full_account(topic)
    return 0


def _handle_completion(rest, verb) -> int:
    shell = rest[0] if rest and not rest[0].startswith("-") else "bash"
    names = sorted(PORCELAIN | set(PLUMBING))
    if shell == "bash":
        word_list = " ".join(names)
        print(
            '_ret_complete() {\n'
            '    local cur\n'
            '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
            f'    COMPREPLY=( $(compgen -W "{word_list}" -- "$cur") )\n'
            '}\n'
            'complete -F _ret_complete ret'
        )
    else:
        word_list = " ".join(names)
        print(f'#compdef ret\n_ret() {{\n    local -a cmds\n    cmds=({word_list})\n'
              f'    _describe "command" cmds\n}}\ncompdef _ret ret')
    return 0


def _unknown_verb(verb: str) -> int:
    candidates = sorted(PORCELAIN | set(PLUMBING))
    matches = difflib.get_close_matches(verb, candidates, n=1, cutoff=0.4)
    msg = f"{verb!r} is not a ret command."
    if matches:
        msg += f" Did you mean {matches[0]!r}?"
    print(f"ret: {msg}", file=sys.stderr)
    return 2


# ==============================================================================
# draft-session triad: observed / declared / unresolved
# ==============================================================================


def _read_draft(ws: str) -> list:
    path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _real_files(ws: str) -> set:
    paths = set()
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d not in (".reticuli", ".claude", ".git")]
        rel_dir = os.path.relpath(dirpath, ws)
        for fn in filenames:
            rel = fn if rel_dir in (".", "") else f"{rel_dir.replace(os.sep, '/')}/{fn}"
            paths.add(rel)
    return paths


_OP_SPLIT_RE = re.compile(r"&&|\|\||;|\||&|\n")


def _command_tokens(cmd: str) -> list:
    toks = []
    for seg in _OP_SPLIT_RE.split(cmd):
        for t in seg.split():
            t = t.strip("'\"(),;:")
            if t:
                toks.append(t)
    return toks


def _static_import_targets(ws: str, path: str) -> list:
    if not path.endswith(".py"):
        return []
    full = os.path.join(ws, path)
    if not os.path.isfile(full):
        return []
    try:
        with open(full, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, OSError, UnicodeDecodeError):
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    out = []
    for n in names:
        cand = f"{n}.py"
        if os.path.isfile(os.path.join(ws, cand)):
            out.append(cand)
    return out


def _triad(ws: str) -> dict:
    events = _read_draft(ws)
    write_ev, read_ev = {}, {}
    for e in events:
        if e.get("event") == "write" and "path" in e:
            write_ev[e["path"]] = e
        elif e.get("event") == "read" and "path" in e:
            read_ev[e["path"]] = e
    bash_cmds = [e["cmd"] for e in events if e.get("event") == "bash" and "cmd" in e]

    try:
        proposal = authoring_mod.propose(ws, [])
    except kernel.ClaimError:
        proposal = {"claim": {"inputs": []}, "generated": []}
    generated = list(proposal.get("generated") or [])
    inputs = list(proposal.get("claim", {}).get("inputs") or [])

    covered = set()
    for cmd in bash_cmds:
        toks = set(_command_tokens(cmd))
        try:
            deciders = set(kernel.gate_deciders(cmd))
        except Exception:
            deciders = set()
        for dec in toks | deciders:
            if dec in generated:
                covered.add(dec)
                for imp in _static_import_targets(ws, dec):
                    if imp in generated:
                        covered.add(imp)

    unresolved = [g for g in generated if g not in covered]
    observed = set(write_ev) | set(read_ev)
    return {"observed": observed, "generated": generated, "inputs": inputs,
            "unresolved": unresolved, "write_ev": write_ev, "read_ev": read_ev,
            "bash_cmds": bash_cmds}


def _render_triad_terse(ws: str) -> str:
    t = _triad(ws)
    o = len(t["observed"])
    de = len(t["generated"]) + len(t["inputs"])
    u = len(t["unresolved"])
    line = f"draft -- observed={o} declared={de} unresolved={u}"
    if u:
        line += f" ({', '.join(t['unresolved'])} undeclared)"
    else:
        line += " packable"
    return line


def _render_triad_all(ws: str) -> str:
    t = _triad(ws)
    real = _real_files(ws)
    all_paths = sorted(real | t["observed"])
    rows = [("path", "observed", "declared", "evidence")]
    for p in all_paths:
        if p in t["write_ev"]:
            obs = "write"
            ev = t["write_ev"][p].get("via") or "-"
        elif p in t["read_ev"]:
            obs = "read"
            ev = t["read_ev"][p].get("via") or "-"
        else:
            obs = "-"
            ev = "-"
            for cmd in t["bash_cmds"]:
                if p in _command_tokens(cmd) and p in real:
                    ev = "gate"
                    break
        if p in t["generated"]:
            decl = "generated"
        elif p in t["inputs"]:
            decl = "input"
        else:
            decl = "-"
        rows.append((p, obs, decl, ev))
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows)


def _render_tree_draft(ws: str) -> str:
    t = _triad(ws)
    lines = [f"draft session: {ws}"]
    for p in sorted(set(t["generated"]) | set(t["inputs"])):
        lines.append(f"  {p}")
    return "\n".join(lines)


# ==============================================================================
# sealed-claim views
# ==============================================================================


def _is_claim(d: str) -> bool:
    return os.path.isfile(os.path.join(d, kernel.STORE, "manifest.json"))


def _declared_pinned(d: str, parsed: dict) -> list:
    try:
        return list(_util.declared_inputs(d, parsed))
    except kernel.ClaimError:
        return list(parsed.get("claim", {}).get("inputs", []))


def _step_class(step: dict) -> str:
    return step.get("class") or ("generated" if step.get("kind") == "produce" else "pinned")


_ROLE_WORDS = {"generated": "free", "pinned": "fixed", "validated": "verdict"}


def _render_files_claim(d: str) -> str:
    parsed = kernel.load_recipe(d)
    rows = []
    for p in _declared_pinned(d, parsed):
        rows.append((p, "pinned", _ROLE_WORDS["pinned"]))
    for step in parsed.get("step", []):
        out = step.get("output")
        if not out:
            continue
        cls = _step_class(step)
        rows.append((out, cls, _ROLE_WORDS.get(cls, cls)))
    if not rows:
        return "(no declared files)"
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) for r in rows)


def _render_tree_claim(d: str, colored: bool) -> str:
    parsed = kernel.load_recipe(d)
    try:
        layers = len(registry_mod.components_of(d))
    except Exception:
        layers = 0
    lines = [f"layers={layers}"]
    rows = []
    for p in _declared_pinned(d, parsed):
        rows.append(("pinned", p))
    for step in parsed.get("step", []):
        out = step.get("output")
        if not out:
            continue
        bucket = "generated" if _step_class(step) == "generated" else "pinned"
        rows.append((bucket, out))
    for bucket, path in rows:
        if colored:
            color = "yellow" if bucket == "generated" else "green"
            label = _paint(" " * 10, color, True)
        else:
            label = f"{bucket:<10}"
        lines.append(f"{label} {path}")
    return "\n".join(lines)


def _scan_claims_names(ws: str) -> list:
    names = []
    base = os.path.join(ws, kernel.STORE, "sealed")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            if os.path.isdir(p):
                try:
                    m = kernel.read_manifest(p)
                    names.append(m.get("name", name))
                except kernel.ClaimError:
                    pass
    return names


def _audit_receipt_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "audit_receipt.json")


def _assess_receipt_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "assess_receipt.json")


def _discovery_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "discovery.json")


def _read_discovery(d: str):
    data = _read_json_safe(_discovery_path(d))
    return data.get("tokens") if data else None


def _statement_lines(d: str) -> list:
    lines = []
    adir = os.path.join(d, "reticuli".join([]), ".reticuli", "attest") \
        if False else os.path.join(d, ".reticuli", "attest")
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            if fn.endswith(".json") and not fn.endswith(".sig"):
                data = _read_json_safe(os.path.join(adir, fn))
                ident = (data or {}).get("identity", "?")
                lines.append(f"  attested by {ident}")
    mdir = os.path.join(d, kernel.SIGN_DIR)
    if os.path.isdir(mdir):
        for fn in sorted(os.listdir(mdir)):
            if fn.endswith(".sign.json"):
                data = _read_json_safe(os.path.join(mdir, fn))
                ident = (data or {}).get("identity", "?")
                lines.append(f"  signed by {ident}")
    return lines


def _next_step(d: str) -> str:
    if not os.path.isfile(os.path.join(d, kernel.MANIFEST)):
        return "ret pack"
    try:
        ver = kernel.verify(d)
    except kernel.ClaimError:
        return "restore the drifted bytes, then verify"
    if not ver.get("ok"):
        return "restore the drifted bytes, then verify"
    if not os.path.isfile(_audit_receipt_path(d)):
        return "ret audit"
    if not os.path.isfile(_assess_receipt_path(d)):
        return "ret assess"
    return "ret crosscheck"


def _render_claim_report(d: str, colored: bool) -> str:
    try:
        ver = kernel.verify(d)
    except kernel.ClaimError:
        ver = {"ok": False}
    lines = []
    if not ver.get("ok"):
        lines.append(f"identity: {_paint('broken', 'red', colored)}")
        lines.append(f"next: {_next_step(d)}")
        return "\n".join(lines)

    lines.append(f"identity: {_paint('fresh', 'green', colored)}")
    receipt = _read_json_safe(_audit_receipt_path(d))
    if receipt:
        lines.append(f"audited: {_paint('ok', 'green', colored)}, on this machine, "
                      f"{_ago(receipt.get('when'))}")
    disc = _read_discovery(d)
    if disc is not None:
        lines.append(f"discovery: {disc} tokens (testimony, outside the cost band)")
    stmt_lines = _statement_lines(d)
    if stmt_lines:
        lines.append(f"{len(stmt_lines)} statement(s)")
        lines.extend(stmt_lines)
    lines.append(f"next: {_next_step(d)}")
    return "\n".join(lines)


def _render_claim_all(d: str) -> str:
    parsed = kernel.load_recipe(d)
    lines = []
    fixed = _declared_pinned(d, parsed)
    lines.append("fixed: " + (", ".join(fixed) if fixed else "(none)"))

    lines.append("deciding:")
    any_deciding = False
    for step in parsed.get("step", []):
        if step.get("kind") != "gate":
            continue
        any_deciding = True
        try:
            deciders = kernel.gate_deciders(step.get("run", ""))
        except Exception:
            deciders = []
        word = ("decided by " + ", ".join(deciders)) if deciders else "decided by the command itself"
        lines.append(f"  {step.get('output')}: {word}")
    if not any_deciding:
        lines.append("  (none)")

    free = [s.get("output") for s in parsed.get("step", []) if _step_class(s) == "generated"]
    lines.append("free: " + (", ".join(free) if free else "(none)"))

    recorded = []
    receipt = _read_json_safe(_audit_receipt_path(d))
    if receipt:
        recorded.append(f"  audit, {_ago(receipt.get('when'))}, earned on present bytes")
    assess_receipt = _read_json_safe(_assess_receipt_path(d))
    if assess_receipt:
        recorded.append(f"  assess, {_ago(assess_receipt.get('when'))}, a receipt, not a verdict")
    lines.append("recorded:")
    lines.extend(recorded or ["  (none)"])

    lines.append("unknown: proof, mutation floor (where undeclared)")
    lines.append(f"next: {_next_step(d)}")
    return "\n".join(lines)


def _claim_status_data(d: str) -> dict:
    manifest = kernel.read_manifest(d)
    ver = kernel.verify(d)
    receipt = _read_json_safe(_audit_receipt_path(d))
    assess_receipt = _read_json_safe(_assess_receipt_path(d))
    return {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": "fresh" if ver.get("ok") else "broken",
        "audited": bool(receipt),
        "deciding": assess_receipt is not None,
        "proof": registry_mod.proof_of(d) if hasattr(registry_mod, "proof_of") else None,
        "signatures": len(_statement_lines(d)),
        "next": _next_step(d),
        "ok": bool(ver.get("ok")),
    }


# ==============================================================================
# pack helpers: trace pruning, discovery stamping
# ==============================================================================


def _prune_stale_trace(ws: str) -> None:
    path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    if not os.path.isfile(path):
        return
    kept = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") in ("write", "read") and "path" in e:
                if not os.path.isfile(os.path.join(ws, e["path"])):
                    continue
            kept.append(line)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))


def _stamp_discovery(ws: str, dest: str) -> None:
    for e in _read_draft(ws):
        if e.get("event") == "session" and e.get("transcript"):
            tpath = e["transcript"]
            if not os.path.isfile(tpath):
                return
            total = 0
            with open(tpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    usage = ((rec.get("message") or {}).get("usage")) or {}
                    total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            os.makedirs(os.path.join(dest, kernel.STORE), exist_ok=True)
            with open(_discovery_path(dest), "w", encoding="utf-8") as f:
                json.dump({"tokens": total}, f)
            return


# ==============================================================================
# producers
# ==============================================================================

_PRODUCERS = {
    "openai": {"cmd": "codex exec --full-auto -", "credential": "OPENAI_API_KEY"},
    "claude": {"cmd": "claude -p --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
}


def _expand_producer(name: str) -> str:
    spec = _PRODUCERS.get(name)
    if spec is None:
        return name
    cred = spec["credential"]
    if not os.environ.get(cred):
        raise kernel.ClaimError(f"the {name} producer needs ${cred} set before it can spend")
    return spec["cmd"]


# ==============================================================================
# audit: inspect-based forwarding of an optional `strict` kwarg
# ==============================================================================


def _clear_pycache(d: str) -> None:
    """Drop any `__pycache__` the last run left behind, so a gate that
    re-imports a just-rewritten generated module recompiles it fresh --
    CPython's bytecode cache keys invalidation off a 1-second-resolution
    mtime, which a fast rewrite-then-rerun can land inside of."""
    for root, dirs, _files in os.walk(d):
        if "__pycache__" in dirs:
            shutil.rmtree(os.path.join(root, "__pycache__"), ignore_errors=True)
            dirs.remove("__pycache__")


def _call_kernel_audit(d: str, strict: bool):
    fn = kernel.audit
    try:
        sig = inspect.signature(fn)
        params = sig.parameters
        accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    except (TypeError, ValueError):
        params, accepts_var_kw = {}, False
    if "strict" in params or accepts_var_kw:
        return fn(d, strict=strict)
    return fn(d)


def _audit_status_word(data: dict) -> str:
    if data.get("ok"):
        return "earned"
    v = data.get("verdict")
    if v == "mismatch":
        return "broken"
    return v or "failed"


def _render_audit_verbose(data: dict) -> str:
    lines = ["[audit]", f"status = {_audit_status_word(data)}"]
    for g in data.get("gates", []) or []:
        word = "reproduced" if g.get("status") == "ok" else g.get("status")
        lines.append(f"  gate {g.get('output')}: {g.get('status')} ({word})")
    lines.append("reproduced" if data.get("ok") else "not reproduced")
    return "\n".join(lines)


def _render_mutation_verbose(score: dict) -> str:
    return "\n".join(["[mutation_score]", f"mutants = {score.get('mutants')}",
                       f"rate = {score.get('rate')}"])


def _render_verify_verbose(data: dict) -> str:
    return "\n".join([
        "[verify]",
        f'name = "{data.get("name")}"',
        f'root = "{data.get("root")}"',
        f"phase = {data.get('phase')}",
    ])


def _render_review_verbose(data: dict) -> str:
    return "\n".join(["[review]", f"root = {data.get('root')}",
                       f"sign_root = {data.get('sign_root')}"])


def _render_crosscheck_verbose(data: dict, m1: str) -> str:
    lines = [
        "[crosscheck]",
        f"verdict = {data.get('verdict')}",
        f"satisfied = {str(bool(data.get('satisfied'))).lower()}",
        "[cost]",
        f"comparable = {(data.get('cost') or {}).get('comparable')}",
    ]
    disc = _read_discovery(m1)
    if disc is not None:
        lines.append(f"discovery = {disc} tokens (testimony, outside the band)")
    lines.append(f"independence = {data.get('independence')}")
    return "\n".join(lines)


# ==============================================================================
# verb handlers
# ==============================================================================


def _handle_init(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret init", add_help=False)
    p.add_argument("ws", nargs="?", default=".")
    p.add_argument("--agent")
    p.add_argument("--no-agent", action="store_true")
    p.add_argument("--name")
    _add_common(p)
    args = p.parse_args(rest)
    if args.agent and args.agent not in ("claude",):
        return _usage("init", f"unsupported agent: {args.agent!r}")
    try:
        os.makedirs(os.path.join(args.ws, kernel.STORE), exist_ok=True)
        gi_path = os.path.join(args.ws, ".gitignore")
        gi_lines = []
        if os.path.isfile(gi_path):
            with open(gi_path, "r", encoding="utf-8") as f:
                gi_lines = f.read().splitlines()
        if not any("ledger.jsonl" in line for line in gi_lines):
            gi_lines.append(".reticuli/ledger.jsonl")
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write("\n".join(gi_lines) + "\n")
        wired = None
        if args.agent == "claude":
            wired = hooks_mod.install(args.ws)
        name = args.name or os.path.basename(os.path.normpath(args.ws)) or args.ws
        data = {"name": name, "path": args.ws, "hooks": wired}
    except kernel.ClaimError as e:
        return _refuse("init", args, str(e))
    if args.json:
        _print_envelope("init", data, True, "initialized", args)
    else:
        print(f"initialized {data['name']} at {data['path']}")
    return 0


def _handle_run(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret run", add_help=False)
    p.add_argument("cmd")
    p.add_argument("-C", "--ws", default=".")
    args = p.parse_args(rest)
    proc = subprocess.run(args.cmd, shell=True, cwd=args.ws)
    try:
        entry = {"event": "bash", "cmd": args.cmd, "ts": time.time()}
        _util.locked_append(os.path.join(args.ws, kernel.STORE, "draft.jsonl"),
                             json.dumps(entry, sort_keys=True))
    except OSError:
        pass
    return proc.returncode


def _handle_hook(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    p = argparse.ArgumentParser(prog="ret hook", add_help=False)
    p.add_argument("payload", nargs="?")
    p.add_argument("-C", "--ws", default=None)
    args = p.parse_args(rest)
    raw = args.payload
    if raw is None:
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as e:
        _err("hook", f"invalid JSON payload: {e}")
        return 2
    try:
        cwd = payload.get("cwd")
        transcript = payload.get("transcript_path")
        if transcript and cwd and os.path.isdir(os.path.join(cwd, kernel.STORE)):
            session_entry = {"event": "session", "transcript": transcript, "ts": time.time()}
            _util.locked_append(os.path.join(cwd, kernel.STORE, "draft.jsonl"),
                                 json.dumps(session_entry, sort_keys=True))
        hooks_mod.event(payload)
    except kernel.ClaimError as e:
        _err("hook", str(e))
        return 1
    return 0


def _handle_status(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret status", add_help=False)
    p.add_argument("d", nargs="?", default=".")
    p.add_argument("--all", action="store_true")
    p.add_argument("--tree", action="store_true")
    p.add_argument("--claims", action="store_true")
    p.add_argument("--files", action="store_true")
    _add_common(p)
    args = p.parse_args(rest)
    d = args.d
    colored = _color_active(args)

    if args.claims:
        names = _scan_claims_names(d)
        if args.json:
            _print_envelope("status", {"claims": names}, True, "claims", args)
        else:
            print("\n".join(names) if names else "(no sealed claims)")
        return 0

    if not os.path.isdir(d):
        return _refuse("status", args, f"no such directory: {d!r}")

    if args.tree:
        text = _render_tree_claim(d, colored) if _is_claim(d) else _render_tree_draft(d)
        if args.json:
            _print_envelope("status", {"tree": text}, True, "tree", args)
        else:
            print(text)
        return 0

    if args.files:
        try:
            text = _render_files_claim(d)
        except kernel.ClaimError as e:
            return _refuse("status", args, str(e))
        if args.json:
            _print_envelope("status", {"files": text}, True, "files", args)
        else:
            print(text)
        return 0

    if _is_claim(d):
        if args.all:
            try:
                print(_render_claim_all(d))
            except kernel.ClaimError as e:
                return _refuse("status", args, str(e))
            return 0
        try:
            data = _claim_status_data(d)
        except kernel.ClaimError as e:
            return _refuse("status", args, str(e))
        ok = data.get("ok", True)
        if args.json:
            _print_envelope("status", data, True, data.get("phase", "claim"), args,
                             root=data.get("root"))
        else:
            print(_render_claim_report(d, colored))
        return 0 if ok else 0

    if args.all:
        print(_render_triad_all(d))
        return 0
    text = _render_triad_terse(d)
    if args.json:
        _print_envelope("status", {"draft": True}, True, "draft", args)
    else:
        print(text)
    return 0


def _handle_pack(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret pack", add_help=False)
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--accept", nargs="+", default=None, metavar="OUTPUT")
    p.add_argument("-o", "--output")
    p.add_argument("--name")
    p.add_argument("--pytest", action="store_true")
    p.add_argument("--environment")
    _add_common(p)
    args = p.parse_args(rest)
    if args.accept and not args.output:
        return _usage("pack", "--accept needs -o to name the destination claim directory")
    try:
        if args.accept:
            _prune_stale_trace(args.root)
            data = dict(authoring_mod.build_claim(args.root, args.accept, args.output,
                                                   name=args.name))
            _stamp_discovery(args.root, args.output)
        elif os.path.isfile(os.path.join(args.root, kernel.RECIPE)) or \
                os.path.isfile(os.path.join(args.root, "claim.toml")):
            manifest = kernel.seal(args.root)
            data = {"ok": True, "name": manifest.get("name"), "root": manifest.get("root")}
        else:
            raise kernel.ClaimError(f"nothing to pack in {args.root!r}: no recipe and no --accept")
    except kernel.ClaimError as e:
        return _refuse("pack", args, str(e))
    if args.json:
        _print_envelope("pack", data, True, "sealed", args, root=data.get("root"))
    else:
        print(f"packed {data.get('name')} {data.get('root')}")
    return 0


def _handle_pull(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret pull", add_help=False)
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("--ws")
    _add_common(p)
    args = p.parse_args(rest)
    try:
        data = registry_mod.pull(args.src, args.dest, ws=args.ws)
    except kernel.ClaimError as e:
        return _refuse("pull", args, str(e))
    if args.json:
        _print_envelope("pull", data, True, "pulled", args)
    else:
        print(f"pulled {data.get('root')}")
    return 0


def _handle_export(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret export", add_help=False)
    p.add_argument("d")
    p.add_argument("tar_path", nargs="?")
    p.add_argument("-o", "--output")
    p.add_argument("--blind", action="store_true")
    _add_common(p)
    args = p.parse_args(rest)
    path = args.output or args.tar_path
    if not path:
        return _usage("export", "export needs a destination path or -o")
    try:
        if path == "-":
            tmp = tempfile.mktemp(prefix="reticuli-export-")
            transfer_mod.export(args.d, tmp, blind=args.blind)
            with open(tmp, "rb") as f:
                sys.stdout.buffer.write(f.read())
            sys.stdout.buffer.flush()
            os.remove(tmp)
        else:
            transfer_mod.export(args.d, path, blind=args.blind)
    except kernel.ClaimError as e:
        return _refuse("export", args, str(e))
    data = {"path": path, "blind": args.blind}
    if args.json:
        _print_envelope("export", data, True, "exported", args)
    return 0


def _handle_import(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret import", add_help=False)
    p.add_argument("tar_path")
    p.add_argument("dest")
    _add_common(p)
    args = p.parse_args(rest)
    try:
        if args.tar_path == "-":
            raw = sys.stdin.buffer.read()
            tmp = tempfile.mktemp(prefix="reticuli-import-")
            with open(tmp, "wb") as f:
                f.write(raw)
            data = transfer_mod.import_(tmp, args.dest)
            os.remove(tmp)
        else:
            if not os.path.isfile(args.tar_path):
                raise kernel.ClaimError(f"no archive at {args.tar_path!r}")
            data = transfer_mod.import_(args.tar_path, args.dest)
    except kernel.ClaimError as e:
        return _refuse("import", args, str(e))
    ok = bool(data.get("ok", True))
    if args.json:
        _print_envelope("import", data, ok, "imported" if ok else "failed", args)
    return 0 if ok else 1


def _handle_verify(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret verify", add_help=False)
    p.add_argument("d", nargs="?", default=".")
    _add_common(p)
    args = p.parse_args(rest)
    try:
        data = dict(kernel.verify(args.d))
        try:
            data.setdefault("name", kernel.read_manifest(args.d).get("name"))
        except kernel.ClaimError:
            pass
        try:
            data["phase"] = kernel.phase(args.d)
        except kernel.ClaimError:
            data["phase"] = "draft"
    except kernel.ClaimError as e:
        return _refuse("verify", args, str(e))
    ok = bool(data.get("ok"))
    status = "fresh" if ok else "broken"
    if args.json:
        _print_envelope("verify", data, ok, status, args, root=data.get("root"))
        return 0 if ok else 1
    if args.verbose:
        print(_render_verify_verbose(data))
        return 0 if ok else 1
    if not ok:
        changed = data.get("changed") or []
        name = os.path.basename(os.path.normpath(args.d))
        _err("verify", f"identity drifted in {name!r} ({', '.join(changed)}); "
                        "hint: re-seal if this is the new truth, or restore the original bytes")
    return 0 if ok else 1


def _handle_audit(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret audit", add_help=False)
    p.add_argument("d", nargs="?", default=".")
    p.add_argument("--shallow", action="store_true")
    p.add_argument("--no-strict", action="store_true")
    p.add_argument("--mutants", type=int, default=None)
    p.add_argument("--record")
    _add_common(p)
    args = p.parse_args(rest)
    strict = not args.no_strict
    score = None
    try:
        _clear_pycache(args.d)
        started = time.monotonic()
        data = dict(_call_kernel_audit(args.d, strict))
        elapsed = time.monotonic() - started

        layers = []
        if not args.shallow:
            try:
                comps = registry_mod.components_of(args.d)
            except Exception:
                comps = []
            if comps:
                deep = registry_mod.audit_deep(args.d)
                data["ok"] = bool(data.get("ok")) and bool(deep.get("ok"))
                layers = deep.get("layers", [])
        data.setdefault("layers", layers)

        try:
            ver = kernel.verify(args.d)
            data.setdefault("recomputed", ver.get("recomputed"))
        except kernel.ClaimError:
            data.setdefault("recomputed", None)
        data["elapsed"] = elapsed
        data.setdefault("environment", data.get("environment") or [])
        try:
            manifest = kernel.read_manifest(args.d)
            data.setdefault("name", manifest.get("name"))
            data.setdefault("root", manifest.get("root"))
        except kernel.ClaimError:
            pass

        if args.mutants is not None:
            try:
                score = kernel.mutation_score(args.d, max_mutants=args.mutants)
            except kernel.ClaimError:
                score = None

        if data.get("ok") and os.path.isdir(args.d):
            os.makedirs(os.path.join(args.d, kernel.STORE), exist_ok=True)
            with open(_audit_receipt_path(args.d), "w", encoding="utf-8") as f:
                json.dump({"ok": True, "when": _stamp()}, f)

        if args.record:
            try:
                doc = record_mod.emit(args.d)
                record_mod.write(doc, args.record)
            except kernel.ClaimError:
                pass
    except kernel.ClaimError as e:
        return _refuse("audit", args, str(e))
    except Exception as e:  # noqa: BLE001 -- audit must never raise raw
        return _refuse("audit", args, f"audit failed: {e}")

    ok = bool(data.get("ok"))
    status = _audit_status_word(data)
    if args.json:
        _print_envelope("audit", data, ok, status, args, root=data.get("root"))
        return 0 if ok else 1
    if args.verbose:
        print(_render_audit_verbose(data))
        if score is not None:
            print(_render_mutation_verbose(score))
        return 0 if ok else 1
    if not ok:
        _err("audit", status)
    return 0 if ok else 1


def _handle_assess(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret assess", add_help=False)
    p.add_argument("d", nargs="?", default=".")
    p.add_argument("--mutants", type=int, default=50)
    _add_common(p)
    args = p.parse_args(rest)
    try:
        data = dict(assess_mod.assess(args.d, mutants=args.mutants))
        parsed = kernel.load_recipe(args.d)
    except kernel.ClaimError as e:
        return _refuse("assess", args, str(e))
    declared = [s.get("output") for s in parsed.get("step", []) if _step_class(s) != "generated"]
    gate_outputs = [s.get("output") for s in parsed.get("step", []) if s.get("kind") == "gate"]
    data["declared"] = declared
    data["gate"] = gate_outputs
    os.makedirs(os.path.join(args.d, kernel.STORE), exist_ok=True)
    with open(_assess_receipt_path(args.d), "w", encoding="utf-8") as f:
        json.dump({"when": _stamp()}, f)
    if args.json:
        _print_envelope("assess", data, True, "measured", args)
    else:
        print(f"mutants={data.get('mutants')} rate={data.get('rate')}")
    return 0


def _handle_rebuild(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret rebuild", add_help=False)
    p.add_argument("d")
    p.add_argument("--producer")
    p.add_argument("-o", "--output", dest="into")
    p.add_argument("--without-guidance", action="store_true")
    _add_common(p)
    args = p.parse_args(rest)
    if not args.producer or not args.into:
        return _usage("rebuild", "rebuild needs --producer and -o/--output")
    try:
        cmd = _expand_producer(args.producer)
        data = dict(kernel.rebuild(args.d, cmd, args.into, guidance=not args.without_guidance))
    except kernel.ClaimError as e:
        return _refuse("rebuild", args, str(e))
    if args.json:
        _print_envelope("rebuild", data, True, "rebuilt", args, root=data.get("root"))
    else:
        print(f"rebuilt {data.get('name')} {data.get('root')}")
    return 0


def _handle_crosscheck(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret crosscheck", add_help=False)
    p.add_argument("machines", nargs="*")
    p.add_argument("--shallow", action="store_true")
    p.add_argument("--mutants", type=int, default=None)
    _add_common(p)
    args = p.parse_args(rest)
    machines = args.machines
    if len(machines) < 2:
        return _usage("crosscheck", "crosscheck needs at least two machines to compare")

    tmp_dir = None
    m2_materialized = False
    try:
        if len(machines) == 2:
            m1, m3 = machines[0], machines[1]
            tmp_dir = tempfile.mkdtemp(prefix="reticuli-m2-")
            m2 = os.path.join(tmp_dir, "m2")
            shutil.copytree(m1, m2)
            m2_materialized = True
        else:
            m1, m2, m3 = machines[0], machines[1], machines[2]
        data = dict(kernel.crosscheck(m1, m2, m3, mutants=args.mutants))
    except kernel.ClaimError as e:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return _refuse("crosscheck", args, str(e))
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    data["m2_materialized"] = m2_materialized
    ok = bool(data.get("satisfied"))
    status = data.get("verdict", "?")
    if args.json:
        _print_envelope("crosscheck", data, ok, status, args, root=None)
        return 0 if ok else 1
    if not ok:
        _err("crosscheck", f"{status}: " + ", ".join(data.get("rejected") or []))
    elif args.verbose:
        print(_render_crosscheck_verbose(data, m1))
    return 0 if ok else 1


def _handle_record(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret record", add_help=False)
    p.add_argument("d", nargs="?", default=".")
    p.add_argument("-o", "--out")
    p.add_argument("--key")
    p.add_argument("--as", dest="as_")
    p.add_argument("--sign", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--signers")
    _add_common(p)
    args = p.parse_args(rest)
    try:
        if args.check:
            data = attest_mod.check(args.d, signers=args.signers)
            ok = bool(data.get("ok"))
            if args.json:
                _print_envelope("record", data, ok, "checked", args)
            return 0 if ok else 1
        if args.key and args.as_:
            data = dict(attest_mod.attest(args.d, args.key, args.as_))
            data.setdefault("ok", True)
            if args.json:
                _print_envelope("record", data, True, "attested", args)
            return 0
        if args.sign and not args.key and not os.environ.get("RETICULI_KEY"):
            raise kernel.ClaimError(
                "record --sign needs the RETICULI_KEY environment variable naming a signing key")
        doc = record_mod.emit(args.d)
        path = args.out or os.path.join(args.d, "record.json")
        record_mod.write(doc, path)
        sign_key = args.key or (os.environ.get("RETICULI_KEY") if args.sign else None)
        if sign_key:
            record_mod.sign(path, sign_key)
        data = {"path": path, "digest": kernel.record_digest(doc), "record": doc}
    except kernel.ClaimError as e:
        return _refuse("record", args, str(e))
    if args.json:
        _print_envelope("record", data, True, "recorded", args)
    return 0


def _signers_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "allowed_signers")


def _append_signer(d: str, key: str, principal: str) -> None:
    try:
        pub = subprocess.run(["ssh-keygen", "-y", "-f", key], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return
    if not pub:
        return
    path = _signers_path(d)
    existing = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    line = f"{principal} {pub}\n"
    if line not in existing:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def _default_signers(d: str, explicit):
    if explicit:
        return explicit
    path = _signers_path(d)
    return path if os.path.isfile(path) else None


def _handle_sign(rest, verb) -> int:
    if _wants_full_help(rest):
        _print_full_account(verb)
        return 0
    if _wants_concise_help(rest):
        print(_USAGE[verb])
        return 0
    p = argparse.ArgumentParser(prog="ret sign", add_help=False)
    p.add_argument("d")
    p.add_argument("--key")
    p.add_argument("--as", dest="as_")
    p.add_argument("--check", action="store_true")
    p.add_argument("--ws")
    p.add_argument("--signers")
    _add_common(p)
    args = p.parse_args(rest)
    try:
        if args.check:
            signers = _default_signers(args.d, args.signers)
            data = attest_mod.sign_check(args.d, ws=args.ws, signers=signers)
            ok = bool(data.get("ok"))
            if args.json:
                _print_envelope("sign", data, ok, "checked", args)
            return 0 if ok else 1
        if args.key and args.as_:
            data = attest_mod.sign(args.d, args.key, args.as_, ws=args.ws)
            _append_signer(args.d, args.key, args.as_)
            if args.json:
                _print_envelope("sign", data, True, "signed", args)
            return 0
        data = attest_mod.review_packet(args.d, ws=args.ws)
    except kernel.ClaimError as e:
        return _refuse("sign", args, str(e))
    if args.json:
        _print_envelope("sign", data, True, "review", args)
    elif args.verbose:
        print(_render_review_verbose(data))
    else:
        print(f"review packet for root {data.get('root')}")
    return 0


# ==============================================================================
# main: the one place argv becomes an exit code
# ==============================================================================

_HANDLERS = {
    "init": _handle_init, "run": _handle_run, "status": _handle_status,
    "pack": _handle_pack, "pull": _handle_pull, "export": _handle_export,
    "import": _handle_import, "verify": _handle_verify, "audit": _handle_audit,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "crosscheck": _handle_crosscheck,
    "record": _handle_record, "sign": _handle_sign,
    "hook": _handle_hook, "help": _handle_help, "completion": _handle_completion,
}


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        _print_top_help()
        return 1
    first = argv[0]
    if first in ("-h", "--help"):
        _print_top_help()
        return 0
    if first == "--version":
        print(_version_line())
        return 0
    verb, rest = first, argv[1:]
    fn = _HANDLERS.get(verb)
    if fn is None:
        return _unknown_verb(verb)
    return fn(rest, verb)


def verbs():
    """Every registered subcommand name -- porcelain, alias, and
    plumbing alike."""
    return tuple(sorted(PORCELAIN | ALIASES | set(PLUMBING)))

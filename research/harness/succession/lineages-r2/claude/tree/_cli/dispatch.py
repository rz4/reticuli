"""reticuli._cli.dispatch: the fourteen-verb grammar (spec/layers.md, surface layer).

This module owns the argv grammar, the human/machine output split, and the
per-verb wiring into the layers beneath (`kernel`, `registry`, `transfer`,
`attest`, `record`, `authoring`, `pack`, `hooks`, `assess`, `feedback`,
`render`, `_util`). It never reaches past those modules' own public
surfaces. `reticuli.cli` re-exports `main` and `verbs` from here; that is
the whole seam a rebuild is pinned by.

Stdlib only.
"""
import argparse
import difflib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from .. import (attest as attest_mod, authoring, feedback, hooks, kernel,
                 pack as pack_mod, record as record_mod, registry, render,
                 transfer, _util)
from ..assess import assess as run_assess
from . import handlers, output

# ---------------------------------------------------------------------------
# the grammar: fourteen porcelain verbs, three plumbing verbs, no aliases
# ---------------------------------------------------------------------------

PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")
PLUMBING = ("hook", "help", "completion")


def verbs() -> set:
    """Every argv token the parser recognizes: the fourteen porcelain verbs
    plus the three plumbing verbs. No accepted older spellings remain."""
    return set(PORCELAIN) | set(PLUMBING)


_VERB_ONELINE = {
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
    "hook": "internal: translate one coding-agent hook payload",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}

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
    "    sign        authorize a claim or proof"
)

_EPILOG = (
    "See 'ret <command> -h' for command usage.\n"
    "See 'ret help <command>' for detailed help; 'ret help -a' lists everything,\n"
    "including plumbing."
)

# ---------------------------------------------------------------------------
# detailed help ('ret help <topic>'; also folded into each subparser's
# description so '<verb> --help' carries the same account under a SYNOPSIS
# header)
# ---------------------------------------------------------------------------

_HELP_DETAIL = {
    "init": (
        "init\n"
        "    Mark a directory as a reticuli session: create its store, wire\n"
        "    the coding-agent handshake (unless --no-agent), and hand off to\n"
        "    a named producer's own agent session if --agent/--producer or\n"
        "    RETICULI_PRODUCER names one. --agent validates the coding\n"
        "    agent whose hooks get wired; an unsupported value refuses."
    ),
    "run": (
        "run\n"
        "    Run one command inside a session, traced into its own draft\n"
        "    trace the same way an agent's own Bash calls are traced. The\n"
        "    child's exit code is returned UNCHANGED: a session's own driver\n"
        "    can use `ret run` as a predicate without translation."
    ),
    "status": (
        "status\n"
        "    The pure view: reads and reports, never executes. A draft\n"
        "    session shows the authoring triad (observed/declared/\n"
        "    unresolved); a sealed claim shows identity, audit and\n"
        "    assessment residue, and the next rung on the ladder toward\n"
        "    `signed`. --tree/--claims/--files/--all are alternate lenses."
    ),
    "pack": (
        "pack\n"
        "    Seal a project as a claim: one boundary, three sources. A\n"
        "    traced session is certified with --accept (needs -o); an\n"
        "    already-declared reticuli.toml seals in place with zero flags;\n"
        "    otherwise --name/--gate/--generated/--inputs/--environment/\n"
        "    --pytest build a fresh self-claim from glob patterns."
    ),
    "pull": (
        "pull\n"
        "    Materialize a claim's current declared content flat into a\n"
        "    fresh directory, and seal it there: a claim becomes a\n"
        "    dependency of a fresh workspace."
    ),
    "export": (
        "export\n"
        "    Write a deterministic tar of a claim's declared content.\n"
        "    --blind withholds every generated output: the room a\n"
        "    rebuilder is asked to regrow, never the implementation itself.\n"
        "    An output of '-' (or -o -) streams the tar to stdout."
    ),
    "import": (
        "import\n"
        "    Extract an archive into a fresh directory, then recompute\n"
        "    identity from the received bytes: verify-on-import, never a\n"
        "    trusted copy. An archive of '-' reads the tar from stdin."
    ),
    "verify": (
        "verify\n"
        "    Recompute the claim's root from the bytes present and compare\n"
        "    it with the sealed manifest. Identity only.\n"
        "    Does not execute acceptance criteria -- for that, use `ret audit`."
    ),
    "audit": (
        "audit\n"
        "    Rerun every acceptance gate, cold and sandboxed, in a fresh\n"
        "    room. Judging is done in the strict jail by default -- a\n"
        "    claim's gates never read your files; --no-strict opts down.\n"
        "    Recurses into composed claims unless --shallow."
    ),
    "assess": (
        "assess\n"
        "    Measure how much a claim's own gates prove, gate by gate, with\n"
        "    deterministic mutation testing (--mutants caps the sample)."
    ),
    "rebuild": (
        "rebuild\n"
        "    Regrow a claim's generated outputs from a producer until\n"
        "    every gate passes. The claim's own generated sources are\n"
        "    withheld from the producer's room; only the pinned check\n"
        "    travels.\n\n"
        "    The producer may be one of the shipped names (--producer\n"
        "    codex, --producer claude, --producer openai) or any program:\n"
        "    a literal shell command line is accepted directly."
    ),
    "crosscheck": (
        "crosscheck\n"
        "    The three-machine test: one root across all three, byte reuse\n"
        "    between M1 and M2, every gate re-earned, and every condition\n"
        "    the claim itself declares. Given only M1 and M3, M2 is a real\n"
        "    byte-copy of M1, materialized on the spot and disclosed."
    ),
    "record": (
        "record\n"
        "    Emit a signed statement of what THIS machine establishes about\n"
        "    a claim right now. With --as (and --key), attests the current\n"
        "    build in place instead; --check reads attestations back.\n"
        "    --sign uses RETICULI_KEY when no --key is given."
    ),
    "sign": (
        "sign\n"
        "    The accountable ceremony: with no key, prints the review\n"
        "    packet a signer would stand behind. --key/--as authorizes it;\n"
        "    --check reads authorizations back."
    ),
    "hook": (
        "hook\n"
        "    Internal: translate one coding-agent hook payload (read from\n"
        "    stdin) into a session's own draft trace."
    ),
    "help": (
        "help\n"
        "    Show detailed help for a command, or -a for everything."
    ),
    "completion": (
        "completion\n"
        "    Print a shell completion script, generated from the grammar."
    ),
    "environment": (
        "environment\n"
        "    RETICULI_KEY        default ssh key used by record/sign --sign\n"
        "    RETICULI_SIGNERS    allowed-signers file consulted at read time\n"
        "    RETICULI_COLOR      auto/always/never -- overrides --color\n"
        "    RETICULI_PRODUCER   default agent CLI launched by `ret init`\n"
        "    RETICULI_TOLERANCE  overrides the crosscheck cost-band tolerance\n"
        "    RETICULI_GATE_TIMEOUT  ceiling on a gate's own declared timeout\n"
        "    RETICULI_ENV_CACHE  where furnished venvs are cached\n"
        "    RETICULI_JAILED     internal: names the sandbox already applied\n"
        "    OPENAI_API_KEY      credential required by --producer openai"
    ),
}


def _synopsis(verb: str) -> str:
    detail = _HELP_DETAIL.get(verb, f"{verb}\n    {_VERB_ONELINE.get(verb, '')}")
    return f"SYNOPSIS\n    ret {verb} ...\n\n{detail}"


# ---------------------------------------------------------------------------
# small shared primitives
# ---------------------------------------------------------------------------

def _refuse(cmd: str, msg: str, args) -> int:
    """The one-voice refusal: a stderr line under plain output, or the
    stable error envelope on stdout (empty stderr) under --json."""
    if getattr(args, "json", False):
        print(json.dumps({"command": cmd, "ok": False, "status": "error",
                          "root": None, "data": {"error": msg}}, sort_keys=True))
    else:
        output._err(cmd, msg)
    return 1


def _print_envelope(cmd: str, ok: bool, status: str, root, data, args) -> None:
    print(json.dumps({"command": cmd, "ok": ok, "status": status,
                      "root": root, "data": data}, sort_keys=True))


def _short(value) -> str:
    """The first 12 characters of a hash-like string -- no ellipsis, so
    the metaphor-era glyph never rides in captured output."""
    if not value:
        return ""
    return value[:12]


def _is_sealed(d: str) -> bool:
    return os.path.isfile(os.path.join(d, kernel.MANIFEST))


def _read_json_residue(path: str):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _read_receipt(d: str, name: str):
    return _read_json_residue(os.path.join(d, kernel.STORE, name))


def _write_receipt(d: str, name: str, payload: dict) -> None:
    path = os.path.join(d, kernel.STORE, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)


def _ledger_entries(d: str) -> list:
    path = os.path.join(d, kernel.LEDGER)
    if not os.path.isfile(path):
        return []
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _discovery_tokens(d: str):
    total = 0
    found = False
    for e in _ledger_entries(d):
        if e.get("event") == "discovery" and "discovery_tokens" in e:
            total += e["discovery_tokens"]
            found = True
    return total if found else None


def _discovery_from_session(ws: str):
    """Sum the input+output token usage reported by every coding-agent
    transcript a session's own trace names -- the discovery bill, carried
    as reported testimony, never fed into the measured cost band."""
    trace_path = os.path.join(ws, hooks.TRACE)
    if not os.path.isfile(trace_path):
        return None
    total = 0
    found = False
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") != "session":
                continue
            transcript = e.get("transcript")
            if not isinstance(transcript, str) or not os.path.isfile(transcript):
                continue
            with open(transcript, "r", encoding="utf-8") as tf:
                for tline in tf:
                    tline = tline.strip()
                    if not tline:
                        continue
                    try:
                        rec = json.loads(tline)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    message = rec.get("message")
                    usage = message.get("usage") if isinstance(message, dict) else None
                    if isinstance(usage, dict):
                        it = usage.get("input_tokens") or 0
                        ot = usage.get("output_tokens") or 0
                        total += it + ot
                        found = True
    return total if found else None


def _snapshot_parts(d: str) -> None:
    """A diagnostic residue snapshot of every declared path's current hash
    -- never part of identity, used only so a later `verify` failure can
    NAME which declared path moved since sealing."""
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        return
    parts = {}
    for p in parsed.get("claim", {}).get("inputs", []):
        full = os.path.join(d, p)
        if os.path.isfile(full):
            parts[p] = kernel._hash_file(full)
    for step in parsed.get("step", []):
        if step["class"] in ("generated", "free"):
            continue
        full = os.path.join(d, step["output"])
        if os.path.isfile(full):
            parts[step["output"]] = kernel._hash_file(full)
    _write_receipt(d, "parts.json", parts)


def _diagnose_broken(d: str) -> str:
    snap = _read_receipt(d, "parts.json")
    changed = []
    if snap:
        try:
            parsed = kernel.load_recipe(d)
        except kernel.ClaimError:
            parsed = None
        if parsed is not None:
            paths = list(parsed.get("claim", {}).get("inputs", []))
            paths += [s["output"] for s in parsed.get("step", [])
                      if s["class"] not in ("generated", "free")]
            for p in paths:
                full = os.path.join(d, p)
                cur = kernel._hash_file(full) if os.path.isfile(full) else None
                if snap.get(p) != cur:
                    changed.append(p)
    if changed:
        return (f"broken: {', '.join(changed)} changed since sealing; "
                f"hint: restore {changed[0]} or re-pack the claim")
    return "broken: the claim no longer verifies; hint: restore its declared files or re-pack it"


def _local_signers_path(d: str) -> str:
    return os.path.join(d, kernel.SIGN_DIR, "signers")


def _remember_sign_signer(d: str, keypath: str, identity: str) -> None:
    try:
        done = subprocess.run(["ssh-keygen", "-y", "-f", keypath],
                              capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return
    pub = done.stdout.strip()
    if not pub:
        return
    path = _local_signers_path(d)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = f"{identity} {pub}\n"
    existing = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = f.read()
    if line not in existing:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)


def _statement_counts(d: str) -> tuple:
    n_att = signed_att = 0
    try:
        att = attest_mod.check(d)
        n_att = len(att.get("attestations", []))
        signed_att = sum(1 for a in att["attestations"] if a.get("verdict") == "signed")
    except Exception:
        pass
    n_sign = signed_sign = 0
    try:
        local = _local_signers_path(d)
        signers = local if os.path.isfile(local) else None
        sc = attest_mod.sign_check(d, signers=signers)
        n_sign = len(sc.get("authorizations", []))
        signed_sign = sum(1 for a in sc["authorizations"] if a.get("verdict") == "authorized")
    except Exception:
        pass
    return n_att + n_sign, signed_att + signed_sign


def _safe_phase(d: str):
    try:
        return kernel.phase(d)
    except kernel.ClaimError:
        return "broken"


def _next_step(d: str, audit_receipt, assess_receipt) -> str:
    if not audit_receipt:
        return "earn an audit: `ret audit`"
    if not assess_receipt:
        return "measure the tests: `ret assess`"
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    if not manifest.get("proof"):
        return "prove independence: `ret crosscheck`"
    if _safe_phase(d) != "signed":
        return "authorize it: `ret sign`"
    return "nothing further -- the claim is signed"


# ---------------------------------------------------------------------------
# status: the draft (session) model
# ---------------------------------------------------------------------------

def _trace_events(ws: str) -> list:
    path = os.path.join(ws, hooks.TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _draft_model(ws: str):
    events = _trace_events(ws)
    has_gate = any(e.get("event") == "bash" for e in events)
    rows = {}
    for e in events:
        kind = e.get("event")
        if kind in ("write", "read") and isinstance(e.get("path"), str):
            rows[e["path"]] = (kind, e.get("via") or "-")
    resolved, unresolved = {}, {}
    for path, (kind, via) in rows.items():
        exists = os.path.isfile(os.path.join(ws, path))
        if exists and has_gate:
            cls = "generated" if kind == "write" else "pinned"
            resolved[path] = (kind, cls, via)
        else:
            unresolved[path] = (kind, "undeclared", via)
    gate_rows = [["gate", "bash", "validated", e.get("via") or "-"]
                 for e in events if e.get("event") == "bash"]
    return rows, resolved, unresolved, gate_rows


def _draft_summary_line(ws: str) -> str:
    rows, resolved, unresolved, _gate_rows = _draft_model(ws)
    line = (f"draft: observed={len(rows)} declared={len(resolved)} "
            f"unresolved={len(unresolved)}")
    line += " packable" if not unresolved else " undeclared"
    return line


def _draft_all_lines(ws: str) -> list:
    rows, resolved, unresolved, gate_rows = _draft_model(ws)
    table_rows = []
    for path in sorted(rows):
        if path in resolved:
            kind, cls, via = resolved[path]
        else:
            kind, cls, via = unresolved[path]
        table_rows.append([path, kind, cls, via])
    for base, _dirs, files in os.walk(ws):
        for fname in files:
            full = os.path.join(base, fname)
            rel = os.path.relpath(full, ws).replace(os.sep, "/")
            if rel.startswith(".reticuli/") or rel.startswith(".claude/"):
                continue
            if rel not in rows:
                table_rows.append([rel, "-", "-", "-"])
    for g in gate_rows:
        table_rows.append(g)
    table_text = render.table(table_rows, headers=["path", "observed", "declared", "evidence"])
    return table_text.split("\n")


# ---------------------------------------------------------------------------
# status: the sealed-claim model
# ---------------------------------------------------------------------------

def _claim_lines(d: str, args=None) -> list:
    manifest = kernel.read_manifest(d)
    name = manifest.get("name")
    root = manifest.get("root") or ""
    try:
        ok = kernel.verify(d)["ok"]
    except kernel.ClaimError:
        ok = False
    if not ok:
        return [f"{name}  broken",
                "  " + _diagnose_broken(d)]

    ident_word = "fresh"
    if args is not None and output._use_color(args):
        ident_word = output._paint(ident_word, "green", args)
    lines = [f"{name}  (identity: {ident_word}, root {_short(root)})"]

    audit_receipt = _read_receipt(d, "audit.receipt.json")
    if audit_receipt:
        lines.append(f"  audited: {audit_receipt.get('when')} on this machine")

    discovery = _discovery_tokens(d)
    if discovery:
        lines.append(f"  discovery: {discovery} tokens (reported testimony)")

    assess_receipt = _read_receipt(d, "assess.receipt.json")
    n_stmt, n_signed = _statement_counts(d)
    if n_stmt:
        lines.append(f"  {n_stmt} statement(s): {n_signed} signed")

    lines.append(f"  next: {_next_step(d, audit_receipt, assess_receipt)}")
    return lines


def _claim_json_data(d: str) -> dict:
    manifest = kernel.read_manifest(d)
    try:
        ok = kernel.verify(d)["ok"]
    except kernel.ClaimError:
        ok = False
    audit_receipt = _read_receipt(d, "audit.receipt.json")
    assess_receipt = _read_receipt(d, "assess.receipt.json")
    n_stmt, _n_signed = _statement_counts(d) if ok else (0, 0)
    deciding = []
    if ok:
        try:
            parsed = kernel.load_recipe(d)
            for step in parsed.get("step", []):
                if step.get("kind") == "gate":
                    deciding.append({"output": step["output"],
                                     "deciders": kernel.gate_deciders(step.get("run", ""))})
        except kernel.ClaimError:
            pass
    return {
        "name": manifest.get("name"),
        "root": manifest.get("root"),
        "phase": _safe_phase(d) if ok else "broken",
        "audited": bool(audit_receipt),
        "deciding": deciding,
        "proof": manifest.get("proof"),
        "signatures": n_stmt,
        "next": _next_step(d, audit_receipt, assess_receipt) if ok else "restore the claim",
    }


def _tree_node(name: str, path: str) -> dict:
    manifest = kernel.read_manifest(path)
    children = [_tree_node(cname, os.path.join(path, rel))
                for cname, rel in (manifest.get("components") or {}).items()]
    return {"label": name, "children": children}


def _tree_lines_claim(d: str, args=None) -> list:
    manifest = kernel.read_manifest(d)
    parsed = kernel.load_recipe(d)
    n_layers = 1 + len(manifest.get("components") or {})
    lines = [f"{manifest.get('name')}  layers={n_layers}"]
    colored = args is not None and output._use_color(args)
    for step in parsed.get("step", []):
        is_generated = step["class"] in ("generated", "free")
        label = "generated" if is_generated else "pinned"
        color = "cyan" if is_generated else "green"
        if colored:
            lines.append(f"  {output._paint(step['output'], color, args)}")
        else:
            lines.append(f"  {label:<11}{step['output']}")
    for path in parsed.get("claim", {}).get("inputs", []):
        if colored:
            lines.append(f"  {output._paint(path, 'green', args)}")
        else:
            lines.append(f"  {'pinned':<11}{path}")
    return lines


def _tree_lines_dispatch(d: str, args=None) -> list:
    if _is_sealed(d):
        return _tree_lines_claim(d, args)
    return [_draft_summary_line(d)]


def _files_lines(d: str) -> list:
    manifest = kernel.read_manifest(d)
    parsed = kernel.load_recipe(d)
    role_for = {"generated": "free", "free": "free", "pinned": "input", "validated": "verdict"}
    rows = []
    for path in parsed.get("claim", {}).get("inputs", []):
        rows.append(["pinned", path, "input"])
    for step in parsed.get("step", []):
        cls = step["class"]
        rows.append([step["output"], cls, role_for.get(cls, cls)])
    lines = [f"{manifest.get('name')}  files"]
    for output_name, cls, role in rows:
        lines.append(f"  {output_name:<24}{cls:<12}{role}")
    return lines


def _claims_lines(ws: str) -> list:
    cs = registry.claims(ws)
    if not cs:
        return ["no claims"]
    return [f"{c['name']}  {c['phase']}  {_short(c['root'])}" for c in cs]


def _all_lines(d: str, args=None) -> list:
    if not _is_sealed(d):
        return _draft_all_lines(d)
    lines = list(_claim_lines(d, args))
    lines.append("")
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        parsed = {"claim": {}, "step": []}
    claim_tbl = parsed.get("claim", {})
    fixed = []
    if "tolerance" in claim_tbl:
        fixed.append(f"tolerance={claim_tbl['tolerance']}")
    if "mutation_floor" in claim_tbl:
        fixed.append(f"mutation_floor={claim_tbl['mutation_floor']}")
    if "envelope" in claim_tbl:
        fixed.append("envelope=" + ",".join(sorted(claim_tbl["envelope"])))
    lines.append(f"fixed: {', '.join(fixed) if fixed else 'none declared'}")

    deciders = set()
    for step in parsed.get("step", []):
        if step.get("kind") == "gate":
            deciders.update(kernel.gate_deciders(step.get("run", "")))
    lines.append(f"deciding: {', '.join(sorted(deciders)) if deciders else 'the recipe text itself'}")

    generated = [s["output"] for s in parsed.get("step", []) if s["class"] in ("generated", "free")]
    lines.append(f"free: {', '.join(generated) if generated else 'none'}")

    audit_receipt = _read_receipt(d, "audit.receipt.json")
    assess_receipt = _read_receipt(d, "assess.receipt.json")
    recorded = []
    if audit_receipt:
        recorded.append(f"audit, {audit_receipt.get('when')}: a receipt, not a verdict")
    if assess_receipt:
        recorded.append(f"assess, {assess_receipt.get('when')}: a receipt, not a verdict")
    lines.append(f"recorded: {'; '.join(recorded) if recorded else 'none'}")

    unknown = [] if assess_receipt else ["mutation coverage"]
    lines.append(f"unknown: {', '.join(unknown) if unknown else 'none'}")

    lines.append(f"next: {_next_step(d, audit_receipt, assess_receipt)}")
    return lines


# ---------------------------------------------------------------------------
# init / run / hook
# ---------------------------------------------------------------------------

_SUPPORTED_AGENTS = {"claude"}


def _ensure_gitignore(ws: str) -> None:
    path = os.path.join(ws, ".gitignore")
    line = ".reticuli/ledger.jsonl\n"
    content = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if "ledger.jsonl" in content:
            return
    with open(path, "a", encoding="utf-8") as f:
        if content and not content.endswith("\n"):
            f.write("\n")
        f.write(line)


def _cmd_init(args):
    agent = args.agent
    if agent is not None and agent not in _SUPPORTED_AGENTS:
        output._err("init", f"unsupported agent: {agent!r}")
        return 2
    try:
        result = handlers.init(args.workspace, producer=args.producer, no_agent=args.no_agent)
    except kernel.ClaimError as e:
        return _refuse("init", str(e), args)
    _ensure_gitignore(args.workspace)
    if args.json:
        _print_envelope("init", True, result.get("status", "initialized"), None, result, args)
        return 0
    print(f"initialized {result.get('path')}")
    return 0


def _cmd_run(args):
    return handlers.run(args.cmd, args.workspace)


def _cmd_hook(args):
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        transcript = payload.get("transcript_path")
        if (isinstance(cwd, str) and isinstance(transcript, str)
                and os.path.isdir(os.path.join(cwd, kernel.STORE))):
            entry = {"event": "session", "transcript": transcript,
                     "ts": time.time(), "via": "hook"}
            _util.locked_append(os.path.join(cwd, hooks.TRACE),
                                json.dumps(entry, sort_keys=True))
    try:
        hooks.event(payload)
    except OSError:
        pass
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def _cmd_status(args):
    d = args.claim
    if not os.path.isdir(d):
        return _refuse("status", f"no such directory: {d!r}", args)
    try:
        if args.tree:
            lines = _tree_lines_dispatch(d, args)
            data, root = {"lines": lines}, None
        elif args.claims:
            lines = _claims_lines(d)
            data, root = {"lines": lines}, None
        elif args.files:
            lines = _files_lines(d)
            data, root = {"lines": lines}, None
        elif args.all:
            lines = _all_lines(d, args)
            data, root = {"lines": lines}, None
        elif args.draft:
            lines = [_draft_summary_line(d)]
            data, root = {"lines": lines}, None
        elif _is_sealed(d):
            lines = _claim_lines(d, args)
            data = _claim_json_data(d)
            root = data["root"]
        else:
            if not os.path.isdir(os.path.join(d, kernel.STORE)):
                raise kernel.ClaimError(f"not a session or claim: {d!r}")
            lines = [_draft_summary_line(d)]
            data, root = {"lines": lines}, None
    except kernel.ClaimError as e:
        return _refuse("status", str(e), args)
    if args.json:
        _print_envelope("status", True, "claim", root, data, args)
        return 0
    for line in lines:
        print(line)
    return 0


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------

def _accept_pack(ws: str, outputs: list, output_dir: str, name):
    """Certify a traced session, filtering out any traced write whose file
    never materialized (or was later deleted) before authoring reads the
    trace -- a stray such event must not crash pack."""
    trace_path = os.path.join(ws, authoring.TRACE)
    original = None
    if os.path.isfile(trace_path):
        with open(trace_path, "r", encoding="utf-8") as f:
            original = f.read()
        kept = []
        for line in original.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                e = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(stripped)
                continue
            if e.get("event") == "write" and isinstance(e.get("path"), str):
                if not os.path.isfile(os.path.join(ws, e["path"])):
                    continue
            kept.append(stripped)
        with open(trace_path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
    try:
        result = authoring.build_claim(ws, outputs, output_dir, name=name)
    finally:
        if original is not None:
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write(original)
    discovery = _discovery_from_session(ws)
    if discovery:
        kernel.ledger(output_dir, {"event": "discovery", "discovery_tokens": discovery})
    _snapshot_parts(output_dir)
    return result


def _apply_environment(path: str, value: str) -> dict:
    import tomllib
    recipe_path = os.path.join(path, kernel.RECIPE)
    with open(recipe_path, "r", encoding="utf-8") as f:
        text = f.read()
    doc = tomllib.loads(text)
    doc.setdefault("claim", {})["environment"] = value
    with open(recipe_path, "w", encoding="utf-8") as f:
        f.write(render.toml(doc))
    return kernel.seal(path)


def _cmd_pack(args):
    path = args.path
    try:
        if args.accept is not None:
            if not args.output:
                output._err("pack", "--accept needs -o/--output naming the claim to write")
                return 2
            result = _accept_pack(path, list(args.accept), args.output, args.name)
        else:
            has_recipe = (os.path.isfile(os.path.join(path, kernel.RECIPE))
                          or os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE)))
            if has_recipe:
                result = kernel.seal(path)
                _snapshot_parts(path)
            elif args.name and (args.gate or args.pytest):
                gate = args.gate or "python3 -m pytest -q"
                result = pack_mod.pack(path, args.name, args.generated, args.inputs,
                                       gate, args.gate_output or "OK")
                if args.environment:
                    result = _apply_environment(path, args.environment)
                _snapshot_parts(path)
                if args.into:
                    registry.pull(path, args.into)
            else:
                raise kernel.ClaimError(
                    "nothing to pack: no reticuli.toml declared, and no --name/--gate given")
    except kernel.ClaimError as e:
        return _refuse("pack", str(e), args)
    except OSError as e:
        return _refuse("pack", f"nothing to pack: {e}", args)
    name, root = result.get("name"), result.get("root") or ""
    if args.json:
        _print_envelope("pack", True, "packed", root, result, args)
        return 0
    print(f"packed {name} ({_short(root)})")
    return 0


# ---------------------------------------------------------------------------
# pull / export / import
# ---------------------------------------------------------------------------

def _cmd_pull(args):
    try:
        result = registry.pull(args.claim, args.into)
    except kernel.ClaimError as e:
        return _refuse("pull", str(e), args)
    if args.json:
        _print_envelope("pull", True, "pulled", result.get("root"), result, args)
        return 0
    print(f"pulled {result.get('name')} ({_short(result.get('root') or '')})")
    return 0


def _cmd_export(args):
    dest = args.output if args.output is not None else args.out
    if not dest:
        return _refuse("export", "export needs an output path (positional or -o)", args)
    try:
        if dest == "-":
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="ret-export-", suffix=".tar")
            os.close(tmp_fd)
            try:
                transfer.export(args.claim, tmp_path, blind=args.blind)
                with open(tmp_path, "rb") as f:
                    shutil.copyfileobj(f, sys.stdout.buffer)
                sys.stdout.buffer.flush()
            finally:
                os.remove(tmp_path)
            return 0
        result = transfer.export(args.claim, dest, blind=args.blind)
    except kernel.ClaimError as e:
        return _refuse("export", str(e), args)
    if args.json:
        _print_envelope("export", True, "exported", None, result, args)
    return 0


def _cmd_import(args):
    try:
        if args.archive == "-":
            tmp_fd, tmp_path = tempfile.mkstemp(prefix="ret-import-", suffix=".tar")
            try:
                with os.fdopen(tmp_fd, "wb") as f:
                    shutil.copyfileobj(sys.stdin.buffer, f)
                result = transfer.import_(tmp_path, args.into)
            finally:
                os.remove(tmp_path)
        else:
            if not os.path.isfile(args.archive):
                raise kernel.ClaimError(f"no archive at {args.archive!r}")
            result = transfer.import_(args.archive, args.into)
    except kernel.ClaimError as e:
        return _refuse("import", str(e), args)
    if args.json:
        _print_envelope("import", True, "imported", result.get("root"), result, args)
    return 0


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def _cmd_verify(args):
    d = args.claim
    try:
        result = kernel.verify(d)
    except kernel.ClaimError as e:
        return _refuse("verify", str(e), args)
    ok = result["ok"]
    status = "fresh" if ok else "broken"
    if args.json:
        data = dict(result)
        try:
            data["phase"] = kernel.phase(d)
        except kernel.ClaimError:
            data["phase"] = "broken"
        _print_envelope("verify", ok, status, result["root"], data, args)
        return 0 if ok else 1
    if not ok:
        output._err("verify", _diagnose_broken(d))
        return 1
    if args.verbose:
        print("[verify]")
        print(f"  name = {result.get('name')!r}")
        print(f'  root = "{result["root"]}"')
        print(f'  recomputed = "{result["recomputed"]}"')
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------

def _audit_kwargs(shallow: bool, strict: bool) -> dict:
    """Thread `shallow`/`strict` toward `kernel.audit` only when its bound
    callable actually accepts them -- forward-compatible with a future
    kernel, and safely inert against the real one, which has no `strict`."""
    try:
        params = inspect.signature(kernel.audit).parameters
    except (TypeError, ValueError):
        params = {}
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    kwargs = {}
    if "shallow" in params or has_var_kw:
        kwargs["shallow"] = shallow
    if "strict" in params or has_var_kw:
        kwargs["strict"] = strict
    return kwargs


def _cmd_audit(args):
    d = args.claim
    strict = not args.no_strict
    started = time.monotonic()
    try:
        base = kernel.audit(d, **_audit_kwargs(args.shallow, strict))
    except kernel.ClaimError as e:
        return _refuse("audit", str(e), args)
    except TypeError as e:
        return _refuse("audit", str(e), args)
    elapsed = time.monotonic() - started

    if args.shallow:
        deep = {"ok": True, "layers": []}
    else:
        try:
            deep = registry.audit_deep(d)
        except kernel.ClaimError:
            deep = {"ok": True, "layers": []}
    ok = bool(base.get("ok")) and deep.get("ok", True)

    try:
        _write_receipt(d, "audit.receipt.json", {"when": _util.stamp(), "ok": ok})
    except OSError:
        pass

    if args.record:
        try:
            doc = record_mod.emit(d)
            record_mod.write(doc, args.record)
        except kernel.ClaimError:
            pass

    data = dict(base)
    data["ok"] = ok
    data.setdefault("recomputed", base.get("root"))
    data["elapsed"] = elapsed
    data["layers"] = deep.get("layers", [])

    if args.json:
        _print_envelope("audit", ok, "earned" if ok else "failed", base.get("root"), data, args)
        return 0 if ok else 1
    if not ok:
        output._err("audit", f"audit did not reproduce for {base.get('name')!r}")
        return 1
    if args.verbose:
        print("[audit]")
        print(f"  name = {base.get('name')!r}")
        print(f'  root = "{base.get("root")}"')
        print("  reproduced = true")
        for g in base.get("gates", []):
            print(f"  gate {g['output']} = {g['status']} ({g.get('quarantine')})")
        if args.mutants:
            score = kernel.mutation_score(d, max_mutants=args.mutants)
            print("[mutation_score]")
            print(f"  mutants = {score['mutants']}")
            print(f"  killed = {score['killed']}")
            print(f"  rate = {score['rate']}")
    return 0


# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------

def _cmd_assess(args):
    d = args.claim
    try:
        result = run_assess(d, mutants=args.mutants)
    except kernel.ClaimError as e:
        return _refuse("assess", str(e), args)
    declared = sorted(result["measured"]) + sorted(result["not_measured"]) + sorted(result["not_applicable"])
    data = dict(result)
    data["declared"] = declared
    data["gate"] = declared
    try:
        _write_receipt(d, "assess.receipt.json", {
            "when": _util.stamp(),
            "measured": result["measured"], "not_measured": result["not_measured"],
            "not_applicable": result["not_applicable"],
        })
    except OSError:
        pass
    if args.json:
        _print_envelope("assess", True, "measured", None, data, args)
        return 0
    if args.verbose:
        print("[assess]")
        score = result.get("mutation_score") or {}
        print(f"  mutants killed = {score.get('killed', 0)}/{score.get('mutants', 0)}")
        print(f"  measured = {', '.join(result['measured']) or 'none'}")
        print(f"  not_measured = {', '.join(result['not_measured']) or 'none'}")
        print(f"  not_applicable = {', '.join(result['not_applicable']) or 'none'}")
    return 0


# ---------------------------------------------------------------------------
# rebuild
# ---------------------------------------------------------------------------

def _preflight_producer(name: str) -> None:
    spec = handlers._PRODUCERS.get(name)
    credential = spec.get("credential") if spec else None
    if credential and not os.environ.get(credential):
        raise kernel.ClaimError(f"the {name} producer needs {credential} set before it can spend")
    argv = handlers._expand_producer(name)
    exe = argv[0] if argv else name
    if shutil.which(exe) is None:
        raise kernel.ClaimError(f"the {name} producer is not on PATH: {exe!r} missing")


def _cmd_rebuild(args):
    d, into, producer = args.claim, args.output, args.producer
    try:
        if producer in handlers._PRODUCERS:
            _preflight_producer(producer)
        if args.chain:
            result = registry.rebuild_chain(d, producer, into, ws=args.ws, reuse=args.reuse)
        else:
            result = kernel.rebuild(d, producer, into)
    except kernel.ClaimError as e:
        return _refuse("rebuild", str(e), args)
    root = result.get("root") or ""
    if args.json:
        _print_envelope("rebuild", True, "rebuilt", root, result, args)
        return 0
    print(f"rebuilt {result.get('name')} ({_short(root)})")
    return 0


# ---------------------------------------------------------------------------
# crosscheck
# ---------------------------------------------------------------------------

def _cmd_crosscheck(args):
    rest = args.rest
    m2_materialized = False
    materialized_tmp = None
    try:
        if len(rest) == 1:
            m1, m3 = args.m1, rest[0]
            materialized_tmp = tempfile.mkdtemp(prefix="ret-m2-")
            shutil.rmtree(materialized_tmp)
            shutil.copytree(m1, materialized_tmp)
            m2 = materialized_tmp
            m2_materialized = True
        elif len(rest) == 2:
            m1, m2, m3 = args.m1, rest[0], rest[1]
        else:
            output._err("crosscheck", "crosscheck needs a third machine, or a pair to compare")
            return 2
        if args.deep:
            result = registry.crosscheck_deep(m1, m2, m3, mutants=args.mutants, signers=args.signers)
        else:
            result = kernel.crosscheck(m1, m2, m3, mutants=args.mutants, signers=args.signers)
    except kernel.ClaimError as e:
        return _refuse("crosscheck", str(e), args)
    finally:
        if materialized_tmp:
            shutil.rmtree(materialized_tmp, ignore_errors=True)

    data = dict(result)
    data["m2_materialized"] = m2_materialized
    ok = bool(result.get("satisfied"))
    status = result.get("verdict", "incomplete")
    root = (result.get("roots") or {}).get("M1")

    if args.json:
        _print_envelope("crosscheck", ok, status, root, data, args)
        return 0 if ok else 1
    if not ok:
        reasons = result.get("rejected") or result.get("incomplete") or ["unknown"]
        output._err("crosscheck", f"crosscheck rejected: {', '.join(reasons)}")
        return 1
    if args.verbose:
        print("[crosscheck]")
        print(f"  satisfied = {str(ok).lower()}")
        print(f"  verdict = {status}")
        print(f"  equivalence = {str(result.get('equivalence')).lower()}")
        print(f"  reuse = {str(result.get('reuse')).lower()}")
        print("[cost]")
        discovery = _discovery_tokens(args.m1)
        if discovery:
            print(f"  discovery: {discovery} tokens (reported testimony, excluded from the band)")
        cost = result.get("cost") or {}
        print(f"  comparable = {cost.get('comparable')}")
        print(f"  tolerance = {cost.get('tolerance')}")
    return 0


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

def _cmd_record(args):
    d = args.claim
    try:
        if args.identity:
            if not args.key:
                return _refuse("record", "record --as needs --key", args)
            result = attest_mod.attest(d, args.key, args.identity)
            if args.json:
                _print_envelope("record", True, "attested", None, result, args)
            return 0

        if args.check:
            signers = args.signers
            result = attest_mod.check(d, signers=signers)
            ok = result["ok"]
            if args.json:
                _print_envelope("record", ok, "checked" if ok else "unverified", None, result, args)
                return 0 if ok else 1
            if not ok:
                output._err("record", "no attestation verifies for this claim")
                return 1
            return 0

        key = args.key
        if args.sign and not key:
            key = os.environ.get("RETICULI_KEY")
            if not key:
                return _refuse("record", "record --sign needs RETICULI_KEY set", args)
        doc = record_mod.emit(d)
        if args.out:
            record_mod.write(doc, args.out)
            if key:
                record_mod.sign(args.out, key)
        if args.json:
            digest = record_mod.digest(doc)
            _print_envelope("record", True, "emitted", doc.get("root"),
                            {"digest": digest, "record": doc}, args)
        return 0
    except kernel.ClaimError as e:
        return _refuse("record", str(e), args)


# ---------------------------------------------------------------------------
# sign
# ---------------------------------------------------------------------------

def _cmd_sign(args):
    d = args.claim
    try:
        if args.check:
            local = _local_signers_path(d)
            signers = args.signers or (local if os.path.isfile(local) else None)
            result = attest_mod.sign_check(d, ws=args.ws, signers=signers)
            ok = result["ok"]
            if args.json:
                _print_envelope("sign", ok, "checked" if ok else "unauthorized", None, result, args)
                return 0 if ok else 1
            if not ok:
                output._err("sign", "no authorization verifies for this claim")
                return 1
            return 0

        if args.identity:
            if not args.key:
                return _refuse("sign", "sign --as needs --key", args)
            result = attest_mod.sign(d, args.key, args.identity, ws=args.ws)
            _remember_sign_signer(d, args.key, args.identity)
            if args.json:
                _print_envelope("sign", True, "signed", None, result, args)
            return 0

        pkt = attest_mod.review_packet(d, ws=args.ws)
        if args.json:
            _print_envelope("sign", True, "review", pkt.get("root"), pkt, args)
            return 0
        if args.verbose:
            print("[review]")
            print(f'  root = "{pkt.get("root")}"')
            print(f'  build_digest = "{pkt.get("build_digest")}"')
            print(f'  sign_root = "{pkt.get("sign_root")}"')
            audit_result = pkt.get("audit") or {}
            print(f"  audit_ok = {str(bool(audit_result.get('ok'))).lower()}")
            print(f"  proof = {pkt.get('proof')}")
        else:
            print(f"review {_short(pkt.get('root') or '')} sign_root={_short(pkt.get('sign_root') or '')}")
        return 0
    except kernel.ClaimError as e:
        return _refuse("sign", str(e), args)


# ---------------------------------------------------------------------------
# help / completion
# ---------------------------------------------------------------------------

def _print_top_help() -> None:
    print("usage: ret [-h] [--version] <command> ...\n")
    print(_DESC)
    print()
    print(_EPILOG)


def _print_help_all() -> None:
    print(_DESC)
    print()
    print("Plumbing")
    for v in PLUMBING:
        print(f"    {v:<11} {_VERB_ONELINE[v]}")


def _cmd_help(args):
    if getattr(args, "all", False):
        _print_help_all()
        return 0
    topic = getattr(args, "topic", None)
    if not topic:
        _print_top_help()
        return 0
    text = _HELP_DETAIL.get(topic)
    if text is None:
        print(f"no help for {topic!r}", file=sys.stderr)
        return 1
    print(text)
    return 0


def _cmd_completion(args):
    if args.shell != "bash":
        print(f"ret: completion: unsupported shell: {args.shell!r}", file=sys.stderr)
        return 1
    words = " ".join(sorted(verbs()))
    print(
        "_ret_complete() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        '    if [ "$COMP_CWORD" -eq 1 ]; then\n'
        f'        COMPREPLY=( $(compgen -W "{words}" -- "$cur") )\n'
        "    fi\n"
        "}\n"
        "complete -F _ret_complete ret"
    )
    return 0


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------

def _common(sp) -> None:
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--verbose", "-v", action="store_true")
    sp.add_argument("--color", choices=("auto", "always", "never"),
                    default=os.environ.get("RETICULI_COLOR", "auto"))


def _build_parser():
    p = argparse.ArgumentParser(prog="ret", add_help=True)
    sub = p.add_subparsers(dest="verb", metavar="command")

    sp = sub.add_parser("init", description=_synopsis("init"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("workspace", nargs="?", default=os.getcwd())
    sp.add_argument("--agent")
    sp.add_argument("--producer")
    sp.add_argument("--no-agent", action="store_true", dest="no_agent")

    sp = sub.add_parser("run", description=_synopsis("run"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("cmd")
    sp.add_argument("-C", "--chdir", dest="workspace", default=os.getcwd())

    sp = sub.add_parser("status", description=_synopsis("status"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")
    sp.add_argument("--files", action="store_true")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--draft", action="store_true")

    sp = sub.add_parser("pack", description=_synopsis("pack"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("path")
    sp.add_argument("--name")
    sp.add_argument("--generated", nargs="*", default=[])
    sp.add_argument("--inputs", nargs="*", default=[])
    sp.add_argument("--gate")
    sp.add_argument("--gate-output", dest="gate_output")
    sp.add_argument("--environment")
    sp.add_argument("--pytest", action="store_true")
    sp.add_argument("-o", "--output")
    sp.add_argument("--accept", nargs="*", default=None)
    sp.add_argument("--into")
    sp.add_argument("--force", action="store_true")

    sp = sub.add_parser("pull", description=_synopsis("pull"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim")
    sp.add_argument("into")

    sp = sub.add_parser("export", description=_synopsis("export"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim")
    sp.add_argument("out", nargs="?", default=None)
    sp.add_argument("-o", "--output")
    sp.add_argument("--blind", action="store_true")

    sp = sub.add_parser("import", description=_synopsis("import"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("archive")
    sp.add_argument("into")

    sp = sub.add_parser("verify", description=_synopsis("verify"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())

    sp = sub.add_parser("audit", description=_synopsis("audit"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--shallow", action="store_true")
    sp.add_argument("--no-strict", action="store_true", dest="no_strict")
    sp.add_argument("--mutants", type=int, default=None)
    sp.add_argument("--record")

    sp = sub.add_parser("assess", description=_synopsis("assess"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--mutants", type=int, default=20)

    sp = sub.add_parser("rebuild", description=_synopsis("rebuild"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim")
    sp.add_argument("-o", "--output", required=True)
    sp.add_argument("--producer", required=True)
    sp.add_argument("--chain", action="store_true")
    sp.add_argument("--reuse", action="store_true")
    sp.add_argument("--ws")

    sp = sub.add_parser("crosscheck", description=_synopsis("crosscheck"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("m1")
    sp.add_argument("rest", nargs="+")
    sp.add_argument("--deep", action="store_true")
    sp.add_argument("--mutants", type=int, default=None)
    sp.add_argument("--signers")

    sp = sub.add_parser("record", description=_synopsis("record"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("-o", "--out")
    sp.add_argument("--key")
    sp.add_argument("--as", dest="identity")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--sign", action="store_true")
    sp.add_argument("--signers")
    sp.add_argument("--anchor")

    sp = sub.add_parser("sign", description=_synopsis("sign"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    _common(sp)
    sp.add_argument("claim", nargs="?", default=os.getcwd())
    sp.add_argument("--key")
    sp.add_argument("--as", dest="identity")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--signers")
    sp.add_argument("--ws")

    sp = sub.add_parser("hook", description=_synopsis("hook"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("-C", "--chdir", default=None)

    sp = sub.add_parser("help", description=_synopsis("help"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("topic", nargs="?")
    sp.add_argument("-a", "--all", action="store_true")

    sp = sub.add_parser("completion", description=_synopsis("completion"),
                        formatter_class=argparse.RawDescriptionHelpFormatter)
    sp.add_argument("shell", choices=("bash",))

    return p


_DISPATCH = {
    "init": _cmd_init, "status": _cmd_status, "pack": _cmd_pack,
    "pull": _cmd_pull, "export": _cmd_export, "import": _cmd_import,
    "verify": _cmd_verify, "audit": _cmd_audit, "assess": _cmd_assess,
    "rebuild": _cmd_rebuild, "crosscheck": _cmd_crosscheck,
    "record": _cmd_record, "sign": _cmd_sign,
}


def _typo_refusal(word: str) -> int:
    matches = difflib.get_close_matches(word, sorted(verbs()), n=1)
    hint = f"; did you mean {matches[0]!r}?" if matches else ""
    print(f"ret: {word!r} is not a ret command{hint}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        _print_top_help()
        return 0
    if argv[0] == "--version":
        print(f"ret {kernel.FORMAT} ({kernel.NAMESPACE})")
        return 0

    verb = argv[0]
    if verb not in verbs():
        return _typo_refusal(verb)

    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        code = e.code
        return code if isinstance(code, int) else (0 if code is None else 1)

    if verb == "run":
        return _cmd_run(args)
    if verb == "hook":
        return _cmd_hook(args)
    if verb == "help":
        return _cmd_help(args)
    if verb == "completion":
        return _cmd_completion(args)
    return _DISPATCH[verb](args)


if __name__ == "__main__":
    sys.exit(main())

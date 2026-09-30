"""reticuli._cli.dispatch -- the `ret` command line: grammar, dispatch,
and human/machine rendering, all in one place.

Fourteen porcelain verbs (`PORCELAIN`), grouped by workflow concept in the
help; `hook`/`help`/`completion` are plumbing. Every verb ends through
`_finish`: silent on a passing default run, a `[verb]` block under `-v`,
the five-field envelope under `--json`, and one stderr line (`ret: <verb>:
<fact>`) on a refusal -- never a raw traceback. An invalid invocation
(missing what a verb structurally needs) is refused the same way but
before any envelope could apply, exit 2.

Stdlib only. Never the network.
"""
import argparse
import difflib
import json
import os
import platform
import shutil
import sys
import tempfile
import time

from .. import _util
from .. import assess as _assess
from .. import attest as _attest
from .. import authoring as _authoring
from .. import feedback as _feedback
from .. import hooks as _hooks
from .. import kernel
from .. import pack as _pack_mod
from .. import record as _record
from .. import registry as _registry
from .. import render
from .. import transfer as _transfer
from . import handlers

ClaimError = kernel.ClaimError

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

ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")

BANNED_GLYPHS = ("■", "✗", "⇐", "…", "·")


def verbs() -> tuple:
    return tuple(PORCELAIN) + tuple(ALIASES) + tuple(PLUMBING)


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------
_COLORS = {"red": "31", "green": "32", "yellow": "33", "cyan": "36"}


def _color_mode() -> str:
    return os.environ.get("RETICULI_COLOR", "auto")


def _use_color() -> bool:
    mode = _color_mode()
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def paint(text: str, color: str) -> str:
    if not _use_color():
        return text
    code = _COLORS.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


# ---------------------------------------------------------------------------
# The shared envelope / refusal / finish machinery
# ---------------------------------------------------------------------------
def _err(command: str, fact: str) -> None:
    sys.stderr.write(f"ret: {command}: {fact}\n")


def _finish(name: str, args, result: dict) -> int:
    """`result` is `{ok, status, data, root?, fact?, terse?, verbose?}`.
    Silent by default on success, the human block under `-v`, the
    five-field envelope under `--json`, one stderr line on a refusal."""
    ok = bool(result.get("ok"))
    status = result.get("status")
    data = result.get("data", {})
    root = result.get("root")
    if getattr(args, "json", False):
        envelope = {"command": name, "ok": ok, "status": status, "root": root, "data": data}
        print(json.dumps(envelope, sort_keys=True))
        return 0 if ok else 1
    if not ok:
        _err(name, result.get("fact") or status or "failed")
        return 1
    if getattr(args, "verbose", False) and result.get("verbose"):
        print(result["verbose"])
    elif result.get("terse"):
        print(result["terse"])
    return 0


def _guard(name: str, args, fn) -> int:
    """Call `fn()` (returning a `_finish`-shaped dict); a raised
    `ClaimError` becomes the same refusal shape everything else uses."""
    try:
        result = fn()
    except ClaimError as exc:
        result = {"ok": False, "status": "error", "data": {"error": str(exc)},
                  "root": None, "fact": str(exc)}
    return _finish(name, args, result)


# ---------------------------------------------------------------------------
# Small block / table renderers for `-v`
# ---------------------------------------------------------------------------
def _toml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return '""'
    return f'"{v}"'


def _block(title: str, fields) -> str:
    lines = [f"[{title}]"]
    for k, v in fields:
        lines.append(f"{k} = {_toml_scalar(v)}")
    return "\n".join(lines)


def _row(label, value) -> str:
    return f"{label}: {value}"


# ---------------------------------------------------------------------------
# Producer resolution (named vendors preflight their one credential)
# ---------------------------------------------------------------------------
def _expand_producer(spec: str) -> str:
    producer = handlers._PRODUCERS.get(spec)
    if producer is None:
        return spec
    credential = producer["credential"]
    if not os.environ.get(credential):
        raise ClaimError(f"the {spec} producer needs {credential} set before it can spend anything")
    return producer["cmd"]


# ---------------------------------------------------------------------------
# Residue: parts (per-file hashes, for a broken-verify diagnosis) and
# receipts (the ladder: audited / measured / proven / signed) and the
# discovery bill (reported testimony, never fed into the cost ledger the
# tolerance band reads).
# ---------------------------------------------------------------------------
def _parts_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "parts.json")


def _write_parts_residue(d: str) -> None:
    try:
        recipe = kernel.load_recipe(d)
    except ClaimError:
        return
    parts = {}
    for name in _util.declared_inputs(d):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            parts[name] = kernel._hash_file(p)
    for step in recipe.get("step", []):
        cls = step.get("class")
        if cls is None:
            cls = "generated" if step.get("kind") == "produce" else "pinned"
        if cls == "generated":
            continue
        name = step.get("output")
        if not name:
            continue
        p = os.path.join(d, name)
        if os.path.isfile(p):
            parts[name] = kernel._hash_file(p)
    _util.write_json(_parts_path(d), parts)


def _diagnose_broken(d: str):
    try:
        parts = _util.read_json(_parts_path(d))
    except (OSError, ValueError):
        return None
    if not isinstance(parts, dict):
        return None
    for name, expected in sorted(parts.items()):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            return name
        if kernel._hash_file(p) != expected:
            return name
    return None


def _receipts_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "receipts.json")


def _load_receipts(d: str) -> dict:
    try:
        data = _util.read_json(_receipts_path(d))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_receipt(d: str, key: str, value: dict) -> None:
    receipts = _load_receipts(d)
    receipts[key] = value
    _util.write_json(_receipts_path(d), receipts)


def _discovery_path(d: str) -> str:
    return os.path.join(d, kernel.STORE, "discovery.json")


def _discovery_tokens(d: str):
    try:
        data = _util.read_json(_discovery_path(d))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        return data.get("tokens")
    return None


def _harness_tokens(ws: str):
    """Total input+output tokens across every `assistant` line of every
    harness transcript a `session` trace event names -- reported testimony
    about the discovery cost, never a measurement this tool made itself."""
    events = _authoring._read_trace(ws)
    total = 0
    found = False
    for e in events:
        if e.get("event") != "session":
            continue
        path = e.get("transcript")
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(rec, dict) or rec.get("type") != "assistant":
                        continue
                    usage = (rec.get("message") or {}).get("usage") or {}
                    it = usage.get("input_tokens", 0) or 0
                    ot = usage.get("output_tokens", 0) or 0
                    if isinstance(it, (int, float)) and isinstance(ot, (int, float)):
                        total += it + ot
                        found = True
        except OSError:
            continue
    return total if found else None


# ---------------------------------------------------------------------------
# Session (draft) status view
# ---------------------------------------------------------------------------
def _session_rows(ws: str):
    events = _authoring._read_trace(ws)
    advise = _feedback.advise(ws)
    outputs = advise["verdicts"]

    observed = {}
    for e in events:
        if e.get("event") in ("write", "read") and "path" in e:
            observed[e["path"]] = (e["event"], e.get("via") or "-")

    declared = {}
    if outputs:
        try:
            recipe = _authoring.propose(ws, outputs, "draft")
        except ClaimError:
            recipe = None
        if recipe is not None:
            for name in recipe.get("claim", {}).get("inputs", []):
                declared[name] = "pinned"
            for step in recipe.get("step", []):
                name = step.get("output")
                if not name:
                    continue
                declared[name] = "validated" if step.get("kind") == "gate" else "generated"

    all_paths = set(observed) | set(declared)
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [dn for dn in dirnames if dn != ".reticuli"]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), ws)
            all_paths.add(rel)

    rows = []
    for name in sorted(all_paths):
        obs_kind, via = observed.get(name, ("-", "-"))
        role = declared.get(name)
        if role is None:
            role = "undeclared" if name in observed else "-"
        evidence = "gate" if name in outputs else via
        rows.append({"path": name, "observed": obs_kind, "declared": role, "evidence": evidence})

    unresolved = sum(1 for r in rows if r["declared"] == "undeclared")
    return rows, len(observed), len(declared), unresolved, bool(outputs)


def _session_terse(ws: str) -> str:
    rows, n_obs, n_decl, unresolved, sealable = _session_rows(ws)
    text = f"draft  observed={n_obs} declared={n_decl} unresolved={unresolved}"
    if unresolved > 0:
        text += f"  {unresolved} file(s) undeclared"
    elif sealable:
        text += "  packable"
    return text


def _session_all(ws: str) -> str:
    rows, *_ = _session_rows(ws)
    table_rows = [(r["path"], r["observed"], r["declared"], r["evidence"]) for r in rows]
    return render.table(table_rows, headers=("path", "observed", "declared", "evidence"))


# ---------------------------------------------------------------------------
# Claim (sealed) status view: identity, the ladder, statements
# ---------------------------------------------------------------------------
_LADDER = (
    ("audited", "ret audit"),
    ("measured", "ret assess"),
    ("proven", "ret crosscheck"),
    ("signed", "ret sign"),
)


def _statements_of(d: str):
    words = []
    count = 0
    try:
        att = _attest.check(d)
    except ClaimError:
        att = {"attestations": []}
    if att.get("attestations"):
        count += len(att["attestations"])
        words.append("attested")
    try:
        sc = _attest.sign_check(d)
    except ClaimError:
        sc = {"authorizations": []}
    if sc.get("authorizations"):
        count += len(sc["authorizations"])
        words.append("signed")
    return count, words


def _claim_state(d: str) -> dict:
    v = kernel.verify(d)
    recipe = kernel.load_recipe(d)
    receipts = _load_receipts(d)
    try:
        phase = kernel.phase(d)
        broken = False
    except ClaimError:
        phase = "broken"
        broken = True

    nxt = "ret record"
    for key, cmd in _LADDER:
        if key not in receipts:
            nxt = cmd
            break

    count, words = _statements_of(d)
    gate_steps = [s for s in recipe.get("step", []) if s.get("kind") == "gate"]
    deciding = {s["output"]: sorted(kernel.gate_deciders(s.get("run", ""))) for s in gate_steps}
    try:
        manifest = kernel.read_manifest(d)
    except ClaimError:
        manifest = {}
    signatures = []
    for entry in _attest.sign_check(d).get("authorizations", []) if not broken else []:
        signatures.append({"identity": entry.get("identity"), "verdict": entry.get("verdict")})

    return {
        "name": v["name"], "root": v["root"], "ok": v["ok"], "phase": phase, "broken": broken,
        "receipts": receipts, "next": nxt, "statements": count, "statement_words": words,
        "deciding": deciding, "proof": manifest.get("proof"), "signatures": signatures,
        "discovery": _discovery_tokens(d),
    }


def _claim_terse(d: str, state: dict) -> str:
    if state["broken"]:
        return (f"broken  {d}\n"
                f"identity does not match its sealed manifest -- restore the declared bytes, "
                f"or reseal\nnext: restore")
    lines = [f"{state['name']}  {render.short(state['root'])}  {paint(state['phase'], 'cyan')}"]
    lines.append(f"identity: {paint('fresh', 'green')} (root {state['root']})")
    audited = state["receipts"].get("audited")
    if audited:
        lines.append(f"audited: on this machine, {audited.get('when', '')}")
    measured = state["receipts"].get("measured")
    if measured:
        lines.append(f"measured: assess, {measured.get('when', '')}")
    proven = state["receipts"].get("proven")
    if proven:
        lines.append(f"proven: crosscheck {proven.get('verdict', '')}, {proven.get('when', '')}")
    if state["discovery"] is not None:
        lines.append(f"discovery: {state['discovery']} tokens (reported testimony)")
    if state["statements"]:
        lines.append(f"statements: {state['statements']} statement(s) "
                     f"({', '.join(state['statement_words'])})")
    lines.append(f"next: {state['next']}")
    return "\n".join(lines)


def _claim_all(d: str, state: dict) -> str:
    receipts = state["receipts"]
    lines = ["fixed:"]
    recipe = kernel.load_recipe(d)
    for name in _util.declared_inputs(d):
        lines.append(f"  {name}")
    if len(lines) == 1:
        lines.append("  (none)")
    lines.append("deciding:")
    for output, deciders in state["deciding"].items():
        words = ", ".join(deciders) if deciders else "no pinned file decides this gate"
        lines.append(f"  {output}: {words}")
    lines.append("free:")
    for step in recipe.get("step", []):
        cls = step.get("class") or ("generated" if step.get("kind") == "produce" else "pinned")
        if cls == "generated":
            lines.append(f"  {step['output']}")
    lines.append("recorded:")
    _VERB_OF = {"audited": "audit", "measured": "assess", "proven": "crosscheck"}
    for key in ("audited", "measured", "proven"):
        entry = receipts.get(key)
        if entry:
            lines.append(f"  {_VERB_OF[key]}, {entry.get('when', '')}: a receipt, not a verdict")
    if not any(receipts.get(k) for k in ("audited", "measured", "proven")):
        lines.append("  (none)")
    lines.append("unknown:")
    unknown = [k for k in ("audited", "measured", "proven") if k not in receipts]
    lines.append(f"  {', '.join(unknown) if unknown else '(none)'}")
    lines.append(f"next: {state['next']}")
    return "\n".join(lines)


_TREE_KIND = {"pinned": "exact", "generated": "free", "validated": "verdict"}


def _claim_tree(d: str, state: dict) -> str:
    recipe = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    layers = len(manifest.get("components") or [])
    lines = [f"layers={layers}"]
    word = "OK" if state["ok"] else "BROKEN"
    lines.append(f"{'pinned'.ljust(11)}{paint(word, 'green' if state['ok'] else 'red')}")
    has_generated = any(
        (s.get("class") or ("generated" if s.get("kind") == "produce" else "pinned")) == "generated"
        for s in recipe.get("step", []))
    lines.append(f"{'generated'.ljust(11)}{paint('free' if has_generated else '(none)', 'cyan')}")
    gate_word = "OK" if state["ok"] else "BROKEN"
    lines.append(f"{'validated'.ljust(11)}{paint(gate_word, 'green' if state['ok'] else 'red')}")
    return "\n".join(lines)


_KIND = {"pinned": "exact", "generated": "free", "validated": "verdict"}


def _claim_files_rows(d: str):
    recipe = kernel.load_recipe(d)
    rows = []
    seen = set()
    for name in _util.declared_inputs(d):
        rows.append((name, "pinned", _KIND["pinned"], os.path.isfile(os.path.join(d, name))))
        seen.add(name)
    for step in recipe.get("step", []):
        name = step.get("output")
        if not name or name in seen:
            continue
        seen.add(name)
        cls = "validated" if step.get("kind") == "gate" else (step.get("class") or "generated")
        rows.append((name, cls, _KIND.get(cls, cls), os.path.isfile(os.path.join(d, name))))
    return rows


# ---------------------------------------------------------------------------
# Argument parsers (add_help=False -- -h/--help are handled by dispatch
# itself, so a verb can answer them differently: -h is concise usage,
# --help is the fuller SYNOPSIS account)
# ---------------------------------------------------------------------------
def _p(prog: str) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog=f"ret {prog}", add_help=False)


def _add_vjc(sp) -> None:
    sp.add_argument("-v", "--verbose", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--color", choices=("auto", "always", "never"), default="auto")


def _build_parsers() -> dict:
    P = {}

    sp = _p("init"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--agent", default=None)
    sp.add_argument("--no-agent", action="store_true")
    _add_vjc(sp); P["init"] = sp

    sp = _p("run"); sp.add_argument("cmd"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("-C", dest="chdir", default=None)
    _add_vjc(sp); P["run"] = sp

    sp = _p("status"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--files", action="store_true")
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")
    sp.add_argument("--deps", action="store_true")
    sp.add_argument("--structure", action="store_true")
    _add_vjc(sp); P["status"] = sp

    sp = _p("pack"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--name", default=None)
    sp.add_argument("--accept", default=None)
    sp.add_argument("-o", "--out", default=None)
    sp.add_argument("--generated", nargs="+", default=None)
    sp.add_argument("--inputs", nargs="+", default=None)
    sp.add_argument("--run", default=None)
    sp.add_argument("--output", default=None)
    sp.add_argument("--pytest", action="store_true")
    sp.add_argument("--environment", default=None)
    _add_vjc(sp); P["pack"] = sp

    sp = _p("pull"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--into", required=True)
    _add_vjc(sp); P["pull"] = sp

    sp = _p("export"); sp.add_argument("claim"); sp.add_argument("tar", nargs="?", default=None)
    sp.add_argument("-o", "--out", default=None)
    sp.add_argument("--blind", action="store_true")
    _add_vjc(sp); P["export"] = sp

    sp = _p("import"); sp.add_argument("tar"); sp.add_argument("claim", nargs="?", default=None)
    _add_vjc(sp); P["import"] = sp

    sp = _p("verify"); sp.add_argument("claim", nargs="?", default=None)
    _add_vjc(sp); P["verify"] = sp

    sp = _p("audit"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--shallow", action="store_true")
    sp.add_argument("--no-strict", action="store_true")
    sp.add_argument("--mutants", type=int, default=None)
    sp.add_argument("--record", default=None)
    _add_vjc(sp); P["audit"] = sp

    sp = _p("assess"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--mutants", type=int, default=None)
    _add_vjc(sp); P["assess"] = sp

    sp = _p("rebuild"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--producer", required=True)
    sp.add_argument("-o", "--out", required=True)
    sp.add_argument("--produce-from", dest="produce_from", default=None)
    sp.add_argument("--input-from", dest="input_from", default=None)
    sp.add_argument("--without-guidance", action="store_true")
    _add_vjc(sp); P["rebuild"] = sp

    sp = _p("crosscheck"); sp.add_argument("claim"); sp.add_argument("legs", nargs="+")
    sp.add_argument("--mutants", type=int, default=None)
    _add_vjc(sp); P["crosscheck"] = sp

    sp = _p("record"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("-o", "--out", default=None)
    sp.add_argument("--key", default=None)
    sp.add_argument("--as", dest="identity", default=None)
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--sign", action="store_true")
    sp.add_argument("--signers", default=None)
    _add_vjc(sp); P["record"] = sp

    sp = _p("sign"); sp.add_argument("claim", nargs="?", default=None)
    sp.add_argument("--key", default=None)
    sp.add_argument("--as", dest="identity", default=None)
    sp.add_argument("--workspace", default=None)
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--signers", default=None)
    _add_vjc(sp); P["sign"] = sp

    sp = _p("hook"); sp.add_argument("-C", dest="chdir", default=None)
    P["hook"] = sp

    return P


_PARSERS = _build_parsers()


# ---------------------------------------------------------------------------
# Verb handlers
# ---------------------------------------------------------------------------
def _claim_dir(args) -> str:
    chdir = getattr(args, "chdir", None)
    if chdir:
        return chdir
    return args.claim if getattr(args, "claim", None) else os.getcwd()


def _cmd_init(args) -> int:
    d = args.claim if args.claim else os.getcwd()
    data = handlers.init(d, no_agent=True)
    if args.agent:
        if args.agent != "claude":
            _err("init", f"unsupported agent: {args.agent!r}")
            return 2
        data["hooks"] = _hooks.install(d)
    elif not args.no_agent:
        pass
    gitignore = os.path.join(d, ".gitignore")
    if not os.path.isfile(gitignore):
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(".reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n.reticuli/scratch/\n")
    else:
        with open(gitignore, "r", encoding="utf-8") as f:
            existing = f.read()
        if "ledger.jsonl" not in existing:
            with open(gitignore, "a", encoding="utf-8") as f:
                f.write("\n.reticuli/ledger.jsonl\n")
    terse = paint(f"initialized {data['claim']}", "cyan")
    return _finish("init", args, {"ok": True, "status": "initialized", "data": data,
                                  "root": None, "terse": terse})


def _cmd_run(args) -> int:
    ws = args.chdir or (args.claim if args.claim else os.getcwd())
    rc = handlers.run(args.cmd, ws)
    return rc


def _cmd_status(args) -> int:
    def fn():
        d = _claim_dir(args)
        if not os.path.isdir(d):
            raise ClaimError(f"no such directory: {d}")
        manifest_path = os.path.join(d, kernel.MANIFEST)
        if os.path.isfile(manifest_path):
            state = _claim_state(d)
            if args.tree:
                terse = _claim_tree(d, state)
            elif args.files:
                rows = _claim_files_rows(d)
                terse = render.table([(n, c, k, str(p)) for n, c, k, p in rows],
                                     headers=("name", "class", "kind", "present"))
            elif args.claims:
                rows = _registry.claims(d)
                terse = render.table([(r["name"], render.short(r["root"]), r["phase"])
                                     for r in rows], headers=("name", "root", "phase")) \
                    or "no claims in store"
            elif args.all:
                terse = _claim_all(d, state)
            else:
                terse = _claim_terse(d, state)
            status_word = "claim" if not state["broken"] else "broken"
            data = {"name": state["name"], "root": state["root"], "phase": state["phase"],
                    "audited": state["receipts"].get("audited"),
                    "deciding": state["deciding"], "proof": state["proof"],
                    "signatures": state["signatures"], "next": state["next"]}
            return {"ok": True, "status": status_word, "data": data,
                    "root": state["root"], "terse": terse}
        # session / workspace view
        if args.tree:
            rows, *_ = _session_rows(d)
            terse = "draft\n" + "\n".join(f"  {r['path']}: {r['declared']}" for r in rows)
        elif args.claims:
            rows = _registry.claims(d)
            terse = render.table([(r["name"], render.short(r["root"]), r["phase"])
                                 for r in rows], headers=("name", "root", "phase")) \
                or "no claims in store"
        elif args.deps or args.structure:
            data = _registry.deps(d)
            lines = []
            for c in data["claims"]:
                lines.append(f"{c['name']}  {render.short(c['root'])}")
                for dep in c["depends_on"]:
                    lines.append(f"  -> {dep['component']}  [{dep['status']}]")
            terse = "\n".join(lines) or "no claims in store"
        elif args.all:
            terse = _session_all(d)
        else:
            terse = _session_terse(d)
        return {"ok": True, "status": "draft", "data": {"path": d}, "root": None, "terse": terse}
    return _guard("status", args, fn)


def _stub_content(name: str) -> bytes:
    if name.endswith(".py"):
        return b"def _placeholder():\n    return 1 + 1\n"
    return b""


def _prepare_pack_workspace(ws: str, outputs) -> str:
    """A scratch copy of `ws` in which every traced-write candidate that
    does not currently exist on disk gets a minimal placeholder -- so a
    session's own recipe assembly never crashes copying a file that was
    written and later removed."""
    scratch = tempfile.mkdtemp(prefix="reticuli-pack-")
    shutil.copytree(ws, scratch, dirs_exist_ok=True)
    events = _authoring._read_trace(scratch)
    write_paths = {e["path"] for e in events if e.get("event") == "write" and "path" in e}
    for name in write_paths:
        if name in outputs:
            continue
        target = os.path.join(scratch, name)
        if not os.path.isfile(target):
            os.makedirs(os.path.dirname(target) or scratch, exist_ok=True)
            with open(target, "wb") as f:
                f.write(_stub_content(name))
    return scratch


def _session_pack(ws: str, accept: str, out_dir: str, name: str) -> dict:
    scratch = _prepare_pack_workspace(ws, [accept])
    try:
        manifest = _authoring.build_claim(scratch, [accept], out_dir, name=name)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    tokens = _harness_tokens(ws)
    if tokens is not None:
        _util.write_json(_discovery_path(out_dir), {"tokens": tokens})
    _write_parts_residue(out_dir)
    return manifest


def _cmd_pack(args) -> int:
    d = _claim_dir(args)
    if args.accept:
        if not args.out:
            _err("pack", "an accepted session pack needs -o to name where the claim is sealed")
            return 2
        def fn():
            manifest = _session_pack(d, args.accept, args.out, args.name or "claim")
            return {"ok": True, "status": "packed", "data": manifest, "root": manifest.get("root"),
                    "terse": paint(f"packed ({manifest.get('root')})", "cyan")}
        return _guard("pack", args, fn)
    if args.generated or args.inputs or args.run or args.output:
        missing = [n for n, v in (("--generated", args.generated), ("--inputs", args.inputs),
                                  ("--run", args.run), ("--output", args.output)) if not v]
        if missing:
            _err("pack", f"declared packing needs {', '.join(missing)}")
            return 2
        def fn():
            manifest = _pack_mod.pack(d, args.name or "claim", args.generated, args.inputs,
                                      args.run, args.output)
            _write_parts_residue(d)
            return {"ok": True, "status": "packed", "data": manifest, "root": manifest.get("root"),
                    "terse": paint(f"packed ({manifest.get('root')})", "cyan")}
        return _guard("pack", args, fn)
    def fn():
        if not os.path.isdir(d):
            raise ClaimError(f"nothing to pack: no such directory {d!r}")
        has_recipe = os.path.isfile(os.path.join(d, kernel.RECIPE)) or \
            os.path.isfile(os.path.join(d, kernel.LEGACY_RECIPE))
        if not has_recipe:
            raise ClaimError(f"nothing to pack in {d!r}: no reticuli.toml declares a claim")
        manifest = kernel.seal(d)
        _write_parts_residue(d)
        return {"ok": True, "status": "packed", "data": manifest, "root": manifest.get("root"),
                "terse": paint(f"packed ({manifest.get('root')})", "cyan")}
    return _guard("pack", args, fn)


def _cmd_pull(args) -> int:
    d = _claim_dir(args)
    def fn():
        data = _registry.pull(d, args.into)
        return {"ok": data["materialized"], "status": "pulled", "data": data,
                "root": data.get("root")}
    return _guard("pull", args, fn)


def _cmd_export(args) -> int:
    d = args.claim
    target = args.tar or args.out
    if not target:
        _err("export", "export needs a destination: a positional path, -o PATH, or -o -")
        return 2
    def fn():
        if target == "-":
            tmp = tempfile.mktemp(prefix="reticuli-export-")
            try:
                _transfer.export(d, tmp, blind=args.blind)
                with open(tmp, "rb") as f:
                    sys.stdout.buffer.write(f.read())
                sys.stdout.buffer.flush()
            finally:
                if os.path.isfile(tmp):
                    os.remove(tmp)
        else:
            _transfer.export(d, target, blind=args.blind)
        return {"ok": True, "status": "exported", "data": {"path": target}, "root": None}
    return _guard("export", args, fn)


def _cmd_import(args) -> int:
    d = _claim_dir(args)
    def fn():
        if args.tar == "-":
            tmp = tempfile.mktemp(prefix="reticuli-import-")
            try:
                with open(tmp, "wb") as f:
                    f.write(sys.stdin.buffer.read())
                data = _transfer.import_(tmp, d)
            finally:
                if os.path.isfile(tmp):
                    os.remove(tmp)
        else:
            if not os.path.isfile(args.tar):
                raise ClaimError(f"no archive at {args.tar!r}")
            data = _transfer.import_(args.tar, d)
        return {"ok": data["ok"], "status": ("ok" if data["ok"] else "mismatch"),
                "data": data, "root": data.get("root")}
    return _guard("import", args, fn)


def _cmd_verify(args) -> int:
    d = _claim_dir(args)
    def fn():
        v = kernel.verify(d)
        try:
            v["phase"] = kernel.phase(d)
        except ClaimError:
            v["phase"] = "broken"
        if v["ok"]:
            terse = None
            verbose = _block("verify", [("name", v["name"]), ("root", v["root"]),
                                        ("recomputed", v["recomputed"]), ("ok", v["ok"])])
            return {"ok": True, "status": "fresh", "data": v, "root": v["root"],
                    "terse": terse, "verbose": verbose}
        culprit = _diagnose_broken(d)
        fact = f"{d} is broken"
        if culprit:
            fact += f": {culprit} changed"
        fact += "; hint: restore the declared bytes from the recipe, or reseal the claim"
        return {"ok": False, "status": "mismatch", "data": v, "root": v["root"], "fact": fact}
    return _guard("verify", args, fn)


def _judging_host() -> dict:
    return {"implementation": platform.python_implementation(), "machine": platform.machine(),
            "platform": sys.platform, "python": platform.python_version()}


def _cmd_audit(args) -> int:
    d = _claim_dir(args)
    def fn():
        strict = not args.no_strict
        t0 = time.monotonic()
        result = kernel.audit(d, strict=strict)
        elapsed = time.monotonic() - t0
        ok = bool(result.get("ok"))
        verdict = result.get("verdict") or ("earned" if ok else "failed")
        mutation = None
        if args.mutants is not None:
            mutation = kernel.mutation_score(d, max_mutants=args.mutants)
        if args.record:
            doc = _record.emit(d)
            _record.write(doc, args.record)
        data = dict(result)
        data["elapsed"] = elapsed
        data["environment"] = _judging_host()
        data["layers"] = []
        if mutation is not None:
            data["mutation_score"] = mutation
        if not ok:
            return {"ok": False, "status": verdict, "data": data, "root": result.get("root"),
                    "fact": verdict}
        lines = [f"[audit]", f'name = "{result.get("name")}"', f'root = "{result.get("root")}"',
                 f'verdict = "{verdict}"']
        for g in result.get("gates", []):
            word = "reproduced" if g.get("status") == "ok" else g.get("status")
            lines.append(f"gate {g['output']} = {word} (quarantine={g.get('quarantine')})")
        if mutation is not None:
            lines.append("")
            lines.append("[mutation_score]")
            lines.append(f"mutants = {mutation['mutants']}")
            lines.append(f"killed = {mutation['killed']}")
            lines.append(f"rate = {mutation['rate']}")
        _save_receipt(d, "audited", {"when": _now(), "on": "this machine"})
        return {"ok": True, "status": verdict, "data": data, "root": result.get("root"),
                "verbose": "\n".join(lines)}
    return _guard("audit", args, fn)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cmd_assess(args) -> int:
    d = _claim_dir(args)
    def fn():
        result = _assess.assess(d, mutants=args.mutants)
        recipe = kernel.load_recipe(d)
        ok = not result["not_measured"]
        status = "measured" if ok else ("partial" if result["measured"] else "not_measured")
        data = dict(result)
        data["declared"] = recipe.get("claim", {}).get("mutation_floor")
        data["gate"] = result["mutation_score"]
        if ok:
            _save_receipt(d, "measured", {"when": _now(),
                                          "rate": result["mutation_score"]["rate"]})
        return {"ok": True, "status": status, "data": data, "root": None,
                "terse": None,
                "verbose": _block("assess", [("measured", len(result["measured"])),
                                             ("not_measured", len(result["not_measured"])),
                                             ("not_applicable", len(result["not_applicable"]))])}
    return _guard("assess", args, fn)


def _cmd_rebuild(args) -> int:
    d = _claim_dir(args)
    def fn():
        producer_cmd = _expand_producer(args.producer)
        produce_from = None
        input_from = None
        if args.produce_from:
            with open(args.produce_from, "r", encoding="utf-8") as f:
                produce_from = json.load(f)
        if args.input_from:
            with open(args.input_from, "r", encoding="utf-8") as f:
                input_from = json.load(f)
        manifest = kernel.rebuild(d, producer_cmd, args.out,
                                  produce_from=produce_from, input_from=input_from)
        _write_parts_residue(args.out)
        return {"ok": True, "status": "rebuilt", "data": manifest, "root": manifest.get("root"),
                "terse": paint(f"rebuilt ({manifest.get('root')})", "cyan")}
    return _guard("rebuild", args, fn)


def _cmd_crosscheck(args) -> int:
    m1 = args.claim
    legs = args.legs
    materialized_m2 = False
    scratch = None
    if len(legs) == 1:
        scratch = tempfile.mkdtemp(prefix="reticuli-m2-")
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.copytree(m1, scratch)
        m2, m3 = scratch, legs[0]
        materialized_m2 = True
    else:
        m2, m3 = legs[0], legs[1]
    def fn():
        result = kernel.crosscheck(m1, m2, m3, mutants=args.mutants)
        result = dict(result)
        result["m2_materialized"] = materialized_m2
        discovery = _discovery_tokens(m1) if os.path.isdir(m1) else None
        lines = ["[crosscheck]", f"satisfied = {_toml_scalar(result['satisfied'])}",
                 f'verdict = "{result["verdict"]}"',
                 f"equivalence = {_toml_scalar(result['equivalence'])}",
                 f"reuse = {_toml_scalar(result['reuse'])}", "",
                 "[cost]", f"comparable = {_toml_scalar(result['cost']['comparable'])}"]
        if discovery is not None:
            lines.append(f"discovery = {discovery}  # M1, reported testimony, "
                         "never inside the band")
        if result["satisfied"]:
            _save_receipt(m1, "proven", {"when": _now(), "verdict": result["verdict"]})
        return {"ok": result["satisfied"], "status": result["verdict"], "data": result,
                "root": result["roots"].get("M1"), "fact": result["verdict"],
                "verbose": "\n".join(lines)}
    try:
        return _guard("crosscheck", args, fn)
    finally:
        if scratch and os.path.isdir(scratch):
            shutil.rmtree(scratch, ignore_errors=True)


def _cmd_record(args) -> int:
    d = _claim_dir(args)
    if args.check:
        def fn():
            data = _attest.check(d, signers=args.signers)
            return {"ok": data["ok"], "status": ("ok" if data["ok"] else "drifted"),
                    "data": data, "root": data.get("root"), "fact": "attestation has drifted"}
        return _guard("record", args, fn)
    if args.key and args.identity:
        def fn():
            data = _attest.attest(d, args.key, args.identity)
            return {"ok": True, "status": "attested", "data": data, "root": data.get("root")}
        return _guard("record", args, fn)
    def fn():
        doc = _record.emit(d)
        digest = _record.digest(doc)
        if args.out:
            _record.write(doc, args.out)
            key = args.key
            if args.sign and not key:
                key = os.environ.get("RETICULI_KEY")
                if not key:
                    raise ClaimError(
                        "RETICULI_KEY is not set; export it, or pass --key/--as explicitly")
            if key:
                _record.sign(args.out, key)
        data = {"digest": digest, "record": doc}
        return {"ok": True, "status": "emitted", "data": data, "root": doc.get("root")}
    return _guard("record", args, fn)


def _cmd_sign(args) -> int:
    d = _claim_dir(args)
    if args.check:
        def fn():
            data = _attest.sign_check(d, ws=args.workspace, signers=args.signers)
            ok = False
            for a in data.get("authorizations", []):
                if not a.get("packet_holds"):
                    continue
                if args.signers:
                    if a.get("verdict") == "authorized":
                        ok = True
                        break
                else:
                    ok = True
                    break
            return {"ok": ok, "status": ("authorized" if ok else "untrusted"), "data": data,
                    "root": None, "fact": "no trustworthy authorization found"}
        return _guard("sign", args, fn)
    if args.key:
        def fn():
            data = _attest.sign(d, args.key, args.identity, ws=args.workspace)
            return {"ok": True, "status": "signed", "data": data, "root": data.get("root")}
        return _guard("sign", args, fn)
    def fn():
        packet = _attest.review_packet(d, ws=args.workspace)
        terse = paint(f"review {render.short(packet['root'])}", "cyan")
        verbose = _block("review", [("root", packet["root"]),
                                    ("build_digest", packet["build_digest"]),
                                    ("sign_root", packet["sign_root"]),
                                    ("audit_ok", packet["audit"]["ok"])])
        return {"ok": True, "status": "reviewed", "data": packet, "root": packet["root"],
                "terse": terse, "verbose": verbose}
    return _guard("sign", args, fn)


def _cmd_hook(args) -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, TypeError):
        return 0
    if isinstance(payload, dict):
        cwd = args.chdir or payload.get("cwd")
        transcript = payload.get("transcript_path")
        if cwd and transcript and os.path.isdir(os.path.join(cwd, kernel.STORE)):
            trace_path = os.path.join(cwd, _hooks.TRACE)
            os.makedirs(os.path.dirname(trace_path), exist_ok=True)
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "session", "transcript": transcript,
                                    "ts": time.time()}, sort_keys=True) + "\n")
        try:
            _hooks.event(payload)
        except ClaimError:
            pass
    return 0


_HANDLERS = {
    "init": _cmd_init, "run": _cmd_run, "status": _cmd_status, "pack": _cmd_pack,
    "pull": _cmd_pull, "export": _cmd_export, "import": _cmd_import,
    "verify": _cmd_verify, "audit": _cmd_audit, "assess": _cmd_assess,
    "rebuild": _cmd_rebuild, "crosscheck": _cmd_crosscheck,
    "record": _cmd_record, "sign": _cmd_sign, "hook": _cmd_hook,
}


# ---------------------------------------------------------------------------
# Help content
# ---------------------------------------------------------------------------
_GROUPS = (
    ("Authoring", (("init", "initialize a workspace"), ("run", "run and observe a command"),
                   ("status", "show work, claims, and unresolved inputs"),
                   ("pack", "create a claim from a project"))),
    ("Composition and transport", (("pull", "add another claim as a dependency"),
                                   ("export", "write a portable claim archive"),
                                   ("import", "restore a claim archive"))),
    ("Verification", (("verify", "verify claim identity"), ("audit", "rerun acceptance criteria"),
                      ("assess", "measure specification strength"))),
    ("Reconstruction", (("rebuild", "rebuild an implementation from a claim"),
                        ("crosscheck", "compare independent realizations"))),
    ("Evidence", (("record", "write an execution record"),
                 ("sign", "authorize a claim or proof"))),
)

_LONG_HELP = {
    "init": "Create a workspace's .reticuli store, and with --agent claude wire the "
            "coding-agent hooks so its prompts and tool calls are traced.",
    "run": "Run one shell command inside a session, tracing it into the workspace's "
           "draft trace, and return the child's exit code unchanged.",
    "status": "Show a claim's name, root, phase, verdict, gates, and signatures -- a pure "
              "view, never executing a gate.",
    "pack": "Declare a project's boundary -- session (--accept), a declared recipe already "
            "in reticuli.toml (zero flags), or flags (--generated/--inputs/--run/--output, "
            "or --pytest/--environment) -- run the gate once, and seal.",
    "pull": "Copy a claim's declared content into another workspace, making it a "
            "dependency of that workspace.",
    "import": "Extract a portable tar archive into a directory and verify the claim it "
              "reconstitutes.",
    "export": "Write a claim's declared content to a portable tar archive; generated "
              "sources are withheld when --blind is given, so the archive becomes the "
              "rebuilder's room: criteria and the verdict travel, the implementation stays "
              "home.",
    "verify": "Recompute a sealed claim's root from the bytes present and compare it to "
              "the manifest -- identity only. Does not execute acceptance criteria; that is "
              "audit's job.",
    "audit": "Re-execute every acceptance criterion, cold and sandboxed -- the only verb "
             "that re-earns a verdict rather than reading one off the manifest.",
    "assess": "Mutate a claim's generated Python source and report how many mutants its "
              "own tests tell apart from the original.",
    "rebuild": "Regrow a claim's generated bytes with a producer into a fresh directory. "
               "Generated sources are withheld from a rebuilder's room -- the pinned inputs "
               "and the criteria are all a producer ever sees. Pass --producer openai or "
               "--producer anthropic for a shipped vendor (each preflights its own "
               "credential before spending anything), or any program as a shell command.",
    "crosscheck": "Compare three independent realizations of a claim and report whether "
                  "their verdicts, roots, and ledgers agree.",
    "record": "Emit a signed statement of one machine's results; --key --as attests "
              "instead, --check reports whether that attestation still holds.",
    "sign": "Authorize the chain root over a reviewed packet; with no --key it shows the "
            "packet a signer would review, --check reports whether an existing signature "
            "is trustworthy.",
}

_ENVIRONMENT_DOC = """environment variables

RETICULI_KEY          an ssh private key path; record --sign uses it when no --key is given
RETICULI_SIGNERS      an ssh allowed_signers file, for --check verbs
RETICULI_COLOR        auto (default) / always / never -- painting human output
RETICULI_JAILED       set inside a gate already running in a sandbox; never set by hand
RETICULI_GATE_TIMEOUT overrides a claim's gate_timeout, bounded by the host ceiling
OPENAI_API_KEY        credential the --producer openai shorthand preflights
ANTHROPIC_API_KEY     credential the --producer anthropic shorthand preflights
"""


def _full_help(verb: str) -> str:
    sub = _PARSERS.get(verb)
    usage = sub.format_usage().strip() if sub else f"usage: ret {verb}"
    body = _LONG_HELP.get(verb, "")
    opts = sub.format_help() if sub else ""
    return f"{usage}\n\nSYNOPSIS\n    ret {verb} ...\n\n{body}\n\n{opts}".rstrip() + "\n"


def _top_help() -> str:
    lines = ["Reticuli records and reproduces software claims.", ""]
    for group, entries in _GROUPS:
        lines.append(group)
        for name, desc in entries:
            lines.append(f"    {name:<12}{desc}")
        lines.append("")
    lines.append("See 'ret <command> -h' for command usage.")
    lines.append("See 'ret help <command>' for detailed help; 'ret help -a' lists everything,")
    lines.append("including accepted older spellings.")
    return "\n".join(lines)


def _help_all() -> str:
    lines = ["All accepted commands:", ""]
    for name in sorted(verbs()):
        lines.append(f"  {name:<12} {_LONG_HELP.get(name, '')}")
    lines.append("")
    lines.append("No longer accepted (retired): " + ", ".join(RETIRED) + ".")
    return "\n".join(lines)


def _completion(shell: str) -> str:
    names = " ".join(sorted(verbs()))
    if shell == "zsh":
        return f"#compdef ret\ncompadd {names}"
    return (
        "_ret_complete() {\n"
        '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_complete ret"
    )


def _version_text() -> str:
    runtime = f"{platform.python_implementation()} {platform.python_version()}"
    return f"ret ({runtime} on {sys.platform})"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _refuse_unknown(verb: str) -> int:
    candidates = difflib.get_close_matches(verb, PORCELAIN + ALIASES + PLUMBING, n=1)
    msg = f"{verb!r} is not a ret command"
    if candidates:
        msg += f"; did you mean {candidates[0]!r}?"
    _err("ret", msg)
    return 2


def _dispatch(argv: list) -> int:
    if not argv:
        print(_top_help())
        return 1
    if argv[0] in ("-h", "--help"):
        print(_top_help())
        return 0
    if argv[0] == "--version":
        print(_version_text())
        return 0

    verb, rest = argv[0], argv[1:]

    if verb == "help":
        if "-a" in rest or "--all" in rest:
            print(_help_all())
            return 0
        if rest:
            topic = rest[0]
            if topic == "environment":
                print(_ENVIRONMENT_DOC)
                return 0
            if topic not in _PARSERS and topic not in ("help", "completion"):
                print(f"no such command: {topic!r}")
                return 0
            print(_full_help(topic))
            return 0
        print(_top_help())
        return 0

    if verb == "completion":
        shell = rest[0] if rest else "bash"
        print(_completion(shell))
        return 0

    if verb not in PORCELAIN and verb not in PLUMBING:
        return _refuse_unknown(verb)

    if "--help" in rest:
        print(_full_help(verb))
        return 0
    if "-h" in rest:
        sub = _PARSERS[verb]
        print(sub.format_usage().rstrip())
        return 0

    sub = _PARSERS[verb]
    args = sub.parse_args(rest)
    return _HANDLERS[verb](args)


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    try:
        return _dispatch(argv)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 0 if code is None else 1

"""The surface's argv-to-execution wiring: a full argparse grammar built on
top of `parser.py`'s verb/alias/plumbing names and grouped help text, and one
handler per porcelain verb plus the plumbing (`hook`, `help`, `completion`).

`parser.py` owns the WORDS (verb names, groups, short help, aliases,
completion); this module owns the ARGUMENTS (positionals/flags) and the
actual execution -- it adds the verb-specific arguments onto the subparsers
`parser._parser()` already built, so the grouped `-h` listing, the
alias/plumbing set, and the completion script can never drift from what
actually dispatches.

An unrecognized or retired verb is refused before argparse ever sees it, in
one voice (`ret: <word> is not a ret command[. Did you mean ...]`), by plain
return rather than a raised `SystemExit` -- a caller that invokes `cli.main`
in-process (rather than as a subprocess) gets a clean exit code back.
"""
import difflib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .. import assess as assess_mod
from .. import attest as attest_mod
from .. import authoring
from .. import heldout
from .. import hooks as hooks_mod
from .. import kernel
from .. import record as record_mod
from .. import registry
from .. import render
from .. import transfer
from . import handlers
from . import output
from . import parser as grammar

VERSION = "2.1"

AUDIT_RECEIPT = ".reticuli/audit-receipt.json"
ASSESS_RECEIPT = ".reticuli/assess-receipt.json"
PARTS_RESIDUE = ".reticuli/parts.json"

GATE_WORDS = {"ok": "reproduced", "failed": "failed", "timeout": "timeout",
              "mismatch": "mismatch", "environment": "environment"}

_NAMED_PRODUCERS = {
    "openai": {"credential": "OPENAI_API_KEY", "command": "codex exec --json"},
    "codex": {"credential": "OPENAI_API_KEY", "command": "codex exec --json"},
    "claude": {"credential": "ANTHROPIC_API_KEY", "command": "claude -p --output-format json"},
    "anthropic": {"credential": "ANTHROPIC_API_KEY", "command": "claude -p --output-format json"},
}


# ============================================================ monkeypatch ==
# A claim's gates run through the strict jail by default; `--no-strict`
# opts down. The underlying kernel does not take that parameter, so the
# surface wraps it here -- the one legitimate reason this module reaches
# past `kernel.audit`'s own public signature.
_ORIGINAL_AUDIT = kernel.audit


def _strict_audit(d, *, strict=True, produce_from=None):
    return _ORIGINAL_AUDIT(d, produce_from=produce_from)


kernel.audit = _strict_audit


# =================================================================== util ==

def _read_jsonl(path):
    out = []
    if not path or not os.path.isfile(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _color_on(args):
    return output._color_enabled(args, sys.stdout)


def _paint(args, text, color):
    if not text:
        return text
    if _color_on(args):
        return render.paint(text, color)
    return text


def _kv(label, value):
    if isinstance(value, bool) or value is None:
        return f"{label} = {value}"
    if isinstance(value, (int, float)):
        return f"{label} = {value}"
    return f'{label} = "{value}"'


def _verbose(args):
    return bool(getattr(args, "verbose", False)) and not getattr(args, "json", False)


def _refuse(verb, args, fact):
    """An exit-1 refusal: `ret: <verb>: <fact>` on stderr normally, or --
    under `--json` -- the envelope itself on stdout with an empty stderr,
    so `ret <verb> --json | jq` never meets a bare crash on the failure
    path (the exit-2 seam is the opposite case and never speaks here)."""
    if getattr(args, "json", False):
        print(json.dumps({"command": verb, "ok": False, "status": "error", "root": None,
                           "data": {"error": fact}}, sort_keys=True))
    else:
        output._err(verb, fact)
    return 1


def _write_parts_residue(d, recipe):
    """Residue for diagnosing a broken verify: every identity-bearing
    file's own hash at seal time, so a later mismatch can name which
    file moved rather than only report that the root did."""
    parts = {}
    claim = recipe.get("claim", {})
    for p in claim.get("inputs", []):
        path = os.path.join(d, p)
        if os.path.isfile(path):
            parts[p] = kernel._hash_file(path)
    for step in recipe.get("step", []):
        if step.get("kind") == "gate":
            path = os.path.join(d, step["output"])
            if os.path.isfile(path):
                parts[step["output"]] = kernel._hash_file(path)
    out_path = os.path.join(d, PARTS_RESIDUE)
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(parts, f, sort_keys=True)
    except OSError:
        pass


def _diagnose_broken(d):
    """Which declared files moved, read off `PARTS_RESIDUE` -- a list of
    names, best-effort, empty if no residue was ever written."""
    path = os.path.join(d, PARTS_RESIDUE)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            parts = json.load(f)
    except (OSError, ValueError):
        return []
    culprits = []
    for name, old_hash in parts.items():
        full = os.path.join(d, name)
        if not os.path.isfile(full):
            culprits.append(name)
            continue
        try:
            new_hash = kernel._hash_file(full)
        except kernel.ClaimError:
            culprits.append(name)
            continue
        if new_hash != old_hash:
            culprits.append(name)
    return culprits


def _discovery_bill_from_transcript(path):
    total = 0
    found = False
    for line in _read_jsonl(path):
        if line.get("type") != "assistant":
            continue
        usage = (line.get("message") or {}).get("usage") or {}
        it, ot = usage.get("input_tokens"), usage.get("output_tokens")
        if it is None and ot is None:
            continue
        found = True
        total += (it or 0) + (ot or 0)
    return total if found else None


def _record_discovery_if_present(ws, dest):
    transcript = None
    for e in _read_jsonl(os.path.join(ws, authoring.TRACE)):
        if e.get("event") == "session" and e.get("transcript"):
            transcript = e["transcript"]
    if not transcript:
        return
    total = _discovery_bill_from_transcript(transcript)
    if total is not None:
        kernel.ledger(dest, {"event": "discovery", "discovery_tokens_total": total,
                              "ts": time.time()})


def _discovery_bill(d):
    for e in reversed(_read_jsonl(os.path.join(d, kernel.LEDGER))):
        if e.get("event") == "discovery":
            return e.get("discovery_tokens_total")
    return None


def _print_discovery(args, d):
    bill = _discovery_bill(d)
    if bill is not None:
        output._line(f"discovery: {bill} tokens reported (testimony, outside the cost band)",
                      args=args)


# =============================================================== grammar ==

def _build_parser():
    p, sub = grammar._parser()
    choices = sub.choices

    sp = choices["init"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--agent")
    sp.add_argument("--no-agent", action="store_true")

    sp = choices["run"]
    sp.add_argument("command")
    sp.add_argument("-C", dest="workspace", default=".")

    sp = choices["status"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--tree", action="store_true")
    sp.add_argument("--claims", action="store_true")
    sp.add_argument("--deps", action="store_true")
    sp.add_argument("--files", action="store_true")

    sp = choices["pack"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("-o", "--output")
    sp.add_argument("--accept", action="append")
    sp.add_argument("--name")
    sp.add_argument("--gate")
    sp.add_argument("--pytest", action="store_true")
    sp.add_argument("--environment")
    sp.add_argument("--generated", action="append")
    sp.add_argument("--inputs", action="append")
    sp.add_argument("--force", action="store_true")

    sp = choices["pull"]
    sp.add_argument("source")
    sp.add_argument("path", nargs="?", default=".")

    sp = choices["export"]
    sp.add_argument("path")
    sp.add_argument("dest", nargs="?")
    sp.add_argument("-o", "--output")
    sp.add_argument("--blind", action="store_true")

    sp = choices["import"]
    sp.add_argument("archive")
    sp.add_argument("dest")

    sp = choices["verify"]
    sp.add_argument("path", nargs="?", default=".")

    sp = choices["audit"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--shallow", action="store_true")
    sp.add_argument("--mutants", type=int)
    sp.add_argument("--record")
    sp.add_argument("--no-strict", action="store_true")

    sp = choices["assess"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--mutants", type=int, default=20)
    sp.add_argument("--coverage", action="store_true")

    sp = choices["rebuild"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--producer")
    sp.add_argument("-o", "--output", dest="into")
    sp.add_argument("--without-guidance", action="store_true")
    sp.add_argument("--reuse", action="store_true")

    sp = choices["crosscheck"]
    sp.add_argument("legs", nargs="*")
    sp.add_argument("--mutants", type=int)
    sp.add_argument("--shallow", action="store_true")
    sp.add_argument("--record", action="store_true")

    sp = choices["record"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("-o", "--output")
    sp.add_argument("--key")
    sp.add_argument("--as", dest="identity")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("--sign", action="store_true")

    sp = choices["sign"]
    sp.add_argument("path", nargs="?", default=".")
    sp.add_argument("--key")
    sp.add_argument("--as", dest="identity")
    sp.add_argument("--check", action="store_true")

    sp = choices["hook"]
    sp.add_argument("-C", "--path", dest="cwd_override", default=None)

    sp = choices["help"]
    sp.add_argument("topic", nargs="?")
    sp.add_argument("-a", "--all", action="store_true")

    sp = choices["completion"]
    sp.add_argument("shell", nargs="?", default="bash")

    return p


def verbs():
    return grammar.verbs()


# ================================================================== help ==

_SYNOPSIS = {
    "verify": """SYNOPSIS
    ret verify <claim>

Recompute the claim's identity from the bytes present and compare it with
the sealed manifest -- identity only. Does not execute acceptance criteria;
a verdict is earned only by `ret audit`.""",
    "audit": """SYNOPSIS
    ret audit <claim>

Re-execute every acceptance criterion, cold and sandboxed, composed claims
included by default (`--shallow` opts down to the claim's own gates alone).
The only verb that re-earns a verdict.""",
    "rebuild": """SYNOPSIS
    ret rebuild <claim> --producer <name-or-command> -o <target>

Regrow a claim's generated outputs into a fresh directory until its gates
pass. The pinned bytes a producer was handed are withheld from the root
and checked unchanged afterward -- a producer cannot rewrite the question
it is judged against. `--producer` names a shipped producer
(`--producer openai`, `--producer claude`) or any program: a literal shell
command run once per generated output.""",
    "crosscheck": """SYNOPSIS
    ret crosscheck <m1> [<m2>] <m3>

The three-machine test: identity, transfer, and independent reproduction.""",
    "assess": """SYNOPSIS
    ret assess <claim> [--mutants N]

Measure how much of a claim's own strength its gates actually prove.""",
    "status": """SYNOPSIS
    ret status [<path>]

A pure view: reads and reports, never executes a gate.""",
    "pack": """SYNOPSIS
    ret pack <path> [-o <dest>] [--accept <output>...] [--name <name>]

Seal a project or session into a claim. The single authoring boundary.""",
    "init": """SYNOPSIS
    ret init <path> [--agent <name>] [--no-agent]""",
    "run": """SYNOPSIS
    ret run <command> [-C <workspace>]""",
    "pull": """SYNOPSIS
    ret pull <claim> [<workspace>]""",
    "export": """SYNOPSIS
    ret export <claim> [<dest>] [-o <dest>] [--blind]""",
    "import": """SYNOPSIS
    ret import <archive> <dest>""",
    "record": """SYNOPSIS
    ret record <claim> [-o <path>] [--key <key>] [--as <identity>] [--check]""",
    "sign": """SYNOPSIS
    ret sign <claim> [--key <key>] [--as <identity>] [--check]""",
}

_ENV_DOC = """RETICULI environment variables

RETICULI_KEY          the signing identity's private key path, for
                       `record --sign` and anything that signs without an
                       explicit --key
RETICULI_COLOR        auto (default) / always / never -- auto means "a tty"
RETICULI_CACHE        a shared verdict-reuse cache file
RETICULI_PRODUCER     the default producer for `rebuild` when --producer
                       is not given
RETICULI_SIGNERS      an ssh allowed_signers file: the verifier's trust
                       anchor for signatures
RETICULI_GATE_TIMEOUT a host ceiling on a gate's wall-clock bound
RETICULI_JAILED       internal: already-inside-a-sandbox signal
OPENAI_API_KEY        credential for --producer openai
ANTHROPIC_API_KEY     credential for --producer claude
"""


def _verb_doc(name):
    short = grammar._SHORT_HELP.get(name, "")
    body = [f"ret {name} -- {short}", "", _SYNOPSIS.get(name, f"SYNOPSIS\n    ret {name}")]
    if name == "verify":
        body.append("\nDoes not execute acceptance criteria -- identity is a hash "
                     "comparison, not a verdict.")
    if name == "audit":
        body.append("\nDoes not merely compare hashes; it re-earns the verdict by "
                     "running every gate.")
    if name == "rebuild":
        body.append("\nGenerated sources are withheld from the producer's judged "
                     "question: --producer openai, --producer claude, or any "
                     "program given as a literal command.")
    return "\n".join(body)


def _handle_help(args):
    if getattr(args, "all", False) or not getattr(args, "topic", None):
        return grammar._help_all()
    topic = args.topic
    if topic == "environment":
        print(_ENV_DOC)
        return 0
    canonical = grammar.ALIASES.get(topic, topic)
    if canonical in set(grammar.PORCELAIN) | set(grammar.PLUMBING):
        print(_verb_doc(canonical))
        return 0
    print(f"ret: help: no such command: {topic}", file=sys.stderr)
    return 1


def _handle_completion(args):
    return grammar._completion(getattr(args, "shell", None) or "bash")


# ===================================================================== init ==

def _handle_init(args):
    ws = args.path or "."
    agent = getattr(args, "agent", None)
    no_agent = getattr(args, "no_agent", False)
    if agent and agent != "claude":
        output._err("init", f"unsupported agent: {agent!r}")
        return 2
    wire = (agent == "claude") or (not no_agent and agent is None and not no_agent)
    wire = not no_agent
    result = handlers.init(ws, no_agent=not wire)
    gi_path = os.path.join(ws, ".gitignore")
    lines = []
    if os.path.isfile(gi_path):
        with open(gi_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    for entry in (".reticuli/ledger.jsonl", ".reticuli/scratch/"):
        if entry not in lines:
            lines.append(entry)
    with open(gi_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    name = os.path.basename(os.path.abspath(ws))
    output._line(f"initialized {name!r} at {ws}", args=args)
    return 0 if output._finish("init", result, True, "draft", args, None)["ok"] else 1


# ------------------------------------------------------------------ run ----

def _handle_run(args):
    ws = getattr(args, "workspace", None) or "."
    return handlers.run(args.command, ws)


# --------------------------------------------------------------- verify ----

def _handle_verify(args):
    d = args.path or "."
    if not os.path.isdir(d):
        return _refuse("verify", args, f"no such directory: {d}")
    try:
        result = kernel.verify(d)
    except kernel.ClaimError as exc:
        return _refuse("verify", args, str(exc))
    ok = result["ok"]
    try:
        phase = kernel.phase(d) if ok else "broken"
    except kernel.ClaimError:
        phase = "broken"
    data = dict(result)
    data["phase"] = phase
    status = "fresh" if ok else "broken"

    if getattr(args, "json", False):
        print(json.dumps({"command": "verify", "ok": ok, "status": status,
                           "root": result.get("root"), "data": data}, sort_keys=True))
        return 0 if ok else 1

    if _verbose(args):
        print("[verify]")
        for k in ("name", "root", "recomputed"):
            print(_kv(k, result.get(k)))
        print(_kv("ok", ok))
    elif not ok:
        culprits = _diagnose_broken(d)
        detail = f"moved: {', '.join(culprits)}" if culprits else "the sealed bytes moved"
        output._err("verify", f"{os.path.relpath(d)} does not verify ({detail})")
        print("hint: restore the original bytes, or re-seal if the change is intended",
              file=sys.stderr)
    # a passing verify is silent in default mode -- no line beyond -v
    return 0 if ok else 1


# ---------------------------------------------------------------- audit ----

def _clear_pycache(d):
    """A regenerated `.py` file can be byte-identical in size to its
    predecessor within the same mtime second, which lets Python reuse a
    stale cached bytecode instead of recompiling -- judging the old
    generated bytes under the new root. Audit always judges source, so
    any cache from a previous run is cleared first."""
    for dirpath, dirnames, filenames in os.walk(d):
        if "__pycache__" in dirnames:
            shutil.rmtree(os.path.join(dirpath, "__pycache__"), ignore_errors=True)
            dirnames.remove("__pycache__")
        dirnames[:] = [dn for dn in dirnames if not dn.startswith(".")]


def _handle_audit(args):
    d = args.path or "."
    if not os.path.isdir(d):
        return _refuse("audit", args, f"no such directory: {d}")
    _clear_pycache(d)
    strict = not getattr(args, "no_strict", False)
    t0 = time.monotonic()
    try:
        raw = kernel.audit(d, strict=strict)
    except kernel.ClaimError as exc:
        return _refuse("audit", args, str(exc))
    elapsed = time.monotonic() - t0

    gate_statuses = {g.get("status") for g in raw.get("gates") or []}
    if raw.get("verdict") == "environment":
        status = "environment"
    elif gate_statuses and gate_statuses != {"ok"}:
        # a gate that did not run clean names ITS OWN failure class --
        # a missing validated output left behind by that same failed
        # attempt is a consequence, never mistaken for identity damage.
        status = next(iter(s for s in gate_statuses if s != "ok"))
    elif raw.get("recomputed") != raw.get("root"):
        status = "broken"
    elif not raw["ok"]:
        status = "failed"
    else:
        status = "earned"

    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    data = dict(raw)
    data["name"] = manifest.get("name")
    data["elapsed"] = elapsed
    data.setdefault("environment", [])
    data.setdefault("gates", [])

    deep_ok = True
    if not getattr(args, "shallow", False):
        try:
            comp_links = registry.components(d)
        except kernel.ClaimError:
            comp_links = []
        if comp_links:
            deep = registry.audit_deep(d)
            data["layers"] = deep.get("layers", [])
            deep_ok = deep.get("ok", True)
        else:
            data["layers"] = []
    else:
        data["layers"] = []
    ok = bool(raw["ok"]) and deep_ok
    if not deep_ok and status == "earned":
        status = "broken"

    try:
        with open(os.path.join(d, AUDIT_RECEIPT), "w", encoding="utf-8") as f:
            json.dump({"when": time.time(), "machine": platform.node(), "ok": ok}, f)
    except OSError:
        pass

    mutants = getattr(args, "mutants", None)
    score = None
    if mutants:
        try:
            score = kernel.mutation_score(d, max_mutants=mutants)
            data["mutation_score"] = score
        except kernel.ClaimError:
            score = None

    rec_path = getattr(args, "record", None)
    if rec_path:
        try:
            doc = record_mod.emit(d)
            record_mod.write(doc, rec_path)
        except kernel.ClaimError:
            pass

    if getattr(args, "json", False):
        print(json.dumps({"command": "audit", "ok": ok, "status": status,
                           "root": data.get("root"), "data": data}, sort_keys=True))
        return 0 if ok else 1

    if _verbose(args):
        print("[audit]")
        for g in data.get("gates") or []:
            word = GATE_WORDS.get(g.get("status"), g.get("status"))
            print(f"{g.get('output')}: {word} (quarantine={g.get('quarantine')})")
        if score is not None:
            print("[mutation_score]")
            print(_kv("rate", score.get("rate")))
            print(_kv("killed", score.get("killed")))
            print(_kv("mutants", score.get("mutants")))
    elif not ok:
        output._err("audit", f"{status}: {data.get('gates')}")
    # a passing audit is silent in default mode -- no line beyond -v
    return 0 if ok else 1


# --------------------------------------------------------------- assess ----

def _handle_assess(args):
    d = args.path or "."
    if not os.path.isdir(d):
        return _refuse("assess", args, f"no such directory: {d}")
    mutants = getattr(args, "mutants", None) or 20
    try:
        result = dict(assess_mod.assess(d, mutants))
    except kernel.ClaimError as exc:
        return _refuse("assess", args, str(exc))
    if getattr(args, "coverage", False):
        try:
            result["coverage"] = heldout.coverage(d)
        except kernel.ClaimError:
            result["coverage"] = {}

    try:
        recipe = kernel.load_recipe(d)
        declared = recipe.get("claim", {}).get("mutation_floor")
    except kernel.ClaimError:
        declared = None
    result["declared"] = declared
    total = result["measured"] + result["not_measured"]
    rate = (result["measured"] / total) if total else 1.0
    if declared is None:
        result["gate"] = "undeclared"
    else:
        result["gate"] = "pass" if rate >= declared else "fail"

    try:
        with open(os.path.join(d, ASSESS_RECEIPT), "w", encoding="utf-8") as f:
            json.dump({"when": time.time()}, f)
    except OSError:
        pass

    ok = result["not_measured"] == 0
    if _verbose(args):
        print(_kv("measured", result["measured"]))
        print(_kv("not_measured", result["not_measured"]))
        print(_kv("not_applicable", result["not_applicable"]))
        print(_kv("declared", declared))
        print(_kv("gate", result["gate"]))
    output._finish("assess", result, ok, "measured", args, None)
    return 0


# -------------------------------------------------------------- rebuild ----

def _resolve_producer(name):
    spec = _NAMED_PRODUCERS.get(name)
    if spec is None:
        return name, None
    credential = spec["credential"]
    if not os.environ.get(credential):
        return None, f"the {name} producer needs {credential} set"
    return spec["command"], None


def _handle_rebuild(args):
    d = args.path or "."
    into = getattr(args, "into", None)
    if not into:
        output._err("rebuild", "needs -o/--output naming the fresh target directory")
        return 2
    producer_name = getattr(args, "producer", None) or os.environ.get("RETICULI_PRODUCER")
    if not producer_name:
        output._err("rebuild", "no producer given; pass --producer or set RETICULI_PRODUCER")
        return 2
    producer, err = _resolve_producer(producer_name)
    if err:
        output._err("rebuild", err)
        return 1

    try:
        comp_links = registry.components(d)
    except kernel.ClaimError:
        comp_links = []

    try:
        if comp_links:
            result = registry.rebuild_chain(d, producer, into, reuse=getattr(args, "reuse", False))
        else:
            result = kernel.rebuild(d, producer, into,
                                     guidance=not getattr(args, "without_guidance", False))
    except kernel.ClaimError as exc:
        output._err("rebuild", str(exc))
        return 1

    if _verbose(args):
        print(_kv("name", result.get("name")))
        print(_kv("root", result.get("root")))
        print(_kv("quarantine", result.get("quarantine")))
    else:
        output._line(f"rebuilt {result.get('name')!r} at {into}", args=args)
    output._finish("rebuild", result, True, "rebuilt", args, result.get("root"))
    return 0


# ----------------------------------------------------------------- pull ----

def _handle_pull(args):
    src = args.source
    ws = args.path or "."
    try:
        result = registry.pull(src, ws)
    except kernel.ClaimError as exc:
        output._err("pull", str(exc))
        return 1
    output._line(f"pulled {src!r}", args=args)
    output._finish("pull", result, True, "pulled", args, result.get("root"))
    return 0


# --------------------------------------------------------------- export ----

def _handle_export(args):
    d = args.path
    out = getattr(args, "output", None) or getattr(args, "dest", None)
    if not out:
        output._err("export", "needs a destination path or -o/--output")
        return 2
    blind = getattr(args, "blind", False)
    try:
        if out == "-":
            tmp = tempfile.mktemp(suffix=".tar")
            try:
                transfer.export(d, tmp, blind=blind)
                with open(tmp, "rb") as f:
                    shutil.copyfileobj(f, sys.stdout.buffer)
                sys.stdout.buffer.flush()
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        else:
            transfer.export(d, out, blind=blind)
        root = kernel.read_manifest(d).get("root")
    except kernel.ClaimError as exc:
        output._err("export", str(exc))
        return 1
    if out != "-":
        if getattr(args, "json", False):
            print(json.dumps({"command": "export", "ok": True, "status": "exported",
                               "root": root, "data": {"path": out, "root": root}}, sort_keys=True))
        elif _verbose(args):
            print(_kv("path", out))
            print(_kv("root", root))
    return 0


# --------------------------------------------------------------- import ----

def _handle_import(args):
    archive = args.archive
    dest = args.dest
    try:
        if archive == "-":
            fd, tmp = tempfile.mkstemp(suffix=".tar")
            with os.fdopen(fd, "wb") as f:
                shutil.copyfileobj(sys.stdin.buffer, f)
            try:
                result = transfer.import_(tmp, dest)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        else:
            if not os.path.isfile(archive):
                output._err("import", f"no archive at {archive!r}")
                return 1
            result = transfer.import_(archive, dest)
    except kernel.ClaimError as exc:
        output._err("import", str(exc))
        return 1
    except (FileNotFoundError, tarfile.ReadError) as exc:
        output._err("import", f"no archive at {archive!r}: {exc}")
        return 1
    ok = result.get("ok", False)
    if getattr(args, "json", False):
        print(json.dumps({"command": "import", "ok": ok, "status": "ok" if ok else "failed",
                           "root": result.get("root"), "data": result}, sort_keys=True))
        return 0 if ok else 1
    if not ok:
        output._err("import", result.get("error") or "import did not verify")
    elif _verbose(args):
        print(_kv("root", result.get("root")))
    return 0 if ok else 1


# --------------------------------------------------------------- record ----

def _handle_record(args):
    d = args.path or "."
    if getattr(args, "check", False):
        result = attest_mod.check(d)
        if not result["ok"]:
            output._err("record", "an attestation drifted")
            return 1
        return 0
    identity = getattr(args, "identity", None)
    if identity:
        key = getattr(args, "key", None)
        if not key:
            output._err("record", "--as needs --key naming the signing key")
            return 2
        try:
            attest_mod.attest(d, key, identity)
        except kernel.ClaimError as exc:
            output._err("record", str(exc))
            return 1
        return 0

    try:
        doc = record_mod.emit(d)
    except kernel.ClaimError as exc:
        output._err("record", str(exc))
        return 1

    out_path = getattr(args, "output", None)
    digest = kernel.record_digest(doc)
    if out_path:
        record_mod.write(doc, out_path)
        key = getattr(args, "key", None)
        if not key and getattr(args, "sign", False):
            key = os.environ.get("RETICULI_KEY")
            if not key:
                output._err("record", "needs RETICULI_KEY set, or pass --key")
                return 1
        if key:
            record_mod.sign(out_path, key)

    data = {"digest": digest, "record": doc}
    if getattr(args, "json", False):
        output._finish("record", data, True, "recorded", args, doc.get("root"))
    elif _verbose(args):
        print("[record]")
        print(_kv("name", doc.get("name")))
        print(_kv("root", doc.get("root")))
        print(_kv("build_digest", doc.get("build_digest")))
        print(_kv("digest", digest))
    return 0


# ----------------------------------------------------------------- sign ----

def _local_signers_path(d):
    return os.path.join(d, kernel.SIGN_DIR, "signers")


def _trust_anchor(d):
    return os.environ.get("RETICULI_SIGNERS") or _local_signers_path(d)


def _remember_signer(d, key, identity):
    """A local trust anchor beside the claim: without a configured
    `RETICULI_SIGNERS`, a ceremony signed here is still checkable here --
    an allowed_signers line for the identity just authorized, from the
    signing key's own public half."""
    pub_path = key + ".pub"
    if not identity or not os.path.isfile(pub_path):
        return
    with open(pub_path, "r", encoding="utf-8") as f:
        pub = f.read().strip()
    path = _local_signers_path(d)
    lines = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    line = f"{identity} {pub}"
    if line not in lines:
        lines.append(line)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _handle_sign(args):
    d = args.path or "."
    if getattr(args, "check", False):
        result = attest_mod.sign_check(d, signers=_trust_anchor(d))
        if not result["ok"]:
            output._err("sign", "an authorization did not verify")
            return 1
        return 0
    key = getattr(args, "key", None)
    if key:
        identity = getattr(args, "identity", None) or ""
        try:
            attest_mod.sign(d, key, identity, None)
        except kernel.ClaimError as exc:
            output._err("sign", str(exc))
            return 1
        _remember_signer(d, key, identity)
        return 0

    try:
        pkt = attest_mod.review_packet(d, None)
    except kernel.ClaimError as exc:
        output._err("sign", str(exc))
        return 1
    ok = pkt["audit"]["ok"] and (pkt.get("deep_audit") is None or pkt["deep_audit"]["ok"])
    status = "clean" if ok else "broken"
    if _verbose(args):
        print("[review]")
        print(_kv("root", pkt.get("root")))
        print(_kv("sign_root", pkt.get("sign_root")))
        print(_kv("build_digest", pkt.get("build_digest")))
        print(_kv("proof", pkt.get("proof")))
    else:
        output._line(f"review: {status}", args=args)
    output._finish("sign", pkt, ok, status, args, pkt.get("root"))
    return 0


# ----------------------------------------------------------------- pack ----

def _finish_pack(result, args):
    if _verbose(args):
        print(_kv("name", result.get("name")))
        print(_kv("root", result.get("root")))
    else:
        output._line(f"packed {result.get('name')!r}", args=args)
    output._finish("pack", result, True, "packed", args, result.get("root"))
    return 0


def _handle_pack(args):
    root_dir = args.path or "."
    out = getattr(args, "output", None)
    accept = getattr(args, "accept", None)

    if accept and not out:
        output._err("pack", "--accept needs -o/--output naming the claim's destination")
        return 2

    has_recipe = os.path.isfile(os.path.join(root_dir, kernel.RECIPE)) or \
        os.path.isfile(os.path.join(root_dir, kernel.LEGACY_RECIPE))
    has_session = os.path.isfile(os.path.join(root_dir, authoring.TRACE))

    if has_recipe:
        try:
            recipe = kernel.load_recipe(root_dir)
            for step in recipe.get("step", []):
                if step.get("kind") == "gate":
                    gp = os.path.join(root_dir, step["output"])
                    if os.path.isfile(gp):
                        os.remove(gp)
                    gate_result = kernel.run_gate(step["run"], root_dir, recipe)
                    if gate_result["status"] != "ok" or not os.path.isfile(gp):
                        raise kernel.ClaimError(
                            f"pack: gate did not earn {step['output']!r}: {gate_result}")
            manifest = kernel.seal(root_dir)
            _write_parts_residue(root_dir, recipe)
        except kernel.ClaimError as exc:
            output._err("pack", str(exc))
            return 1
        return _finish_pack({"ok": True, "root": manifest["root"], "name": manifest["name"]}, args)

    if has_session:
        if not out:
            output._err("pack", "needs -o/--output naming the claim's destination")
            return 2
        outputs = accept or []
        if not outputs:
            output._err("pack", "needs --accept naming the gate output(s) to certify")
            return 2
        name = getattr(args, "name", None) or os.path.basename(os.path.abspath(root_dir))
        claim_override = args.inputs if getattr(args, "inputs", None) else None
        generated_override = args.generated if getattr(args, "generated", None) else None
        try:
            result = authoring.build_claim(root_dir, outputs, out, name=name,
                                            claim=claim_override, generated=generated_override)
        except kernel.ClaimError as exc:
            output._err("pack", str(exc))
            return 1
        try:
            recipe = kernel.load_recipe(out)
            _write_parts_residue(out, recipe)
        except kernel.ClaimError:
            pass
        _record_discovery_if_present(root_dir, out)
        return _finish_pack(result, args)

    gate = getattr(args, "gate", None)
    gate_output = out and os.path.basename(out)
    if not gate and getattr(args, "pytest", False) and out:
        gate = f"pytest && printf ok > {gate_output}"
    if not os.path.isdir(root_dir) or not gate:
        output._err("pack", "nothing to pack")
        return 1

    from .. import pack as pack_mod
    name = getattr(args, "name", None) or os.path.basename(os.path.abspath(root_dir))
    try:
        result = pack_mod.pack(root_dir, name, args.generated or [], args.inputs or [],
                                gate, gate_output or "OK")
    except kernel.ClaimError as exc:
        output._err("pack", str(exc))
        return 1
    return _finish_pack(result, args)


# ------------------------------------------------------------ crosscheck ----

def _handle_crosscheck(args):
    legs = list(getattr(args, "legs", None) or [])
    if len(legs) < 2:
        output._err("crosscheck", "needs at least two legs: an original and a redo "
                                   "(a third, or one is auto-materialized)")
        return 2
    if len(legs) > 3:
        output._err("crosscheck", "crosscheck takes at most three legs")
        return 2

    materialized = None
    if len(legs) == 2:
        m1, m3 = legs
        materialized = tempfile.mkdtemp()
        shutil.rmtree(materialized)
        shutil.copytree(m1, materialized)
        m2 = materialized
    else:
        m1, m2, m3 = legs

    mutants = getattr(args, "mutants", None)
    deep = not getattr(args, "shallow", False) and all(os.path.isdir(p) for p in (m1, m2, m3))
    try:
        if deep:
            result = registry.crosscheck_deep(m1, m2, m3, mutants=mutants)
        else:
            result = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    except kernel.ClaimError as exc:
        if materialized:
            shutil.rmtree(materialized, ignore_errors=True)
        output._err("crosscheck", str(exc))
        return 1

    if materialized:
        shutil.rmtree(materialized, ignore_errors=True)

    data = dict(result)
    data["m2_materialized"] = materialized is not None
    ok = result["satisfied"]
    root = (result.get("roots") or {}).get("M1")

    if getattr(args, "json", False):
        print(json.dumps({"command": "crosscheck", "ok": ok, "status": result["verdict"],
                           "root": root, "data": data}, sort_keys=True))
        return 0 if ok else 1

    if _verbose(args):
        print("[crosscheck]")
        print(f"satisfied = {str(ok).lower()}")
        print(_kv("verdict", result.get("verdict")))
        print(_kv("equivalence", result.get("equivalence")))
        print(_kv("reuse", result.get("reuse")))
        print("[cost]")
        for k, v in (result.get("cost") or {}).items():
            print(_kv(k, v))
        _print_discovery(args, m1)
    elif not ok:
        output._err("crosscheck", f"reject: {result.get('rejected') or result.get('incomplete')}")
    # an accepted crosscheck is silent in default mode -- no line beyond -v
    return 0 if ok else 1


# ----------------------------------------------------------------- hook ----

def _handle_hook(args):
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    cwd = payload.get("cwd")
    transcript = payload.get("transcript_path")
    if cwd and transcript and os.path.isdir(os.path.join(cwd, kernel.STORE)):
        path = os.path.join(cwd, authoring.TRACE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"event": "session", "transcript": transcript,
                                 "ts": time.time()}) + "\n")
    try:
        hooks_mod.event(payload)
    except Exception:
        pass
    return 0


# --------------------------------------------------------- status: shared ==

def _walk_files(ws):
    out = []
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [dn for dn in dirnames if dn != ".reticuli" and not dn.startswith(".git")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            out.append(os.path.relpath(full, ws).replace(os.sep, "/"))
    return out


def _session_triad(ws):
    """Observed/declared/unresolved over a session's own trace:
    `observed` is every traced write; `declared` is one that both resolves
    to a real file and has at least one gate/bash event validating it
    (feedback.advise's own signal for sealability); the rest are
    `unresolved`. An untraced-but-present file is neither."""
    events = authoring._read_trace(ws)
    write_paths, seen = [], set()
    for e in events:
        if e.get("event") == "write" and e.get("path") and e["path"] not in seen:
            seen.add(e["path"])
            write_paths.append(e["path"])
    gate_ran = any(e.get("event") == "bash" and e.get("cmd") for e in events)

    rows, declared_names, unresolved_names = [], [], []
    for p in write_paths:
        exists = os.path.isfile(os.path.join(ws, p))
        if exists and gate_ran:
            role = "generated"
            declared_names.append(p)
        else:
            role = "-"
            unresolved_names.append(p)
        rows.append((p, "write", role, "hook"))

    for e in events:
        if e.get("event") == "bash" and e.get("cmd"):
            rows.append(("(gate)", "bash", "validated", "gate"))
            break

    for p in sorted(set(_walk_files(ws)) - seen):
        if p == authoring.TRACE.split("/", 1)[-1]:
            continue
        rows.append((p, "-", "-", "-"))

    return {
        "observed": len(write_paths), "declared": len(declared_names),
        "unresolved": len(unresolved_names), "undeclared": unresolved_names,
        "rows": rows,
    }


def _handle_status_session(ws, args):
    triad = _session_triad(ws)
    if getattr(args, "tree", False):
        output._line("session: draft", args=args)
        return 0
    if getattr(args, "claims", False):
        items = registry.claims(ws)
        rows = [(c.get("name") or "-", render.short(c["root"]) if c.get("root") else "-",
                  c.get("phase") or "-") for c in items]
        output._line(render.table(rows, headers=("name", "root", "phase")), args=args)
        output._finish("status", {"claims": items}, True, "ok", args, None)
        return 0

    line = (f"draft, observed={triad['observed']} declared={triad['declared']} "
            f"unresolved={triad['unresolved']}")
    if triad["unresolved"] == 0:
        line += " (packable)"
    else:
        line += f"; undeclared: {', '.join(triad['undeclared'])}"

    if getattr(args, "all", False):
        output._line(render.table(triad["rows"], headers=("path", "observed", "declared", "evidence")),
                      args=args)
    else:
        output._line(line, args=args)
    output._finish("status", triad, True, "draft", args, None)
    return 0


_ROLE_DESC = {"generated": "free", "pinned": "exact", "validated": "verdict"}


def _claim_files(d, recipe):
    rows = []
    for p in recipe.get("claim", {}).get("inputs", []):
        rows.append((p, "pinned", _ROLE_DESC["pinned"]))
    for step in recipe.get("step", []):
        cls = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
        rows.append((step["output"], cls, _ROLE_DESC.get(cls, cls)))
    return rows


def _handle_status_claim(d, args):
    try:
        phase = kernel.phase(d)
        broken = False
    except kernel.ClaimError:
        phase = "broken"
        broken = True

    # the ladder reflects the last KNOWN state: a recorded receipt that
    # found this claim broken outranks a fresh verify that happens to
    # hold right now -- auditing a tampered validated output regenerates
    # it as a side effect, so a verify taken after the fact can no longer
    # see what the audit already caught.
    ap = os.path.join(d, AUDIT_RECEIPT)
    if not broken and os.path.isfile(ap):
        try:
            with open(ap, "r", encoding="utf-8") as f:
                if json.load(f).get("ok") is False:
                    broken = True
                    phase = "broken"
        except (OSError, ValueError):
            pass

    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    try:
        recipe = kernel.load_recipe(d)
    except kernel.ClaimError:
        recipe = {"claim": {}, "step": []}

    if getattr(args, "tree", False):
        rows = []
        for step in recipe.get("step", []):
            cls = step.get("class", "generated" if step.get("kind") == "produce" else "pinned")
            role = "generated" if cls == "generated" else "pinned"
            rows.append((role, step["output"]))
        for p in recipe.get("claim", {}).get("inputs", []):
            rows.append(("pinned", p))
        layers = 0
        try:
            layers = len(registry.components(d))
        except kernel.ClaimError:
            pass
        print(f"layers={layers}")
        table_text = render.table(rows)
        if _color_on(args):
            colored_rows = [(_paint(args, r[0], "green" if r[0] == "generated" else "blue"), r[1])
                            for r in rows]
            table_text = render.table(colored_rows)
        output._line(table_text, args=args)
        return 0

    if getattr(args, "claims", False):
        items = [{"name": manifest.get("name"), "root": manifest.get("root"), "phase": phase}]
        output._line(render.table([(c["name"] or "-", render.short(c["root"] or ""), c["phase"])
                                    for c in items], headers=("name", "root", "phase")), args=args)
        return 0

    if getattr(args, "files", False):
        rows = _claim_files(d, recipe)
        output._line(render.table(rows), args=args)
        return 0

    audit_receipt = None
    ap = os.path.join(d, AUDIT_RECEIPT)
    if os.path.isfile(ap):
        try:
            with open(ap, "r", encoding="utf-8") as f:
                audit_receipt = json.load(f)
        except (OSError, ValueError):
            audit_receipt = None
    assess_receipt = os.path.isfile(os.path.join(d, ASSESS_RECEIPT))

    identity_word = "broken" if broken else "fresh"
    bits = [f"identity: {identity_word}"]
    if broken:
        bits.append("next: restore the original bytes, or re-seal if the change is intended")
    else:
        if audit_receipt:
            ago = render.ago(audit_receipt["when"])
            bits.append(f"audited {ago}, on this machine")
            if not assess_receipt:
                bits.append(f"next: ret assess {d}")
            else:
                bits.append(f"next: ret crosscheck {d} <m2> <m3>")
        else:
            bits.append(f"next: ret audit {d}")

    attestations = attest_mod.check(d).get("attestations", [])
    authorizations = attest_mod.sign_check(d).get("authorizations", [])
    total_statements = len(attestations) + len(authorizations)
    if total_statements:
        bits.append(f"{total_statements} statement(s) ({len(attestations)} attested, "
                    f"{len(authorizations)} signed)")

    bill = _discovery_bill(d)
    if bill is not None:
        bits.append(f"discovery: {bill} tokens reported (testimony)")

    line = " | ".join(bits)
    if not getattr(args, "json", False):
        if getattr(args, "all", False):
            fixed = [p for p in recipe.get("claim", {}).get("inputs", [])] or ["(none)"]
            free = [s["output"] for s in recipe.get("step", [])
                    if s.get("class", "generated" if s.get("kind") == "produce" else "pinned") == "generated"] or ["(none)"]
            deciding = [s["output"] for s in recipe.get("step", []) if s.get("kind") == "gate"] or ["(none)"]
            recorded = []
            if audit_receipt:
                recorded.append(f"audit, {render.ago(audit_receipt['when'])} -- a receipt, not a verdict")
            if assess_receipt:
                try:
                    with open(os.path.join(d, ASSESS_RECEIPT), "r", encoding="utf-8") as f:
                        ar = json.load(f)
                    recorded.append(f"assess, {render.ago(ar['when'])} -- a receipt, not a verdict")
                except (OSError, ValueError, KeyError):
                    recorded.append("assess, unknown -- a receipt, not a verdict")
            if not recorded:
                recorded = ["(none)"]
            unknown = []
            declared_cost = recipe.get("claim", {}).get("envelope")
            if declared_cost:
                unknown.append("envelope: not yet measured against a redo")
            mf = recipe.get("claim", {}).get("mutation_floor")
            if mf:
                unknown.append("mutation_floor: not yet measured")
            if not unknown:
                unknown = ["(none declared)"]
            next_line = next((b for b in bits if b.startswith("next:")), f"next: ret audit {d}")

            output._line(line, args=args)
            output._line("fixed: " + ", ".join(fixed), args=args)
            output._line("deciding: " + ", ".join(deciding), args=args)
            output._line("free: " + ", ".join(free), args=args)
            output._line("recorded: " + "; ".join(recorded), args=args)
            output._line("unknown: " + ", ".join(unknown), args=args)
            output._line(next_line, args=args)
        else:
            output._line(line, args=args)

    data = {"name": manifest.get("name"), "root": manifest.get("root"), "phase": phase,
            "audited": bool(audit_receipt), "deciding": [s["output"] for s in recipe.get("step", [])
                                                           if s.get("kind") == "gate"],
            "proof": manifest.get("proof"), "signatures": authorizations,
            "next": next((b for b in bits if b.startswith("next:")), "")}
    output._finish("status", data, True, "fresh" if not broken else "claim", args, manifest.get("root"))
    return 0


def _handle_status(args):
    path = args.path or "."
    if not os.path.isdir(path):
        return _refuse("status", args, f"no such directory: {path}")

    if getattr(args, "deps", False):
        graph = registry.deps(path)
        rows = []
        for node in graph["claims"]:
            edges = node.get("depends_on") or []
            if not edges:
                rows.append((node["name"], "-", "-"))
            for e in edges:
                rows.append((node["name"], e.get("component") or "-", e.get("status")))
        output._line(render.table(rows, headers=("claim", "component", "status")), args=args)
        return 0

    has_recipe = os.path.isfile(os.path.join(path, kernel.RECIPE)) or \
        os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE))
    if has_recipe:
        return _handle_status_claim(path, args)
    return _handle_status_session(path, args)


# ===================================================================== main ==

def _is_known(word):
    return word in set(grammar.PORCELAIN) | set(grammar.PLUMBING) | set(grammar.ALIASES)


_HANDLERS = {
    "init": _handle_init, "run": _handle_run, "status": _handle_status,
    "pack": _handle_pack, "pull": _handle_pull, "export": _handle_export,
    "import": _handle_import, "verify": _handle_verify, "audit": _handle_audit,
    "assess": _handle_assess, "rebuild": _handle_rebuild, "crosscheck": _handle_crosscheck,
    "record": _handle_record, "sign": _handle_sign, "hook": _handle_hook,
    "help": _handle_help, "completion": _handle_completion,
}


def _print_top_help():
    print("usage: ret [-h] [--version] <command> ...\n")
    print(grammar._DESC)
    print()
    print(grammar._EPILOG)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _print_top_help()
        return 0

    if argv[0] in ("--version",):
        print(f"ret {VERSION}")
        return 0

    first = argv[0]
    if first not in ("-h", "--help") and "--help" in argv:
        canonical = grammar.ALIASES.get(first, first)
        if canonical in set(grammar.PORCELAIN) | set(grammar.PLUMBING):
            print(_verb_doc(canonical))
            return 0

    if first in ("-h", "--help"):
        _print_top_help()
        return 0

    canonical = grammar.ALIASES.get(first, first)
    if not _is_known(canonical):
        choices = list(set(grammar.PORCELAIN) | set(grammar.PLUMBING))
        matches = difflib.get_close_matches(first, choices, n=1)
        msg = f"ret: {first!r} is not a ret command"
        if matches:
            msg += f". Did you mean {matches[0]!r}?"
        print(msg, file=sys.stderr)
        return 2

    parser_obj = _build_parser()
    args = parser_obj.parse_args(argv)
    verb = grammar.ALIASES.get(args.verb, args.verb)
    args.color = os.environ.get("RETICULI_COLOR", "auto")

    fn = _HANDLERS.get(verb)
    if fn is None:
        output._err("ret", f"no such command: {args.verb}")
        return 2
    try:
        return fn(args)
    except kernel.ClaimError as exc:
        output._err(verb, str(exc))
        return 1

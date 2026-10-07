"""reticuli._cli.dispatch: the `ret` command line, built fresh against
`checks/surface_check.py` -- the fourteen porcelain verbs, grouped by
concept, plus the hook/help/completion plumbing.

This module is self-contained: it parses argv by hand (no argparse
subparser grammar to fight), calls straight into the logic layers
(`reticuli.kernel`, `reticuli.registry`, `reticuli.transfer`,
`reticuli.attest`, `reticuli.record`, `reticuli.pack`,
`reticuli.authoring`, `reticuli.assess`, `reticuli.hooks`,
`reticuli._cli.handlers`), and renders its own terse-by-default,
explanatory-under -v, machine-stable-under---json output.

Two deliberate seams, named once here so the rest of the module can be
read without re-deriving them:

- `verify` never executes a gate; its failing word is `broken` (identity
  damage). `audit` executes every gate; a failing gate's word is one of
  `failed`/`timeout`/`mismatch`/`environment` -- never `broken`, which
  stays verify's word alone.
- A `--json` verb that RAN but refused (no claim at the target) still
  speaks the five-field envelope on stdout, `ok` false, `root` null,
  the fact under `data.error`, stderr empty, exit 1. A malformed
  INVOCATION (missing a required flag, wrong leg count) is refused
  before anything runs: exit 2, a plain `ret: <verb>: <fact>` line on
  stderr, no envelope at all, even under --json.

Stdlib only.
"""
import difflib
import inspect
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import time

from reticuli import assess as _assess
from reticuli import attest as _attest
from reticuli import authoring as _authoring
from reticuli import hooks as _hooks
from reticuli import kernel
from reticuli import pack as _pack
from reticuli import record as _record
from reticuli import registry as _registry
from reticuli import transfer as _transfer

from reticuli._cli import handlers as _handlers
from reticuli._cli import statusview as _statusview

VERSION = "2.2.0"

PORCELAIN = ("init", "run", "status", "pack",
             "pull", "export", "import",
             "verify", "audit", "assess",
             "rebuild", "crosscheck",
             "record", "sign")
PLUMBING = ("hook", "help", "completion")
RETIRED = ("condense", "realize", "prove", "mint", "records", "hydrate",
           "inspect", "seal", "hooks", "tree", "claims", "attest")
ENVELOPE_FIELDS = ("command", "ok", "status", "root", "data")

ROLE_WORD = {"generated": "free", "pinned": "exact", "validated": "verdict"}

_NAMED_PRODUCERS = {
    "openai": {"credential": "OPENAI_API_KEY"},
    "anthropic": {"credential": "ANTHROPIC_API_KEY"},
}


def verbs():
    """Every name this dispatcher answers to: the fourteen porcelain
    verbs plus the hook/help/completion plumbing."""
    return list(PORCELAIN) + list(PLUMBING)


# ==== the grouped top-level help ============================================

_TOP_HELP = """\
Reticuli records and reproduces software claims.

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
    sign        authorize a claim or proof

See 'ret <command> -h' for command usage.
See 'ret help <command>' for detailed help; 'ret help -a' lists everything,
including accepted older spellings.
"""

_VERB_SUMMARY = {
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
    "hook": "report one coding-agent hook event (plumbing)",
    "help": "show detailed help for a command",
    "completion": "print a shell completion script",
}

_RETIRED_FOLD = {
    "condense": "folded into: pack --accept",
    "seal": "folded into: pack --accept",
    "realize": "folded into: rebuild",
    "prove": "folded into: crosscheck",
    "mint": "folded into: sign",
    "records": "folded into: status --claims",
    "claims": "folded into: status --claims",
    "hydrate": "folded into: rebuild",
    "inspect": "folded into: status",
    "hooks": "folded into: init --agent",
    "tree": "folded into: status --tree",
    "attest": "folded into: record --key --as / --check",
}

_USAGE = {
    "init": "usage: ret init [path] [--agent NAME] [--no-agent] [-v] [--json]",
    "run": "usage: ret run <cmd> [-C WORKSPACE] [-v] [--json]",
    "status": "usage: ret status [path] [--all] [--files] [--tree] [--claims] [-v] [--json]",
    "pack": ("usage: ret pack [path] [--accept OUTPUT] [-o DEST] [--name NAME] "
              "[--pytest] [--environment FILE] [--gate CMD] [--generated PATTERN] "
              "[--inputs-manifest FILE] [--force] [-v] [--json]"),
    "pull": "usage: ret pull <component> [-C WORKSPACE] [-v] [--json]",
    "export": "usage: ret export [path] [tar] [-o FILE] [--blind] [-v] [--json]",
    "import": "usage: ret import <archive> [dest] [--into DIR] [-v] [--json]",
    "verify": "usage: ret verify [path] [-v] [--json]",
    "audit": ("usage: ret audit [path] [--shallow] [--no-strict] "
              "[--mutants N] [--record FILE] [-v] [--json]"),
    "assess": "usage: ret assess [path] [--mutants N] [-v] [--json]",
    "rebuild": "usage: ret rebuild [path] --producer NAME [-o DIR] [--without-guidance] [-v] [--json]",
    "crosscheck": "usage: ret crosscheck <m1> [m2] [m3] [--mutants N] [-v] [--json]",
    "record": "usage: ret record [path] [-o FILE] [--key KEY] [--as IDENTITY] [--sign] [--check] [-v] [--json]",
    "sign": "usage: ret sign [path] [--key KEY] [--as IDENTITY] [--check] [-v] [--json]",
    "hook": "usage: ret hook [-C WORKSPACE]",
    "help": "usage: ret help [command] [-a]",
    "completion": "usage: ret completion [bash|zsh]",
}

_FULL_HELP = {
    "init": (
        "SYNOPSIS\n"
        "    Mark a directory as a reticuli session: create the .reticuli\n"
        "    store and, when --agent names a supported agent, wire its\n"
        "    coding-agent hooks into the project. Idempotent."
    ),
    "run": (
        "SYNOPSIS\n"
        "    Run one literal shell command inside a workspace and return its\n"
        "    exit code UNCHANGED -- a transparent boundary, so a session can\n"
        "    use it as a predicate. When the workspace is already a session,\n"
        "    the call is appended to its draft trace."
    ),
    "status": (
        "SYNOPSIS\n"
        "    A pure view: reads and reports, never executes a gate. Shows a\n"
        "    session's authoring triad (observed/declared/unresolved) or a\n"
        "    claim's identity, audit receipt, and the ladder's next rung."
    ),
    "pack": (
        "SYNOPSIS\n"
        "    One boundary, three sources: a session's own trace (--accept),\n"
        "    a declared recipe already on disk (zero flags), or an explicit\n"
        "    --gate/--pytest/--environment declaration."
    ),
    "pull": (
        "SYNOPSIS\n"
        "    Add another claim as a dependency, materializing it under the\n"
        "    current workspace's registry."
    ),
    "export": (
        "SYNOPSIS\n"
        "    Write a deterministic tar of a claim's declared bytes. --blind\n"
        "    withholds every generated output -- the room a rebuilder\n"
        "    regrows into. `-o -` writes the archive to stdout."
    ),
    "import": (
        "SYNOPSIS\n"
        "    Restore a claim archive into a directory and verify on import:\n"
        "    identity and verdicts re-verify from the received bytes alone.\n"
        "    `-` reads the archive from stdin."
    ),
    "verify": (
        "SYNOPSIS\n"
        "    Recompute the root from the bytes present and compare it with\n"
        "    the sealed manifest. Identity only.\n"
        "    Does not execute acceptance criteria -- audit does that."
    ),
    "audit": (
        "SYNOPSIS\n"
        "    Re-execute every gate, cold and sandboxed, composed claims\n"
        "    included by default (--shallow opts out). The only verb that\n"
        "    re-earns a verdict; strict by default, --no-strict opts down."
    ),
    "assess": (
        "SYNOPSIS\n"
        "    Measure specification strength: mutation kill rate over a\n"
        "    claim's generated Python outputs."
    ),
    "rebuild": (
        "SYNOPSIS\n"
        "    Regrow the generated outputs until the gates pass; generated\n"
        "    sources are withheld from the room a producer sees, and the\n"
        "    ledger records what it cost. --producer openai and --producer\n"
        "    anthropic name the shipped producers, preflighted for a\n"
        "    credential before anything is spent; a producer is any program\n"
        "    that can read the room and write files."
    ),
    "crosscheck": (
        "SYNOPSIS\n"
        "    The three-machine test: compare independent realizations. A\n"
        "    leg is a claim directory or a signed record. With two legs,\n"
        "    the second is auto-materialized as a transfer copy of the\n"
        "    first (M2); --mutants holds a declared mutation floor to a\n"
        "    redo."
    ),
    "record": (
        "SYNOPSIS\n"
        "    With -o, emit and sign the portable record document\n"
        "    (spec/record.md). Without -o, attest a build's root and build\n"
        "    digest in place. --check verifies what is already there."
    ),
    "sign": (
        "SYNOPSIS\n"
        "    A human signs the root; never an agent's act. With no flags,\n"
        "    shows the review packet a signer would stand behind. --check\n"
        "    verifies an authorization already on disk."
    ),
    "hook": (
        "SYNOPSIS\n"
        "    Plumbing: record one coding-agent hook event, read as JSON on\n"
        "    stdin, into the session's draft trace. Never blocks the agent."
    ),
    "help": (
        "SYNOPSIS\n"
        "    Show detailed help for one command, or (-a) list every command\n"
        "    this parser knows, including retired spellings."
    ),
    "completion": (
        "SYNOPSIS\n"
        "    Print a shell completion script, generated from the grammar\n"
        "    itself."
    ),
    "environment": (
        "Environment variables this tool reads:\n\n"
        "    RETICULI_KEY        default signing key path for --sign\n"
        "    RETICULI_SIGNERS    allowed_signers anchor for --check\n"
        "    RETICULI_COLOR      auto|always|never (default: auto)\n"
        "    RETICULI_GATE_TIMEOUT  host ceiling on a gate's wall-clock bound\n"
        "    RETICULI_JAILED     internal: already inside a sandbox\n"
    ),
}


def _print_help(verb: str) -> None:
    print(_USAGE.get(verb, f"usage: ret {verb}"))
    body = _FULL_HELP.get(verb)
    if body:
        print()
        print(f"ret {verb}\n")
        print(body)


def _print_help_all() -> None:
    for v in verbs():
        print(f"{v:<12} {_VERB_SUMMARY.get(v, '')}")
    print()
    print("retired (no longer accepted):")
    for name in sorted(_RETIRED_FOLD):
        print(f"  {name:<10} {_RETIRED_FOLD[name]}")


# ==== tiny manual argv parsing -- no argparse grammar to fight =============

def _take_flag(args, *names):
    found, out = False, []
    for a in args:
        if a in names:
            found = True
        else:
            out.append(a)
    return found, out


def _take_value(args, *names):
    value, out = None, []
    i = 0
    while i < len(args):
        a = args[i]
        if a in names and i + 1 < len(args):
            value = args[i + 1]
            i += 2
            continue
        matched = False
        for n in names:
            if a.startswith(n + "="):
                value = a[len(n) + 1:]
                matched = True
                break
        if matched:
            i += 1
            continue
        out.append(a)
        i += 1
    return value, out


# ==== the --json envelope, and the one-voice refusal lines ==================

def _envelope(cmd: str, data, ok: bool, status: str, as_json: bool, root=None) -> None:
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if as_json:
        doc = {"command": cmd, "ok": ok, "status": status, "root": root, "data": data}
        print(json.dumps(doc, sort_keys=True))


def _refuse(cmd: str, fact: str, as_json: bool, code: int = 1) -> int:
    """The verb RAN but refused: exit 1. Under --json, the envelope still
    speaks (ok false, status error, root null, the fact under data.error)
    with an EMPTY stderr; otherwise a plain `ret: <verb>: <fact>` line."""
    if as_json:
        doc = {"command": cmd, "ok": False, "status": "error", "root": None,
               "data": {"error": fact}}
        print(json.dumps(doc, sort_keys=True))
    else:
        sys.stderr.write(f"ret: {cmd}: {fact}\n")
    return code


def _invalid(cmd: str, fact: str) -> int:
    """The INVOCATION itself was malformed: exit 2, a plain stderr line,
    never an envelope -- even if --json was requested."""
    sys.stderr.write(f"ret: {cmd}: {fact}\n")
    return 2


# ==== color: RETICULI_COLOR, never a --color flag ===========================

def _use_color() -> bool:
    mode = os.environ.get("RETICULI_COLOR", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _paint(text: str, code: str) -> str:
    return f"\x1b[{code}m{text}\x1b[0m"


def _short(h):
    return h[:8] if isinstance(h, str) else "-"


def _fmt_date(ts) -> str:
    if not ts:
        return "unknown"
    try:
        import datetime
        return datetime.datetime.utcfromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return "unknown"


# ==== init, run (reuse the existing session/handlers layer) ================

_GITIGNORE_LINES = (".reticuli/ledger.jsonl\n", ".reticuli/room/\n")


def _ensure_gitignore(path: str) -> None:
    """`init` is git-native: the ledger (host-local bookkeeping, never
    identity-bearing) and the gate's scratch room are not source."""
    gi_path = os.path.join(path, ".gitignore")
    existing = ""
    if os.path.isfile(gi_path):
        with open(gi_path, encoding="utf-8") as f:
            existing = f.read()
    missing = [line for line in _GITIGNORE_LINES if line.strip() not in existing]
    if missing:
        with open(gi_path, "a", encoding="utf-8") as f:
            f.writelines(missing)


def _cmd_init(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("init")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    no_agent, rest = _take_flag(rest, "--no-agent")
    agent, rest = _take_value(rest, "--agent")
    path = rest[0] if rest else "."

    if agent is not None and agent not in ("claude",):
        return _invalid("init", f"unsupported agent: {agent!r} (known: claude)")

    result = _handlers.init(path, no_agent=no_agent)
    _ensure_gitignore(result.get("path") or path)
    _envelope("init", result, True, "initialized", as_json)
    if not as_json:
        print(f"initialized {result.get('path')}")
        if verbose:
            for name in result.get("created", []):
                print(f"  created: {name}")
    return 0


def _cmd_run(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("run")
        return 0
    _verbose, rest = _take_flag(rest, "-v", "--verbose")
    _as_json, rest = _take_flag(rest, "--json")
    ws, rest = _take_value(rest, "-C", "--workspace")
    if not rest:
        return _invalid("run", "a command is required")
    cmd = rest[0]
    return _handlers.run(cmd, ws=ws or ".")


# ==== the agent hook (plumbing) ==============================================

def _dispatch_hook(rest):
    ws_override, _rest = _take_value(rest, "-C", "--workspace")
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = None
    if isinstance(payload, dict):
        ws = ws_override or payload.get("cwd")
        if ws_override:
            payload = dict(payload, cwd=ws_override)
        transcript = payload.get("transcript_path")
        if transcript and ws and os.path.isdir(os.path.join(ws, ".reticuli")):
            try:
                entry = {"event": "session", "transcript": transcript,
                         "ts": time.time(), "via": "hook"}
                path = os.path.join(ws, ".reticuli", "draft.jsonl")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, sort_keys=True) + "\n")
            except Exception:
                pass
        try:
            _hooks.event(payload)
        except Exception:
            pass
    return 0


# ==== the discovery bill: reported testimony, never fed into cost() ========

def _collect_discovery(ws: str):
    """Scan a session's draft trace for `session` events naming a harness
    transcript, and sum the assistant usage it reports -- the discovery
    cost, carried as testimony and never fed into the cost band."""
    path = os.path.join(ws, ".reticuli", "draft.jsonl")
    if not os.path.isfile(path):
        return None
    total = 0
    found = False
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("event") != "session":
                    continue
                transcript = event.get("transcript")
                if not transcript or not os.path.isfile(transcript):
                    continue
                with open(transcript, encoding="utf-8") as tf:
                    for tline in tf:
                        tline = tline.strip()
                        if not tline:
                            continue
                        try:
                            rec = json.loads(tline)
                        except ValueError:
                            continue
                        if rec.get("type") != "assistant":
                            continue
                        usage = (rec.get("message") or {}).get("usage") or {}
                        in_tok = usage.get("input_tokens") or 0
                        out_tok = usage.get("output_tokens") or 0
                        if isinstance(in_tok, (int, float)) and isinstance(out_tok, (int, float)):
                            total += in_tok + out_tok
                            found = True
    except OSError:
        return None
    return {"tokens": total} if found else None


def _discovery_summary(claim_dir: str):
    try:
        events = kernel.ledger_events(claim_dir)
    except Exception:
        return None
    for event in reversed(events):
        if event.get("event") == "discovery":
            return event.get("report")
    return None


# ==== pack: session / declared / flags ======================================

def _pack_session(ws: str, outputs: list, dest: str, name: str) -> dict:
    """`authoring.build_claim`, with one workaround: a traced write whose
    file was later deleted must not crash the copy -- the session's trace
    is transiently filtered (and restored afterward) to drop write events
    for paths no longer present on disk."""
    trace_path = os.path.join(ws, _authoring.TRACE)
    backup = None
    if os.path.isfile(trace_path):
        with open(trace_path, encoding="utf-8") as f:
            original = f.read()
        filtered, changed = [], False
        for line in original.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                filtered.append(line)
                continue
            if event.get("event") == "write":
                p = event.get("path")
                if p and not os.path.isfile(os.path.join(ws, p)):
                    changed = True
                    continue
            filtered.append(line)
        if changed:
            backup = original
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write("\n".join(filtered) + ("\n" if filtered else ""))
    try:
        return _authoring.build_claim(ws, outputs, dest, name=name)
    finally:
        if backup is not None:
            with open(trace_path, "w", encoding="utf-8") as f:
                f.write(backup)


def _cmd_pack(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("pack")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    force, rest = _take_flag(rest, "--force")
    pytest_, rest = _take_flag(rest, "--pytest")
    accept, rest = _take_value(rest, "--accept")
    out_dest, rest = _take_value(rest, "-o", "--output")
    name, rest = _take_value(rest, "--name")
    inputs_manifest, rest = _take_value(rest, "--inputs-manifest")
    environment, rest = _take_value(rest, "--environment")
    gate, rest = _take_value(rest, "--gate")
    generated_patterns, rest = _take_value(rest, "--generated")
    path = rest[0] if rest else "."

    if accept:
        if not out_dest:
            return _invalid("pack", "pack --accept needs -o naming the claim destination")
        if not name:
            return _invalid("pack", "pack --accept needs --name naming the claim")

        if os.path.isdir(out_dest) and os.listdir(out_dest):
            if not force:
                return _invalid("pack", f"refusing to pack into a non-empty directory without --force: {out_dest!r}")
            shutil.rmtree(out_dest)

        discovery = _collect_discovery(path)
        try:
            result = _pack_session(path, [accept], out_dest, name)
        except kernel.ClaimError as exc:
            return _refuse("pack", str(exc), as_json)
        if discovery:
            try:
                kernel.ledger(out_dest, {"event": "discovery", "report": discovery})
            except Exception:
                pass
        data = {"root": result.get("root"), "name": result.get("name")}
        _envelope("pack", data, True, "packed", as_json)
        if not as_json:
            print(f"packed {out_dest}")
        return 0

    has_recipe = (os.path.isfile(os.path.join(path, kernel.RECIPE))
                  or os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE)))

    if not has_recipe and not (gate or pytest_):
        return _refuse("pack", "nothing to pack", as_json)

    if not has_recipe:
        # --- flags mode: pack a fresh project directly -----------------
        if not name:
            return _invalid("pack", "pack needs --name naming the claim")
        gate_cmd = gate or ("pytest" if pytest_ else None)
        if not gate_cmd:
            return _invalid("pack", "pack needs --gate (or --pytest) naming the gate command")
        patterns = [generated_patterns] if generated_patterns else []
        try:
            result = _pack.pack(path, name, generated=patterns, gate=gate_cmd,
                                 gate_output=out_dest or "OK",
                                 inputs_manifest=inputs_manifest,
                                 environment=environment)
        except kernel.ClaimError as exc:
            return _refuse("pack", str(exc), as_json)
        _envelope("pack", result, True, "packed", as_json)
        if not as_json:
            print(f"packed {path}")
        return 0

    # --- declared mode: reticuli.toml IS the declaration ------------------
    try:
        parsed = kernel.load_recipe(path)
        for step in parsed.get("step", []):
            if step.get("kind") != "gate":
                continue
            res = kernel.run_gate(step["run"], path, parsed)
            if res["status"] != "ok":
                raise kernel.ClaimError(f"the gate did not pass: {res['status']}")
        manifest = kernel.seal(path)
    except kernel.ClaimError as exc:
        return _refuse("pack", str(exc), as_json)
    data = {"root": manifest.get("root"), "name": manifest.get("name")}
    _envelope("pack", data, True, "packed", as_json)
    if not as_json:
        print(f"packed {path}")
    return 0


# ==== verify =================================================================

def _broken_reasons(path: str):
    try:
        manifest = kernel.read_manifest(path)
    except kernel.ClaimError:
        return []
    sealed_parts = manifest.get("parts")
    if not isinstance(sealed_parts, dict):
        return []
    changed = []
    for key, old_hash in sealed_parts.items():
        if key in ("digest", "recipe"):
            continue
        _, _, rel = key.partition(":")
        full = os.path.join(path, rel)
        try:
            new_hash = kernel._hash_file(full)
        except Exception:
            changed.append(rel)
            continue
        if new_hash != old_hash:
            changed.append(rel)
    return sorted(set(changed))


def _cmd_verify(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("verify")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    path = rest[0] if rest else "."

    try:
        result = kernel.verify(path)
    except kernel.ClaimError as exc:
        return _refuse("verify", str(exc), as_json)

    ok = result["ok"]
    try:
        phase = kernel.phase(path) if ok else None
    except kernel.ClaimError:
        phase = None
    status = "fresh" if ok else "broken"
    data = {"name": result.get("name"), "root": result.get("root"),
            "recomputed": result.get("recomputed"), "phase": phase, "ok": ok}
    _envelope("verify", data, ok, status, as_json)

    if as_json:
        return 0 if ok else 1
    if ok:
        if verbose:
            print("[verify]")
            print(f"  name = {json.dumps(data['name'])}")
            print(f'  root = "{data["root"]}"')
            print(f"  phase = {phase}")
        return 0
    changed = _broken_reasons(path)
    named = ", ".join(changed) if changed else "(unknown)"
    sys.stderr.write(f"ret: verify: broken ({named} changed since sealing)\n")
    sys.stderr.write("hint: restore the original bytes, or re-run 'ret rebuild'\n")
    return 1


# ==== audit ===================================================================

def _audit_accepts_strict() -> bool:
    try:
        sig = inspect.signature(kernel.audit)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if any(p.kind == p.VAR_KEYWORD for p in params.values()):
        return True
    return "strict" in params


def _call_audit(path, strict):
    kwargs = {}
    if _audit_accepts_strict():
        kwargs["strict"] = strict
    return kernel.audit(path, **kwargs)


def _gate_status_word(result: dict) -> str:
    if result.get("ok"):
        return "earned"
    gates = result.get("gates") or []
    words = {g.get("status") for g in gates if g.get("status") and g.get("status") != "ok"}
    for w in ("environment", "timeout", "failed", "mismatch"):
        if w in words:
            return w
    return result.get("verdict") or "mismatch"


def _cmd_audit(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("audit")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    shallow, rest = _take_flag(rest, "--shallow")
    no_strict, rest = _take_flag(rest, "--no-strict")
    record_dest, rest = _take_value(rest, "--record")
    mutants, rest = _take_value(rest, "--mutants")
    path = rest[0] if rest else "."
    strict = not no_strict

    start = time.time()
    try:
        base = _call_audit(path, strict)
    except kernel.ClaimError as exc:
        return _refuse("audit", str(exc), as_json)
    except Exception:
        return _refuse("audit", "audit could not complete", as_json)

    ok = bool(base.get("ok"))
    layers = []
    if not shallow:
        try:
            deep = _registry.audit_deep(path)
            layers = deep.get("layers") or []
            ok = ok and bool(deep.get("ok", True))
        except kernel.ClaimError:
            pass
    elapsed = time.time() - start

    result = dict(base, ok=ok, layers=layers)
    try:
        manifest = kernel.read_manifest(path)
        result["name"] = manifest.get("name")
    except kernel.ClaimError:
        result["name"] = None
    result["recomputed"] = result.get("root")
    result["elapsed"] = elapsed

    mscore = None
    if mutants:
        try:
            mscore = kernel.mutation_score(path, max_mutants=int(mutants))
        except (kernel.ClaimError, ValueError):
            mscore = None

    if ok:
        try:
            kernel.ledger(path, {"event": "audit", "ts": time.time()})
        except Exception:
            pass

    status = "earned" if ok else _gate_status_word(result)
    _envelope("audit", result, ok, status, as_json)

    if record_dest:
        try:
            doc = _record.emit(path)
            _record.write(doc, record_dest)
        except kernel.ClaimError:
            pass

    if as_json:
        return 0 if ok else 1

    if verbose:
        print("[audit]")
        for g in result.get("gates", []):
            word = "reproduced" if g.get("status") == "ok" else g.get("status")
            print(f"  {g.get('output')}: {word} (quarantine={g.get('quarantine')})")
        if mscore is not None:
            print("[mutation_score]")
            print(f"  rate = {mscore['rate']}")
            print(f"  mutants = {mscore['mutants']}")
    elif not ok:
        sys.stderr.write(f"ret: audit: {status}\n")
    return 0 if ok else 1


# ==== assess ==================================================================

def _cmd_assess(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("assess")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    mutants, rest = _take_value(rest, "--mutants")
    path = rest[0] if rest else "."

    try:
        result = _assess.assess(path, mutants=int(mutants) if mutants else None)
        parsed = kernel.load_recipe(path)
    except (kernel.ClaimError, ValueError) as exc:
        return _refuse("assess", str(exc), as_json)

    gate_outputs = [s["output"] for s in parsed.get("step", []) if s.get("kind") == "gate"]
    declared = parsed.get("claim", {}).get("mutation_floor")
    data = dict(result, declared=declared, gate=gate_outputs)
    try:
        kernel.ledger(path, {"event": "assess", "ts": time.time()})
    except Exception:
        pass
    _envelope("assess", data, True, "measured", as_json)
    if not as_json and verbose:
        print("[assess]")
        print(f"  mutants = {result['mutants']}")
        print(f"  rate = {result['rate']}")
    return 0


# ==== rebuild =================================================================

def _cmd_rebuild(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("rebuild")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    without_guidance, rest = _take_flag(rest, "--without-guidance")
    producer, rest = _take_value(rest, "--producer")
    into, rest = _take_value(rest, "-o", "--into")
    path = rest[0] if rest else "."

    if not producer:
        return _invalid("rebuild", "rebuild needs --producer naming the producer")
    if not into:
        into = tempfile.mkdtemp(prefix="reticuli-rebuild-")

    if producer in _NAMED_PRODUCERS:
        cred = _NAMED_PRODUCERS[producer]["credential"]
        if cred not in os.environ:
            return _refuse("rebuild", f"the {producer} producer needs {cred} set in the environment", as_json)
        cmd = producer
    else:
        cmd = producer

    try:
        result = kernel.rebuild(path, cmd, into, guidance=not without_guidance)
    except kernel.ClaimError as exc:
        return _refuse("rebuild", str(exc), as_json)

    data = dict(result, into=into)
    _envelope("rebuild", data, True, "rebuilt", as_json)
    if not as_json:
        print(f"rebuilt {into}")
        if verbose:
            for g in result.get("gates", []):
                print(f"  {g.get('output')}: {g.get('status')}")
    return 0


# ==== crosscheck ==============================================================

def _materialize_m2(m1: str) -> str:
    tar_path = tempfile.mktemp(suffix=".tar")
    _transfer.export(m1, tar_path)
    tmp_dir = tempfile.mkdtemp(prefix="reticuli-m2-")
    shutil.rmtree(tmp_dir)
    try:
        _transfer.import_(tar_path, tmp_dir)
    finally:
        try:
            os.remove(tar_path)
        except OSError:
            pass
    return tmp_dir


def _cmd_crosscheck(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("crosscheck")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    mutants, rest = _take_value(rest, "--mutants")
    legs = rest

    if len(legs) < 2 or len(legs) > 3:
        return _invalid("crosscheck", "requires 2 or 3 machine legs; one realization is not a comparison")

    m2_materialized = False
    tmp_m2 = None
    if len(legs) == 2:
        m1, m3 = legs
        try:
            tmp_m2 = _materialize_m2(m1)
        except kernel.ClaimError as exc:
            return _refuse("crosscheck", str(exc), as_json)
        m2 = tmp_m2
        m2_materialized = True
    else:
        m1, m2, m3 = legs

    try:
        result = _registry.crosscheck_deep(m1, m2, m3, mutants=int(mutants) if mutants else None)
    except kernel.ClaimError as exc:
        if tmp_m2:
            shutil.rmtree(tmp_m2, ignore_errors=True)
        return _refuse("crosscheck", str(exc), as_json)

    data = dict(result, m2_materialized=m2_materialized)
    ok = result["satisfied"]
    status = result["verdict"]
    _envelope("crosscheck", data, ok, status, as_json)

    if not as_json:
        if not ok:
            reasons = result.get("rejected") or result.get("incomplete") or []
            sys.stderr.write(f"ret: crosscheck: {status} ({', '.join(reasons)})\n")
        elif verbose:
            print("[crosscheck]")
            print(f"  satisfied = {str(result['satisfied']).lower()}")
            print(f"  verdict = {result['verdict']}")
            for role, r in (result.get("roots") or {}).items():
                print(f"  {role} = {r}")
            print("[cost]")
            cost_info = result.get("cost") or {}
            print(f"  comparable = {cost_info.get('comparable')}")
            for unit, info in (cost_info.get("envelope") or {}).items():
                print(f"  envelope.{unit} = {info}")
            discovery = _discovery_summary(m1) if os.path.isdir(m1) else None
            if discovery:
                print(f"  discovery: {discovery.get('tokens')} tokens "
                      "(reported testimony, excluded from the cost band)")

    if tmp_m2:
        shutil.rmtree(tmp_m2, ignore_errors=True)
    return 0 if ok else 1


# ==== export / import / pull =================================================

def _cmd_export(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("export")
        return 0
    _verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    blind, rest = _take_flag(rest, "--blind")
    out, rest = _take_value(rest, "-o", "--out", "--output")
    path = rest[0] if rest else "."
    tar_dest = out
    if tar_dest is None and len(rest) > 1:
        tar_dest = rest[1]
    if tar_dest is None:
        tar_dest = os.path.basename(os.path.abspath(path).rstrip(os.sep)) + ".tar"

    to_stdout = tar_dest == "-"
    actual = tempfile.mktemp(suffix=".tar") if to_stdout else tar_dest
    try:
        _transfer.export(path, actual, blind=blind)
    except kernel.ClaimError as exc:
        return _refuse("export", str(exc), as_json)

    if to_stdout:
        with open(actual, "rb") as f:
            data = f.read()
        try:
            os.remove(actual)
        except OSError:
            pass
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
        return 0

    _envelope("export", {"path": actual}, True, "exported", as_json)
    return 0


def _cmd_import(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("import")
        return 0
    _verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    into, rest = _take_value(rest, "--into")
    if not rest:
        return _invalid("import", "an archive path is required")
    archive = rest[0]
    dest = into or (rest[1] if len(rest) > 1 else ".")

    tmp = None
    actual = archive
    if archive == "-":
        data = sys.stdin.buffer.read()
        fd, tmp = tempfile.mkstemp(suffix=".tar")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        actual = tmp
    elif not os.path.isfile(archive):
        return _refuse("import", f"no archive at {archive!r}", as_json)

    try:
        result = _transfer.import_(actual, dest)
    except kernel.ClaimError as exc:
        return _refuse("import", str(exc), as_json)
    finally:
        if tmp:
            try:
                os.remove(tmp)
            except OSError:
                pass

    _envelope("import", result, True, "imported", as_json)
    return 0


def _cmd_pull(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("pull")
        return 0
    _verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    ws, rest = _take_value(rest, "-C", "--workspace")
    if not rest:
        return _invalid("pull", "a component path is required")
    component = rest[0]
    target = ws or os.getcwd()
    try:
        result = _registry.pull(component, target)
    except kernel.ClaimError as exc:
        return _refuse("pull", str(exc), as_json)
    _envelope("pull", result, True, "pulled", as_json)
    if not as_json:
        print(f"pulled {result.get('name')}")
    return 0


# ==== record / sign: the local signer anchor ================================

def _anchor_for(path: str):
    env = os.environ.get("RETICULI_SIGNERS")
    if env:
        return env
    local = os.path.join(path, ".reticuli", "allowed_signers")
    return local if os.path.isfile(local) else None


def _register_anchor(claim_dir: str, identity: str, key_path: str) -> None:
    pub_path = key_path + ".pub"
    if not identity or not os.path.isfile(pub_path):
        return
    try:
        with open(pub_path, encoding="utf-8") as f:
            pub_line = f.read().strip()
    except OSError:
        return
    parts = pub_line.split()
    if len(parts) < 2:
        return
    keytype, keydata = parts[0], parts[1]
    anchor_path = os.path.join(claim_dir, ".reticuli", "allowed_signers")
    line = f"{identity} {keytype} {keydata}\n"
    os.makedirs(os.path.dirname(anchor_path), exist_ok=True)
    existing = ""
    if os.path.isfile(anchor_path):
        with open(anchor_path, encoding="utf-8") as f:
            existing = f.read()
    if line not in existing:
        with open(anchor_path, "a", encoding="utf-8") as f:
            f.write(line)


def _cmd_record(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("record")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    check_, rest = _take_flag(rest, "--check")
    sign_, rest = _take_flag(rest, "--sign")
    key, rest = _take_value(rest, "--key")
    as_, rest = _take_value(rest, "--as")
    out, rest = _take_value(rest, "-o", "--out", "--output")
    path = rest[0] if rest else "."

    if check_:
        try:
            result = _attest.check(path, signers=_anchor_for(path))
        except kernel.ClaimError as exc:
            return _refuse("record", str(exc), as_json)
        ok = result["ok"]
        _envelope("record", result, ok, "checked" if ok else "unsigned", as_json)
        if not as_json and verbose:
            for a in result.get("attestations", []):
                print(f"  {a.get('identity') or 'unknown'}: {a.get('verdict')}")
        return 0 if ok else 1

    if out:
        signing_key = key
        if sign_ and not signing_key:
            signing_key = os.environ.get("RETICULI_KEY")
            if not signing_key:
                return _refuse("record", "RETICULI_KEY is not set; --sign needs a configured identity", as_json)
        try:
            doc = _record.emit(path)
        except kernel.ClaimError as exc:
            return _refuse("record", str(exc), as_json)
        _record.write(doc, out)
        if signing_key:
            try:
                _record.sign(out, signing_key)
            except Exception as exc:
                return _refuse("record", f"could not sign record: {exc}", as_json)
            if as_:
                _register_anchor(path, as_, signing_key)
        data = {"digest": _record.digest(doc), "record": doc}
        _envelope("record", data, True, "recorded", as_json)
        return 0

    if not key or not as_:
        return _invalid("record", "record needs --key and --as (attest in place), -o (emit a record), or --check")
    try:
        result = _attest.attest(path, key, as_)
    except kernel.ClaimError as exc:
        return _refuse("record", str(exc), as_json)
    _register_anchor(path, as_, key)
    _envelope("record", result, True, "attested", as_json)
    return 0


def _cmd_sign(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("sign")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    check_, rest = _take_flag(rest, "--check")
    key, rest = _take_value(rest, "--key")
    as_, rest = _take_value(rest, "--as")
    path = rest[0] if rest else "."

    if check_:
        try:
            result = _attest.sign_check(path, signers=_anchor_for(path))
        except kernel.ClaimError as exc:
            return _refuse("sign", str(exc), as_json)
        ok = result["ok"]
        _envelope("sign", result, ok, "authorized" if ok else "unauthorized", as_json)
        if not as_json and verbose:
            for a in result.get("authorizations", []):
                print(f"  {a.get('identity') or 'unknown'}: {a.get('verdict')}")
        return 0 if ok else 1

    if key:
        if not as_:
            return _invalid("sign", "sign --key needs --as naming the identity")
        try:
            result = _attest.sign(path, key, as_)
        except kernel.ClaimError as exc:
            return _refuse("sign", str(exc), as_json)
        _register_anchor(path, as_, key)
        _envelope("sign", result, True, "authorized", as_json)
        return 0

    try:
        packet = _attest.review_packet(path)
    except kernel.ClaimError as exc:
        return _refuse("sign", str(exc), as_json)
    _envelope("sign", packet, True, "review", as_json)
    if as_json:
        return 0
    if verbose:
        audit_v = packet.get("audit")
        audit_word = audit_v.get("verdict") if isinstance(audit_v, dict) else audit_v
        print("[review]")
        print(f"  root = \"{packet.get('root')}\"")
        print(f"  build_digest = \"{packet.get('build_digest')}\"")
        print(f"  sign_root = \"{packet.get('sign_root')}\"")
        print(f"  audit = {audit_word}")
    else:
        print(f"review: root={_short(packet.get('root'))} sign_root={_short(packet.get('sign_root'))}")
    return 0


# ==== status: the pure view ===================================================

def _read_draft(ws: str) -> list:
    path = os.path.join(ws, ".reticuli", "draft.jsonl")
    events = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        pass
    return events


def _one_hop_imports(ws, pyfile, generated_set):
    found = set()
    path = os.path.join(ws, pyfile)
    if not os.path.isfile(path):
        return found
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return found
    for m in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.MULTILINE):
        candidate = m.group(1) + ".py"
        if candidate in generated_set:
            found.add(candidate)
    return found


def _session_triad(ws: str):
    try:
        recipe = _authoring.propose(ws, [], "status-preview")
    except kernel.ClaimError:
        return None
    generated = sorted({s["output"] for s in recipe.get("step", []) if s.get("kind") == "produce"})
    claim_inputs = sorted(set(recipe.get("claim", {}).get("inputs", [])))
    events = _read_draft(ws)
    bash_cmds = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    combined = " && ".join(bash_cmds)
    direct = kernel.gate_deciders(combined) if combined else []
    generated_set = set(generated)
    covered = {d for d in direct if d in generated_set}
    for dec in list(covered):
        if dec.endswith(".py"):
            covered |= _one_hop_imports(ws, dec, generated_set)
    unresolved = [g for g in generated if g not in covered]
    return {"generated": generated, "inputs": claim_inputs, "unresolved": unresolved,
            "events": events, "combined_cmd": combined}


def _status_session_default(ws, as_json, verbose):
    triad = _session_triad(ws)
    if triad is None:
        data = {"phase": "draft", "observed": 0, "declared": 0, "unresolved": 0}
    else:
        observed = len({e.get("path") for e in triad["events"]
                         if e.get("event") in ("write", "read") and e.get("path")})
        data = {"phase": "draft", "observed": observed, "declared": len(triad["inputs"]),
                "unresolved": len(triad["unresolved"]),
                "unresolved_files": triad["unresolved"]}
    _envelope("status", data, True, "draft", as_json)
    if as_json:
        return 0
    packable = data["unresolved"] == 0
    line = (f"draft  observed={data['observed']}  declared={data['declared']}"
            f"  unresolved={data['unresolved']}")
    if packable:
        line += "  packable"
    else:
        line += "  undeclared: " + ", ".join(data.get("unresolved_files") or [])
    print(line)
    return 0


def _status_session_all(ws) -> str:
    triad = _session_triad(ws)
    header = ("path", "observed", "declared", "evidence")
    if triad is None:
        return "  ".join(header)
    generated_set = set(triad["generated"])
    input_set = set(triad["inputs"])
    events = triad["events"]
    obs = {}
    for e in events:
        kind = e.get("event")
        p = e.get("path")
        if kind in ("write", "read") and p:
            obs.setdefault(p, (kind, e.get("via") or "hook"))
    try:
        tokens = shlex.split(triad["combined_cmd"]) if triad["combined_cmd"] else []
    except ValueError:
        tokens = []
    disk_files = set()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in (".reticuli", ".git", ".claude")]
        rel_root = os.path.relpath(root, ws)
        for name in files:
            rel = name if rel_root == "." else f"{rel_root}/{name}".replace(os.sep, "/")
            disk_files.add(rel)
    all_paths = sorted(set(obs) | generated_set | input_set | disk_files)
    lines = ["  ".join(header)]
    for p in all_paths:
        if p in obs:
            kind, via = obs[p]
        elif p in tokens:
            kind, via = "bash", "gate"
        else:
            kind, via = "-", "-"
        declared = "generated" if p in generated_set else ("input" if p in input_set else "-")
        lines.append(f"{p:<24} {kind:<10} {declared:<12} {via}")
    return "\n".join(lines)


def _status_tree_session(ws) -> str:
    triad = _session_triad(ws)
    lines = ["draft"]
    if triad:
        for p in triad["generated"]:
            lines.append(f"generated  {p}")
        for p in triad["inputs"]:
            lines.append(f"input      {p}")
    return "\n".join(lines)


def _has_ledger_event(path, name) -> bool:
    try:
        return any(e.get("event") == name for e in kernel.ledger_events(path))
    except Exception:
        return False


def _ledger_last_ts(path, name):
    try:
        events = kernel.ledger_events(path)
    except Exception:
        return None
    for e in reversed(events):
        if e.get("event") == name:
            return e.get("ts")
    return None


def _mutation_residue(path):
    mscore_path = os.path.join(path, kernel.STORE, "mutation_score.json")
    if not os.path.isfile(mscore_path):
        return None
    try:
        with open(mscore_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _safe_attest_check(path):
    try:
        return _attest.check(path, signers=_anchor_for(path))
    except Exception:
        return {"ok": False, "attestations": []}


def _safe_sign_check(path):
    try:
        return _attest.sign_check(path, signers=_anchor_for(path))
    except Exception:
        return {"ok": False, "authorizations": []}


def _next_rung(audited, assessed, crosschecked, signed) -> str:
    if not audited:
        return "ret audit"
    if not assessed:
        return "ret assess"
    if not crosschecked:
        return "ret crosscheck"
    if not signed:
        return "ret sign"
    return "ret pack"


def _status_claim_default(path, as_json, verbose):
    try:
        manifest = kernel.read_manifest(path)
        kernel.load_recipe(path)
        vr = kernel.verify(path)
    except kernel.ClaimError as exc:
        return _refuse("status", str(exc), as_json)

    color_on = _use_color()
    name = manifest.get("name")
    root = manifest.get("root")

    if not vr.get("ok"):
        data = {"name": name, "root": root, "phase": "broken", "verified": False,
                 "next": "ret rebuild"}
        _envelope("status", data, True, "claim", as_json)
        if as_json:
            return 0
        line = f"{name}@{_short(root)} (broken) -> restore the original bytes or re-run rebuild"
        if color_on:
            line = _paint(line, "31")
        print(line)
        return 0

    try:
        phase = kernel.phase(path)
    except kernel.ClaimError:
        phase = "sealed"

    audited = _has_ledger_event(path, "audit")
    assessed = _has_ledger_event(path, "assess")
    crosschecked = bool(manifest.get("proof"))
    signed = phase == "signed"
    next_rung = _next_rung(audited, assessed, crosschecked, signed)

    attest_result = _safe_attest_check(path)
    sign_result = _safe_sign_check(path)
    n_statements = len(attest_result.get("attestations", [])) + len(sign_result.get("authorizations", []))
    n_signed = sum(1 for a in sign_result.get("authorizations", []) if a.get("verdict") == "authorized")

    data = {"name": name, "root": root, "phase": phase, "audited": audited,
            "deciding": _mutation_residue(path), "proof": manifest.get("proof"),
            "signatures": [a.get("identity") for a in sign_result.get("authorizations", [])],
            "next": next_rung}
    _envelope("status", data, True, "claim", as_json)
    if as_json:
        return 0

    lines = []
    header = f"{name}@{_short(root)} (identity: fresh, {phase})"
    if color_on:
        header = _paint(header, "32")
    lines.append(header)
    if audited:
        when = _ledger_last_ts(path, "audit")
        lines.append(f"audited: on this machine, {_fmt_date(when)}")
    discovery = _discovery_summary(path)
    if discovery:
        lines.append(f"discovery: {discovery.get('tokens')} tokens "
                      "(reported testimony, excluded from the cost band)")
    if n_statements:
        lines.append(f"{n_statements} statement(s) ({'signed' if n_signed else 'unsigned'})")
    lines.append(f"next: {next_rung}")
    print("\n".join(lines))
    return 0


def _status_claim_all(path) -> str:
    try:
        parsed = kernel.load_recipe(path)
        manifest = kernel.read_manifest(path)
    except kernel.ClaimError as exc:
        return f"ret: status: {exc}"

    fixed, deciding, free, unknown = [], [], [], []
    for p in parsed.get("claim", {}).get("inputs", []):
        fixed.append(p)
    for step in parsed.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_class)
        if cls == "generated":
            free.append(output)
        elif cls == "validated":
            deciding.append(output)
        else:
            fixed.append(output)

    lines = [
        "fixed:    " + (", ".join(fixed) or "(none)"),
        "deciding: " + (", ".join(deciding) or "(none)"),
        "free:     " + (", ".join(free) or "(none)"),
        "unknown:  " + (", ".join(unknown) or "(none)"),
        "",
        "recorded:",
    ]
    try:
        events = kernel.ledger_events(path)
    except Exception:
        events = []
    for event in events:
        if event.get("event") in ("audit", "assess", "discovery"):
            lines.append(f"  {event.get('event')}, {_fmt_date(event.get('ts'))}: a receipt, not a verdict")

    audited = _has_ledger_event(path, "audit")
    assessed = _has_ledger_event(path, "assess")
    crosschecked = bool(manifest.get("proof"))
    try:
        signed = kernel.phase(path) == "signed"
    except kernel.ClaimError:
        signed = False
    lines.append("")
    lines.append(f"next: {_next_rung(audited, assessed, crosschecked, signed)}")
    return "\n".join(lines)


def _status_files(path) -> str:
    try:
        parsed = kernel.load_recipe(path)
    except kernel.ClaimError as exc:
        return f"ret: status: {exc}"
    rows = []
    for p in parsed.get("claim", {}).get("inputs", []):
        rows.append((p, "pinned", ROLE_WORD["pinned"]))
    for step in parsed.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_class)
        rows.append((output, cls, ROLE_WORD.get(cls, cls)))
    return "\n".join(f"{p:<24} {c:<12} {r}" for p, c, r in rows)


def _tree_row(label, path, color_on) -> str:
    if color_on:
        code = "32" if label == "pinned" else "36"
        return _paint(path, code)
    return f"{label:<10} {path}"


def _status_tree_claim(path) -> str:
    try:
        parsed = kernel.load_recipe(path)
        manifest = kernel.read_manifest(path)
    except kernel.ClaimError as exc:
        return f"ret: status: {exc}"
    color_on = _use_color()
    lines = []
    for p in parsed.get("claim", {}).get("inputs", []):
        lines.append(_tree_row("pinned", p, color_on))
    for step in parsed.get("step", []):
        output = step.get("output")
        if not output:
            continue
        default_class = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_class)
        label = "generated" if cls == "generated" else "pinned"
        lines.append(_tree_row(label, output, color_on))
    components = manifest.get("components") or []
    lines.append(f"layers={len(components)}")
    return "\n".join(lines)


def _cmd_status(rest):
    if "-h" in rest or "--help" in rest:
        _print_help("status")
        return 0
    verbose, rest = _take_flag(rest, "-v", "--verbose")
    as_json, rest = _take_flag(rest, "--json")
    all_, rest = _take_flag(rest, "--all")
    files_, rest = _take_flag(rest, "--files")
    tree_, rest = _take_flag(rest, "--tree")
    claims_, rest = _take_flag(rest, "--claims")
    path = rest[0] if rest else "."

    if not os.path.isdir(path):
        return _refuse("status", "no such directory", as_json)

    if claims_:
        print(_statusview._r_claims(path))
        return 0

    is_claim = os.path.isfile(os.path.join(path, kernel.STORE, "manifest.json"))

    if tree_:
        print(_status_tree_claim(path) if is_claim else _status_tree_session(path))
        return 0

    if files_:
        if not is_claim:
            return _refuse("status", "--files applies to a sealed claim", as_json)
        print(_status_files(path))
        return 0

    if all_:
        print(_status_claim_all(path) if is_claim else _status_session_all(path))
        return 0

    if is_claim:
        return _status_claim_default(path, as_json, verbose)
    return _status_session_default(path, as_json, verbose)


# ==== main: top-level routing ================================================

_ROUTES = {
    "init": _cmd_init,
    "run": _cmd_run,
    "status": _cmd_status,
    "pack": _cmd_pack,
    "pull": _cmd_pull,
    "export": _cmd_export,
    "import": _cmd_import,
    "verify": _cmd_verify,
    "audit": _cmd_audit,
    "assess": _cmd_assess,
    "rebuild": _cmd_rebuild,
    "crosscheck": _cmd_crosscheck,
    "record": _cmd_record,
    "sign": _cmd_sign,
}


def _completion(shell: str) -> None:
    names = " ".join(verbs())
    if shell == "zsh":
        print(
            "#compdef ret\n"
            f"_ret() {{ compadd {names}; }}\n"
            "compdef _ret ret\n"
        )
        return
    print(
        "_ret_complete() {\n"
        "    local cur\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
        "}\n"
        "complete -F _ret_complete ret"
    )


def _cmd_help(rest):
    all_, rest = _take_flag(rest, "-a", "--all")
    if all_ or not rest:
        _print_help_all()
        return 0
    topic = rest[0]
    if topic in _FULL_HELP:
        print(f"ret {topic}\n")
        print(_FULL_HELP[topic])
        return 0
    if topic in _RETIRED_FOLD:
        print(f"ret: {topic}: retired; {_RETIRED_FOLD[topic]}")
        return 0
    sys.stderr.write(f"ret: unknown command {topic!r}; see 'ret help -a'\n")
    return 1


def _cmd_completion(rest):
    shell = "bash"
    for a in rest:
        if a in ("bash", "zsh"):
            shell = a
    _completion(shell)
    return 0


def _suggest(verb: str):
    matches = difflib.get_close_matches(verb, list(PORCELAIN) + list(PLUMBING), n=1)
    return matches[0] if matches else None


def _dispatch(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(_TOP_HELP)
        return 0
    if argv[0] == "--version":
        print(f"ret {VERSION}")
        return 0

    verb, rest = argv[0], argv[1:]

    if verb in RETIRED:
        sys.stderr.write(f"ret: {verb}: refused; this spelling is retired "
                          f"({_RETIRED_FOLD.get(verb, 'see ret help -a')})\n")
        return 2

    if verb == "hook":
        return _dispatch_hook(rest)
    if verb == "help":
        return _cmd_help(rest)
    if verb == "completion":
        return _cmd_completion(rest)

    fn = _ROUTES.get(verb)
    if fn is None:
        suggestion = _suggest(verb)
        msg = f"ret: '{verb}' is not a ret command"
        if suggestion:
            msg += f"; did you mean '{suggestion}'?"
        sys.stderr.write(msg + "\n")
        return 2

    try:
        return fn(rest)
    except kernel.ClaimError as exc:
        return _refuse(verb, str(exc), "--json" in rest)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 1)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        return _dispatch(argv)
    except Exception as exc:  # never let a raw traceback reach the user
        sys.stderr.write(f"ret: error: {exc}\n")
        return 1

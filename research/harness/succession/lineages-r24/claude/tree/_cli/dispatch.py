"""reticuli._cli.dispatch: the verb implementations (spec/layers.md "surface";
checks/surface_check.py is this module's definition, by way of cli.py).

Each `do_<verb>` function takes the parsed argparse.Namespace for that verb
and returns a process exit code. A `kernel.ClaimError` raised while loading
or computing a claim's state is the one refusal every handler converts the
same way (`_claim_error_envelope_or_err`): under `--json` it is the stable
envelope with `status: "error"` and the fact under `data.error`; otherwise
it is the one-voice stderr line `ret: <verb>: <fact>`. Beyond that boundary,
each verb's own success/failure vocabulary is its own (`verify` says
`fresh`/`mismatch`; `audit` says `earned`/`broken`/a gate's own failure
class) -- the vocabulary is normative (spec/verification.md) and never
blurred between verbs.

`audit` is strict by default: `kernel.audit` is wrapped here, once, with an
isolating `strict` parameter (an isolated copy of the claim is judged, so a
claim's gates never see a stray file that happens to share its directory);
`--no-strict` opts down to judging in place. The wrapper is installed at
import time, so every caller of the public `kernel.audit` -- not just this
module's own dispatch -- gets the strict behavior as the default.
"""
import difflib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from reticuli import (
    _util,
    assess as assess_mod,
    attest,
    authoring,
    hooks,
    kernel,
    pack as pack_mod,
    record,
    registry,
    render,
    transfer,
)

# ---------------------------------------------------------------------------
# small shared primitives
# ---------------------------------------------------------------------------

BANNED_GLYPHS = ("■", "✗", "⇐", "…", "·")

_PAINT_CODES = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "blue": "34"}


def _color_enabled() -> bool:
    mode = os.environ.get("RETICULI_COLOR", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text: str, color, enabled: bool) -> str:
    if not enabled or not color:
        return text
    code = _PAINT_CODES.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _err(cmd: str, fact: str) -> None:
    print(f"ret: {cmd}: {fact}", file=sys.stderr)


def _short(root) -> str:
    return render.short(root) if root else ""


def _read_json_silent(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _claim_error_envelope_or_err(cmd: str, args, e) -> int:
    if getattr(args, "json", False):
        print(json.dumps(
            {"command": cmd, "ok": False, "status": "error", "root": None,
             "data": {"error": str(e)}}, sort_keys=True))
    else:
        _err(cmd, str(e))
    return 1


def _envelope(cmd: str, ok: bool, status: str, root, data) -> None:
    print(json.dumps(
        {"command": cmd, "ok": bool(ok), "status": status, "root": root, "data": data},
        sort_keys=True))


def _parse_envelope_flags(items) -> dict:
    out = {}
    for item in items or []:
        unit, _, value = item.partition("=")
        if unit and value:
            out[unit] = float(value)
    return out


# ---------------------------------------------------------------------------
# audit: strict-by-default wrapper installed onto the public kernel surface
# ---------------------------------------------------------------------------

_real_kernel_audit = kernel.audit


def _strict_audit(d, produce_from=None, strict=True):
    if not strict:
        return _real_kernel_audit(d, produce_from=produce_from)
    if not os.path.isdir(d):
        raise kernel.ClaimError(f"no such directory: {d!r}")
    tmp = tempfile.mkdtemp(prefix="reticuli-strict-")
    try:
        shutil.copytree(d, tmp, dirs_exist_ok=True, symlinks=True)
        for base, dirs, _files in os.walk(tmp):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(base, "__pycache__"), ignore_errors=True)
        return _real_kernel_audit(tmp, produce_from=produce_from)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


kernel.audit = _strict_audit


def _audit_status_word(result) -> str:
    if result.get("ok"):
        return "earned"
    if result.get("verdict") == "mismatch":
        return "broken"
    if result.get("environment"):
        return "environment"
    bad = {g.get("status") for g in result.get("gates", []) if g.get("status") != "ok"}
    return next(iter(bad), "failed")


def _write_audit_receipt(d) -> None:
    try:
        store = os.path.join(d, kernel.STORE)
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, "audit-receipt.json"), "w", encoding="utf-8") as f:
            json.dump({"when": _util.stamp(), "machine": platform.machine(),
                       "platform": sys.platform}, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# producers: a named shortcut preflights its credential before anything spends
# ---------------------------------------------------------------------------

_PRODUCER_PASSTHROUGH = ("OPENAI_BASE_URL", "RETICULI_PRICE", "RETICULI_AGENT_TURNS")

_PRODUCERS = {
    "codex": {"command": "codex exec --full-auto --skip-git-repo-check",
              "credential": "OPENAI_API_KEY"},
    "claude": {"command": "claude -p --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
    "openai": {"command": "codex exec --full-auto --skip-git-repo-check",
               "credential": "OPENAI_API_KEY"},
}


def _expand_producer(name):
    info = _PRODUCERS.get(name)
    if info is not None:
        credential = info["credential"]
        if not os.environ.get(credential):
            raise kernel.ClaimError(
                f"the {name} producer needs {credential} set in the environment")
        command = info["command"]
    else:
        command = name
    env = {k: os.environ[k] for k in _PRODUCER_PASSTHROUGH if k in os.environ}
    return command, env


# ---------------------------------------------------------------------------
# init: mark a workspace, wire the agent handshake
# ---------------------------------------------------------------------------

_SUPPORTED_AGENTS = ("claude",)


def do_init(args) -> int:
    ws = args.dir
    agent = getattr(args, "agent", None)
    no_agent = getattr(args, "no_agent", False)
    if agent is not None and agent not in _SUPPORTED_AGENTS:
        _err("init", f"unsupported agent: {agent!r}")
        return 2

    os.makedirs(ws, exist_ok=True)
    os.makedirs(os.path.join(ws, kernel.STORE), exist_ok=True)

    gi = os.path.join(ws, ".gitignore")
    if os.path.isfile(gi):
        with open(gi, "r", encoding="utf-8") as f:
            content = f.read()
        if "ledger.jsonl" not in content:
            with open(gi, "a", encoding="utf-8") as f:
                f.write("\n.reticuli/ledger.jsonl\n")
    else:
        with open(gi, "w", encoding="utf-8") as f:
            f.write(".reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n")

    if not no_agent:
        hooks.install(ws)

    print(f"initialized {ws}")
    return 0


# ---------------------------------------------------------------------------
# run: the CLI's own traced predicate -- a transparent boundary
# ---------------------------------------------------------------------------

def do_run(args) -> int:
    ws = getattr(args, "C", None) or "."
    cmd = args.cmd
    proc = subprocess.run(cmd, shell=True, cwd=ws)
    rc = proc.returncode
    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        trace_path = os.path.join(ws, ".reticuli", "draft.jsonl")
        try:
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "bash", "cmd": cmd, "ts": time.time(),
                                     "via": "shell"}, sort_keys=True))
                f.write("\n")
        except OSError:
            pass
    return rc


# ---------------------------------------------------------------------------
# status: the pure view -- draft session, sealed claim, tree, claims
# ---------------------------------------------------------------------------

def _read_draft_events(ws):
    path = os.path.join(ws, ".reticuli", "draft.jsonl")
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
            except ValueError:
                continue
    return out


def _status_draft(ws, args) -> int:
    if not os.path.isdir(ws):
        return _claim_error_envelope_or_err("status", args, kernel.ClaimError("no such directory"))

    events = _read_draft_events(ws)
    writes = {}
    has_gate = False
    for e in events:
        if e.get("event") == "write" and isinstance(e.get("path"), str):
            writes[e["path"]] = e.get("via", "hook")
        elif e.get("event") == "bash":
            has_gate = True

    observed = len(writes)
    if has_gate:
        declared = observed
        unresolved_paths = []
    else:
        declared = 0
        unresolved_paths = list(writes)
    unresolved = len(unresolved_paths)
    sealable = has_gate and unresolved == 0

    if getattr(args, "json", False):
        data = {"observed": observed, "declared": declared, "unresolved": unresolved,
                "sealable": sealable}
        _envelope("status", True, "draft", None, data)
        return 0

    if getattr(args, "all", False):
        lines = [f"{'path':<24}{'observed':<12}{'declared':<12}evidence"]
        for p in sorted(writes):
            lines.append(f"{p:<24}{'write':<12}{'generated':<12}{writes[p]}")
        for e in events:
            if e.get("event") == "bash":
                lines.append(f"{'(gate)':<24}{'bash':<12}{'gate':<12}{e.get('via', 'hook')}")
        skip = {".reticuli", ".claude", ".gitignore", "reticuli.toml", "claim.toml"}
        try:
            for name in sorted(os.listdir(ws)):
                if name in skip or name in writes:
                    continue
                if os.path.isfile(os.path.join(ws, name)):
                    lines.append(f"{name:<24}{'-':<12}{'-':<12}-")
        except OSError:
            pass
        print("\n".join(lines))
        return 0

    line = f"draft  observed={observed} declared={declared} unresolved={unresolved}"
    if sealable:
        line += "  packable"
    for p in unresolved_paths:
        line += f"\n  {p}  undeclared"
    print(_paint(line, "green" if unresolved == 0 else None, _color_enabled()))
    return 0


_ROLE = {"generated": "free", "validated": "verdict", "pinned": "exact"}


def _effective_class(step):
    cls = step.get("class")
    if cls is not None:
        return cls
    return "generated" if step.get("kind") == "produce" else "pinned"


def _status_files(d, args) -> int:
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err("status", args, e)
    lines = []
    for step in parsed.get("step", []) or []:
        cls = _effective_class(step)
        role = _ROLE.get(cls, cls)
        lines.append(f"{step['output']:<20}{cls:<12}{role}")
    print("\n".join(lines))
    return 0


def _read_discovery(d):
    return _read_json_silent(os.path.join(d, kernel.STORE, "discovery.json"))


def _parse_stamp(when):
    import datetime
    try:
        dt = datetime.datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ")
        return dt.replace(tzinfo=datetime.timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def _status_default_text(d, manifest, v) -> str:
    lines = [f"{manifest['name']}  {_short(v['root'])}"]
    if not v["ok"]:
        lines.append("identity: broken")
        lines.append("next: restore the claim -- re-seal or recover the original bytes")
        return "\n".join(lines)

    lines.append("identity: fresh")
    receipt = _read_json_silent(os.path.join(d, kernel.STORE, "audit-receipt.json"))
    if receipt:
        ts = _parse_stamp(receipt.get("when"))
        where = "on this machine" if receipt.get("machine") == platform.machine() \
            else f"on {receipt.get('machine')}"
        ago = render.ago(ts) if ts is not None else "a while ago"
        lines.append(f"audited: {ago} {where}")
    else:
        lines.append("audited: never")

    discovery = _read_discovery(d)
    if discovery:
        lines.append(f"discovery: {discovery.get('tokens')} tokens (reported testimony)")

    attest_dir = os.path.join(d, ".reticuli", "attest")
    attest_n = len([f for f in os.listdir(attest_dir) if f.endswith(".json")]) \
        if os.path.isdir(attest_dir) else 0
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    sign_n = len([f for f in os.listdir(sign_dir) if f.endswith(".sign.json")]) \
        if os.path.isdir(sign_dir) else 0
    total_statements = attest_n + sign_n
    if total_statements:
        lines.append(f"{total_statements} statement(s): "
                      f"{attest_n} attested, {sign_n} signed")

    assessed = os.path.isfile(os.path.join(d, kernel.STORE, "assess-receipt.json"))
    if manifest.get("proof"):
        nxt = "fully proven; ret sign to authorize"
    elif assessed:
        nxt = "ret crosscheck"
    else:
        nxt = "ret assess"
    lines.append(f"next: {nxt}")
    return "\n".join(lines)


def _status_all_text(d) -> str:
    parsed = kernel.load_recipe(d)
    lines = ["fixed:"]
    for step in parsed.get("step", []) or []:
        if _effective_class(step) != "generated":
            deciders = ", ".join(kernel.gate_deciders(step.get("run", "") or "")) or "(none)"
            lines.append(f"  {step['output']}  deciding: {deciders}")
    lines.append("deciding: the files named above decide each gate's verdict")
    lines.append("free:")
    for step in parsed.get("step", []) or []:
        if _effective_class(step) == "generated":
            lines.append(f"  {step['output']}")
    lines.append("recorded:")
    receipt = _read_json_silent(os.path.join(d, kernel.STORE, "audit-receipt.json"))
    if receipt:
        lines.append(f"  audit, {receipt.get('when')} -- a receipt, not a verdict")
    if os.path.isfile(os.path.join(d, kernel.STORE, "assess-receipt.json")):
        lines.append(f"  assess, {_util.stamp()} -- a receipt, not a verdict")
    lines.append("unknown:")
    lines.append("  crosscheck, sign -- not yet performed")
    assessed = os.path.isfile(os.path.join(d, kernel.STORE, "assess-receipt.json"))
    nxt = "ret crosscheck" if assessed else "ret assess"
    lines.append(f"next: {nxt}")
    return "\n".join(lines)


def _status_json_data(d, manifest, v) -> dict:
    parsed = kernel.load_recipe(d)
    receipt = _read_json_silent(os.path.join(d, kernel.STORE, "audit-receipt.json"))
    assessed = os.path.isfile(os.path.join(d, kernel.STORE, "assess-receipt.json"))
    nxt = "ret crosscheck" if assessed else "ret assess"
    deciding = {}
    for step in parsed.get("step", []) or []:
        if step.get("kind") == "gate":
            deciding[step["output"]] = kernel.gate_deciders(step.get("run", "") or "")
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    signatures = sorted(f for f in os.listdir(sign_dir) if f.endswith(".sign.json")) \
        if os.path.isdir(sign_dir) else []
    return {
        "name": manifest["name"], "root": v["root"], "phase": kernel.phase(d),
        "audited": receipt, "deciding": deciding, "proof": manifest.get("proof"),
        "signatures": signatures, "next": nxt,
    }


def _status_claim(d, args) -> int:
    try:
        manifest = kernel.read_manifest(d)
        v = kernel.verify(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err("status", args, e)

    if getattr(args, "files", False):
        return _status_files(d, args)

    if getattr(args, "json", False):
        data = _status_json_data(d, manifest, v)
        status_word = "fresh" if v["ok"] else "claim"
        _envelope("status", True, status_word, v["root"], data)
        return 0

    if getattr(args, "all", False):
        print(_status_all_text(d))
        return 0

    text = _status_default_text(d, manifest, v)
    print(_paint(text, "green" if v["ok"] else "red", _color_enabled()))
    return 0


def _status_tree(d, args) -> int:
    manifest_path = os.path.join(d, kernel.STORE, "manifest.json")
    color_on = _color_enabled()
    if os.path.isfile(manifest_path):
        try:
            manifest = kernel.read_manifest(d)
            parsed = kernel.load_recipe(d)
        except kernel.ClaimError as e:
            return _claim_error_envelope_or_err("status", args, e)
        comps = registry.components_of(d)
        layers = 1 + len(comps)
        lines = [f"{manifest['name']}  layers={layers}"]
        for step in parsed.get("step", []) or []:
            if _effective_class(step) != "generated":
                if color_on:
                    lines.append(_paint(step["output"], "cyan", True))
                else:
                    lines.append(f"{'pinned':<10} {step['output']}")
        print("\n".join(lines))
        return 0

    lines = [f"draft  {d}"]
    for c in registry.claims(d):
        lines.append(f"  {c['name']}  {c['phase']}")
    print("\n".join(lines))
    return 0


def _status_claims(ws, args) -> int:
    try:
        found = registry.claims(ws)
    except kernel.ClaimError:
        found = []
    print("\n".join(c["name"] for c in found))
    return 0


def do_status(args) -> int:
    d = args.dir
    if getattr(args, "tree", False):
        return _status_tree(d, args)
    if getattr(args, "claims", False):
        return _status_claims(d, args)
    if not os.path.isfile(os.path.join(d, kernel.STORE, "manifest.json")):
        return _status_draft(d, args)
    return _status_claim(d, args)


# ---------------------------------------------------------------------------
# pack: the single authoring boundary
# ---------------------------------------------------------------------------

def _write_discovery(ws, claim_dir) -> None:
    trace_path = os.path.join(ws, ".reticuli", "draft.jsonl")
    if not os.path.isfile(trace_path):
        return
    transcript_path = None
    with open(trace_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("event") == "session" and isinstance(ev.get("transcript"), str):
                transcript_path = ev["transcript"]
    if not transcript_path or not os.path.isfile(transcript_path):
        return
    total = 0
    found = False
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") != "assistant":
                continue
            usage = (obj.get("message") or {}).get("usage")
            if isinstance(usage, dict):
                total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                found = True
    if found:
        store = os.path.join(claim_dir, kernel.STORE)
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, "discovery.json"), "w", encoding="utf-8") as f:
            json.dump({"tokens": total}, f)


def _pack_session(ws, output, rec, name) -> dict:
    """Certify `ws`'s session: a traced write whose file was later deleted
    (or never materialized) must not crash pack -- it is simply dropped
    from the candidate generated/input sets before `authoring.build_claim`
    ever enforces its own on-disk precondition."""
    proposal = authoring.propose(ws, [output], name)
    generated = [p for p in proposal["generated"] if os.path.isfile(os.path.join(ws, p))]
    inputs = [p for p in proposal["inputs"] if os.path.isfile(os.path.join(ws, p))]
    return authoring.build_claim(ws, [output], rec, name=name, claim=inputs, generated=generated)


def do_pack(args) -> int:
    cmd = "pack"
    d = getattr(args, "dir", ".") or "."
    accept = getattr(args, "accept", None)
    out = getattr(args, "out", None)

    if accept and not out:
        _err(cmd, "--accept needs -o naming the sealed claim's destination; "
                  "refusing before building anything")
        return 2

    try:
        if accept:
            name = getattr(args, "name", None) or os.path.basename(os.path.abspath(d))
            result = _pack_session(d, accept, out, name)
            _write_discovery(d, out)
            root = result["root"]
        elif os.path.isfile(os.path.join(d, kernel.RECIPE)) \
                or os.path.isfile(os.path.join(d, kernel.LEGACY_RECIPE)):
            manifest = registry.seal_with(d)
            root = manifest["root"]
        elif getattr(args, "generated", None) or getattr(args, "gate", None):
            name = getattr(args, "name", None) or os.path.basename(os.path.abspath(d))
            result = pack_mod.pack(
                d, name, args.generated or [], args.inputs or [], args.gate,
                gate_output=getattr(args, "gate_output", None) or "OK",
                claim_format=getattr(args, "format", None),
                envelope=_parse_envelope_flags(getattr(args, "envelope", None)) or None,
                mutation_floor=getattr(args, "mutation_floor", None),
                requires=getattr(args, "requires", None),
                inputs_manifest=getattr(args, "inputs_manifest", None),
                environment=getattr(args, "environment", None))
            root = result["root"]
        else:
            raise kernel.ClaimError("nothing to pack")
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    if getattr(args, "json", False):
        _envelope(cmd, True, "ok", root, {"root": root})
        return 0
    print(f"packed {_short(root)}")
    return 0


# ---------------------------------------------------------------------------
# verify: identity only
# ---------------------------------------------------------------------------

def _diff_part(d):
    parts_path = os.path.join(d, kernel.STORE, "parts.json")
    if not os.path.isfile(parts_path):
        return None
    sealed = _read_json_silent(parts_path)
    if not sealed:
        return None
    changed = []
    for key, val in sealed.items():
        if key in ("digest", "recipe"):
            continue
        _prefix, _sep, path = key.partition(":")
        full = os.path.join(d, path)
        try:
            cur = kernel._hash_file(full)
        except kernel.ClaimError:
            cur = None
        if cur != val:
            changed.append(path)
    return ", ".join(changed) if changed else None


def do_verify(args) -> int:
    cmd = "verify"
    d = args.dir
    try:
        v = kernel.verify(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    ok = v["ok"]
    status = "fresh" if ok else "mismatch"
    data = {"name": v.get("name"), "root": v["root"], "recomputed": v["recomputed"],
            "phase": None, "ok": ok}
    try:
        data["phase"] = kernel.phase(d)
    except kernel.ClaimError:
        pass

    if getattr(args, "json", False):
        _envelope(cmd, ok, status, v["root"], data)
        return 0 if ok else 1

    if not ok:
        name = os.path.basename(os.path.normpath(d))
        changed = _diff_part(d)
        detail = f"{name}: identity mismatch" + (f" ({changed} changed)" if changed else "")
        _err(cmd, f"{detail}; hint: re-seal the claim or restore the original bytes")
        return 1

    if getattr(args, "verbose", False):
        print(f"[verify]\nname = \"{v.get('name')}\"\n"
              f"root = \"{v['root']}\"\nrecomputed = \"{v['recomputed']}\"")
    return 0


# ---------------------------------------------------------------------------
# audit: the judge
# ---------------------------------------------------------------------------

def do_audit(args) -> int:
    cmd = "audit"
    d = args.dir
    shallow = getattr(args, "shallow", False)
    no_strict = getattr(args, "no_strict", False)
    t0 = time.time()

    try:
        if shallow:
            result = kernel.audit(d, strict=not no_strict)
            layers = []
        else:
            deep = registry.audit_deep(d)
            result = dict(kernel.audit(d, strict=not no_strict))
            layers = deep["layers"]
            result["ok"] = bool(result.get("ok")) and bool(deep.get("ok"))
        manifest = kernel.read_manifest(d)
        v = kernel.verify(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    elapsed = time.time() - t0
    _write_audit_receipt(d)

    ms = None
    mutants = getattr(args, "mutants", None)
    if mutants:
        try:
            ms = kernel.mutation_score(d, max_mutants=mutants)
        except kernel.ClaimError:
            ms = None

    record_path = getattr(args, "record", None)
    if record_path:
        try:
            doc = record.emit(d)
            record.write(doc, record_path)
        except kernel.ClaimError:
            pass

    status = _audit_status_word(result)
    ok = bool(result.get("ok"))
    data = {
        "name": manifest.get("name"),
        "root": v.get("root"),
        "recomputed": v.get("recomputed"),
        "elapsed": elapsed,
        "environment": result.get("environment") or [],
        "layers": layers,
        "gates": result.get("gates", []),
    }
    if ms is not None:
        data["mutation_score"] = ms

    if getattr(args, "json", False):
        _envelope(cmd, ok, status, v.get("root"), data)
        return 0 if ok else 1

    if not ok:
        _err(cmd, f"{status}: the claim's verdict did not hold")
        return 1

    if getattr(args, "verbose", False):
        lines = ["[audit]", f"root = \"{v.get('root')}\""]
        for g in data["gates"]:
            disp = "reproduced" if g.get("status") == "ok" else g.get("status")
            lines.append(f"  gate {g.get('output')}: {disp}")
        if ms is not None:
            lines.append("[mutation_score]")
            lines.append(f"  rate = {ms['rate']}")
            lines.append(f"  mutants = {ms['mutants']}")
        print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# assess: how much the pinned suite proves
# ---------------------------------------------------------------------------

def do_assess(args) -> int:
    cmd = "assess"
    d = args.dir
    mutants = getattr(args, "mutants", 20)
    try:
        result = assess_mod.assess(d, mutants=mutants)
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    gates = [s for s in parsed.get("step", []) or [] if s.get("kind") == "gate"]
    data = dict(result)
    data["declared"] = [g["output"] for g in gates]
    data["gate"] = gates[0]["run"] if gates else None
    status = "measured"

    try:
        store = os.path.join(d, kernel.STORE)
        os.makedirs(store, exist_ok=True)
        with open(os.path.join(store, "assess-receipt.json"), "w", encoding="utf-8") as f:
            json.dump({"when": _util.stamp(), "rate": result["rate"]}, f)
    except OSError:
        pass

    if getattr(args, "json", False):
        _envelope(cmd, True, status, None, data)
        return 0

    if getattr(args, "verbose", False):
        print(f"[assess]\n  rate = {result['rate']}\n  measured = {result['measured']}\n"
              f"  not_measured = {result['not_measured']}")
    return 0


# ---------------------------------------------------------------------------
# rebuild: regrow generated outputs
# ---------------------------------------------------------------------------

def do_rebuild(args) -> int:
    cmd = "rebuild"
    d = args.dir
    try:
        command, env = _expand_producer(getattr(args, "producer", None))
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    into = getattr(args, "into", None) or d
    try:
        result = kernel.rebuild(d, command, into,
                                 produce_from=None,
                                 input_from=None,
                                 guidance=getattr(args, "guidance", True),
                                 producer_env=env or None)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    root = result["root"]
    if getattr(args, "json", False):
        _envelope(cmd, True, "ok", root, result)
        return 0
    print(f"rebuilt {root}")
    return 0


# ---------------------------------------------------------------------------
# crosscheck: the three-machine test
# ---------------------------------------------------------------------------

def do_crosscheck(args) -> int:
    cmd = "crosscheck"
    m1, m2, m3 = args.m1, args.m2, getattr(args, "m3", None)
    tmp = None
    m2_materialized = False
    if m3 is None:
        tmp = tempfile.mkdtemp(prefix="reticuli-m2-")
        shutil.copytree(m1, tmp, dirs_exist_ok=True)
        real_m2, real_m3 = tmp, m2
        m2_materialized = True
    else:
        real_m2, real_m3 = m2, m3

    try:
        result = kernel.crosscheck(m1, real_m2, real_m3, mutants=getattr(args, "mutants", None))
    except kernel.ClaimError as e:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        return _claim_error_envelope_or_err(cmd, args, e)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)

    data = dict(result)
    data["m2_materialized"] = m2_materialized
    discovery = _read_discovery(m1) if os.path.isdir(m1) else None
    if discovery:
        data["discovery"] = discovery

    ok = result["satisfied"]
    status = result["verdict"]
    root = result.get("roots", {}).get("M1")

    if getattr(args, "json", False):
        _envelope(cmd, ok, status, root, data)
        return 0 if ok else 1

    if not ok:
        reasons = result.get("rejected") or result.get("incomplete") or ["unspecified"]
        _err(cmd, f"{status}: {', '.join(reasons)}")
        return 1

    if getattr(args, "verbose", False):
        lines = ["[crosscheck]", f"satisfied = {'true' if ok else 'false'}",
                 f"verdict = {status}", "[cost]",
                 f"  comparable = {result['cost'].get('comparable')}",
                 f"  envelope = {result['cost'].get('envelope')}"]
        if discovery:
            lines.append(f"  discovery: {discovery.get('tokens')} tokens "
                         "(reported testimony, not in the cost band)")
        print("\n".join(lines))
    return 0


# ---------------------------------------------------------------------------
# export / import: deterministic transport, the blind room
# ---------------------------------------------------------------------------

def do_export(args) -> int:
    cmd = "export"
    d = args.dir
    out = getattr(args, "out", None) or getattr(args, "out_flag", None)
    if not out:
        _err(cmd, "export needs an output path (positional, or -o)")
        return 2
    try:
        if out == "-":
            tmp_path = tempfile.mktemp(prefix="reticuli-export-")
            transfer.export(d, tmp_path, blind=getattr(args, "blind", False))
            with open(tmp_path, "rb") as f:
                payload = f.read()
            os.remove(tmp_path)
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
            return 0
        transfer.export(d, out, blind=getattr(args, "blind", False))
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    if getattr(args, "json", False):
        _envelope(cmd, True, "ok", None, {"out": out})
    return 0


def do_import(args) -> int:
    cmd = "import"
    tar_path = args.tar
    into = args.into
    tmp_path = None
    try:
        if tar_path == "-":
            tmp_path = tempfile.mktemp(prefix="reticuli-import-")
            with open(tmp_path, "wb") as f:
                f.write(sys.stdin.buffer.read())
            result = transfer.import_(tmp_path, into)
        else:
            if not os.path.isfile(tar_path):
                raise kernel.ClaimError(f"no archive found at {tar_path!r}")
            result = transfer.import_(tar_path, into)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.remove(tmp_path)

    ok = result["ok"]
    if getattr(args, "json", False):
        _envelope(cmd, ok, "ok" if ok else "mismatch", result.get("root"), result)
        return 0 if ok else 1
    if not ok:
        _err(cmd, "import did not verify")
        return 1
    return 0


# ---------------------------------------------------------------------------
# pull: a claim becomes a standalone dependency
# ---------------------------------------------------------------------------

def do_pull(args) -> int:
    cmd = "pull"
    try:
        result = registry.pull(args.dir, args.into)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)
    if getattr(args, "json", False):
        _envelope(cmd, True, "ok", result.get("root"), result)
    return 0


# ---------------------------------------------------------------------------
# record: evidence (machine) -- the record document, or the lightweight
# claim-level attestation folded in under --key/--as and --check
# ---------------------------------------------------------------------------

def do_record(args) -> int:
    cmd = "record"
    d = args.dir
    out = getattr(args, "out", None)
    key = getattr(args, "key", None)
    identity_str = getattr(args, "identity", None)
    check = getattr(args, "check", False)
    sign_flag = getattr(args, "sign_flag", False)

    try:
        if check:
            anchor = os.environ.get("RETICULI_SIGNERS")
            res = attest.check(d, signers=anchor)
            ok = res["ok"]
            if getattr(args, "json", False):
                _envelope(cmd, ok, "ok" if ok else "unverified", None, res)
                return 0 if ok else 1
            if not ok:
                _err(cmd, "attestation did not verify")
                return 1
            return 0

        if out:
            doc = record.emit(d)
            if sign_flag:
                env_key = os.environ.get("RETICULI_KEY")
                if not env_key:
                    raise kernel.ClaimError(
                        "record --sign needs RETICULI_KEY set to a signing key path")
                key = env_key
            record.write(doc, out)
            if key:
                record.sign(out, key)
            data = {"digest": record.digest(doc), "record": doc}
            if getattr(args, "json", False):
                _envelope(cmd, True, "ok", doc.get("root"), data)
                return 0
            return 0

        if key and identity_str:
            res = attest.attest(d, key, identity_str)
            if getattr(args, "json", False):
                _envelope(cmd, True, "ok", res.get("root"), res)
                return 0
            return 0

        raise kernel.ClaimError("record needs -o, --check, or --key together with --as")
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)


# ---------------------------------------------------------------------------
# sign: the accountable ceremony (human), and the review view
# ---------------------------------------------------------------------------

def _sign_check_unanchored(d) -> dict:
    """Like `attest.sign_check`, except when no trust anchor is configured:
    an authorization statement is reported `unsigned` (intact, not yet
    verified against anyone) rather than `unauthorized` -- the same
    unsigned/tampered duality `attest.check` already gives attestations,
    applied here to the signing ceremony's own statements."""
    import hashlib
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    authorizations = []
    ok_overall = True
    found_any = False
    if os.path.isdir(sign_dir):
        for fname in sorted(os.listdir(sign_dir)):
            if not fname.endswith(".sign.json"):
                continue
            found_any = True
            stmt_path = os.path.join(sign_dir, fname)
            with open(stmt_path, "rb") as f:
                stmt_bytes = f.read()
            try:
                stmt = json.loads(stmt_bytes)
            except ValueError:
                ok_overall = False
                authorizations.append({"verdict": "malformed", "packet_holds": False})
                continue
            canonical = json.dumps(stmt, sort_keys=True).encode()
            intact = canonical == stmt_bytes
            prefix = fname[: -len(".sign.json")]
            packet_path = os.path.join(sign_dir, prefix + ".packet.json")
            packet_holds = False
            if os.path.isfile(packet_path):
                with open(packet_path, "rb") as f:
                    packet_bytes = f.read()
                if hashlib.sha256(packet_bytes).hexdigest() == stmt.get("packet_digest"):
                    try:
                        packet = json.loads(packet_bytes)
                        manifest = kernel.read_manifest(d)
                        packet_holds = packet.get("root") == manifest.get("root")
                    except ValueError:
                        pass
            ok_this = intact and packet_holds
            authorizations.append({"verdict": "unsigned" if intact else "tampered",
                                    "packet_holds": packet_holds})
            if not ok_this:
                ok_overall = False
    return {"ok": ok_overall and found_any, "authorizations": authorizations}


def do_sign(args) -> int:
    cmd = "sign"
    d = args.dir
    key = getattr(args, "key", None)
    identity_str = getattr(args, "identity", None)
    check = getattr(args, "check", False)

    try:
        if check:
            anchor = os.environ.get("RETICULI_SIGNERS")
            if anchor and os.path.isfile(anchor):
                res = attest.sign_check(d, signers=anchor)
            else:
                res = _sign_check_unanchored(d)
            ok = res["ok"]
            if getattr(args, "json", False):
                _envelope(cmd, ok, "ok" if ok else "unauthorized", None, res)
                return 0 if ok else 1
            if not ok:
                _err(cmd, "authorization did not verify")
                return 1
            return 0

        if key and identity_str:
            res = attest.sign(d, key, identity_str)
            if getattr(args, "json", False):
                _envelope(cmd, True, "ok", res.get("root"), res)
                return 0
            return 0

        pkt = attest.review_packet(d)
    except kernel.ClaimError as e:
        return _claim_error_envelope_or_err(cmd, args, e)

    if getattr(args, "json", False):
        _envelope(cmd, True, "ok", pkt.get("root"), pkt)
        return 0
    if getattr(args, "verbose", False):
        print(f"[review]\nroot = \"{pkt.get('root')}\"\n"
              f"sign_root = \"{pkt.get('sign_root')}\"\n"
              f"build_digest = \"{pkt.get('build_digest')}\"")
    else:
        print(f"review {_short(pkt.get('root'))}")
    return 0


# ---------------------------------------------------------------------------
# hook: the agent handshake -- plumbing, silent
# ---------------------------------------------------------------------------

def do_hook(args) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0

    cwd = payload.get("cwd")
    transcript = payload.get("transcript_path")
    if isinstance(cwd, str) and isinstance(transcript, str) \
            and os.path.isdir(os.path.join(cwd, kernel.STORE)):
        trace_path = os.path.join(cwd, hooks.TRACE)
        try:
            os.makedirs(os.path.dirname(trace_path), exist_ok=True)
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": "session", "transcript": transcript,
                                     "ts": time.time(), "via": "hook"}, sort_keys=True))
                f.write("\n")
        except OSError:
            pass

    hooks.event(payload)
    return 0

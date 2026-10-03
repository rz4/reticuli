"""Dispatch: one function per porcelain verb, called by `cli.main` after
the argv grammar has parsed a verb's arguments (spec/layers.md, "surface").

Every `cmd_*` function takes the parsed `argparse.Namespace` for one verb
and returns the process exit code, printing whatever that verb's contract
calls for itself -- a silent verb (verify/audit/crosscheck/export/import/
record/sign --key/run) prints nothing on a plain success, a few verbs
(init/pack/rebuild/sign with no key) print one short word naming what
happened, and `status` always renders a report. `-v` renders a `[name]`
block of the same facts a `--json` call would carry under `data`; `--json`
always speaks the five-field envelope. Nothing here is a kernel private:
every fact is read through `reticuli.kernel`'s pinned surface, or through
the exchange/authoring layers built on it.
"""
import inspect
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time

from reticuli import _util
from reticuli import assess as assess_mod
from reticuli import attest
from reticuli import authoring
from reticuli import hooks
from reticuli import kernel
from reticuli import record as record_mod
from reticuli import registry
from reticuli import render
from reticuli import transfer

ENVELOPE = ("command", "ok", "status", "root", "data")


# ===========================================================================
# Small shared helpers: the refusal voice, the JSON envelope, color, and the
# `[name]` verbose block every `-v` rendering reduces to.
# ===========================================================================


def _err(verb, msg):
    print(f"ret: {verb}: {msg}", file=sys.stderr)


def _envelope_line(command, ok, status, root, data):
    print(json.dumps(
        {"command": command, "ok": ok, "status": status, "root": root, "data": data},
        sort_keys=True,
    ))


def _refuse(args, verb, msg, code=1):
    """A refusal: exit 2 is a plain stderr line (no envelope, ever); exit 1
    speaks the five-field envelope under `--json` (ok false, status error,
    the fact under `data.error`) and the one-voice stderr line otherwise.
    """
    if code == 2:
        _err(verb, msg)
        return 2
    if getattr(args, "json", False):
        _envelope_line(verb, False, "error", None, {"error": msg})
    else:
        _err(verb, msg)
    return code


def _color_enabled():
    mode = os.environ.get("RETICULI_COLOR", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


_CODES = {"red": "31", "green": "32", "yellow": "33", "cyan": "36"}


def _paint(text, color):
    if not color or not _color_enabled():
        return text
    code = _CODES.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _fmt_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, sort_keys=True)


def _vblock(name, fields):
    print(f"[{name}]")
    for k, v in fields.items():
        print(f"{k} = {_fmt_val(v)}")


def _short(root):
    return root[:12] if isinstance(root, str) else "?"


# ===========================================================================
# Residue this layer keeps beside a claim: the audit receipt, the assess
# receipt, and the discovery ledger -- none of it identity, all of it read
# back by `status`/`crosscheck -v` to orient a reader.
# ===========================================================================


def _residue_path(d, name):
    return os.path.join(d, kernel.STORE, name)


def _read_residue(d, name):
    path = _residue_path(d, name)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_residue(d, name, obj):
    try:
        path = _residue_path(d, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True)
    except OSError:
        pass


def _write_audit_receipt(d, ok):
    _write_residue(d, "audit-receipt.json",
                    {"when": time.time(), "host": socket.gethostname(), "ok": ok})


def _write_assess_receipt(d):
    _write_residue(d, "assess-receipt.json", {"when": time.time()})


def _discovery_tokens(d):
    doc = _read_residue(d, "discovery.json")
    return doc.get("tokens") if isinstance(doc, dict) else None


def _read_draft_trace(ws):
    path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    events = []
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def _write_discovery(ws, rec):
    """The session's reported discovery cost: every assistant turn's token
    usage, summed across every harness transcript a `session` event names
    -- testimony that rides the claim beside the ledger, never inside the
    cost band a redo is held to.
    """
    total = 0
    found = False
    for e in _read_draft_trace(ws):
        if e.get("event") != "session":
            continue
        transcript = e.get("transcript")
        if not (isinstance(transcript, str) and os.path.isfile(transcript)):
            continue
        found = True
        with open(transcript, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                usage = (obj.get("message") or {}).get("usage") or {}
                total += int(usage.get("input_tokens") or 0)
                total += int(usage.get("output_tokens") or 0)
    if found:
        _write_residue(rec, "discovery.json", {"tokens": total})


def _ladder_next(d):
    if _read_residue(d, "audit-receipt.json") is None:
        return f"ret audit {d}"
    if _read_residue(d, "assess-receipt.json") is None:
        return f"ret assess {d}"
    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    if not manifest.get("proof"):
        return f"ret crosscheck {d}"
    return "nothing further -- crosschecked and proven"


# ===========================================================================
# init
# ===========================================================================

_SUPPORTED_AGENTS = {"claude"}


def cmd_init(args):
    verb = "init"
    ws = args.workspace or "."
    agent = args.agent
    if agent is not None and agent not in _SUPPORTED_AGENTS:
        _err(verb, f"unsupported agent: {agent!r}")
        return 2

    store = os.path.join(ws, kernel.STORE)
    already = os.path.isdir(store)
    os.makedirs(store, exist_ok=True)

    gi_path = os.path.join(ws, ".gitignore")
    gi_lines = []
    if os.path.isfile(gi_path):
        with open(gi_path, "r", encoding="utf-8") as f:
            gi_lines = f.read().splitlines()
    wanted = ".reticuli/ledger.jsonl"
    if wanted not in gi_lines:
        gi_lines.append(wanted)
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write("\n".join(gi_lines) + "\n")

    hooks_result = None
    if agent is not None and not args.no_agent:
        hooks_result = hooks.install(ws)

    status = "already initialized" if already else "initialized"
    data = {"workspace": ws, "status": status, "hooks": hooks_result}
    if args.json:
        _envelope_line(verb, True, status, None, data)
    elif args.verbose:
        _vblock(verb, data)
    else:
        print(f"{status} {ws}")
    return 0


# ===========================================================================
# run: a transparent boundary -- the child's exit code, unwrapped.
# ===========================================================================

_KEEP_ENV = ("PATH", "LANG", "LC_ALL", "TZ", "HOME")


def cmd_run(args):
    ws = args.workspace or "."
    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
    producer = os.environ.get("RETICULI_PRODUCER")
    if producer:
        env["RETICULI_PRODUCER"] = producer
    proc = subprocess.run(args.cmd, shell=True, cwd=ws, env=env)
    return proc.returncode


# ===========================================================================
# status: a pure view. Never executes a gate; never fails -- it reports and
# points at the fix.
# ===========================================================================


def _recipe_present(ws):
    return (os.path.isfile(os.path.join(ws, kernel.RECIPE))
            or os.path.isfile(os.path.join(ws, "claim.toml")))


def _existing_names(ws):
    names = set()
    for root_dir, dirs, files in os.walk(ws):
        dirs[:] = [dd for dd in dirs if dd != kernel.STORE]
        for fname in files:
            rel = os.path.relpath(os.path.join(root_dir, fname), ws).replace(os.sep, "/")
            names.add(rel)
    return names


def _draft_classify(ws):
    trace = _read_draft_trace(ws)
    writes, reads, bash_cmds = [], [], []
    for e in trace:
        ev = e.get("event")
        if ev == "write":
            p = e.get("path")
            if isinstance(p, str) and p not in writes:
                writes.append(p)
        elif ev == "read":
            p = e.get("path")
            if isinstance(p, str) and p not in reads:
                reads.append(p)
        elif ev == "bash":
            c = e.get("cmd")
            if isinstance(c, str):
                bash_cmds.append(c)

    has_gate = bool(bash_cmds)
    existing = _existing_names(ws)
    rows = []
    unresolved = []
    declared = 0
    seen = set()

    for p in writes:
        seen.add(p)
        cls = "generated" if has_gate else None
        rows.append({"path": p, "observed": "write", "declared": cls or "-", "evidence": "hook"})
        if cls:
            declared += 1
        else:
            unresolved.append(p)

    for p in reads:
        if p in seen:
            continue
        seen.add(p)
        referenced = any(p in c for c in bash_cmds)
        cls = "pinned" if (referenced and p in existing) else None
        rows.append({"path": p, "observed": "read", "declared": cls or "-",
                     "evidence": "gate" if referenced else "hook"})
        if cls:
            declared += 1

    for c in bash_cmds:
        for tok in c.split():
            if tok in existing and tok not in seen:
                seen.add(tok)
                rows.append({"path": tok, "observed": "-", "declared": "pinned", "evidence": "gate"})
                declared += 1

    return {
        "rows": rows, "observed": len(writes) + len(reads), "declared": declared,
        "unresolved": unresolved, "existing": existing, "seen": seen,
    }


def _status_draft_default(ws, args):
    info = _draft_classify(ws)
    n_unresolved = len(info["unresolved"])
    if args.json:
        data = {"observed": info["observed"], "declared": info["declared"],
                 "unresolved": n_unresolved}
        _envelope_line("status", True, "draft", None, data)
        return 0
    lines = [f"draft  observed={info['observed']} declared={info['declared']} "
             f"unresolved={n_unresolved}"]
    if n_unresolved == 0:
        lines.append("packable")
    else:
        for p in info["unresolved"]:
            lines.append(f"{p}  undeclared")
    print("\n".join(lines))
    return 0


def _status_draft_all(ws, args):
    info = _draft_classify(ws)
    rows = list(info["rows"])
    for name in sorted(info["existing"] - info["seen"]):
        rows.append({"path": name, "observed": "-", "declared": "-", "evidence": "-"})
    text = render.table(rows, headers=["path", "observed", "declared", "evidence"])
    print(text if text else "draft: nothing traced yet")
    return 0


def _status_draft_tree(ws, args):
    print(f"draft session: {ws}")
    return 0


def _status_claims(ws, args):
    sealed = os.path.join(ws, kernel.STORE, "sealed")
    names = []
    if os.path.isdir(sealed):
        names = sorted(n for n in os.listdir(sealed) if os.path.isdir(os.path.join(sealed, n)))
    if args.json:
        _envelope_line("status", True, "claims", None, {"claims": names})
        return 0
    print("\n".join(names) if names else "no sealed claims in this workspace")
    return 0


def _statement_counts(d):
    attest_dir = os.path.join(d, ".reticuli", "attest")
    sign_dir = os.path.join(d, kernel.SIGN_DIR)
    n_attest = 0
    if os.path.isdir(attest_dir):
        n_attest = len([f for f in os.listdir(attest_dir) if f.endswith(".attest.json")])
    n_signed = 0
    if os.path.isdir(sign_dir):
        n_signed = len([f for f in os.listdir(sign_dir) if f.endswith(".sign.json")])
    return n_attest, n_signed


def _status_claim_default(d, args):
    verb = "status"
    try:
        vr = kernel.verify(d)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    try:
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError:
        manifest = {}
    try:
        ph = kernel.phase(d)
    except kernel.ClaimError:
        ph = None

    if args.json:
        n_attest, n_signed = _statement_counts(d)
        status_word = "fresh" if vr.get("ok") else "claim"
        data = {
            "name": vr.get("name"), "root": vr.get("root"), "phase": ph,
            "audited": _read_residue(d, "audit-receipt.json"),
            "deciding": [], "proof": manifest.get("proof"),
            "signatures": {"attested": n_attest, "signed": n_signed},
            "next": _ladder_next(d),
        }
        _envelope_line(verb, True, status_word, vr.get("root"), data)
        return 0

    if not vr.get("ok"):
        print("\n".join([
            f"{vr.get('name')}  broken",
            "identity: broken -- the bytes present no longer match the sealed root",
            "next: restore the original bytes, or re-pack",
        ]))
        return 0

    lines = [f"{vr.get('name')}  {_paint(_short(vr.get('root', '')), 'cyan')}"]
    lines.append(f"identity: {_paint('fresh', 'green')}")
    receipt = _read_residue(d, "audit-receipt.json")
    if receipt is not None:
        host = receipt.get("host")
        where = "on this machine" if host == socket.gethostname() else f"on {host}"
        lines.append(f"audited: {render.ago(receipt['when'])} {where}")
    tokens = _discovery_tokens(d)
    if tokens is not None:
        lines.append(f"discovery: {tokens} tokens (reported testimony)")
    n_attest, n_signed = _statement_counts(d)
    total_statements = n_attest + n_signed
    if total_statements:
        lines.append(f"{total_statements} statement(s): {n_attest} attested, {n_signed} signed")
    lines.append(f"next: {_ladder_next(d)}")
    print("\n".join(lines))
    return 0


def _status_claim_all(d, args):
    try:
        vr = kernel.verify(d)
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError as exc:
        return _refuse(args, "status", str(exc), 1)

    lines = ["fixed", f"    root: {vr.get('root')}", f"    name: {vr.get('name')}", ""]

    lines.append("deciding")
    for step in parsed.get("step", []):
        if step.get("kind") == "gate":
            lines.append(f"    {step['output']}  gate")
    lines.append("")

    lines.append("free")
    for step in parsed.get("step", []):
        if step.get("kind") == "produce" and step.get("class", "generated") == "generated":
            lines.append(f"    {step['output']}  generated")
    lines.append("")

    lines.append("recorded")
    receipt = _read_residue(d, "audit-receipt.json")
    if receipt is not None:
        lines.append(f"    audit, {render.ago(receipt['when'])}: on this machine")
    assess_receipt = _read_residue(d, "assess-receipt.json")
    if assess_receipt is not None:
        lines.append(f"    assess, {render.ago(assess_receipt['when'])}: "
                      f"a receipt, not a verdict")
    lines.append("")

    lines.append("unknown")
    floor = parsed.get("claim", {}).get("mutation_floor")
    lines.append(f"    mutation_floor: "
                 f"{'declared ' + str(floor) if floor is not None else 'not declared'}")
    lines.append("")

    lines.append("next")
    lines.append(f"    {_ladder_next(d)}")

    print("\n".join(lines))
    return 0


def _status_claim_files(d, args):
    try:
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError as exc:
        return _refuse(args, "status", str(exc), 1)

    rows = []
    for name in _util.declared_inputs(parsed):
        rows.append({"path": name, "class": "input", "role": "pinned"})
    for step in parsed.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        role = "free" if cls == "generated" else "verdict" if cls == "validated" else "pinned"
        rows.append({"path": step["output"], "class": cls, "role": role})
    text = render.table(rows, headers=["path", "class", "role"])
    print(text if text else "status --files: nothing declared")
    return 0


_ROLE_COLOR = {"free": "yellow", "pinned": "green"}


def _status_claim_tree(d, args):
    try:
        parsed = kernel.load_recipe(d)
        manifest = kernel.read_manifest(d)
    except kernel.ClaimError as exc:
        return _refuse(args, "status", str(exc), 1)

    layers = len(manifest.get("components") or [])
    colored = _color_enabled()
    lines = [f"layers={layers}"]
    for step in parsed.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        cls = step.get("class", default_cls)
        role = "free" if cls == "generated" else "pinned"
        if colored:
            label = _paint(" " * 11, _ROLE_COLOR.get(role))
        else:
            label = role.ljust(11)
        lines.append(f"{label}{step['output']}")
    print("\n".join(lines))
    return 0


def _status_structure(ws, args):
    print(f"workspace: {ws} (no claim, no draft session)")
    return 0


def cmd_status(args):
    verb = "status"
    ws = args.workspace or "."
    if not os.path.isdir(ws):
        return _refuse(args, verb, f"no such directory: {ws}", 1)

    if args.tree:
        if _recipe_present(ws):
            return _status_claim_tree(ws, args)
        return _status_draft_tree(ws, args)

    if args.claims:
        return _status_claims(ws, args)

    if _recipe_present(ws):
        if args.all:
            return _status_claim_all(ws, args)
        if args.files:
            return _status_claim_files(ws, args)
        return _status_claim_default(ws, args)

    trace_path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    if os.path.isfile(trace_path):
        if args.all:
            return _status_draft_all(ws, args)
        return _status_draft_default(ws, args)

    return _status_structure(ws, args)


# ===========================================================================
# pack: the single authoring boundary.
# ===========================================================================


def cmd_pack(args):
    verb = "pack"
    d = args.workspace or "."
    accept = args.accept or []
    output = args.output

    if accept:
        if not output:
            _err(verb, "--accept needs -o/--output to name the claim's destination")
            return 2
        name = args.name or os.path.basename(os.path.abspath(d).rstrip(os.sep)) or "claim"
        try:
            result = authoring.build_claim(d, accept, output, name=name)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, str(exc), 1)
        _write_discovery(d, output)
        root = result.get("root")
        if args.json:
            _envelope_line(verb, True, "packed", root, result)
        elif args.verbose:
            _vblock(verb, result)
        else:
            print(f"packed {result.get('name')} -> {_short(root)}")
        return 0

    if _recipe_present(d):
        try:
            manifest = kernel.seal(d)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, str(exc), 1)
        root = manifest.get("root")
        if args.json:
            _envelope_line(verb, True, "packed", root, manifest)
        elif args.verbose:
            _vblock(verb, manifest)
        else:
            print(f"packed {manifest.get('name')} -> {_short(root)}")
        return 0

    return _refuse(args, verb, "nothing to pack", 1)


# ===========================================================================
# pull
# ===========================================================================


def cmd_pull(args):
    verb = "pull"
    try:
        result = registry.pull(args.source, args.workspace or ".")
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)
    ok = bool(result.get("materialized", True))
    if args.json:
        _envelope_line(verb, ok, "pulled", result.get("root"), result)
    return 0 if ok else 1


# ===========================================================================
# export / import: deterministic tar, verify-on-import; `-` is the stream.
# ===========================================================================


def cmd_export(args):
    verb = "export"
    d = args.claim or "."
    dest = args.tar or args.out
    if not dest:
        dest = os.path.abspath(d.rstrip(os.sep) or ".") + ".tar"

    try:
        if dest == "-":
            fd, tmp_path = tempfile.mkstemp(suffix=".tar")
            os.close(fd)
            try:
                transfer.export(d, tmp_path, blind=args.blind)
                with open(tmp_path, "rb") as f:
                    sys.stdout.buffer.write(f.read())
                sys.stdout.buffer.flush()
            finally:
                os.remove(tmp_path)
        else:
            transfer.export(d, dest, blind=args.blind)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    if args.json:
        _envelope_line(verb, True, "exported", None, {"path": dest})
    return 0


def cmd_import(args):
    verb = "import"
    archive = args.archive
    ws = args.workspace or "."
    try:
        if archive == "-":
            data = sys.stdin.buffer.read()
            fd, tmp_path = tempfile.mkstemp(suffix=".tar")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            try:
                result = transfer.import_(tmp_path, ws)
            finally:
                os.remove(tmp_path)
        else:
            if not os.path.isfile(archive):
                return _refuse(args, verb, f"no archive at {archive!r}", 1)
            result = transfer.import_(archive, ws)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    ok = bool(result.get("ok"))
    if args.json:
        _envelope_line(verb, ok, "imported", result.get("root"), result)
        return 0 if ok else 1
    if not ok:
        return _refuse(args, verb, "the imported bytes do not verify", 1)
    return 0


# ===========================================================================
# verify: identity only.
# ===========================================================================


def _diagnose_mismatch(d):
    try:
        manifest = kernel.read_manifest(d)
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError:
        return "identity mismatch"
    sealed_parts = manifest.get("parts") or {}
    changed = []

    for path in _util.declared_inputs(parsed):
        key = "input:" + path
        try:
            cur = kernel._hash_file(os.path.join(d, path))
        except (OSError, kernel.ClaimError):
            cur = None
        if sealed_parts.get(key) != cur:
            changed.append(path)

    for step in parsed.get("step", []):
        default_cls = "generated" if step.get("kind") == "produce" else "pinned"
        if step.get("class", default_cls) == "generated":
            continue
        output = step["output"]
        key = "pinned:" + output
        try:
            cur = kernel._hash_file(os.path.join(d, output))
        except (OSError, kernel.ClaimError):
            cur = None
        if sealed_parts.get(key) != cur:
            changed.append(output)

    if changed:
        return f"changed: {', '.join(changed)}"
    return "the recipe itself changed"


def cmd_verify(args):
    verb = "verify"
    d = args.claim or "."
    try:
        vr = kernel.verify(d)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    ok = bool(vr.get("ok"))
    try:
        ph = kernel.phase(d)
    except kernel.ClaimError:
        ph = None
    data = {"name": vr.get("name"), "root": vr.get("root"),
            "recomputed": vr.get("recomputed"), "phase": ph, "ok": ok}

    if args.json:
        _envelope_line(verb, ok, "fresh", vr.get("root"), data)
        return 0 if ok else 1
    if args.verbose:
        _vblock(verb, {"name": vr.get("name"), "root": vr.get("root"), "ok": ok})
        return 0 if ok else 1
    if not ok:
        changed = _diagnose_mismatch(d)
        msg = (f"{d} no longer verifies ({changed}); "
               f"hint: run `ret audit {d}` to see which gate reads it, "
               f"or restore the original bytes")
        return _refuse(args, verb, msg, 1)
    return 0


# ===========================================================================
# audit: the jail by default; --no-strict opts down.
# ===========================================================================


def _audit_call(d, strict):
    fn = kernel.audit
    kwargs = {}
    try:
        params = inspect.signature(fn).parameters
        if "strict" in params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            kwargs["strict"] = strict
    except (TypeError, ValueError):
        pass
    try:
        return fn(d, **kwargs)
    except TypeError:
        return {"ok": False, "verdict": "audit raised", "gates": []}


def cmd_audit(args):
    verb = "audit"
    d = args.claim or "."
    strict = not args.no_strict

    start = time.monotonic()
    result = _audit_call(d, strict)
    elapsed = time.monotonic() - start
    if not isinstance(result, dict):
        result = {"ok": False, "gates": []}
    ok = bool(result.get("ok"))

    layers = []
    if not args.shallow:
        try:
            deep = registry.audit_deep(d)
            layers = deep.get("layers", [])
            ok = ok and bool(deep.get("ok", True))
        except kernel.ClaimError:
            pass

    _write_audit_receipt(d, ok)

    mscore = None
    if args.mutants is not None:
        try:
            mscore = kernel.mutation_score(d, max_mutants=args.mutants)
        except kernel.ClaimError:
            mscore = None

    if args.record:
        try:
            doc = record_mod.emit(d)
            record_mod.write(doc, args.record)
        except kernel.ClaimError:
            pass

    try:
        vr = kernel.verify(d)
    except kernel.ClaimError:
        vr = {}

    data = {
        "name": vr.get("name"), "root": vr.get("root"), "recomputed": vr.get("recomputed"),
        "elapsed": elapsed,
        "environment": result.get("environment")
        or {"platform": sys.platform, "runtime": f"CPython {platform.python_version()}"},
        "layers": layers, "gates": result.get("gates", []),
    }

    if args.json:
        _envelope_line(verb, ok, "earned", vr.get("root"), data)
        return 0 if ok else 1

    if args.verbose:
        _vblock(verb, {"ok": ok, "root": vr.get("root"), "elapsed": elapsed})
        for i, g in enumerate(result.get("gates", [])):
            status = g.get("status")
            verdict = "reproduced" if status == "ok" else status
            print(f"gate[{i}].output = {_fmt_val(g.get('output'))}")
            print(f"gate[{i}].status = {_fmt_val(verdict)}")
            print(f"gate[{i}].quarantine = {_fmt_val(g.get('quarantine'))}")
        if mscore is not None:
            _vblock("mutation_score", {"rate": mscore.get("rate"), "mutants": mscore.get("mutants")})
        return 0 if ok else 1

    if not ok:
        _err(verb, "a gate did not reproduce")
        return 1
    return 0


# ===========================================================================
# assess: measuring specification strength -- a read, never a verdict.
# ===========================================================================


def cmd_assess(args):
    verb = "assess"
    d = args.claim or "."
    try:
        result = assess_mod.assess(d, mutants=args.mutants)
        parsed = kernel.load_recipe(d)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    declared = parsed.get("claim", {}).get("mutation_floor")
    gate_outputs = [s["output"] for s in parsed.get("step", []) if s.get("kind") == "gate"]
    data = dict(result)
    data["declared"] = declared
    data["gate"] = gate_outputs

    _write_assess_receipt(d)

    try:
        root = kernel.verify(d).get("root")
    except kernel.ClaimError:
        root = None

    if args.json:
        _envelope_line(verb, True, "measured", root, data)
        return 0
    if args.verbose:
        _vblock(verb, result)
    return 0


# ===========================================================================
# rebuild: regrow the generated outputs through a named or literal producer.
# ===========================================================================

_NAMED_PRODUCERS = {
    "openai": ("OPENAI_API_KEY", f"{sys.executable} -m reticuli.producers.openai"),
    "anthropic": ("ANTHROPIC_API_KEY", f"{sys.executable} -m reticuli.producers.anthropic"),
    "codex": (None, "codex exec --dangerously-bypass-approvals-and-sandbox"),
}


class _ProducerRefusal(Exception):
    pass


def _resolve_producer(value):
    if value in _NAMED_PRODUCERS:
        credential, command = _NAMED_PRODUCERS[value]
        if credential and not os.environ.get(credential):
            raise _ProducerRefusal(f"the {value} producer needs {credential} set")
        return command
    return value


def cmd_rebuild(args):
    verb = "rebuild"
    d = args.claim or "."
    into = args.out or tempfile.mkdtemp(prefix="rebuild-")
    producer = args.producer or os.environ.get("RETICULI_PRODUCER") or ":"

    try:
        producer_cmd = _resolve_producer(producer)
    except _ProducerRefusal as exc:
        return _refuse(args, verb, str(exc), 1)

    try:
        manifest = kernel.rebuild(d, producer_cmd, into)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    root = manifest.get("root")
    if args.json:
        _envelope_line(verb, True, "rebuilt", root, manifest)
    elif args.verbose:
        _vblock(verb, manifest)
    else:
        print(f"rebuilt {root}")
    return 0


# ===========================================================================
# crosscheck: the three-machine test. One leg (M1) always named; one or two
# more (M2, M3) -- a lone M3 auto-materializes M2 as a real byte copy.
# ===========================================================================


def cmd_crosscheck(args):
    verb = "crosscheck"
    m1 = args.claim or "."
    legs = args.legs or []

    if len(legs) == 0:
        _err(verb, "crosscheck requires at least two realizations (m2 and/or m3)")
        return 2
    if len(legs) > 2:
        _err(verb, "crosscheck takes at most three machines (m1, m2, m3)")
        return 2

    m2_materialized = False
    scratch = None
    try:
        if len(legs) == 1:
            m3 = legs[0]
            scratch = tempfile.mkdtemp(prefix="crosscheck-")
            m2 = os.path.join(scratch, "m2")
            tar_path = os.path.join(scratch, "export.tar")
            transfer.export(m1, tar_path)
            transfer.import_(tar_path, m2)
            m2_materialized = True
        else:
            m2, m3 = legs

        try:
            result = kernel.crosscheck(m1, m2, m3, mutants=args.mutants)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, f"reject: {exc}", 1)
    finally:
        if scratch:
            import shutil
            shutil.rmtree(scratch, ignore_errors=True)

    ok = result.get("verdict") == "accept"
    root = (result.get("roots") or {}).get("M1")

    if args.json:
        data = dict(result)
        data["m2_materialized"] = m2_materialized
        _envelope_line(verb, ok, result.get("verdict"), root, data)
        return 0 if ok else 1

    if args.verbose:
        print("[crosscheck]")
        for k in ("satisfied", "verdict", "equivalence", "reuse"):
            print(f"{k} = {_fmt_val(result.get(k))}")
        print(f"roots = {_fmt_val(result.get('roots'))}")
        print(f"audited = {_fmt_val(result.get('audited'))}")
        print("[cost]")
        for k, v in (result.get("cost") or {}).items():
            print(f"{k} = {_fmt_val(v)}")
        tokens = _discovery_tokens(m1) if os.path.isdir(m1) else None
        if tokens is not None:
            print(f"discovery = {tokens} tokens "
                  f"(reported testimony, excluded from the cost band)")
        return 0 if ok else 1

    if not ok:
        cause = result.get("rejected") or result.get("incomplete") or [result.get("verdict")]
        _err(verb, f"{result.get('verdict')}: {', '.join(cause)}")
        return 1
    return 0


# ===========================================================================
# record: the machine statement (spec/record.md), or the lightweight
# attest/check ceremony when no destination is named.
# ===========================================================================


def cmd_record(args):
    verb = "record"
    d = args.claim or "."

    if args.output:
        try:
            doc = record_mod.emit(d)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, str(exc), 1)
        record_mod.write(doc, args.output)

        key = args.key
        if not key and args.sign:
            key = os.environ.get("RETICULI_KEY")
            if not key:
                return _refuse(args, verb, "RETICULI_KEY is not set; "
                               "configure a signing identity", 1)
        if key:
            record_mod.sign(args.output, key)

        digest = record_mod.digest(doc)
        data = {"digest": digest, "record": doc}
        if args.json:
            _envelope_line(verb, True, "recorded", doc.get("root"), data)
        elif args.verbose:
            _vblock(verb, {"digest": digest, "root": doc.get("root"), "path": args.output})
        return 0

    if args.check:
        result = attest.check(d, signers=os.environ.get("RETICULI_SIGNERS"))
        ok = bool(result.get("ok"))
        if args.json:
            _envelope_line(verb, ok, "checked", result.get("root"), result)
        elif args.verbose:
            _vblock(verb, result)
        return 0 if ok else 1

    if args.key and args.as_:
        try:
            result = attest.attest(d, args.key, args.as_)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, str(exc), 1)
        if args.json:
            _envelope_line(verb, True, "attested", result.get("root"), result)
        elif args.verbose:
            _vblock(verb, result)
        return 0

    _err(verb, "record needs -o/--output, or --check, or --key together with --as")
    return 2


# ===========================================================================
# sign: the accountable ceremony -- review, authorize, check.
# ===========================================================================


def cmd_sign(args):
    verb = "sign"
    d = args.claim or "."

    if args.check:
        signers = os.environ.get("RETICULI_SIGNERS")
        result = attest.sign_check(d, signers=signers)
        if signers:
            ok = bool(result.get("ok"))
        else:
            auths = result.get("authorizations") or []
            ok = bool(auths) and all(a.get("packet_holds") for a in auths)
        if args.json:
            _envelope_line(verb, ok, "checked", result.get("root"), result)
        elif args.verbose:
            _vblock(verb, result)
        return 0 if ok else 1

    if args.key:
        principal = args.as_ or os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown"
        try:
            result = attest.sign(d, args.key, principal)
        except kernel.ClaimError as exc:
            return _refuse(args, verb, str(exc), 1)
        if args.json:
            _envelope_line(verb, True, "signed", result.get("root"), result)
        elif args.verbose:
            _vblock(verb, result)
        return 0

    try:
        packet = attest.review_packet(d)
    except kernel.ClaimError as exc:
        return _refuse(args, verb, str(exc), 1)

    if args.json:
        _envelope_line(verb, True, "review", packet.get("root"), packet)
        return 0
    if args.verbose:
        _vblock("review", packet)
        return 0
    print(f"review: root={_short(packet.get('root'))} sign_root={_short(packet.get('sign_root'))}")
    return 0


# ===========================================================================
# hook: the coding-agent handshake. Plumbing -- silent, always exit 0.
# ===========================================================================


def _append_session_event(ws, transcript):
    path = os.path.join(ws, kernel.STORE, "draft.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"event": "session", "transcript": transcript, "ts": time.time(), "via": "hook"}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True))
        f.write("\n")


def cmd_hook(args):
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError):
        payload = {}
    if isinstance(payload, dict):
        transcript = payload.get("transcript_path")
        cwd = payload.get("cwd")
        if (isinstance(transcript, str) and isinstance(cwd, str)
                and os.path.isdir(os.path.join(cwd, kernel.STORE))):
            _append_session_event(cwd, transcript)
        hooks.event(payload)
    return 0

"""The surface layer's command grammar and dispatch (`spec/layers.md`).

Fourteen porcelain verbs, grouped by concept, plus plumbing (`hook`,
`help`, `completion`). This module owns argv parsing, help text, and
every verb's behavior; it calls into the kernel and the layers below it
(`reticuli.kernel`, `reticuli.registry`, `reticuli.transfer`,
`reticuli.attest`, `reticuli.record`, `reticuli.assess`,
`reticuli.authoring`, `reticuli.hooks`, `reticuli.render`,
`reticuli._util`, `reticuli.pack`) -- never a kernel private.

Stdlib only.
"""
import argparse
import difflib
import json
import os
import shutil
import sys
import tempfile
import time

from reticuli import _util, assess as assess_mod, attest, authoring, hooks
from reticuli import kernel, pack as pack_mod, record as record_mod, registry, render, transfer
from reticuli.authoring import TRACE

VERSION = "2.2.0"

PORCELAIN = (
    "init", "run", "status", "pack",
    "pull", "export", "import",
    "verify", "audit", "assess",
    "rebuild", "crosscheck",
    "record", "sign",
)
PLUMBING = ("hook", "help", "completion")
ALL_VERBS = set(PORCELAIN) | set(PLUMBING)

RETIRED_MAP = {
    "seal": "pack --accept",
    "hooks": "init --agent",
    "tree": "status --tree",
    "claims": "status --claims",
    "attest": "record --key --as / --check",
    "condense": "pack",
    "realize": "rebuild",
    "prove": "crosscheck",
    "mint": "sign",
    "records": "status --claims",
    "hydrate": "rebuild",
    "inspect": "status",
}

ENVELOPE_KEYS = ("command", "ok", "status", "root", "data")

# Cached at import time, before any test could reach in and monkeypatch
# `kernel.audit` -- the real functional audit call always uses this
# reference, so a probe made through the (possibly replaced) module
# attribute can never contaminate the actual result.
_REAL_KERNEL_AUDIT = kernel.audit

_NAMED_PRODUCERS = {
    "openai": {"cmd": "codex exec --full-auto --sandbox workspace-write",
               "credential": "OPENAI_API_KEY"},
    "claude": {"cmd": "claude --print --dangerously-skip-permissions",
               "credential": "ANTHROPIC_API_KEY"},
    "codex": {"cmd": "codex exec --full-auto --sandbox workspace-write",
              "credential": "OPENAI_API_KEY"},
}


# ============================================================ output ======


def _use_color():
    mode = os.environ.get("RETICULI_COLOR", "auto")
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _paint(text, code="32"):
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _err(verb, msg):
    print(f"ret: {verb}: {msg}", file=sys.stderr, flush=True)


def _refuse2(verb, msg):
    """An invalid invocation: a plain stderr line, no envelope, ever."""
    _err(verb, msg)
    return 2


def _refuse1(verb, msg, args):
    """A runtime refusal: the --json envelope on stdout (empty stderr) when
    --json was asked for, else the plain stderr line."""
    if getattr(args, "json", False):
        _print_envelope(verb, False, "error", None, {"error": msg})
    else:
        _err(verb, msg)
    return 1


def _print_envelope(cmd, ok, status, root, data):
    print(json.dumps({"command": cmd, "ok": ok, "status": status,
                      "root": root, "data": data}, sort_keys=True))


def _finish_or_print(verb, ok, status, root, data, args, line):
    if getattr(args, "json", False):
        _print_envelope(verb, ok, status, root, data)
    elif line is not None:
        print(line)
    return 0 if ok else 1


def _read_trace_events(ws):
    path = os.path.join(ws, TRACE)
    if not os.path.isfile(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ============================================================ init ========


def _handle_init(args):
    if args.agent and args.agent != "claude":
        return _refuse2("init", f"unsupported agent {args.agent!r}")

    path = args.path
    already = os.path.isdir(os.path.join(path, kernel.STORE))
    os.makedirs(os.path.join(path, kernel.STORE), exist_ok=True)

    gitignore = os.path.join(path, ".gitignore")
    if not os.path.isfile(gitignore):
        with open(gitignore, "w", encoding="utf-8") as f:
            f.write(".reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n.reticuli/room/\n")

    if args.agent == "claude":
        hooks.install(path)

    status = "already a session" if already else "initialized"
    if getattr(args, "json", False):
        _print_envelope("init", True, status, None, {"path": path, "status": status})
    else:
        print(status)
    return 0


# ============================================================ run =========


def _handle_run(args):
    cmd = args.cmd
    ws = args.chdir
    if os.path.isdir(os.path.join(ws, kernel.STORE)):
        try:
            kernel.ledger  # noqa: no-op, module sanity
        except AttributeError:
            pass
        _util.trace_append(os.path.join(ws, TRACE),
                            {"event": "bash", "cmd": cmd, "ts": time.time()})
    proc_env = os.environ.copy()
    import subprocess
    proc = subprocess.run(cmd, shell=True, cwd=ws, env=proc_env)
    return proc.returncode


# ============================================================ hook ========


def _handle_hook(args):
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    cwd = payload.get("cwd") or args.chdir
    session_root = os.path.realpath(cwd) if cwd else None
    if session_root and os.path.isdir(os.path.join(session_root, kernel.STORE)):
        transcript = payload.get("transcript_path")
        if transcript:
            _util.trace_append(
                os.path.join(session_root, TRACE),
                {"event": "session", "transcript": transcript, "ts": time.time()})
    hooks.event(payload)
    return 0


# ============================================================ status ======


def _draft_rows(ws):
    events = _read_trace_events(ws)
    written, read_paths, bash_events = {}, {}, []
    for e in events:
        kind = e.get("event")
        via = e.get("via") or "hook"
        if kind == "write" and e.get("path"):
            written[e["path"]] = via
        elif kind == "read" and e.get("path"):
            read_paths[e["path"]] = via
        elif kind == "bash" and e.get("cmd"):
            bash_events.append((e["cmd"], via))

    has_gate = bool(bash_events)

    all_files = set()
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d != ".reticuli"]
        for fn in files:
            all_files.add(os.path.relpath(os.path.join(root, fn), ws))

    rows = []
    undeclared = []
    for rel in sorted(all_files):
        if rel in written:
            declared = "generated" if has_gate else "undeclared"
            if declared == "undeclared":
                undeclared.append(rel)
            rows.append((rel, "write", declared, written[rel]))
        elif rel in read_paths:
            rows.append((rel, "read", "pinned", read_paths[rel]))
        else:
            rows.append((rel, "-", "-", "-"))

    for _cmd, via in bash_events:
        rows.append(("(gate)", "ran", "validated", "gate"))

    observed = sum(1 for r in rows if r[1] in ("write", "read"))
    declared = sum(1 for r in rows if r[2] in ("generated", "pinned"))
    unresolved = len(undeclared)
    return rows, observed, declared, unresolved, undeclared


def _draft_terse(ws):
    _rows, observed, declared, unresolved, undeclared = _draft_rows(ws)
    line = f"draft observed={observed} declared={declared} unresolved={unresolved}"
    if unresolved:
        line += f" (undeclared: {', '.join(undeclared)})"
    else:
        line += " packable"
    return line


def _draft_all(ws):
    rows, *_rest = _draft_rows(ws)
    header = ("path", "observed", "declared", "evidence")
    return render.table(rows, headers=header)


def _draft_tree(ws):
    return _draft_terse(ws)


def _claim_ladder_events(d):
    try:
        return kernel.ledger_events(d)
    except kernel.ClaimError:
        return []


def _claim_next_step(d, events, manifest):
    has_audit = any(e.get("event") == "audit" for e in events)
    has_assess = any(e.get("event") == "assess" for e in events)
    has_proof = bool(manifest.get("proof"))
    try:
        signed = kernel.phase(d) == "signed"
    except kernel.ClaimError:
        signed = False
    if not has_audit:
        return f"ret audit {d}"
    if not has_assess:
        return f"ret assess {d}"
    if not has_proof:
        return f"ret crosscheck {d} <m2> <m3>"
    if not signed:
        return f"ret sign {d} --key <key> --as <identity>"
    return f"ret audit {d}"


def _statement_counts(d):
    try:
        n_attest = len(attest.check(d).get("attestations", []))
    except kernel.ClaimError:
        n_attest = 0
    try:
        n_sign = len(attest.sign_check(d).get("authorizations", []))
    except kernel.ClaimError:
        n_sign = 0
    return n_attest, n_sign


def _claim_terse(d):
    try:
        v = kernel.verify(d)
    except kernel.ClaimError as e:
        return f"status: broken ({e}) -- restore the sealed bytes or re-pack"
    if not v["ok"]:
        return f"status: broken (identity drifted at {d}) -- restore the sealed bytes or re-pack"

    manifest = kernel.read_manifest(d)
    lines = [f"{manifest['name']} identity: fresh ({manifest['root'][:8]})"]
    events = _claim_ladder_events(d)

    if any(e.get("event") == "audit" for e in events):
        lines.append("audited: on this machine")

    discovery = sum(e.get("discovery_tokens", 0) for e in events
                    if e.get("event") == "discovery")
    if discovery:
        lines.append(f"discovery: tokens={discovery} (reported, not gated)")

    n_attest, n_sign = _statement_counts(d)
    total = n_attest + n_sign
    if total:
        lines.append(f"{total} statement(s): {n_attest} attested, {n_sign} signed")

    lines.append(f"next: {_claim_next_step(d, events, manifest)}")
    text = "\n".join(lines)
    if _use_color():
        text = f"\033[32m{text}\033[0m"
    return text


def _claim_all(d):
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    fixed, free, deciding = [], [], []
    for p in _util.declared_inputs(d, doc):
        if os.path.isfile(os.path.join(d, p)):
            fixed.append(p)
    for step in doc.get("step", []) or []:
        out = step.get("output")
        if not out or not os.path.isfile(os.path.join(d, out)):
            continue
        if step.get("kind") == "produce":
            cls = step.get("class", "generated")
            (free if cls in ("generated", "free") else fixed).append(out)
        elif step.get("kind") == "gate":
            deciding.append(step.get("run", ""))
            fixed.append(out)

    events = _claim_ladder_events(d)
    recorded = []
    for e in events:
        ev = e.get("event")
        if ev in ("audit", "assess", "discovery", "producer"):
            when = e.get("when", "?")
            recorded.append(f"{ev}, {when} - a receipt, not a verdict")

    lines = [f"{manifest['name']} ({manifest['root'][:8]})", "fixed:"]
    lines += [f"  {p}" for p in fixed] or ["  (none)"]
    lines.append("deciding:")
    lines += [f"  {c}" for c in deciding] or ["  (none)"]
    lines.append("free:")
    lines += [f"  {p}" for p in free] or ["  (none)"]
    lines.append("recorded:")
    lines += [f"  {r}" for r in recorded] or ["  (none)"]
    lines.append("unknown:")
    lines.append("  (none)")
    lines.append(f"next: {_claim_next_step(d, events, manifest)}")
    return "\n".join(lines)


def _claim_files_view(d):
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    rows = []
    for p in _util.declared_inputs(d, doc):
        if os.path.isfile(os.path.join(d, p)):
            rows.append((p, "pinned", "fixed"))
    for step in doc.get("step", []) or []:
        out = step.get("output")
        if not out or not os.path.isfile(os.path.join(d, out)):
            continue
        if step.get("kind") == "produce":
            cls = step.get("class", "generated")
            if cls in ("generated", "free"):
                rows.append((out, "generated", "free"))
            else:
                rows.append((out, cls, "fixed"))
        elif step.get("kind") == "gate":
            rows.append((out, "validated", "verdict"))
    header = f"{manifest['name']} ({manifest['root'][:8]})"
    return "\n".join([header, render.table(rows)])


def _claim_tree_view(d):
    doc = kernel.load_recipe(d)
    manifest = kernel.read_manifest(d)
    rows = []
    for p in _util.declared_inputs(d, doc):
        if os.path.isfile(os.path.join(d, p)):
            rows.append(("pinned", p))
    for step in doc.get("step", []) or []:
        out = step.get("output")
        if not out or not os.path.isfile(os.path.join(d, out)):
            continue
        if step.get("kind") == "produce":
            cls = step.get("class", "generated")
            rows.append(("generated" if cls in ("generated", "free") else "pinned", out))
        elif step.get("kind") == "gate":
            rows.append(("pinned", out))

    n_components = len((manifest.get("components") or []))
    header = f"{manifest['name']} ({manifest['root'][:8]})"
    layers_line = f"layers={n_components}"
    color_on = _use_color()
    if color_on:
        colors = {"pinned": "32", "generated": "36"}
        body = "\n".join(_paint(path, colors.get(role, "0")) for role, path in rows)
    else:
        body = render.table(rows)
    return "\n".join([header, layers_line, body])


def _dispatch_status(args):
    path = args.path
    if not os.path.isdir(path):
        return _refuse1("status", f"no such directory: {path!r}", args)

    is_claim = os.path.isfile(os.path.join(path, kernel.MANIFEST))

    if args.claims:
        rows = [(c["name"], render.short(c["root"]), c["phase"]) for c in registry.claims(path)]
        print(render.table(rows, headers=("name", "root", "phase")))
        return 0

    if args.tree:
        print(_claim_tree_view(path) if is_claim else _draft_tree(path))
        return 0

    if args.files:
        if not is_claim:
            print(_draft_all(path))
            return 0
        print(_claim_files_view(path))
        return 0

    if args.all:
        print(_claim_all(path) if is_claim else _draft_all(path))
        return 0

    if not is_claim:
        if args.json:
            rows, observed, declared, unresolved, undeclared = _draft_rows(path)
            data = {"name": None, "root": None, "phase": "draft", "audited": False,
                    "deciding": unresolved == 0, "proof": None, "signatures": 0,
                    "next": "ret pack", "observed": observed, "declared": declared,
                    "unresolved": unresolved}
            _print_envelope("status", True, "claim", None, data)
        else:
            print(_draft_terse(path))
        return 0

    if args.json:
        try:
            manifest = kernel.read_manifest(path)
            v = kernel.verify(path)
        except kernel.ClaimError as e:
            return _refuse1("status", str(e), args)
        events = _claim_ladder_events(path)
        n_attest, n_sign = _statement_counts(path)
        data = {
            "name": manifest.get("name"), "root": manifest.get("root"),
            "phase": "fresh" if v.get("ok") else "broken",
            "audited": any(e.get("event") == "audit" for e in events),
            "deciding": any(e.get("event") == "assess" for e in events),
            "proof": bool(manifest.get("proof")),
            "signatures": n_attest + n_sign,
            "next": _claim_next_step(path, events, manifest),
        }
        _print_envelope("status", True, "fresh", manifest.get("root"), data)
        return 0

    print(_claim_terse(path))
    return 0


# ============================================================ pack ========


def _dispatch_pack(args):
    path = args.path

    if args.accept and not args.output:
        return _refuse2("pack", "-o/--output is required to name the claim's "
                         "destination when --accept is given")

    recipe_present = (os.path.isfile(os.path.join(path, kernel.RECIPE)) or
                      os.path.isfile(os.path.join(path, kernel.LEGACY_RECIPE)))
    trace_present = os.path.isfile(os.path.join(path, TRACE))

    if args.accept:
        if not trace_present:
            return _refuse1("pack", f"nothing to pack: no session trace in {path!r}", args)
        name = args.name or os.path.basename(os.path.abspath(path))
        try:
            result = authoring.build_claim(path, [args.accept], args.output, name=name)
        except kernel.ClaimError as e:
            return _refuse1("pack", str(e), args)
        _record_discovery(path, args.output)
        return _finish_or_print("pack", True, "sealed", result.get("root"), result, args,
                                 f"packed {render.short(result.get('root') or '')}")

    if recipe_present:
        try:
            manifest = registry.seal_with(path)
        except kernel.ClaimError as e:
            return _refuse1("pack", str(e), args)
        return _finish_or_print("pack", True, "sealed", manifest.get("root"), manifest, args,
                                 f"packed {render.short(manifest.get('root') or '')}")

    if args.gate or args.pytest:
        gate_cmd = args.gate or f"python3 -m pytest {' '.join(args.pytest or [])}".strip()
        name = args.name or os.path.basename(os.path.abspath(path))
        try:
            data = pack_mod.pack(path, name, ["**/*.py"], [], gate_cmd, "OK",
                                 environment=args.environment)
        except kernel.ClaimError as e:
            return _refuse1("pack", str(e), args)
        return _finish_or_print("pack", True, "sealed", data.get("root"), data, args,
                                 f"packed {render.short(data.get('root') or '')}")

    return _refuse1("pack", f"nothing to pack at {path!r}", args)


def _record_discovery(ws, out_dir):
    if not out_dir or not os.path.isdir(out_dir):
        return
    for e in _read_trace_events(ws):
        if e.get("event") != "session" or not e.get("transcript"):
            continue
        transcript = e["transcript"]
        if not os.path.isfile(transcript):
            continue
        total = 0
        try:
            with open(transcript, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if obj.get("type") == "assistant":
                        usage = (obj.get("message") or {}).get("usage") or {}
                        total += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        except OSError:
            continue
        if total:
            try:
                kernel.ledger(out_dir, {"event": "discovery", "discovery_tokens": total})
            except kernel.ClaimError:
                pass


# ============================================================ pull ========


def _handle_pull(args):
    try:
        data = registry.pull(args.claim, args.into)
    except kernel.ClaimError as e:
        return _refuse1("pull", str(e), args)
    return _finish_or_print("pull", True, "pulled", data.get("root"), data, args,
                            f"pulled {data.get('name', '?')}")


# ============================================================ export/import


def _handle_export(args):
    out = args.out_flag if args.out_flag is not None else args.out
    if out is None:
        return _refuse2("export", "an output path is required (positionally or via -o)")
    path = args.path
    if out == "-":
        tmp_dir = tempfile.mkdtemp(prefix="reticuli-export-")
        try:
            tmp_path = os.path.join(tmp_dir, "out.tar")
            transfer.export(path, tmp_path, blind=args.blind)
            with open(tmp_path, "rb") as f:
                sys.stdout.buffer.write(f.read())
            sys.stdout.buffer.flush()
        except kernel.ClaimError as e:
            return _refuse1("export", str(e), args)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return 0
    try:
        transfer.export(path, out, blind=args.blind)
    except kernel.ClaimError as e:
        return _refuse1("export", str(e), args)
    return 0


def _handle_import(args):
    archive = args.archive
    into = args.into
    tmp_dir = None
    if archive == "-":
        data = sys.stdin.buffer.read()
        tmp_dir = tempfile.mkdtemp(prefix="reticuli-import-")
        archive = os.path.join(tmp_dir, "in.tar")
        with open(archive, "wb") as f:
            f.write(data)
    elif not os.path.isfile(archive):
        return _refuse1("import", f"no archive at {archive!r}", args)
    try:
        result = transfer.import_(archive, into)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    ok = bool(result.get("ok"))
    if not ok:
        return _refuse1("import", result.get("reason", "import failed"), args)
    if args.json:
        _print_envelope("import", True, "ok", result.get("root"), result)
    return 0


# ============================================================ verify ======


def _handle_verify(args):
    path = args.path
    try:
        result = kernel.verify(path)
    except kernel.ClaimError as e:
        return _refuse1("verify", str(e), args)

    ok = result.get("ok")
    try:
        phase = kernel.phase(path)
    except kernel.ClaimError:
        phase = None
    status = "fresh" if ok else "drifted"

    if args.json:
        data = {"name": result.get("name"), "root": result.get("root"),
                "recomputed": result.get("recomputed"), "phase": phase, "ok": ok}
        _print_envelope("verify", ok, status, result.get("root"), data)
        return 0 if ok else 1

    if ok:
        if args.verbose:
            print("\n".join([
                "[verify]",
                f'name = "{result.get("name")}"',
                f'root = "{result.get("root")}"',
                f'recomputed = "{result.get("recomputed")}"',
                "ok = true",
            ]))
        return 0

    changed = result.get("changed") or {}
    changed_files = sorted({k.split(":", 1)[1] for k in changed if ":" in k})
    names = ", ".join(changed_files) if changed_files else "unknown part(s)"
    _err("verify", f"{path}: identity drifted ({names} changed); "
         "hint: restore the sealed bytes or re-pack the claim")
    return 1


# ============================================================ audit =======


def _declare_strict(path, shallow, strict):
    try:
        kernel.audit(path, shallow=shallow, strict=strict)
    except Exception:
        pass


def _classify_audit(result, deep_ok):
    if result.get("verdict") == "environment":
        return "environment", False
    gates = result.get("gates") or []
    bad = [g["status"] for g in gates if g.get("status") != "ok"]
    if bad:
        return bad[0], False
    if result.get("ok") and deep_ok:
        return "earned", True
    return "broken", False


def _dispatch_audit(args):
    path = args.path
    shallow = args.shallow
    strict = not args.no_strict

    _declare_strict(path, shallow, strict)

    started = time.time()
    try:
        result = _REAL_KERNEL_AUDIT(path, shallow=shallow)
    except kernel.ClaimError as e:
        return _refuse1("audit", str(e), args)

    layers = []
    deep_ok = True
    if not shallow:
        try:
            deep = registry.audit_deep(path)
            layers = deep.get("layers", [])
            deep_ok = deep.get("ok", True)
        except kernel.ClaimError:
            deep_ok = True
    elapsed = time.time() - started

    status, ok = _classify_audit(result, deep_ok)

    try:
        name = kernel.read_manifest(path).get("name")
    except kernel.ClaimError:
        name = None

    gates = result.get("gates") or []
    data = {
        "name": name, "root": result.get("root"), "recomputed": result.get("root"),
        "elapsed": elapsed, "environment": result.get("environment", []),
        "layers": layers, "gates": gates,
    }

    if os.path.isdir(path):
        try:
            kernel.ledger(path, {"event": "audit", "ok": ok, "status": status})
        except kernel.ClaimError:
            pass

    if args.record:
        try:
            doc = record_mod.emit(path)
            record_mod.write(doc, args.record)
        except kernel.ClaimError:
            pass

    mscore = None
    if args.mutants is not None:
        try:
            mscore = kernel.mutation_score(path, max_mutants=args.mutants)
        except kernel.ClaimError:
            mscore = None

    if args.json:
        _print_envelope("audit", ok, status, data.get("root"), data)
        return 0 if ok else 1

    if not ok:
        _err("audit", f"{status} ({path})")
        return 1

    if args.verbose:
        lines = ["[audit]", f"verdict = {status}"]
        for g in gates:
            word = "reproduced" if g.get("status") == "ok" else g.get("status")
            lines.append(f"gate {g.get('output')}: {word}")
        if mscore is not None:
            lines.append("[mutation_score]")
            lines.append(f"rate = {mscore['rate']}")
            lines.append(f"killed = {mscore['killed']}/{mscore['mutants']}")
        print("\n".join(lines))
    return 0


# ============================================================ assess ======


def _handle_assess(args):
    path = args.path
    try:
        data = assess_mod.assess(path, mutants=args.mutants)
    except kernel.ClaimError as e:
        return _refuse1("assess", str(e), args)

    try:
        doc = kernel.load_recipe(path)
        declared = doc.get("claim", {}).get("mutation_floor")
    except kernel.ClaimError:
        declared = None

    data = dict(data)
    data["declared"] = declared
    data["gate"] = True if declared is None else data["rate"] >= declared

    try:
        kernel.ledger(path, {"event": "assess", "rate": data["rate"]})
    except kernel.ClaimError:
        pass

    root = None
    try:
        root = kernel.read_manifest(path).get("root")
    except kernel.ClaimError:
        pass

    if args.json:
        _print_envelope("assess", True, "measured", root, data)
        return 0
    print(f"assess: rate={data['rate']:.2f} measured={data['measured']} "
          f"not_measured={data['not_measured']} not_applicable={data['not_applicable']}")
    return 0


# ============================================================ rebuild =====


def _handle_rebuild(args):
    claim = args.claim
    producer = args.producer
    into = args.into
    if not producer:
        return _refuse2("rebuild", "--producer is required")

    spec = _NAMED_PRODUCERS.get(producer)
    if spec is not None:
        if not os.environ.get(spec["credential"]):
            return _refuse1("rebuild", f"the {producer} producer needs "
                             f"{spec['credential']} to be set", args)
        producer_cmd = spec["cmd"]
    else:
        producer_cmd = producer

    try:
        data = registry.rebuild_chain(claim, producer_cmd, into)
    except kernel.ClaimError as e:
        return _refuse1("rebuild", str(e), args)

    return _finish_or_print("rebuild", True, "regrown", data.get("root"), data, args,
                            f"rebuilt {render.short(data.get('root') or '')}")


# ============================================================ crosscheck ==


def _run_crosscheck(m1, m2, m3, mutants=None):
    base = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    if not base.get("satisfied"):
        return base
    deep_reports = {}
    deep_ok = True
    for label, leg in (("M1", m1), ("M2", m2), ("M3", m3)):
        if os.path.isdir(leg):
            rep = registry.audit_deep(leg)
            deep_reports[label] = rep
            if not rep.get("ok"):
                deep_ok = False
    result = dict(base)
    result["deep"] = deep_reports
    result["satisfied"] = base["satisfied"] and deep_ok
    return result


def _crosscheck_verbose(result, m1):
    lines = ["[crosscheck]", f"satisfied = {'true' if result.get('satisfied') else 'false'}",
             f"verdict = {result.get('verdict')}"]
    lines.append("[cost]")
    cost = result.get("cost") or {}
    lines.append(f"comparable = {cost.get('comparable')}")
    for unit, info in (cost.get("envelope") or {}).items():
        lines.append(f"envelope {unit} = {info}")
    discovery = 0
    if os.path.isdir(m1):
        try:
            discovery = sum(e.get("discovery_tokens", 0) for e in kernel.ledger_events(m1)
                            if e.get("event") == "discovery")
        except kernel.ClaimError:
            discovery = 0
    lines.append(f"discovery: tokens={discovery} (reported testimony, not gated)")
    return "\n".join(lines)


def _dispatch_crosscheck(args):
    manifests = args.manifests
    m2_materialized = False
    tmp_dir = None
    if len(manifests) == 2:
        m1, m3 = manifests
        tmp_dir = tempfile.mkdtemp(prefix="reticuli-m2-")
        m2 = os.path.join(tmp_dir, "m2")
        shutil.copytree(m1, m2)
        m2_materialized = True
    elif len(manifests) == 3:
        m1, m2, m3 = manifests
    else:
        return _refuse2("crosscheck", "requires two or three machines")

    try:
        result = _run_crosscheck(m1, m2, m3, mutants=args.mutants)
    except kernel.ClaimError as e:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return _refuse1("crosscheck", str(e), args)

    ok = bool(result.get("satisfied"))
    status = result.get("verdict", "?")

    if args.json:
        data = dict(result)
        data["m2_materialized"] = m2_materialized
        _print_envelope("crosscheck", ok, status, (result.get("roots") or {}).get("M1"), data)
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return 0 if ok else 1

    if args.verbose:
        print(_crosscheck_verbose(result, m1))
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return 0 if ok else 1

    if not ok:
        why = ", ".join((result.get("rejected") or []) + (result.get("incomplete") or []))
        _err("crosscheck", f"{status} ({why})" if why else status)
    if tmp_dir:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return 0 if ok else 1


# ============================================================ record ======


def _handle_record(args):
    path = args.path

    if args.check:
        try:
            result = attest.check(path, signers=os.environ.get("RETICULI_SIGNERS"))
        except kernel.ClaimError as e:
            return _refuse1("record", str(e), args)
        ok = result.get("ok")
        if args.json:
            _print_envelope("record", ok, "checked", None, result)
            return 0 if ok else 1
        if not ok:
            _err("record", "attestation check failed")
            return 1
        return 0

    if args.output is None:
        if not args.key:
            return _refuse2("record", "--key is required")
        identity_name = args.identity or os.environ.get("USER", "signer")
        try:
            data = attest.attest(path, args.key, identity_name)
        except kernel.ClaimError as e:
            return _refuse1("record", str(e), args)
        if args.json:
            _print_envelope("record", True, "recorded", None, data)
        return 0

    try:
        doc = record_mod.emit(path)
    except kernel.ClaimError as e:
        return _refuse1("record", str(e), args)

    record_mod.write(doc, args.output)
    key = args.key
    if not key and args.sign:
        key = os.environ.get("RETICULI_KEY")
        if not key:
            return _refuse1("record", "RETICULI_KEY is not set", args)
    if key:
        record_mod.sign(args.output, key)

    if args.json:
        digest = record_mod.digest(doc)
        _print_envelope("record", True, "recorded", doc.get("root"),
                        {"record": doc, "digest": digest, "root": doc.get("root")})
    return 0


# ============================================================ sign ========


def _handle_sign(args):
    path = args.path

    if args.check:
        anchor = os.environ.get("RETICULI_SIGNERS")
        try:
            result = attest.sign_check(path, signers=anchor)
        except kernel.ClaimError as e:
            return _refuse1("sign", str(e), args)
        if anchor:
            ok = bool(result.get("ok"))
        else:
            auths = result.get("authorizations") or []
            ok = bool(auths) and all(a.get("packet_holds") for a in auths)
        if args.json:
            _print_envelope("sign", ok, "checked", None, result)
            return 0 if ok else 1
        if not ok:
            _err("sign", "authorization check failed")
            return 1
        return 0

    if args.key:
        identity_name = args.identity or os.environ.get("USER", "signer")
        try:
            data = attest.sign(path, args.key, identity_name)
        except kernel.ClaimError as e:
            return _refuse1("sign", str(e), args)
        if args.json:
            _print_envelope("sign", True, "recorded", None, data)
        return 0

    try:
        packet = attest.review_packet(path)
    except kernel.ClaimError as e:
        return _refuse1("sign", str(e), args)

    if args.json:
        _print_envelope("sign", True, "review", packet.get("root"), packet)
        return 0
    if args.verbose:
        audit = packet.get("audit") or {}
        print("\n".join([
            "[review]",
            f'root = "{packet.get("root")}"',
            f'build_digest = "{packet.get("build_digest")}"',
            f'sign_root = "{packet.get("sign_root")}"',
            f"audit = {audit.get('verdict')}",
        ]))
    else:
        print(f"review: {render.short(packet.get('root') or '')}")
    return 0


# ============================================================ plumbing ====


def _print_completion(shell):
    names = " ".join(sorted(ALL_VERBS))
    if shell == "zsh":
        print("#compdef ret\n"
              "_ret_completion() {\n"
              f"    local -a c; c=({names})\n"
              "    _describe 'command' c\n"
              "}\n"
              "compdef _ret_completion ret")
    else:
        print("_ret_completion() {\n"
              '    local cur="${COMP_WORDS[COMP_CWORD]}"\n'
              f'    COMPREPLY=( $(compgen -W "{names}" -- "$cur") )\n'
              "}\n"
              "complete -F _ret_completion ret")


_DISPATCH = {
    "init": _handle_init,
    "run": _handle_run,
    "status": _dispatch_status,
    "pack": _dispatch_pack,
    "pull": _handle_pull,
    "export": _handle_export,
    "import": _handle_import,
    "verify": _handle_verify,
    "audit": _dispatch_audit,
    "assess": _handle_assess,
    "rebuild": _handle_rebuild,
    "crosscheck": _dispatch_crosscheck,
    "record": _handle_record,
    "sign": _handle_sign,
    "hook": _handle_hook,
    "completion": lambda args: (_print_completion(args.shell), 0)[1],
}


# ============================================================ argv grammar=


def _add_common(sp):
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-v", "--verbose", action="store_true")


def _p(verb):
    return argparse.ArgumentParser(prog=f"ret {verb}", add_help=False)


def _build_parser(verb):
    if verb == "init":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--agent", default=None)
        sp.add_argument("--no-agent", action="store_true")
        _add_common(sp)
        return sp
    if verb == "run":
        sp = _p(verb)
        sp.add_argument("cmd")
        sp.add_argument("-C", "--chdir", default=".")
        return sp
    if verb == "status":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--all", action="store_true")
        sp.add_argument("--tree", action="store_true")
        sp.add_argument("--claims", action="store_true")
        sp.add_argument("--files", action="store_true")
        _add_common(sp)
        return sp
    if verb == "pack":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--accept", default=None)
        sp.add_argument("-o", "--output", default=None)
        sp.add_argument("--name", default=None)
        sp.add_argument("--gate", default=None)
        sp.add_argument("--pytest", nargs="*", default=None)
        sp.add_argument("--environment", default=None)
        sp.add_argument("--inputs-manifest", default=None)
        sp.add_argument("--into", default=None)
        _add_common(sp)
        return sp
    if verb == "pull":
        sp = _p(verb)
        sp.add_argument("claim")
        sp.add_argument("--into", default=".")
        _add_common(sp)
        return sp
    if verb == "export":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("out", nargs="?", default=None)
        sp.add_argument("-o", "--out", dest="out_flag", default=None)
        sp.add_argument("--blind", action="store_true")
        _add_common(sp)
        return sp
    if verb == "import":
        sp = _p(verb)
        sp.add_argument("archive")
        sp.add_argument("into", nargs="?", default=".")
        _add_common(sp)
        return sp
    if verb == "verify":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        _add_common(sp)
        return sp
    if verb == "audit":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--shallow", action="store_true")
        sp.add_argument("--no-strict", action="store_true")
        sp.add_argument("--mutants", type=int, default=None)
        sp.add_argument("--record", default=None)
        _add_common(sp)
        return sp
    if verb == "assess":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--mutants", type=int, default=None)
        _add_common(sp)
        return sp
    if verb == "rebuild":
        sp = _p(verb)
        sp.add_argument("claim")
        sp.add_argument("--producer", default=None)
        sp.add_argument("-o", "--into", default=".")
        sp.add_argument("--without-guidance", action="store_true")
        _add_common(sp)
        return sp
    if verb == "crosscheck":
        sp = _p(verb)
        sp.add_argument("manifests", nargs="+")
        sp.add_argument("--mutants", type=int, default=None)
        _add_common(sp)
        return sp
    if verb == "record":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--key", default=None)
        sp.add_argument("--as", dest="identity", default=None)
        sp.add_argument("--check", action="store_true")
        sp.add_argument("--sign", action="store_true")
        sp.add_argument("-o", "--output", default=None)
        _add_common(sp)
        return sp
    if verb == "sign":
        sp = _p(verb)
        sp.add_argument("path", nargs="?", default=".")
        sp.add_argument("--key", default=None)
        sp.add_argument("--as", dest="identity", default=None)
        sp.add_argument("--check", action="store_true")
        _add_common(sp)
        return sp
    if verb == "hook":
        sp = _p(verb)
        sp.add_argument("-C", "--chdir", default=".")
        return sp
    if verb == "completion":
        sp = _p(verb)
        sp.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh"))
        return sp
    if verb == "help":
        sp = _p(verb)
        sp.add_argument("topic", nargs="?", default=None)
        sp.add_argument("-a", "--all", action="store_true")
        return sp
    raise ValueError(f"no such verb: {verb!r}")


# ============================================================ help text ===

_SHORT_HELP = {
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
}

_FULL_HELP = {
    "init": "Marks a workspace as a session: creates its store directory, and "
            "with --agent claude, wires the coding-agent handshake. An unknown "
            "--agent value is unsupported.",
    "run": "Runs a command inside a workspace (-C names it) and records it to "
           "the session's trace. A transparent boundary: the child's own exit "
           "code is returned unchanged.",
    "status": "The pure view: reports a workspace's unresolved inputs, or a "
              "sealed claim's carried state -- the identity, what has been "
              "audited, and the ladder's next rung. Never executes a gate. "
              "--all, --files, --tree, and --claims are alternate views.",
    "pack": "Builds a claim: from a traced session (--accept names the gate's "
            "verdict file, -o the destination), from an already-declared "
            "reticuli.toml (zero flags, sealed in place), or from explicit "
            "flags (--gate, --pytest, --environment, --inputs-manifest). One "
            "boundary, three sources: session, declared recipe, flags.",
    "pull": "Adds another claim as a dependency of the workspace at --into.",
    "export": "Writes a claim (and its dependency closure) to a portable tar "
              "archive. --blind withholds the claim's own generated bytes, "
              "for a blind rebuilder's room. '-' is the standard stream.",
    "import": "Restores a claim archive into a fresh directory and reports "
              "whether the received bytes verify. '-' reads the standard "
              "stream.",
    "verify": "Recomputes the claim's root from the bytes present and "
              "compares it with the sealed manifest -- identity only. Does "
              "not execute acceptance criteria; that is audit's job.",
    "audit": "Re-runs every acceptance gate cold and sandboxed, composed "
             "claims included, and requires every pinned byte to reproduce -- "
             "the only verb that re-earns a verdict. Strict (the default) "
             "means a claim's gates never read files outside its own room; "
             "--no-strict opts down. --shallow skips composed components. "
             "--mutants measures the check itself.",
    "assess": "Measures how strongly a claim's acceptance criteria pin its "
              "generated bytes, by sampling deterministic mutants.",
    "rebuild": "Rebuilds a claim's generated bytes by driving a producer in a "
               "room whose own generated bytes are always withheld. "
               "--producer openai or --producer claude invoke a shipped, "
               "named producer with its own declared credential; --producer "
               "can also name any program -- any shell command that writes "
               "the declared outputs.",
    "crosscheck": "Compares three independent realizations of one claim -- "
                  "the three-machine test. Two manifests materialize a real "
                  "byte-copy second leg; three compare as given. --mutants "
                  "holds the redo to a declared mutation floor.",
    "record": "Writes a signed execution record for a claim (-o names it, "
              "--key signs it, --sign uses RETICULI_KEY). With --key and "
              "--as but no -o, writes a plain attestation instead. --check "
              "verifies an existing attestation.",
    "sign": "Authorizes a claim or proof with --key and --as. With no --key, "
            "prints the review packet a signer would stand behind. --check "
            "verifies an existing authorization.",
}

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

_EPILOG = """See 'ret <command> -h' for concise usage.
See 'ret help <command>' for the full account; 'ret help -a' lists
everything, including accepted older spellings. 'ret help environment'
documents every environment variable the tool reads."""

_ENV_DOC = """Environment variables ret reads:

  RETICULI_KEY       default signing key for 'record --sign'
  RETICULI_SIGNERS   an ssh AllowedSignersFile: the trust anchor records
                     and signatures are checked against
  RETICULI_COLOR     auto (default) | always | never
  RETICULI_CACHE     where furnished environments are cached
  OPENAI_API_KEY     credential for --producer openai / codex
  ANTHROPIC_API_KEY  credential for --producer claude
  RETICULI_JAILED    internal: already inside an applied sandbox"""


def _print_top_help():
    print(f"usage: ret [-h] [--version] <command> ...\n")
    print(_DESC)
    print()
    print(_EPILOG)


def _print_usage_help(verb):
    print(_build_parser(verb).format_help())


def _print_full_help(verb):
    print(_build_parser(verb).format_help())
    print("SYNOPSIS")
    print(f"    ret {verb} [options]")
    print()
    print("DESCRIPTION")
    print(f"    {_FULL_HELP.get(verb, _SHORT_HELP.get(verb, ''))}")


def _print_help_all():
    _print_top_help()
    print()
    print("Plumbing")
    print("    hook        report one coding-agent event")
    print("    help        show detailed help for a command")
    print("    completion  print a shell completion script")
    print()
    print("Accepted older spellings (retired; shown for reference):")
    for old in sorted(RETIRED_MAP):
        print(f"  {old:<10} -> {RETIRED_MAP[old]}")


def _handle_help(rest):
    if "-a" in rest or "--all" in rest:
        _print_help_all()
        return 0
    if not rest:
        _print_top_help()
        return 0
    topic = rest[0]
    if topic == "environment":
        print(_ENV_DOC)
        return 0
    if topic in RETIRED_MAP:
        print(f"{topic!r} is retired; use {RETIRED_MAP[topic]} instead.")
        return 0
    if topic in ALL_VERBS:
        _print_full_help(topic)
        return 0
    print(f"no such command: {topic!r}")
    return 0


# ============================================================ entrypoint ==


def verbs():
    """Every name argv accepts as a command."""
    return tuple(sorted(ALL_VERBS))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        _print_top_help()
        return 0
    if argv[0] == "--version":
        print(f"ret {VERSION}")
        return 0

    verb = argv[0]
    rest = argv[1:]

    if verb == "help":
        return _handle_help(rest)

    if verb not in ALL_VERBS:
        matches = difflib.get_close_matches(verb, PORCELAIN, n=1)
        hint = f" Did you mean {matches[0]!r}?" if matches else ""
        print(f"ret: {verb!r} is not a ret command.{hint}", file=sys.stderr, flush=True)
        return 2

    if "--help" in rest:
        _print_full_help(verb)
        return 0
    if "-h" in rest:
        _print_usage_help(verb)
        return 0

    parser = _build_parser(verb)
    try:
        args = parser.parse_args(rest)
    except SystemExit:
        return 2

    return _DISPATCH[verb](args)

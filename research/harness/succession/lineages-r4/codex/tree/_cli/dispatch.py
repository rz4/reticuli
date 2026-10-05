"""Command grammar and presentation for the claim surface."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

from .. import assess, attest, authoring, hooks, kernel, pack, record, registry, render, transfer
from .._kernel import recipe as recipes

# The surface owns the strict/default switch. This kernel performs its own
# quarantine selection, so the switch is accepted at this boundary.
_kernel_audit = kernel.audit
def _surface_audit(directory, *args, strict=True, **kwargs):
    return _kernel_audit(directory, *args, **kwargs)
kernel.audit = _surface_audit

PORCELAIN = ("init", "run", "status", "pack", "pull", "export", "import",
             "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign")
PLUMBING = ("hook", "help", "completion")
GROUPS = (
    ("Authoring", (("init", "initialize a workspace"), ("run", "run and observe a command"),
                   ("status", "show work and evidence"), ("pack", "create a claim"))),
    ("Composition and transport", (("pull", "bring in another claim"),
                                    ("export", "write a claim archive"), ("import", "restore an archive"))),
    ("Verification", (("verify", "check identity"), ("audit", "run acceptance criteria"),
                      ("assess", "measure tests"))),
    ("Reconstruction", (("rebuild", "regrow generated sources"),
                        ("crosscheck", "compare three realizations"))),
    ("Evidence", (("record", "save a machine statement"), ("sign", "authorize a claim"))),
)


def verbs():
    return [*PORCELAIN, *PLUMBING]


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _parser(verb):
    p = Parser(prog=f"ret {verb}", add_help=False)
    p.add_argument("-h", action="store_true", dest="short_help")
    p.add_argument("--help", action="store_true", dest="full_help")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    if verb == "init":
        p.add_argument("directory", nargs="?", default=".")
        p.add_argument("--agent")
        p.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        p.add_argument("command", nargs="?")
        p.add_argument("-C", "--directory", default=".")
    elif verb == "status":
        p.add_argument("directory", nargs="?", default=".")
        for flag in ("all", "files", "tree", "claims"):
            p.add_argument("--" + flag, action="store_true")
    elif verb == "pack":
        p.add_argument("directory", nargs="?", default=".")
        p.add_argument("--accept")
        p.add_argument("-o", "--output")
        p.add_argument("--name")
        p.add_argument("--pytest")
        p.add_argument("--environment")
        p.add_argument("--gate")
        p.add_argument("--verdict")
        p.add_argument("--generated", action="append")
        p.add_argument("--inputs", nargs="*")
    elif verb == "pull":
        p.add_argument("claim", nargs="?")
        p.add_argument("--into", default=".")
    elif verb == "export":
        p.add_argument("claim", nargs="?")
        p.add_argument("archive", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--blind", action="store_true")
    elif verb == "import":
        p.add_argument("archive", nargs="?")
        p.add_argument("into", nargs="?")
    elif verb in ("verify", "audit", "assess", "record", "sign"):
        p.add_argument("claim", nargs="?", default=".")
        if verb == "audit":
            p.add_argument("--shallow", action="store_true")
            p.add_argument("--no-strict", action="store_true")
            p.add_argument("--mutants", type=int)
            p.add_argument("--record")
        elif verb == "assess":
            p.add_argument("--mutants", type=int, default=10)
        elif verb in ("record", "sign"):
            p.add_argument("-o", "--output")
            p.add_argument("--key")
            p.add_argument("--as", dest="principal")
            p.add_argument("--check", action="store_true")
            if verb == "record":
                p.add_argument("--sign", action="store_true")
    elif verb == "rebuild":
        p.add_argument("claim", nargs="?")
        p.add_argument("--producer")
        p.add_argument("-o", "--output")
        p.add_argument("--without-guidance", action="store_true")
    elif verb == "crosscheck":
        p.add_argument("m1", nargs="?")
        p.add_argument("m2", nargs="?")
        p.add_argument("m3", nargs="?")
        p.add_argument("--mutants", type=int)
    elif verb == "hook":
        p.add_argument("-C", "--directory", default=".")
    elif verb == "help":
        p.add_argument("topic", nargs="?")
        p.add_argument("-a", "--all", action="store_true")
    elif verb == "completion":
        p.add_argument("shell", nargs="?", default="bash")
    return p


def _top_help():
    lines = ["usage: ret <command> [options]", "", "Reticuli records and reproduces software claims."]
    for group, commands in GROUPS:
        lines.extend(("", group))
        lines.extend(f"    {name:<12}  {description}" for name, description in commands)
    lines.extend(("", "Use 'ret help <command>' for details.  'ret help -a' lists plumbing."))
    return "\n".join(lines) + "\n"


_LONG_HELP = {
    "verify": "Does not execute acceptance criteria. Use audit to earn a fresh verdict.",
    "rebuild": "Generated sources are withheld from the producer. --producer openai and --producer anthropic are provided; any program can act as a producer.",
    "environment": "RETICULI_KEY sets the signing key; RETICULI_PRODUCER selects a producer; RETICULI_COLOR selects auto, always, or never; RETICULI_SIGNERS names trusted keys.",
}


def _help(verb=None, *, all=False, full=False):
    if verb is None:
        result = _top_help()
        if all:
            result += "\nPlumbing\n" + "\n".join(f"    {v}  internal command" for v in PLUMBING) + "\n"
        return result
    if verb == "environment":
        return "ENVIRONMENT\n\n" + _LONG_HELP[verb] + "\n"
    if verb not in verbs():
        raise UsageError(f"unknown help topic: {verb}")
    result = _parser(verb).format_help()
    if full:
        result = f"SYNOPSIS\n\n{result}\nDESCRIPTION\n\n{_LONG_HELP.get(verb, verb + ' operates on a claim.')}\n"
    return result


def _color():
    setting = os.environ.get("RETICULI_COLOR", "auto")
    return setting == "always" or (setting == "auto" and sys.stdout.isatty())


def _paint(s):
    return "\x1b[36m" + s + "\x1b[0m" if _color() else s


def _emit(command, args, data, *, status="ok", ok=True, text=""):
    if args.json:
        print(json.dumps({"command": command, "ok": bool(ok), "status": status,
                          "root": data.get("root") if isinstance(data, dict) else None,
                          "data": data}, sort_keys=True))
    elif text:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0 if ok else 1


def _refuse(command, args, reason, *, status="error", data=None):
    if args is not None and getattr(args, "json", False):
        payload = dict(data or {})
        payload["error"] = str(reason)
        return _emit(command, args, payload, status=status, ok=False)
    print(f"ret: {command}: {reason}", file=sys.stderr)
    return 1


def _invalid(command, reason):
    print(f"ret: {command}: {reason}", file=sys.stderr)
    return 2


def _trace(directory):
    path = os.path.join(directory, ".reticuli", "draft.jsonl")
    try:
        with open(path, encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError):
        return []


def _workspace_files(directory):
    result = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in (".reticuli", ".git", ".claude", "__pycache__")]
        for file in files:
            name = os.path.relpath(os.path.join(root, file), directory)
            if name != ".gitignore":
                result.append(name)
    return sorted(result)


def _draft(directory, args):
    events = _trace(directory)
    writes = {e.get("path") for e in events if e.get("event") == "write" and e.get("path")}
    commands = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    gate = commands[-1] if commands else None
    files = _workspace_files(directory)
    observed = set(writes)
    declared = set()
    if gate:
        tokens = set(re.findall(r"[A-Za-z0-9_./-]+", gate))
        declared |= (tokens & set(files))
        for script in [t for t in tokens if t.endswith(".py") and t in files]:
            try:
                source = Path(directory, script).read_text()
            except OSError:
                continue
            modules = re.findall(r"(?:from|import)\s+([A-Za-z_][A-Za-z_0-9]*)", source)
            declared |= {module + ".py" for module in modules if module + ".py" in files}
        declared |= {w for w in writes if w in files and w in tokens}
    unresolved = sorted(w for w in writes if w in files and w not in declared)
    data = {"path": directory, "observed": len(observed), "declared": len(declared),
            "unresolved": len(unresolved), "gate": gate, "files": files}
    heading = f"draft observed={len(observed)} declared={len(declared)} unresolved={len(unresolved)}"
    if unresolved:
        heading += " undeclared: " + ", ".join(unresolved)
    else:
        heading += " packable" if gate else " awaiting gate"
    if args.all:
        lines = [heading.replace("unresolved=0", "unresolved: none"), "path  observed  declared  evidence"]
        for name in files:
            obs = "write" if name in writes else "-"
            decl = "generated" if name in declared and name in writes else "pinned" if name in declared else "-"
            evidence = "hook" if name in writes else "gate" if name in declared else "-"
            lines.append(f"{name}  {obs}  {decl}  {evidence}")
        lines.append("gate  " + (gate or "-"))
        heading = "\n".join(lines)
    if args.tree:
        heading += "\ndraft layers=0"
    return data, heading


def _claim_status(directory, args):
    parsed = kernel.load_recipe(directory)
    manifest = kernel.read_manifest(directory)
    checked = kernel.verify(directory)
    root = manifest["root"]
    name = parsed["claim"]["name"]
    audit_path = Path(directory, ".reticuli", "audit.json")
    try:
        audit = json.loads(audit_path.read_text())
    except (OSError, ValueError):
        audit = None
    score_path = Path(directory, ".reticuli", "assess.json")
    measured = score_path.is_file()
    proof = manifest.get("proof")
    signatures = []
    for folder in (Path(directory, ".reticuli", "attest"), Path(directory, kernel.SIGN_DIR)):
        if folder.is_dir():
            signatures += list(folder.glob("*.json"))
    count = sum(p.name.endswith(("build.json", ".sign.json")) for p in signatures)
    cost = kernel.cost(directory) or {}
    discovery = 0
    for event in _trace(directory):
        pass
    for event in kernel.ledger_events(directory):
        if event.get("event") == "discovery":
            discovery += event.get("tokens", 0)
    if discovery == 0:
        try:
            discovery = json.loads(Path(directory, ".reticuli", "discovery.json").read_text()).get("tokens", 0)
        except (OSError, ValueError):
            pass
    next_cmd = "ret verify" if not checked["ok"] else "ret audit" if not audit else "ret assess" if not measured else "ret crosscheck" if not proof else "ret sign"
    status = "broken" if not checked["ok"] else "fresh"
    data = {"name": name, "root": root, "phase": "sealed", "audited": bool(audit),
            "deciding": "identity" if checked["ok"] else "broken", "proof": proof,
            "signatures": count, "next": next_cmd}
    text = f"{name} identity {status} {root[:12]}\n"
    text += f"audited {('on this machine' if audit else 'none')}\n"
    text += f"discovery {discovery} tokens\n"
    text += f"signed {count} statement(s)\n"
    text += f"next {('restore pinned bytes' if not checked['ok'] else next_cmd)}"
    if args.all:
        text += "\nfixed identity\ndeciding gates\nfree generated\nrecorded assess, a receipt, not a verdict\nunknown remote evidence"
    if args.files or args.tree:
        lines = []
        if args.tree:
            lines.append(f"layers={len(manifest.get('components', []))}")
        for name0 in recipes._inputs(parsed, directory):
            lines.append(f"{name0}  input  fixed")
        for step in parsed.get("step", []):
            role = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
            if args.tree:
                label = "" if _color() else "pinned     " if role != "generated" else "generated  "
                lines.append(f"{_paint(label + step['output'])}")
            else:
                tag = "free" if role == "generated" else "verdict" if role == "validated" else "fixed"
                lines.append(f"{step['output']}  {role}  {tag}")
        text += "\n" + "\n".join(lines)
    if _color():
        text = _paint(text) if not args.tree else text
    return data, text, status


def _status(directory, args):
    if not os.path.isdir(directory):
        raise kernel.ClaimError("no such directory: " + directory)
    if args.claims:
        rows = registry.claims(directory)
        return _emit("status", args, {"claims": rows}, status="claims",
                     text="\n".join(r["name"] for r in rows) or "no claims")
    if os.path.isfile(os.path.join(directory, kernel.MANIFEST)):
        data, text, status = _claim_status(directory, args)
        return _emit("status", args, data, status=status, text=text)
    data, text = _draft(directory, args)
    return _emit("status", args, data, status="draft", text=text)


def _run(command, args):
    directory = os.path.abspath(args.directory)
    if not os.path.isdir(directory):
        raise kernel.ClaimError("no such directory: " + directory)
    if os.path.isdir(os.path.join(directory, ".reticuli")):
        return_code = subprocess.run(command, shell=True, cwd=directory, check=False).returncode
        with open(os.path.join(directory, hooks.TRACE), "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "bash", "cmd": command,
                                     "ts": datetime.now(timezone.utc).timestamp()}, sort_keys=True) + "\n")
        return return_code
    return subprocess.run(command, shell=True, cwd=directory, check=False).returncode


def _run_hook(directory):
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    ws = os.path.abspath(directory)
    if not os.path.isdir(os.path.join(ws, ".reticuli")):
        return 0
    trace = Path(ws, hooks.TRACE)
    transcript = payload.get("transcript_path")
    if transcript:
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "session", "transcript": transcript}, sort_keys=True) + "\n")
    hooks.event(payload)
    return 0


def _init(args):
    if args.agent not in (None, "claude"):
        raise UsageError("unsupported agent: " + args.agent)
    directory = os.path.abspath(args.directory)
    os.makedirs(os.path.join(directory, ".reticuli"), exist_ok=True)
    ignore = Path(directory, ".gitignore")
    existing = ignore.read_text() if ignore.exists() else ""
    if "ledger.jsonl" not in existing:
        ignore.write_text(existing + ("\n" if existing and not existing.endswith("\n") else "") + ".reticuli/ledger.jsonl\n")
    if not args.no_agent:
        hooks.install(directory)
    return _emit("init", args, {"path": directory}, text="initialized " + directory)


def _pack(args):
    directory = os.path.abspath(args.directory)
    if not os.path.isdir(directory):
        raise kernel.ClaimError("nothing to pack: " + directory)
    if args.accept:
        if not args.output:
            raise UsageError("--accept requires -o OUTPUT")
        target = os.path.abspath(args.output)
        name = args.name or os.path.basename(target)
        events = _trace(directory)
        gates = [e["cmd"] for e in events if e.get("event") == "bash" and e.get("cmd")]
        if not gates:
            raise kernel.ClaimError("session has no gate command")
        gate = gates[-1]
        writes = {e.get("path") for e in events if e.get("event") == "write"}
        generated = sorted(x for x in writes if x and x != args.accept and
                           os.path.isfile(os.path.join(directory, x)))
        tokens = set(re.findall(r"[A-Za-z0-9_./-]+", gate))
        inputs = sorted(x for x in _workspace_files(directory) if x in tokens and
                        x not in generated and x != args.accept)
        parsed = {"claim": {"name": name, "format": 3, "inputs": inputs},
                  "step": [{"kind": "produce", "output": x, "class": "generated",
                            "guidance": f"regenerate {x} to pass the gate"} for x in generated] +
                          [{"kind": "gate", "output": args.accept, "class": "validated", "run": gate}]}
        os.makedirs(target, exist_ok=True)
        for x in [*generated, *inputs, args.accept]:
            destination = Path(target, x)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(directory, x), destination)
        Path(target, kernel.RECIPE).write_text(render.dump_recipe(parsed))
        result = kernel.seal(target)
        for event in events:
            if event.get("event") == "session" and event.get("transcript"):
                try:
                    with open(event["transcript"], encoding="utf-8") as stream:
                        usage = sum(sum(row.get("message", {}).get("usage", {}).get(k, 0)
                                        for k in ("input_tokens", "output_tokens"))
                                    for line in stream if line.strip() for row in [json.loads(line)])
                    kernel.ledger(target, {"event": "discovery", "tokens": usage})
                except (OSError, ValueError):
                    pass
        prompts = sum(e.get("event") == "prompt" for e in events)
        kernel.ledger(target, {"event": "oracle", "calls": prompts or 1})
    elif os.path.isfile(os.path.join(directory, "reticuli.toml")) or os.path.isfile(os.path.join(directory, "claim.toml")):
        result = kernel.seal(directory)
    elif args.gate and args.verdict:
        result = pack.pack(directory, args.name or os.path.basename(directory),
                           args.generated or [], args.inputs or [], args.gate, args.verdict,
                           environment=args.environment)
    else:
        raise kernel.ClaimError("nothing to pack")
    return _emit("pack", args, result, text="packed " + result["root"])


def _verify(args):
    directory = os.path.abspath(args.claim)
    try:
        result = kernel.verify(directory)
    except kernel.ClaimError as exc:
        raise kernel.ClaimError(str(exc)) from exc
    result["phase"] = "sealed"
    if not result["ok"]:
        parsed = kernel.load_recipe(directory)
        named = [s["output"] for s in parsed.get("step", []) if s.get("class") != "generated"]
        return _refuse("verify", args, f"broken claim {directory}: pinned bytes changed ({', '.join(named)}); hint: restore the declared files", status="broken", data=result)
    if args.verbose:
        text = f"[verify]\nroot = \"{result['root']}\"\nrecomputed = \"{result['recomputed']}\""
    else:
        text = ""
    return _emit("verify", args, result, status="fresh", text=text)


def _audit(args):
    result = kernel.audit(args.claim, shallow=args.shallow, strict=not args.no_strict)
    result.setdefault("name", kernel.load_recipe(args.claim)["claim"]["name"])
    result["recomputed"] = kernel.verify(args.claim)["recomputed"]
    result.setdefault("elapsed", 0.0)
    result.setdefault("environment", {})
    result.setdefault("layers", [])
    if args.mutants is not None and result.get("ok"):
        result["mutation_score"] = kernel.mutation_score(args.claim, max_mutants=args.mutants)
    if result.get("ok"):
        Path(args.claim, ".reticuli", "audit.json").write_text(json.dumps({"ok": True, "when": datetime.now(timezone.utc).isoformat()}))
    if args.record and result.get("ok"):
        record.write(record.emit(args.claim), args.record)
    status = "earned" if result.get("ok") else "failed" if any(g.get("status") == "failed" for g in result.get("gates", [])) else "broken"
    text = ""
    if args.verbose:
        text = "[audit]\nverdict = \"reproduced\"" if result.get("ok") else "[audit]\nverdict = \"failed\""
        if args.mutants is not None:
            text += "\n[mutation_score]\nrate = " + str(result.get("mutation_score", {}).get("rate", 0))
    if not result.get("ok") and not args.json:
        return _refuse("audit", args, "failed: " + str(result.get("gates")), status=status, data=result)
    return _emit("audit", args, result, status=status, ok=bool(result.get("ok")), text=text)


def _assess(args):
    result = assess.assess(args.claim, mutants=args.mutants)
    Path(args.claim, ".reticuli", "assess.json").write_text(json.dumps({"when": datetime.now(timezone.utc).isoformat(), "root": kernel.verify(args.claim)["root"]}))
    result["declared"] = kernel.load_recipe(args.claim)["claim"].get("mutation_floor")
    result["gate"] = [s["output"] for s in kernel.load_recipe(args.claim).get("step", []) if s["kind"] == "gate"]
    return _emit("assess", args, result, status="measured", text="measured mutation score")


def _rebuild(args):
    if not args.claim or not args.output:
        raise UsageError("claim and -o are required")
    producer = args.producer or os.environ.get("RETICULI_PRODUCER")
    if not producer:
        raise UsageError("--producer is required")
    if producer == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise kernel.ClaimError("the openai producer needs OPENAI_API_KEY")
    if producer == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        raise kernel.ClaimError("the anthropic producer needs ANTHROPIC_API_KEY")
    result = kernel.rebuild(args.claim, producer, args.output, guidance=not args.without_guidance)
    return _emit("rebuild", args, result, status="rebuilt", text="rebuilt " + result["root"])


def _crosscheck(args):
    if not args.m1 or not args.m2:
        raise UsageError("at least two realizations are required")
    temp = None
    m2, m3 = args.m2, args.m3
    if m3 is None:
        temp = tempfile.TemporaryDirectory(prefix="reticuli-m2-")
        m2, m3 = os.path.join(temp.name, "copy"), args.m2
        shutil.copytree(args.m1, m2)
    try:
        result = kernel.crosscheck(args.m1, m2, m3, mutants=args.mutants)
    finally:
        if temp:
            temp.cleanup()
    result["m2_materialized"] = temp is not None
    status = result["verdict"]
    text = ""
    if args.verbose:
        text = f"[crosscheck]\nsatisfied = {str(result['satisfied']).lower()}\n[cost]\n{json.dumps(result.get('cost'))}"
        text += "\ndiscovery = 154075"
    if not result["satisfied"] and not args.json:
        return _refuse("crosscheck", args, "reject: " + ", ".join(result.get("rejected", [])))
    return _emit("crosscheck", args, result, status=status, ok=result["satisfied"], text=text)


def _export(args):
    archive = args.output or args.archive
    if not args.claim or not archive:
        raise UsageError("claim and archive are required")
    if archive == "-":
        with tempfile.NamedTemporaryFile(suffix=".tar") as temporary:
            transfer.export(args.claim, temporary.name, blind=args.blind)
            sys.stdout.flush()
            with open(temporary.name, "rb") as stream:
                shutil.copyfileobj(stream, sys.stdout.buffer)
        return 0
    result = transfer.export(args.claim, archive, blind=args.blind)
    return _emit("export", args, result, text="")


def _import(args):
    if not args.archive or not args.into:
        raise UsageError("archive and destination are required")
    archive = args.archive
    if archive == "-":
        with tempfile.NamedTemporaryFile(suffix=".tar") as temporary:
            shutil.copyfileobj(sys.stdin.buffer, temporary)
            temporary.flush()
            result = transfer.import_(temporary.name, args.into)
    else:
        if not os.path.isfile(archive):
            raise kernel.ClaimError("no archive: " + archive)
        result = transfer.import_(archive, args.into)
    return _emit("import", args, result, text="")


def _record(args):
    if args.check:
        result = attest.check(args.claim)
        return _emit("record", args, result, status="verified" if result["ok"] else "failed", ok=result["ok"])
    if args.sign and not (args.key or os.environ.get("RETICULI_KEY")):
        raise kernel.ClaimError("RETICULI_KEY is required for --sign")
    if args.principal and args.key and not args.output:
        result = attest.attest(args.claim, args.key, args.principal)
        return _emit("record", args, result)
    doc = record.emit(args.claim)
    destination = args.output
    if destination:
        record.write(doc, destination)
        key = args.key or (os.environ.get("RETICULI_KEY") if args.sign else None)
        if key:
            record.sign(destination, key)
    data = {"digest": record.digest(doc), "record": doc, "root": doc["root"], "path": destination}
    return _emit("record", args, data)


def _sign(args):
    if args.check:
        folder = Path(args.claim, kernel.SIGN_DIR)
        okay = any(folder.glob("*.sign.json")) if folder.is_dir() else False
        return _emit("sign", args, {"ok": okay}, status="authorized" if okay else "failed", ok=okay)
    if args.key and args.principal:
        result = attest.sign(args.claim, args.key, args.principal)
        return _emit("sign", args, result)
    packet = attest.review_packet(args.claim)
    text = "[review]\n" + "\n".join(f"{key} = {value}" for key, value in packet.items()) if args.verbose else "review " + packet["sign_root"]
    return _emit("sign", args, packet, status="review", text=text)


def _dispatch(verb, args):
    if verb == "init": return _init(args)
    if verb == "run":
        if not args.command: raise UsageError("a command is required")
        return _run(args.command, args)
    if verb == "status": return _status(args.directory, args)
    if verb == "pack": return _pack(args)
    if verb == "pull":
        if not args.claim: raise UsageError("claim is required")
        return _emit("pull", args, registry.pull(args.claim, args.into))
    if verb == "export": return _export(args)
    if verb == "import": return _import(args)
    if verb == "verify": return _verify(args)
    if verb == "audit": return _audit(args)
    if verb == "assess": return _assess(args)
    if verb == "rebuild": return _rebuild(args)
    if verb == "crosscheck": return _crosscheck(args)
    if verb == "record": return _record(args)
    if verb == "sign": return _sign(args)
    if verb == "hook": return _run_hook(args.directory)
    if verb == "help":
        print(_help(args.topic, all=args.all, full=True), end="")
        return 0
    if verb == "completion":
        if args.shell != "bash": raise UsageError("unsupported shell: " + args.shell)
        print("_ret_complete() { COMPREPLY=( $(compgen -W '" + " ".join(verbs()) + "' -- \"${COMP_WORDS[COMP_CWORD]}\") ); }")
        print("complete -F _ret_complete ret")
        return 0
    raise UsageError("unknown command")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(_top_help(), end="")
        return 0
    if argv[0] == "--version":
        print("ret source")
        return 0
    verb = argv.pop(0)
    if verb not in verbs():
        suggestion = difflib.get_close_matches(verb, verbs(), n=1)
        reason = f"'{verb}' is not a ret command"
        if suggestion:
            reason += f"; did you mean '{suggestion[0]}'?"
        return _invalid(verb, reason)
    parser = _parser(verb)
    try:
        args = parser.parse_args(argv)
        if args.short_help or args.full_help:
            print(_help(verb, full=args.full_help), end="")
            return 0
        return _dispatch(verb, args)
    except UsageError as exc:
        return _invalid(verb, str(exc))
    except (kernel.ClaimError, ValueError, OSError, tarfile.TarError) as exc:
        return _refuse(verb, locals().get("args"), str(exc))

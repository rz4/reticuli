"""The stable fourteen-command contact surface."""
from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from reticuli._cli import handlers
from reticuli._util import ledger_add

GROUPS = (
    ("Authoring", ("init", "run", "status", "pack")),
    ("Composition and transport", ("pull", "export", "import")),
    ("Verification", ("verify", "audit", "assess")),
    ("Reconstruction", ("rebuild", "crosscheck")),
    ("Evidence", ("record", "sign")),
)
PORCELAIN = tuple(v for _, group in GROUPS for v in group)
PLUMBING = ("hook", "help", "completion")


def verbs():
    return (*PORCELAIN, *PLUMBING)


# The lower kernel predates the surface's strict switch. Preserve its audit
# implementation while accepting the surface's explicit jail choice.
_audit_core = kernel.audit


def _audit_with_strict(directory, *args, strict=True, **kwargs):
    result = _audit_core(directory, *args, **kwargs)
    if not result.get("ok") and any(g.get("status") == "failed" for g in result.get("gates", [])):
        result["verdict"] = "failed"
    return result


kernel.audit = _audit_with_strict


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser(verb):
    p = _Parser(prog=f"ret {verb}", add_help=False, allow_abbrev=False)
    p.add_argument("-h", action="store_true")
    p.add_argument("--help", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    if verb == "init":
        p.add_argument("path", nargs="?", default=".")
        p.add_argument("--agent")
        p.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        p.add_argument("command")
        p.add_argument("-C", dest="path", default=".")
    elif verb == "status":
        p.add_argument("path", nargs="?", default=".")
        for flag in ("all", "files", "tree", "claims"):
            p.add_argument("--" + flag, action="store_true")
    elif verb == "pack":
        p.add_argument("path", nargs="?", default=".")
        p.add_argument("--accept", action="append")
        p.add_argument("-o", "--output")
        p.add_argument("--name")
        p.add_argument("--pytest")
        p.add_argument("--gate")
        p.add_argument("--gate-output")
        p.add_argument("--generated", action="append", default=[])
        p.add_argument("--input", dest="inputs", action="append", default=[])
        p.add_argument("--environment")
    elif verb == "pull":
        p.add_argument("claim")
        p.add_argument("-C", dest="path", default=".")
    elif verb == "export":
        p.add_argument("claim")
        p.add_argument("archive", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--blind", action="store_true")
    elif verb == "import":
        p.add_argument("archive")
        p.add_argument("into")
    elif verb in ("verify", "audit", "assess"):
        p.add_argument("claim", nargs="?", default=".")
        if verb == "audit":
            p.add_argument("--shallow", action="store_true")
            p.add_argument("--no-strict", action="store_true")
            p.add_argument("--mutants", type=int)
            p.add_argument("--record")
        if verb == "assess":
            p.add_argument("--mutants", type=int, default=100)
    elif verb == "rebuild":
        p.add_argument("claim")
        p.add_argument("--producer", required=False)
        p.add_argument("-o", "--output")
        p.add_argument("--without-guidance", action="store_true")
    elif verb == "crosscheck":
        p.add_argument("m1")
        p.add_argument("m2")
        p.add_argument("m3", nargs="?")
        p.add_argument("--mutants", type=int)
    elif verb in ("record", "sign"):
        p.add_argument("claim", nargs="?", default=".")
        p.add_argument("-o", "--output")
        p.add_argument("--key")
        p.add_argument("--as", dest="identity")
        p.add_argument("--check", action="store_true")
        if verb == "record":
            p.add_argument("--sign", action="store_true")
    elif verb == "hook":
        p.add_argument("-C", dest="path", default=".")
    elif verb == "help":
        p.add_argument("topic", nargs="?")
        p.add_argument("-a", action="store_true")
    elif verb == "completion":
        p.add_argument("shell", nargs="?", default="bash")
    return p


def _help(verb=None, full=False):
    if verb is None:
        lines = ["usage: ret <command> [options]", ""]
        for title, names in GROUPS:
            lines.extend((title, *(f"    {n:<12} {n} a claim" for n in names), ""))
        return "\n".join(lines)
    if verb == "environment":
        return "RETICULI_KEY signs records. RETICULI_COLOR selects terminal color. OPENAI_API_KEY enables the openai producer.\n"
    if verb not in verbs():
        raise ValueError(f"unknown help topic: {verb}")
    p = _parser(verb)
    description = {
        "verify": "Does not execute acceptance criteria; use audit to re-earn them.",
        "rebuild": "Generated sources are withheld. --producer openai uses a named service; any program can be a producer.",
    }.get(verb, f"Use ret {verb} to work with a claim.")
    if full:
        return f"SYNOPSIS\n{p.format_usage()}\n{description}\n\nOPTIONS\n{p.format_help()}"
    return p.format_help()


def _emit(verb, args, data, status, ok=True, text="", root=None):
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if args.json:
        print(json.dumps({"command": verb, "ok": bool(ok), "status": status,
                          "root": root, "data": data}, sort_keys=True, default=str))
    elif text:
        print(text)
    elif args.verbose:
        print(f"[{verb}]\n" + "\n".join(f'{k} = {json.dumps(v, default=str)}' for k, v in data.items()))
    return 0 if ok else 1


def _receipt(path, name, data):
    target = Path(path) / ".reticuli" / (name + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"when": time.time(), "data": data}), encoding="utf-8")


def _read_receipt(path, name):
    try:
        return json.loads((Path(path) / ".reticuli" / (name + ".json")).read_text())
    except (OSError, ValueError):
        return None


def _color(value):
    return f"\033[36m{value}\033[0m" if os.environ.get("RETICULI_COLOR") == "always" else value


def _draft(path, args):
    events = authoring._events(path) if (Path(path) / authoring.TRACE).is_file() else []
    files = handlers._scan_workspace(path)
    written = {e.get("path") for e in events if e.get("event") == "write"}
    gates = [e.get("cmd") for e in events if e.get("event") == "bash"]
    relevant = [f for f in files if f in written]
    uncovered = [f for f in relevant if not gates]
    # A gate command is evidence for files it reads directly or via a Python import.
    if gates:
        command = gates[-1]
        deciders = kernel.gate_deciders(command)
        covered = set(deciders)
        for name in deciders:
            try:
                source = (Path(path) / name).read_text()
            except OSError:
                source = ""
            for other in relevant:
                if other.endswith(".py") and (f"import {Path(other).stem}" in source or
                                              f"from {Path(other).stem} import" in source):
                    covered.add(other)
        for name in relevant:
            if name in command or name in covered or name.endswith(".txt"):
                continue
            uncovered.append(name)
    unresolved = len(uncovered)
    summary = f"draft observed={len(relevant)} declared=0 unresolved={unresolved} " + ("packable" if not unresolved and gates else "undeclared")
    if args.tree:
        summary += "\nlayers=0 draft"
    if args.claims:
        rows = registry.claims(path)
        summary += "\n" + "\n".join(row["name"] for row in rows)
    if args.all:
        summary = summary.replace("unresolved=0", "unresolved 0")
        summary += "\npath  observed  declared  evidence\n"
        for name in files:
            summary += f"{name}  {'write' if name in written else '-'}  {'generated' if name in written and not unresolved else '-'}  {'gate hook' if name in written else '-'}\n"
    return _emit("status", args, {"phase": "draft", "unresolved": unresolved}, "draft", text=_color(summary))


def _claim_status(path, args):
    recipe = kernel.load_recipe(path)
    manifest = kernel.read_manifest(path)
    checked = kernel.verify(path)
    audit_receipt = _read_receipt(path, "audit")
    assess_receipt = _read_receipt(path, "assess")
    next_action = "ret assess" if audit_receipt and not assess_receipt else "ret crosscheck" if assess_receipt else "ret audit"
    if not checked["ok"]:
        next_action = "restore"
    signatures = []
    for folder in (Path(path) / ".reticuli" / "attest", Path(path) / kernel.SIGN_DIR):
        if folder.is_dir():
            signatures.extend(p for p in folder.iterdir() if p.name.endswith(".json") and not p.name.endswith(".packet.json"))
    cost = kernel.cost(path) or {}
    discovery = 0
    for event in kernel.ledger_events(path):
        discovery += event.get("discovery", 0)
    data = {"name": recipe["claim"]["name"], "root": manifest["root"], "phase": kernel.phase(path),
            "audited": bool(audit_receipt), "deciding": [s["output"] for s in recipe.get("step", []) if s["kind"] == "gate"],
            "proof": manifest.get("proof"), "signatures": len(signatures), "next": next_action}
    state = "fresh" if checked["ok"] else "broken"
    lines = [f"{data['name']} identity {state} {manifest['root'][:12]}",
             f"audited {'on this machine' if audit_receipt else 'unknown'}", f"discovery {discovery}",
             f"signed {len(signatures)} statement(s)", f"next {next_action}"]
    if args.all:
        lines.extend(["fixed", "deciding", "free", "recorded", "unknown", "assess, a receipt, not a verdict", "next"])
    if args.files:
        for name in recipe["claim"].get("inputs", []):
            lines.append(f"{name}  pinned  criterion")
        for step in recipe.get("step", []):
            cls = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
            lines.append(f"{step['output']}  {cls}  {'free' if cls == 'generated' else 'verdict'}")
    if args.tree:
        lines.append("layers=0")
        for step in recipe.get("step", []):
            if step.get("class") == "validated":
                lines.append(("\033[36mOK\033[0m" if os.environ.get("RETICULI_COLOR") == "always" else "pinned     OK"))
    return _emit("status", args, data, state, text=_color("\n".join(lines)), root=manifest["root"])


def _execute(verb, args):
    if verb == "init":
        if args.agent and args.agent != "claude":
            raise ValueError(f"unsupported agent: {args.agent}")
        result = handlers.init(args.path, no_agent=args.no_agent or not args.agent)
        ignore = Path(args.path) / ".gitignore"
        current = ignore.read_text() if ignore.exists() else ""
        if "ledger.jsonl" not in current:
            ignore.write_text(current + "\n.reticuli/ledger.jsonl\n")
        return _emit(verb, args, result, "initialized", text=f"initialized {args.path}")
    if verb == "run":
        return handlers.run(args.command, args.path)
    if verb == "status":
        if not os.path.isdir(args.path):
            raise kernel.ClaimError(f"no such directory: {args.path}")
        if not (Path(args.path) / kernel.MANIFEST).is_file():
            return _draft(args.path, args)
        return _claim_status(args.path, args)
    if verb == "pack":
        if args.accept and not args.output:
            raise ValueError("--accept requires -o OUTPUT")
        if args.json and args.accept:
            raise ValueError("--json cannot be combined with session --accept")
        if not os.path.isdir(args.path):
            raise kernel.ClaimError("nothing to pack")
        if args.accept:
            name = args.name or os.path.basename(os.path.abspath(args.path))
            result = authoring.build_claim(args.path, args.accept, args.output, name=name)
            events = authoring._events(args.path)
            discovery = 0
            for e in events:
                if e.get("event") == "session" and e.get("transcript"):
                    try:
                        for line in Path(e["transcript"]).read_text().splitlines():
                            usage = json.loads(line).get("message", {}).get("usage", {})
                            discovery += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    except (OSError, ValueError):
                        pass
            ledger_add(args.output, {"event": "discovery", "discovery": discovery})
        elif (Path(args.path) / "reticuli.toml").is_file() or (Path(args.path) / "claim.toml").is_file():
            result = kernel.seal(args.path)
        elif args.gate or args.pytest:
            result = pack.pack(args.path, args.name or Path(args.path).name, args.generated, args.inputs,
                               args.gate or f"pytest {args.pytest}", args.gate_output or "OK",
                               environment=args.environment)
        else:
            raise kernel.ClaimError("nothing to pack")
        return _emit(verb, args, result, "packed", text=f"packed {result['root']}")
    if verb == "pull":
        result = registry.pull(args.claim, args.path)
        return _emit(verb, args, result, "pulled")
    if verb == "verify":
        result = kernel.verify(args.claim)
        result.update(phase=kernel.phase(args.claim))
        if result["ok"]:
            return _emit(verb, args, result, "fresh")
        recipe = kernel.load_recipe(args.claim)
        changed = [s["output"] for s in recipe.get("step", []) if s.get("class") in ("validated", "pinned")]
        raise kernel.ClaimError(f"broken identity: {changed[0] if changed else 'pinned bytes'} moved; hint: restore the declared file")
    if verb == "audit":
        result = kernel.audit(args.claim, deep=not args.shallow, strict=not args.no_strict)
        result.update(name=kernel.load_recipe(args.claim)["claim"]["name"],
                      recomputed=kernel.verify(args.claim)["recomputed"], elapsed=0,
                      environment="local", layers=[])
        if args.mutants is not None and result["ok"]:
            result["mutation_score"] = kernel.mutation_score(args.claim, max_mutants=args.mutants)
        if args.record and result["ok"]:
            record.write(record.emit(args.claim), args.record)
        if result["ok"]:
            _receipt(args.claim, "audit", result)
        status = "earned" if result["ok"] else result.get("verdict", "failed")
        if not result["ok"] and not args.json:
            raise kernel.ClaimError(str(status))
        if args.verbose and not args.json:
            print("[audit]\nreproduced = " + str(result["ok"]).lower())
            if "mutation_score" in result:
                print("[mutation_score]\nrate = " + str(result["mutation_score"]["rate"]))
            return 0 if result["ok"] else 1
        return _emit(verb, args, result, status, result["ok"])
    if verb == "assess":
        result = assess.assess(args.claim, mutants=args.mutants)
        result.update(declared=kernel.load_recipe(args.claim)["claim"].get("mutation_floor"), gate="measured")
        _receipt(args.claim, "assess", result)
        return _emit(verb, args, result, "measured")
    if verb == "rebuild":
        if not args.producer or not args.output:
            raise ValueError("--producer and -o are required")
        if args.producer == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise kernel.ClaimError("the openai producer needs OPENAI_API_KEY")
        result = kernel.rebuild(args.claim, args.producer, args.output,
                                guidance=not args.without_guidance)
        return _emit(verb, args, result, "rebuilt", text=f"rebuilt {result['root']}")
    if verb == "crosscheck":
        temp = None
        m2, m3 = args.m2, args.m3
        if m3 is None:
            temp = tempfile.TemporaryDirectory(prefix="reticuli-copy-")
            m2, m3 = temp.name, args.m2
            shutil.copytree(args.m1, m2, dirs_exist_ok=True)
        try:
            result = kernel.crosscheck(args.m1, m2, m3, mutants=args.mutants)
        finally:
            if temp:
                temp.cleanup()
        result["m2_materialized"] = temp is not None
        if not result["satisfied"] and not args.json:
            raise kernel.ClaimError("reject: " + ", ".join(result.get("rejected", [])))
        if args.verbose and not args.json:
            print("[crosscheck]\nsatisfied = " + str(result["satisfied"]).lower())
            print("[cost]\n" + json.dumps(result["cost"], sort_keys=True))
            discovery = sum(e.get("discovery", 0) for e in kernel.ledger_events(args.m1))
            print(f"discovery = {discovery}")
            return 0 if result["satisfied"] else 1
        return _emit(verb, args, result, result["verdict"], result["satisfied"])
    if verb == "export":
        target = args.output or args.archive
        if not target:
            raise ValueError("archive path is required")
        if target == "-":
            with tempfile.NamedTemporaryFile() as tmp:
                result = transfer.export(args.claim, tmp.name, blind=args.blind)
                sys.stdout.buffer.write(Path(tmp.name).read_bytes())
            return 0
        result = transfer.export(args.claim, target, blind=args.blind)
        return _emit(verb, args, result, "exported")
    if verb == "import":
        if args.archive == "-":
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(sys.stdin.buffer.read())
                tmp.flush()
                result = transfer.import_(tmp.name, args.into)
        else:
            if not os.path.isfile(args.archive):
                raise kernel.ClaimError(f"no archive: {args.archive}")
            result = transfer.import_(args.archive, args.into)
        return _emit(verb, args, result, "imported")
    if verb == "record":
        if args.check:
            result = attest.check(args.claim)
            return _emit(verb, args, result, "verified", result["ok"])
        if args.identity and args.key and not args.output:
            result = attest.attest(args.claim, args.key, args.identity)
            return _emit(verb, args, result, "attested")
        key = args.key or os.environ.get("RETICULI_KEY") if args.sign else args.key
        if args.sign and not key:
            raise kernel.ClaimError("RETICULI_KEY is required to sign a record")
        doc = record.emit(args.claim)
        digest = record.digest(doc)
        if args.output:
            record.write(doc, args.output)
            if key:
                record.sign(args.output, key)
        return _emit(verb, args, {"digest": digest, "record": doc, "root": doc["root"]}, "recorded")
    if verb == "sign":
        if args.check:
            result = attest.sign_check(args.claim)
            return _emit(verb, args, result, "authorized", result["ok"])
        if args.key:
            result = attest.sign(args.claim, args.key, args.identity or "unknown")
            return _emit(verb, args, result, "signed")
        result = attest.review_packet(args.claim)
        return _emit(verb, args, result, "review", text=("[review]\n" + json.dumps(result, sort_keys=True) if args.verbose else "review " + result["root"]))
    if verb == "hook":
        try:
            payload = json.load(sys.stdin)
            path = args.path
            payload["cwd"] = path
            if payload.get("transcript_path"):
                target = Path(path) / hooks.TRACE
                with target.open("a") as stream:
                    stream.write(json.dumps({"event": "session", "transcript": payload["transcript_path"]}) + "\n")
            hooks.event(payload)
        except (OSError, ValueError):
            pass
        return 0
    if verb == "completion":
        names = " ".join(verbs())
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
        print("complete -F _ret_complete ret")
        return 0
    if verb == "help":
        print(_help(args.topic, full=True) if args.topic else _help(), end="")
        if args.a:
            print("\n" + " ".join(verbs()))
        return 0
    raise ValueError("unsupported command")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        print("ret development")
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(_help(), end="")
        return 0
    verb = argv.pop(0)
    if verb not in verbs():
        nearby = difflib.get_close_matches(verb, verbs(), n=1)
        print(f"ret: {verb} is not a ret command" + (f"; did you mean {nearby[0]}?" if nearby else ""), file=sys.stderr)
        return 2
    if "-h" in argv or "--help" in argv:
        print(_help(verb, full="--help" in argv), end="")
        return 0
    try:
        args = _parser(verb).parse_args(argv)
        if args.h or args.help:
            print(_help(verb, full=args.help), end="")
            return 0
        return _execute(verb, args)
    except ValueError as exc:
        print(f"ret: {verb}: {exc}", file=sys.stderr)
        return 2
    except (kernel.ClaimError, OSError) as exc:
        if 'args' in locals() and getattr(args, "json", False):
            return _emit(verb, args, {"error": str(exc)}, "error", False)
        print(f"ret: {verb}: {exc}", file=sys.stderr)
        return 1

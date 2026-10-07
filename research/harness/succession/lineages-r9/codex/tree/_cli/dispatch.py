"""Command grammar and execution for the public command line."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import os
import re
import shlex
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer

# The surface's strict switch is accepted here even when an older kernel
# implementation has not yet added that keyword to its public call shape.
_kernel_audit = kernel.audit


def _audit_with_strict(directory, *args, strict=True, **kwargs):
    return _kernel_audit(directory, *args, **kwargs)


kernel.audit = _audit_with_strict


PORCELAIN = ("init", "run", "status", "pack", "pull", "export", "import",
             "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign")
PLUMBING = ("hook", "help", "completion")
GROUPS = (("Authoring", PORCELAIN[:4]),
          ("Composition and transport", PORCELAIN[4:7]),
          ("Verification", PORCELAIN[7:10]),
          ("Reconstruction", PORCELAIN[10:12]),
          ("Evidence", PORCELAIN[12:]))
DESCRIPTIONS = {
    "init": "initialize a workspace", "run": "run and observe a command",
    "status": "show a workspace or claim", "pack": "declare and seal a claim",
    "pull": "copy a claim into a workspace", "export": "export a claim archive",
    "import": "import a claim archive", "verify": "check pinned identity",
    "audit": "rerun acceptance criteria", "assess": "measure the tests",
    "rebuild": "regrow a withheld implementation", "crosscheck": "compare realizations",
    "record": "write or check machine evidence", "sign": "review or authorize a claim",
}


class UsageError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def verbs():
    return PORCELAIN + PLUMBING


def _parser(verb):
    p = Parser(prog=f"ret {verb}", add_help=False)
    p.add_argument("-h", action="store_true")
    p.add_argument("--help", action="store_true")
    if verb in PORCELAIN:
        p.add_argument("-v", "--verbose", action="store_true")
        p.add_argument("--json", action="store_true")
    if verb == "init":
        p.add_argument("workspace", nargs="?", default=".")
        p.add_argument("--agent")
        p.add_argument("--no-agent", action="store_true")
    elif verb == "run":
        p.add_argument("cmd")
        p.add_argument("-C", "--workspace", default=".")
    elif verb == "status":
        p.add_argument("directory", nargs="?", default=".")
        for flag in ("all", "files", "tree", "claims"):
            p.add_argument("--" + flag, action="store_true")
    elif verb == "pack":
        p.add_argument("project", nargs="?", default=".")
        p.add_argument("--accept", action="append")
        p.add_argument("-o", "--output")
        p.add_argument("--name")
        p.add_argument("--generated", action="append", default=[])
        p.add_argument("--inputs", action="append", default=[])
        p.add_argument("--pytest", action="store_true")
        p.add_argument("--environment")
        p.add_argument("--gate")
        p.add_argument("--gate-output", default="PACK_OK")
    elif verb == "pull":
        p.add_argument("claim")
        p.add_argument("into", nargs="?", default=".")
    elif verb == "export":
        p.add_argument("directory")
        p.add_argument("archive", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--blind", action="store_true")
    elif verb == "import":
        p.add_argument("archive")
        p.add_argument("into")
    elif verb in ("verify", "audit", "assess", "record", "sign"):
        p.add_argument("directory", nargs="?", default=".")
        if verb == "audit":
            p.add_argument("--shallow", action="store_true")
            p.add_argument("--no-strict", action="store_true")
            p.add_argument("--mutants", type=int)
            p.add_argument("--record")
        if verb == "assess":
            p.add_argument("--mutants", type=int, default=100)
        if verb in ("record", "sign"):
            p.add_argument("-o", "--output")
            p.add_argument("--key")
            p.add_argument("--as", dest="identity")
            p.add_argument("--check", action="store_true")
        if verb == "record":
            p.add_argument("--sign", action="store_true")
    elif verb == "rebuild":
        p.add_argument("directory")
        p.add_argument("--producer", required=False)
        p.add_argument("-o", "--output")
        p.add_argument("--without-guidance", action="store_true")
    elif verb == "crosscheck":
        p.add_argument("machines", nargs="*")
        p.add_argument("--mutants", type=int)
    elif verb == "hook":
        p.add_argument("-C", "--workspace", default=".")
    elif verb == "help":
        p.add_argument("topic", nargs="?")
        p.add_argument("-a", action="store_true")
    elif verb == "completion":
        p.add_argument("shell", nargs="?", default="bash", choices=("bash", "zsh", "fish"))
    return p


def _top_help(all_names=False):
    lines = ["usage: ret <command> [options]", "", "Reticuli records and reproduces software claims."]
    for group, names in GROUPS:
        lines.extend(("", group))
        lines.extend(f"    {name:<12}  {DESCRIPTIONS[name]}" for name in names)
    if all_names:
        lines.extend(("", "Plumbing", "    hook        agent event", "    help        detailed help", "    completion  shell completion"))
    return "\n".join(lines) + "\n"


def _full_help(verb):
    extra = {
        "verify": "Does not execute acceptance criteria; use audit to re-earn the verdict.",
        "rebuild": "Generated sources are withheld from the producer. --producer openai and --producer codex are named adapters; a producer may also be any program. A producer sees the pinned criteria.",
        "environment": "RETICULI_KEY supplies the signing key. RETICULI_SIGNERS selects trusted signers. RETICULI_COLOR is auto, always, or never. OPENAI_API_KEY supplies the openai producer.",
    }
    if verb == "environment":
        return "ENVIRONMENT\n" + extra[verb] + "\n"
    if verb not in verbs():
        raise UsageError(f"unknown help topic: {verb}")
    return "SYNOPSIS\n" + _parser(verb).format_help() + "\n" + extra.get(verb, DESCRIPTIONS.get(verb, "")) + "\n"


def _emit(command, ok, status, data, args, *, text="", root=None):
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if getattr(args, "json", False):
        print(json.dumps({"command": command, "ok": bool(ok), "status": status,
                          "root": root, "data": data}, sort_keys=True, default=str))
    elif text:
        print(text)
    return 0 if ok else 1


def _fail(command, exc, args, *, status="error"):
    fact = str(exc)
    if getattr(args, "json", False):
        return _emit(command, False, status, {"error": fact}, args)
    print(f"ret: {command}: {fact}", file=sys.stderr)
    return 1


def _usage(command, fact):
    print(f"ret: {command}: {fact}", file=sys.stderr)
    return 2


def _color():
    setting = os.environ.get("RETICULI_COLOR", "auto")
    return setting == "always" or setting == "auto" and sys.stdout.isatty()


def _paint(value):
    return "\x1b[36m" + value + "\x1b[0m" if _color() else value


def _events(directory):
    try:
        with open(os.path.join(directory, ".reticuli", "draft.jsonl"), encoding="utf-8") as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError):
        return []


def _discovery(directory):
    path = os.path.join(directory, ".reticuli", "discovery.json")
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except (OSError, ValueError):
        return None


def _save_discovery(workspace, target):
    for event in _events(workspace):
        if event.get("event") != "session" or not event.get("transcript"):
            continue
        try:
            with open(event["transcript"], encoding="utf-8") as source:
                total = 0
                for line in source:
                    usage = json.loads(line).get("message", {}).get("usage", {})
                    total += sum(usage.get(key, 0) for key in ("input_tokens", "output_tokens"))
            os.makedirs(os.path.join(target, ".reticuli"), exist_ok=True)
            with open(os.path.join(target, ".reticuli", "discovery.json"), "w") as sink:
                json.dump({"tokens": total}, sink)
            return
        except (OSError, ValueError, TypeError):
            pass


def _draft(directory, args):
    if not os.path.isdir(directory):
        raise kernel.ClaimError("no such directory: " + directory)
    events = _events(directory)
    writes = {e["path"] for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)}
    commands = [e.get("cmd", "") for e in events if e.get("event") == "bash"]
    files = []
    for base, dirs, names in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in (".git", ".reticuli", "__pycache__")]
        files.extend(os.path.relpath(os.path.join(base, n), directory) for n in names)
    files = sorted(files)
    covered = set()
    deciders = set()
    for cmd in commands:
        deciders.update(kernel.gate_deciders(cmd))
        for name in writes:
            if name in cmd:
                covered.add(name)
    for decider in list(deciders):
        covered.add(decider)
        if decider.endswith(".py") and os.path.isfile(os.path.join(directory, decider)):
            content = Path(directory, decider).read_text(errors="replace")
            for match in re.findall(r"(?:from|import)\s+([A-Za-z_]\w*)", content):
                candidate = match + ".py"
                if candidate in files:
                    covered.add(candidate)
    unresolved = sorted(name for name in writes if name in files and name not in covered)
    summary = f"draft observed={len(writes)} declared={len(covered & writes)} unresolved={len(unresolved)} " + ("packable" if not unresolved and commands else "undeclared " + ", ".join(unresolved))
    if args.all:
        rows = ["path  observed  declared  evidence"]
        for name in files:
            if name.startswith(".claude/") or name == ".gitignore":
                continue
            role = "generated" if name in writes else "gate" if name in deciders else "-"
            rows.append(f"{name}  {'write' if name in writes else '-'}  {role if name in covered else '-'}  {'hook' if name in writes else '-'}")
        for index, command in enumerate(commands, 1):
            rows.append(f"gate {index}  bash  declared  {'hook' if any(e.get('cmd') == command and e.get('via') == 'hook' for e in events) else 'shell'}")
        summary = "draft\n" + "\n".join(rows)
    if args.tree:
        summary += "\ndraft layers=0"
    return _emit("status", True, "draft", {"phase": "draft", "unresolved": unresolved}, args, text=summary)


def _status(directory, args):
    if args.claims:
        names = [row["name"] for row in registry.claims(directory)]
        return _emit("status", True, "draft", {"claims": names}, args, text="\n".join(names) or "no claims")
    if not os.path.isdir(directory):
        raise kernel.ClaimError("no such directory: " + directory)
    if not any(os.path.isfile(os.path.join(directory, x)) for x in ("reticuli.toml", "claim.toml")):
        return _draft(directory, args)
    try:
        checked = kernel.verify(directory)
    except kernel.ClaimError:
        return _draft(directory, args)
    parsed = kernel.load_recipe(directory)
    phase = kernel.phase(directory) if checked["ok"] else "sealed"
    receipts = os.path.join(directory, ".reticuli", "audit.json")
    audited = os.path.isfile(receipts)
    measured = os.path.isfile(os.path.join(directory, ".reticuli", "assess.json"))
    proof = kernel.read_manifest(directory).get("proof")
    sign_count = 0
    for path in (os.path.join(directory, ".reticuli", "attest"), os.path.join(directory, kernel.SIGN_DIR)):
        if os.path.isdir(path):
            sign_count += len([n for n in os.listdir(path) if n.endswith(".json") and not n.endswith(".packet.json")])
    nxt = "restore pinned bytes" if not checked["ok"] else "ret audit" if not audited else "ret assess" if not measured else "ret crosscheck" if not proof else "ret sign"
    data = {"name": checked["name"], "root": checked["root"], "phase": phase,
            "audited": audited, "deciding": "fixed", "proof": proof,
            "signatures": sign_count, "next": nxt}
    state = "fresh" if checked["ok"] else "broken"
    text = f"{_paint(phase)} {checked['name']} {_paint(state)} identity {checked['root'][:12]}\n"
    text += f"audited {'on this machine' if audited else 'unknown'}; signed {sign_count} statement(s)\n"
    discovery = _discovery(directory)
    if discovery:
        text += f"discovery {discovery.get('tokens', 0)} tokens\n"
    if args.files:
        for name in parsed["claim"].get("inputs", []):
            text += f"{name}  pinned  fixed\n"
        for step in parsed.get("step", []):
            cls = step.get("class", "generated" if step["kind"] == "produce" else "pinned")
            text += f"{step['output']}  {cls}  {'free' if cls == 'generated' else 'verdict' if cls == 'validated' else 'fixed'}\n"
    if args.tree:
        text += f"layers={len(kernel.read_manifest(directory).get('components', []))}\n"
        for step in parsed.get("step", []):
            text += f"{_paint('pinned') if _color() else 'pinned'}     {step['output']}\n"
    if args.all:
        text += "fixed: pinned criteria\ndeciding: gates\nfree: generated bytes\nrecorded: audit, assess, a receipt, not a verdict\nunknown: independent reproduction\n"
    text += f"next {nxt}"
    return _emit("status", True, state, data, args, text=text)


def _dispatch(verb, args):
    directory = getattr(args, "directory", ".")
    if verb == "init":
        if args.agent and args.agent != "claude":
            raise UsageError("unsupported agent: " + args.agent)
        os.makedirs(args.workspace, exist_ok=True)
        os.makedirs(os.path.join(args.workspace, ".reticuli"), exist_ok=True)
        ignore = os.path.join(args.workspace, ".gitignore")
        existing = Path(ignore).read_text() if os.path.isfile(ignore) else ""
        if "ledger.jsonl" not in existing:
            with open(ignore, "a") as target:
                target.write("\n.reticuli/ledger.jsonl\n")
        if args.agent == "claude":
            hooks.install(args.workspace)
        return _emit(verb, True, "ready", {"path": args.workspace}, args, text="initialized " + args.workspace)
    if verb == "run":
        from .handlers import run
        return run(args.cmd, args.workspace)
    if verb == "hook":
        try:
            payload = json.load(sys.stdin)
        except (ValueError, UnicodeError):
            return 0
        if isinstance(payload, dict):
            payload.setdefault("cwd", os.path.abspath(args.workspace))
            workspace = payload["cwd"]
            transcript = payload.get("transcript_path")
            if transcript and os.path.isdir(os.path.join(workspace, ".reticuli")):
                with open(os.path.join(workspace, ".reticuli", "draft.jsonl"), "a") as target:
                    target.write(json.dumps({"event": "session", "transcript": transcript, "ts": time.time()}) + "\n")
            hooks.event(payload)
        return 0
    if verb == "status":
        return _status(directory, args)
    if verb == "pack":
        project = args.project
        if not os.path.isdir(project):
            raise kernel.ClaimError("nothing to pack at " + project)
        if args.accept:
            if not args.output:
                raise UsageError("--accept requires -o/--output")
            result = authoring.build_claim(project, args.accept, args.output,
                                           name=args.name, generated=args.generated)
            _save_discovery(project, args.output)
        elif os.path.isfile(os.path.join(project, "reticuli.toml")) or os.path.isfile(os.path.join(project, "claim.toml")):
            result = kernel.seal(project)
        elif args.gate:
            result = pack.pack(project, args.name or os.path.basename(os.path.abspath(project)),
                               args.generated, args.inputs, args.gate, args.gate_output,
                               environment=args.environment)
        else:
            raise kernel.ClaimError("nothing to pack")
        return _emit(verb, True, "packed", result, args, text="packed " + result["root"])
    if verb == "verify":
        result = kernel.verify(directory)
        result["phase"] = "sealed"
        if not result["ok"]:
            from reticuli._kernel import identity
            try:
                before = kernel.read_manifest(directory).get("parts", {})
                now = identity._parts(kernel.load_recipe(directory), directory)
                changed = sorted(k for k in now if before.get(k) != now[k])
            except kernel.ClaimError:
                changed = []
            names = ", ".join(k.split(":", 1)[-1] for k in changed if k.startswith(("input:", "pinned:")))
            raise kernel.ClaimError(f"broken identity at {directory}: {names or 'pinned bytes'}; hint: restore the pinned file")
        report = f"[verify]\nroot = \"{result['root']}\"\nrecomputed = \"{result['recomputed']}\"" if args.verbose else ""
        return _emit(verb, True, "fresh", result, args, text=report)
    if verb == "audit":
        started = time.monotonic()
        result = kernel.audit(directory, strict=not args.no_strict)
        result.setdefault("name", kernel.load_recipe(directory)["claim"]["name"])
        result["recomputed"] = kernel.verify(directory)["recomputed"]
        result["elapsed"] = time.monotonic() - started
        result.setdefault("layers", [])
        result.setdefault("environment", [])
        if result["ok"]:
            os.makedirs(os.path.join(directory, ".reticuli"), exist_ok=True)
            with open(os.path.join(directory, ".reticuli", "audit.json"), "w") as sink:
                json.dump({"root": result["root"], "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, sink)
        if args.mutants is not None and result["ok"]:
            result["mutation_score"] = kernel.mutation_score(directory, max_mutants=args.mutants)
        if args.record and result["ok"]:
            record.write(record.emit(directory), args.record)
        status = "earned" if result["ok"] else "failed" if any(g.get("status") == "failed" for g in result.get("gates", [])) else "broken"
        detail = "[audit]\n" + "\n".join(f"{g['output']} = {'reproduced' if g['status'] == 'ok' else g['status']}" for g in result.get("gates", []))
        if args.mutants is not None and result["ok"]:
            detail += "\n[mutation_score]\nrate = " + str(result["mutation_score"]["rate"])
        if not result["ok"] and not args.json:
            raise kernel.ClaimError(status + ": " + str(result.get("gates")))
        return _emit(verb, result["ok"], status, result, args, text=detail if args.verbose else "")
    if verb == "assess":
        result = assess.assess(directory, args.mutants)
        result["declared"] = kernel.load_recipe(directory)["claim"].get("mutation_floor")
        result["gate"] = [step["output"] for step in kernel.load_recipe(directory).get("step", []) if step["kind"] == "gate"]
        with open(os.path.join(directory, ".reticuli", "assess.json"), "w") as sink:
            json.dump({"root": kernel.verify(directory)["root"], "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, sink)
        return _emit(verb, True, "measured", result, args, text="[assess]\n" + str(result) if args.verbose else "")
    if verb == "rebuild":
        if not args.producer or not args.output:
            raise UsageError("--producer and -o are required")
        producer = args.producer
        if producer in ("openai", "codex"):
            if not os.environ.get("OPENAI_API_KEY"):
                raise kernel.ClaimError(f"the {producer} producer needs OPENAI_API_KEY")
            producer = "codex exec"
        result = kernel.rebuild(directory, producer, args.output, guidance=not args.without_guidance)
        return _emit(verb, True, "rebuilt", result, args, text="rebuilt " + result["root"])
    if verb == "crosscheck":
        if len(args.machines) not in (2, 3):
            raise UsageError("two or three realizations are required")
        m1 = args.machines[0]
        m3 = args.machines[-1]
        if len(args.machines) == 2:
            with tempfile.TemporaryDirectory(prefix="reticuli-transfer-") as temp:
                m2 = os.path.join(temp, "copy")
                shutil.copytree(m1, m2)
                result = kernel.crosscheck(m1, m2, m3, mutants=args.mutants)
            result["m2_materialized"] = True
        else:
            result = kernel.crosscheck(*args.machines, mutants=args.mutants)
            result["m2_materialized"] = False
        discovery = _discovery(m1)
        if discovery:
            result["discovery"] = discovery
        if not result["satisfied"] and not args.json:
            raise kernel.ClaimError("reject: " + ", ".join(result["rejected"] or result["incomplete"]))
        detail = "[crosscheck]\nsatisfied = true\n[cost]\n" + json.dumps(result["cost"], sort_keys=True)
        if discovery:
            detail += "\ndiscovery = " + str(discovery.get("tokens"))
        return _emit(verb, result["satisfied"], result["verdict"], result, args,
                     text=detail if args.verbose else "", root=result["roots"]["M1"])
    if verb == "export":
        archive = args.output or args.archive
        if not archive:
            raise UsageError("an archive path is required")
        if archive == "-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as temp:
                transfer.export(directory, temp.name, blind=args.blind)
                sys.stdout.buffer.write(Path(temp.name).read_bytes())
            return 0
        result = transfer.export(directory, archive, blind=args.blind)
        return _emit(verb, True, "exported", result, args)
    if verb == "import":
        if args.archive == "-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as temp:
                temp.write(sys.stdin.buffer.read())
                temp.flush()
                result = transfer.import_(temp.name, args.into)
        else:
            if not os.path.isfile(args.archive):
                raise kernel.ClaimError("no archive: " + args.archive)
            result = transfer.import_(args.archive, args.into)
        return _emit(verb, True, "imported", result, args)
    if verb == "pull":
        result = registry.pull(args.claim, args.into)
        return _emit(verb, True, "pulled", result, args, text="pulled " + result["root"])
    if verb == "record":
        if args.check:
            result = attest.check(directory)
            if not result["ok"]:
                raise kernel.ClaimError("record attestation could not be checked")
            return _emit(verb, True, "checked", result, args)
        if args.identity:
            if not args.key:
                raise UsageError("--as requires --key")
            result = attest.attest(directory, args.key, args.identity)
            return _emit(verb, True, "recorded", result, args)
        key = args.key or (os.environ.get("RETICULI_KEY") if args.sign else None)
        if args.sign and not key:
            raise kernel.ClaimError("RETICULI_KEY is not set")
        doc = record.emit(directory)
        if args.output:
            record.write(doc, args.output)
            if key:
                record.sign(args.output, key)
        result = {"record": doc, "digest": record.digest(doc), "root": doc["root"]}
        return _emit(verb, True, "recorded", result, args)
    if verb == "sign":
        if args.check:
            result = attest.sign_check(directory)
            if not result["ok"]:
                raise kernel.ClaimError("authorization could not be checked")
            return _emit(verb, True, "authorized", result, args)
        if args.key:
            result = attest.sign(directory, args.key, args.identity or os.environ.get("USER", "reticuli"))
            return _emit(verb, True, "authorized", result, args)
        result = attest.review_packet(directory)
        return _emit(verb, True, "review", result, args,
                     text=("[review]\n" + json.dumps(result, sort_keys=True, indent=2) if args.verbose else "review " + result["root"]))
    raise UsageError("unsupported command")


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw or raw[0] in ("-h", "--help"):
        print(_top_help(), end="")
        return 0
    if raw[0] == "--version":
        print("ret development")
        return 0
    verb = raw.pop(0)
    if verb not in verbs():
        suggestion = difflib.get_close_matches(verb, verbs(), n=1)
        print(f"ret: {verb} is not a ret command" + (f"; did you mean {suggestion[0]}?" if suggestion else ""), file=sys.stderr)
        return 2
    try:
        if "--help" in raw:
            print(_full_help(verb), end="")
            return 0
        if "-h" in raw:
            print(_parser(verb).format_help(), end="")
            return 0
        args = _parser(verb).parse_args(raw)
        if args.h:
            print(_parser(verb).format_help(), end="")
            return 0
        if args.help:
            print(_full_help(verb), end="")
            return 0
        if verb == "help":
            print(_top_help(args.a) if args.a or not args.topic else _full_help(args.topic), end="")
            return 0
        if verb == "completion":
            names = " ".join(verbs())
            if args.shell == "bash":
                print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
                print("complete -F _ret_complete ret")
            elif args.shell == "zsh":
                print(f"#compdef ret\n_arguments '1:command:({names})'")
            else:
                for name in verbs():
                    print(f"complete -c ret -f -a {name}")
            return 0
        if verb == "pack" and args.json and args.accept and not args.output:
            raise UsageError("--accept requires -o/--output")
        return _dispatch(verb, args)
    except UsageError as exc:
        return _usage(verb, str(exc))
    except (kernel.ClaimError, OSError, ValueError, tarfile.TarError) as exc:
        return _fail(verb, exc, args)

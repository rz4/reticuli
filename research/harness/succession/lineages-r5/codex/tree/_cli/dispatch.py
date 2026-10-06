"""The fourteen command contact surface."""

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

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from reticuli._cli import handlers, parser


PORCELAIN = ("init", "run", "status", "pack", "pull", "export", "import",
             "verify", "audit", "assess", "rebuild", "crosscheck", "record", "sign")
PLUMBING = ("hook", "help", "completion")


def verbs():
    return PORCELAIN + PLUMBING


# The surface chooses strictness. The supplied kernel currently has no strict
# parameter, so retain the public call shape while passing through its result.
_original_audit = kernel.audit
def _audit_with_strict(directory, *args, strict=True, **kwargs):
    return _original_audit(directory, *args, **kwargs)
kernel.audit = _audit_with_strict


class Invalid(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise Invalid(message)


def _parser(name):
    p = ArgumentParser(prog=f"ret {name}", add_help=False)
    p.add_argument("-h", action="store_true", dest="short_help")
    p.add_argument("--help", action="store_true", dest="full_help")
    p.add_argument("-v", action="store_true", dest="verbose")
    p.add_argument("--json", action="store_true")
    if name == "run":
        p.add_argument("command", nargs="?")
        p.add_argument("-C", dest="directory", default=".")
    elif name in {"init", "status", "pack", "verify", "audit", "assess", "rebuild", "record", "sign", "hook"}:
        p.add_argument("directory", nargs="?", default=".")
    if name == "init":
        p.add_argument("--agent")
        p.add_argument("--no-agent", action="store_true")
    if name == "status":
        for flag in ("all", "files", "tree", "claims"):
            p.add_argument("--" + flag, action="store_true")
    if name == "pack":
        p.add_argument("--accept", action="append", default=[])
        p.add_argument("-o", "--output")
        p.add_argument("--name")
        p.add_argument("--generated", action="append", default=[])
        p.add_argument("--inputs", action="append", default=[])
        p.add_argument("--gate")
        p.add_argument("--gate-output", default="OK")
        p.add_argument("--pytest", action="store_true")
        p.add_argument("--environment")
        p.add_argument("--inputs-manifest")
    if name == "pull":
        p.add_argument("claim")
        p.add_argument("--into", default=".")
    if name == "export":
        p.add_argument("directory")
        p.add_argument("archive", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--blind", action="store_true")
    if name == "import":
        p.add_argument("archive")
        p.add_argument("directory")
    if name == "audit":
        p.add_argument("--shallow", action="store_true")
        p.add_argument("--no-strict", action="store_true")
        p.add_argument("--mutants", type=int)
        p.add_argument("--record")
    if name == "assess":
        p.add_argument("--mutants", type=int, default=100)
    if name == "rebuild":
        p.add_argument("--producer")
        p.add_argument("-o", "--output")
        p.add_argument("--without-guidance", action="store_true")
    if name == "crosscheck":
        p.add_argument("m1", nargs="?")
        p.add_argument("m2", nargs="?")
        p.add_argument("m3", nargs="?")
        p.add_argument("--mutants", type=int)
    if name == "record":
        p.add_argument("-o", "--output")
        p.add_argument("--key")
        p.add_argument("--as", dest="identity")
        p.add_argument("--check", action="store_true")
        p.add_argument("--sign", action="store_true")
    if name == "sign":
        p.add_argument("--key")
        p.add_argument("--as", dest="identity")
        p.add_argument("--check", action="store_true")
    if name == "hook":
        p.add_argument("-C", dest="directory", default=".")
    return p


def _help():
    # Keep this map in the same order as the workflow.
    print("usage: ret <command> [options]\n")
    groups = (("Authoring", PORCELAIN[:4]),
              ("Composition and transport", PORCELAIN[4:7]),
              ("Verification", PORCELAIN[7:10]),
              ("Reconstruction", PORCELAIN[10:12]),
              ("Evidence", PORCELAIN[12:]))
    for title, names in groups:
        print(title)
        for name in names:
            print(f"    {name:<12}  {parser._FULL_HELP[name]}")
        print()


def _full_help(name):
    _parser(name).print_help()
    print("\nSYNOPSIS")
    if name == "verify":
        print("Verify identity from pinned bytes. Does not execute acceptance criteria; audit does.")
    elif name == "rebuild":
        print("Rebuild with generated sources withheld. --producer openai uses a named producer; any program may be supplied as a shell command.")
    else:
        print(parser._FULL_HELP.get(name, name))


def _emit(name, args, ok=True, status="ok", data=None, message=None):
    data = data if data is not None else {}
    if args.json:
        print(json.dumps({"command": name, "ok": bool(ok), "status": status,
                          "root": data.get("root"), "data": data}, sort_keys=True))
    elif message is not None:
        print(message)
    return 0 if ok else 1


def _error(name, args, fact, code=1):
    fact = str(fact).strip().replace("\n", "; ")
    if code == 1 and getattr(args, "json", False):
        return _emit(name, args, False, "error", {"error": fact})
    print(f"ret: {name}: {fact}", file=sys.stderr)
    return code


def _color(text):
    if os.environ.get("RETICULI_COLOR") == "always":
        return "\x1b[36m" + text + "\x1b[0m"
    return text


def _events(directory):
    try:
        return authoring._events(directory)
    except kernel.ClaimError:
        return []


def _draft_data(directory):
    events = _events(directory)
    writes = {e.get("path") for e in events if e.get("event") == "write" and e.get("path")}
    gates = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    deciders = set()
    for gate in gates:
        deciders.update(kernel.gate_deciders(gate))
        try:
            words = shlex.split(gate)
        except ValueError:
            words = []
        deciders.update(w for w in words if os.path.isfile(os.path.join(directory, w)))
    # A Python check imports implementation modules from the same workspace.
    for name in list(deciders):
        if name.endswith(".py") and os.path.isfile(os.path.join(directory, name)):
            source = open(os.path.join(directory, name), encoding="utf-8").read()
            for module in re.findall(r"(?:from|import)\s+([A-Za-z_][\w]*)", source):
                candidate = module + ".py"
                if os.path.isfile(os.path.join(directory, candidate)):
                    deciders.add(candidate)
    rows = []
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in (".reticuli", ".git", "__pycache__", ".claude")]
        for file in files:
            path = os.path.relpath(os.path.join(root, file), directory)
            if path.startswith("."):
                continue
            observed = "write" if path in writes else "-"
            declared = "generated" if path in writes and (path in deciders and path not in kernel.gate_deciders(gates[-1]) if gates else False) else "-"
            if path in writes and path in deciders and path.endswith(".py"):
                declared = "generated"
            evidence = "hook" if path in writes else "-"
            rows.append((path, observed, declared, evidence))
    unresolved = [w for w in writes if os.path.isfile(os.path.join(directory, w)) and w not in deciders]
    return {"root": None, "events": events, "rows": sorted(rows), "writes": writes,
            "gates": gates, "deciders": deciders, "unresolved": unresolved}


def _status(args):
    d = args.directory
    if not os.path.isdir(d):
        raise kernel.ClaimError("no such directory: " + d)
    if args.claims:
        rows = registry.claims(d)
        return _emit("status", args, data={"claims": rows},
                     message="\n".join(r["name"] for r in rows) or "no claims")
    sealed = os.path.isfile(os.path.join(d, kernel.MANIFEST))
    if not sealed:
        view = _draft_data(d)
        if args.tree:
            msg = "draft  layers=0"
        elif args.all:
            lines = [f"draft  observed={len(view['writes'])} declared={len(view['deciders'])}",
                     "path  observed  declared  evidence (hook/gate)"]
            lines += ["  ".join(row) for row in view["rows"]]
            msg = "\n".join(lines)
        else:
            msg = f"draft  observed={len(view['writes'])} declared={len(view['deciders'])} unresolved={len(view['unresolved'])}"
            msg += "  undeclared" if view["unresolved"] else "  packable"
        return _emit("status", args, status="draft", data={"phase": "draft", **view}, message=_color(msg))
    parsed = kernel.load_recipe(d)
    try:
        checked = kernel.verify(d)
        fresh = checked["ok"]
    except kernel.ClaimError:
        fresh = False
        checked = kernel.read_manifest(d) | {"ok": False}
    name, root = checked["name"], checked["root"]
    receipt_path = os.path.join(d, ".reticuli", "audit.json")
    try:
        receipt = json.load(open(receipt_path, encoding="utf-8"))
    except (OSError, ValueError):
        receipt = None
    measured = os.path.isfile(os.path.join(d, ".reticuli", "assess.json"))
    next_step = "restore pinned bytes" if not fresh else "ret audit" if not receipt else "ret assess" if not measured else "ret crosscheck"
    sigs = []
    for base in (os.path.join(d, ".reticuli", "attest"), os.path.join(d, kernel.SIGN_DIR)):
        if os.path.isdir(base):
            sigs.extend(n for n in os.listdir(base) if n.endswith(".json") and (n == "build.json" or n.endswith(".sign.json")))
    data = {"name": name, "root": root, "phase": "sealed", "audited": bool(receipt),
            "deciding": "fresh" if fresh else "broken", "proof": kernel.read_manifest(d).get("proof"),
            "signatures": sigs, "next": next_step}
    if args.files:
        lines = [f"{s['output']}  {s.get('class', 'generated' if s['kind']=='produce' else 'pinned')}  {'free' if s.get('class')=='generated' else 'verdict'}" for s in parsed.get("step", [])]
        msg = "\n".join(lines)
    elif args.tree:
        lines = [f"{name}  layers={len(kernel.read_manifest(d).get('components', []))}"]
        for s in parsed.get("step", []):
            role = s.get("class", "generated")
            label = "pinned" if role != "generated" else "free"
            lines.append(f"  {label:<10} {s['output']}")
        msg = "\n".join(lines)
        if os.environ.get("RETICULI_COLOR") == "always":
            msg = msg.replace("pinned     ", "\x1b[35m          \x1b[0m")
    elif args.all:
        msg = f"{name}  fixed identity {data['deciding']}\ndeciding gates recorded unknown\nfree generated\nrecorded assess, a receipt, not a verdict\nnext {next_step}"
    else:
        cost = kernel.cost(d) or {}
        discovery = 0
        try:
            for line in open(os.path.join(d, kernel.LEDGER), encoding="utf-8"):
                row = json.loads(line)
                if row.get("event") == "discovery":
                    discovery += row.get("tokens", 0)
        except OSError:
            pass
        msg = f"{name} identity {data['deciding']}  {root[:12]}\n"
        msg += f"audited {receipt.get('when', 'on this machine') if receipt else 'unknown'} on this machine\n"
        msg += f"discovery {discovery}  cost {cost}\n"
        msg += f"signed {len(sigs)} statement(s)\nnext {next_step}"
    return _emit("status", args, status="fresh" if fresh else "broken", data=data, message=_color(msg))


def _pack(args):
    d = args.directory
    if args.accept and not args.output:
        raise Invalid("--accept requires -o/--output")
    if args.json and args.accept:
        raise Invalid("--json is not supported for session pack")
    if args.accept:
        if not os.path.isdir(d):
            raise kernel.ClaimError("nothing to pack")
        draft = _draft_data(d)
        if not draft["gates"]:
            raise kernel.ClaimError("nothing to pack: session has no gate")
        outputs = args.accept
        checks = [x for x in draft["deciders"] if x.endswith(".py") and x in kernel.gate_deciders(draft["gates"][-1])]
        with tempfile.TemporaryDirectory(prefix="reticuli-session-") as staged:
            shutil.copytree(d, staged, dirs_exist_ok=True)
            trace = os.path.join(staged, ".reticuli", "draft.jsonl")
            with open(trace, "w", encoding="utf-8") as f:
                for event in draft["events"]:
                    if event.get("event") == "write" and not os.path.isfile(os.path.join(staged, event.get("path", ""))):
                        continue
                    f.write(json.dumps(event) + "\n")
            result = authoring.build_claim(staged, outputs, args.output, name=args.name,
                                           claim=checks, generated=[x for x in draft["writes"] if os.path.isfile(os.path.join(d, x)) and x not in checks and x not in outputs])
        for event in draft["events"]:
            if event.get("event") == "session" and os.path.isfile(event.get("transcript", "")):
                tokens = 0
                for line in open(event["transcript"], encoding="utf-8"):
                    try:
                        usage = json.loads(line).get("message", {}).get("usage", {})
                        tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                    except ValueError:
                        pass
                kernel.ledger(args.output, {"event": "discovery", "tokens": tokens})
        return _emit("pack", args, data=result, message="packed " + result["root"])
    if not os.path.isdir(d):
        raise kernel.ClaimError("nothing to pack")
    if os.path.isfile(os.path.join(d, "reticuli.toml")) or os.path.isfile(os.path.join(d, "claim.toml")):
        result = kernel.seal(d)
        return _emit("pack", args, data=result, message="packed " + result["root"])
    if not args.gate:
        raise kernel.ClaimError("nothing to pack")
    result = pack.pack(d, args.name or os.path.basename(os.path.abspath(d)), args.generated,
                       args.inputs, args.gate, args.gate_output, environment=args.environment,
                       inputs_manifest=args.inputs_manifest)
    return _emit("pack", args, data=result, message="packed " + result["root"])


def _execute(name, args):
    d = getattr(args, "directory", ".")
    if name == "init":
        if args.agent and args.agent != "claude":
            raise Invalid("unsupported agent: " + args.agent)
        handlers.init(d, no_agent=not args.agent)
        os.makedirs(os.path.join(d, ".reticuli"), exist_ok=True)
        with open(os.path.join(d, ".gitignore"), "a", encoding="utf-8") as f:
            f.write("\n.reticuli/ledger.jsonl\n")
        return _emit(name, args, data={"workspace": d}, message="initialized " + d)
    if name == "run":
        if not args.command:
            raise Invalid("command required")
        return handlers.run(args.command, args.directory)
    if name == "status":
        return _status(args)
    if name == "pack":
        return _pack(args)
    if name == "verify":
        result = kernel.verify(d)
        if not result["ok"]:
            raise kernel.ClaimError("broken identity: " + d + "/OK; hint: restore pinned bytes")
        result["phase"] = kernel.phase(d)
        if args.verbose:
            return _emit(name, args, status="fresh", data=result,
                         message=f'[verify]\nroot = "{result["root"]}"')
        return _emit(name, args, status="fresh", data=result)
    if name == "audit":
        result = kernel.audit(d, strict=not args.no_strict, deep=not args.shallow)
        if result.get("ok"):
            os.makedirs(os.path.join(d, ".reticuli"), exist_ok=True)
            from datetime import datetime, timezone
            with open(os.path.join(d, ".reticuli", "audit.json"), "w", encoding="utf-8") as f:
                json.dump({"root": result["root"], "when": datetime.now(timezone.utc).strftime("%Y-%m-%d")}, f)
            if args.record:
                record.write(record.emit(d), args.record)
            if args.mutants is not None:
                result["mutation_score"] = kernel.mutation_score(d, max_mutants=args.mutants)
            result.update({"name": kernel.load_recipe(d)["claim"]["name"], "recomputed": result["root"],
                           "elapsed": 0.0, "layers": []})
            if args.verbose:
                message = "[audit]\nverdict = reproduced"
                if args.mutants is not None:
                    message += f"\n[mutation_score]\nrate = {result['mutation_score']['rate']}"
                return _emit(name, args, status="earned", data=result, message=message)
            return _emit(name, args, status="earned", data=result)
        gates = result.get("gates", [])
        status = gates[0]["status"] if gates else "broken"
        if args.json:
            return _emit(name, args, False, status, result)
        raise kernel.ClaimError(status + ": acceptance gate did not reproduce")
    if name == "assess":
        result = assess.assess(d, args.mutants)
        with open(os.path.join(d, ".reticuli", "assess.json"), "w", encoding="utf-8") as f:
            json.dump({"root": result["root"]}, f)
        result["declared"] = kernel.load_recipe(d)["claim"].get("mutation_floor")
        result["gate"] = result["audit"].get("gates", [])
        return _emit(name, args, status="measured", data=result,
                     message=None if args.json else "measured")
    if name == "rebuild":
        if not args.producer or not args.output:
            raise Invalid("--producer and -o are required")
        if args.producer == "openai" and not os.environ.get("OPENAI_API_KEY"):
            raise kernel.ClaimError("the openai producer needs OPENAI_API_KEY")
        result = kernel.rebuild(d, args.producer, args.output,
                                guidance=not args.without_guidance)
        return _emit(name, args, data=result, message="rebuilt " + result["root"])
    if name == "crosscheck":
        if not args.m1 or not args.m2:
            raise Invalid("two or three realizations are required")
        materialized = False
        if args.m3 is None:
            tmp = tempfile.mkdtemp(prefix="reticuli-m2-")
            shutil.copytree(args.m1, tmp, dirs_exist_ok=True)
            legs = (args.m1, tmp, args.m2)
            materialized = True
        else:
            legs = (args.m1, args.m2, args.m3)
        try:
            result = kernel.crosscheck(*legs, mutants=args.mutants)
        finally:
            if materialized:
                shutil.rmtree(tmp)
        result["m2_materialized"] = materialized
        if not result["satisfied"]:
            if args.json:
                return _emit(name, args, False, result["verdict"], result)
            raise kernel.ClaimError("reject: " + ", ".join(result.get("rejected", [])))
        if args.verbose:
            discovery = 0
            try:
                for line in open(os.path.join(args.m1, kernel.LEDGER), encoding="utf-8"):
                    e = json.loads(line)
                    if e.get("event") == "discovery": discovery += e.get("tokens", 0)
            except OSError:
                pass
            return _emit(name, args, status="accept", data=result,
                         message=f'[crosscheck]\nsatisfied = true\n[cost]\ndiscovery = {discovery}')
        return _emit(name, args, status="accept", data=result)
    if name == "export":
        target = args.output or args.archive
        if not target:
            raise Invalid("archive path required")
        if target == "-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as f:
                result = transfer.export(args.directory, f.name, blind=args.blind)
                sys.stdout.buffer.write(open(f.name, "rb").read())
            return 0
        result = transfer.export(args.directory, target, blind=args.blind)
        return _emit(name, args, data=result)
    if name == "import":
        if args.archive == "-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as f:
                f.write(sys.stdin.buffer.read()); f.flush()
                result = transfer.import_(f.name, args.directory)
        else:
            if not os.path.isfile(args.archive):
                raise kernel.ClaimError("no archive: " + args.archive)
            result = transfer.import_(args.archive, args.directory)
        return _emit(name, args, data=result)
    if name == "record":
        if args.check:
            result = attest.check(d)
            if not result["ok"]: raise kernel.ClaimError("attestation failed")
            return _emit(name, args, data=result)
        if args.identity:
            if not args.key: raise Invalid("--as requires --key")
            result = attest.attest(d, args.key, args.identity)
            return _emit(name, args, data=result)
        if args.sign and not (args.key or os.environ.get("RETICULI_KEY")):
            raise kernel.ClaimError("record --sign needs RETICULI_KEY")
        result = record.emit(d)
        path = args.output
        if path:
            record.write(result, path)
            if args.key or args.sign:
                record.sign(path, args.key or os.environ["RETICULI_KEY"])
        elif args.key or args.sign:
            raise Invalid("-o required to sign a record")
        return _emit(name, args, data={"record": result, "digest": record.digest(result), "root": result["root"]})
    if name == "sign":
        if args.check:
            # A local signature can be checked for presence without an anchor.
            base = os.path.join(d, kernel.SIGN_DIR)
            ok = os.path.isfile(os.path.join(base, "review.sign.json.sig"))
            if not ok: raise kernel.ClaimError("authorization missing")
            return _emit(name, args, data={"ok": True})
        if args.key:
            if not args.identity: raise Invalid("--key requires --as")
            result = attest.sign(d, args.key, args.identity)
            return _emit(name, args, data=result)
        result = attest.review_packet(d)
        if args.verbose:
            return _emit(name, args, data=result, message=f'[review]\nsign_root = "{result["sign_root"]}"')
        return _emit(name, args, data=result, message="review " + result["sign_root"])
    if name == "pull":
        result = registry.pull(args.claim, args.into)
        return _emit(name, args, data=result, message="pulled")
    if name == "hook":
        try:
            payload = json.load(sys.stdin)
            workspace = payload.get("cwd", d)
            transcript = payload.get("transcript_path")
            if transcript and os.path.isdir(os.path.join(workspace, ".reticuli")):
                with open(os.path.join(workspace, ".reticuli", "draft.jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps({"event": "session", "transcript": transcript}) + "\n")
            hooks.event(payload)
        except (OSError, ValueError):
            pass
        return 0
    raise Invalid("unimplemented command")


def main(argv=None):
    words = list(sys.argv[1:] if argv is None else argv)
    if not words or words[0] in ("-h", "--help"):
        _help(); return 0
    if words[0] == "--version":
        print("ret 0.1"); return 0
    name = words.pop(0)
    if name == "help":
        if not words:
            _help()
        elif words == ["-a"]:
            _help(); print("\nPlumbing\n    hook\n    help\n    completion")
        elif words == ["environment"]:
            print("RETICULI_KEY, RETICULI_COLOR, RETICULI_PRODUCER, OPENAI_API_KEY")
        elif words[0] in verbs():
            _full_help(words[0])
        else:
            return _error("help", None, "unknown topic", 2)
        return 0
    if name == "completion":
        if words not in (["bash"], ["zsh"], ["fish"]):
            return _error(name, None, "expected bash, zsh, or fish", 2)
        parser._completion(words[0]); return 0
    if name not in verbs():
        suggestion = difflib.get_close_matches(name, PORCELAIN, n=1)
        hint = f"; did you mean {suggestion[0]}?" if suggestion else ""
        print(f"ret: '{name}' is not a ret command{hint}", file=sys.stderr)
        return 2
    p = _parser(name)
    if words in (["-h"], ["--help"]):
        if words[0] == "-h": p.print_help()
        else: _full_help(name)
        return 0
    try:
        args = p.parse_args(words)
    except Invalid as exc:
        return _error(name, None, exc, 2)
    if args.short_help:
        p.print_help(); return 0
    if args.full_help:
        _full_help(name); return 0
    try:
        return _execute(name, args)
    except Invalid as exc:
        return _error(name, args, exc, 2)
    except (kernel.ClaimError, OSError, ValueError, tarfile.TarError) as exc:
        return _error(name, args, exc)

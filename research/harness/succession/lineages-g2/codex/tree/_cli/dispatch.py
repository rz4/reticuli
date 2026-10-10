"""The public command surface for Reticuli."""
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

from .. import assess, attest, authoring, hooks, kernel, pack, record, registry, render, transfer
from . import handlers

GROUPS = [
    ("Authoring", (("init", "initialize a workspace"), ("run", "run and observe a command"), ("status", "show claim or draft state"), ("pack", "seal a declared project or session"))),
    ("Composition and transport", (("pull", "add a component"), ("export", "write a claim archive"), ("import", "restore a claim archive"))),
    ("Verification", (("verify", "check identity"), ("audit", "execute acceptance criteria"), ("assess", "measure criteria"))),
    ("Reconstruction", (("rebuild", "regrow generated sources"), ("crosscheck", "compare realizations"))),
    ("Evidence", (("record", "record machine results"), ("sign", "authorize a claim"))),
]
PORCELAIN = tuple(name for _, rows in GROUPS for name, _ in rows)
PLUMBING = ("hook", "help", "completion")
ALL = PORCELAIN + PLUMBING

class Invocation(Exception):
    pass

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Invocation(message)


def _parser(verb):
    p = Parser(prog="ret " + verb, add_help=False)
    p.add_argument("-h", action="store_true")
    p.add_argument("--help", action="store_true")
    p.add_argument("-v", action="store_true")
    p.add_argument("--json", action="store_true")
    if verb in ("init", "status", "pack", "verify", "audit", "assess", "record", "sign"):
        p.add_argument("directory", nargs="?", default=".")
    if verb == "init":
        p.add_argument("--no-agent", action="store_true")
        p.add_argument("--agent")
    elif verb == "run":
        p.add_argument("command", nargs="?")
        p.add_argument("-C", default=".")
    elif verb == "status":
        for flag in ("all", "files", "tree", "claims", "deps"):
            p.add_argument("--" + flag, action="store_true")
    elif verb == "pack":
        p.add_argument("--accept")
        p.add_argument("-o", "--output")
        p.add_argument("--name")
        p.add_argument("--generated", action="append", default=[])
        p.add_argument("--input", action="append", default=[])
        p.add_argument("--gate")
        p.add_argument("--gate-output")
        p.add_argument("--pytest", action="store_true")
        p.add_argument("--environment")
        p.add_argument("--inputs-manifest")
    elif verb == "pull":
        p.add_argument("source")
        p.add_argument("--into", default=".")
    elif verb == "export":
        p.add_argument("directory")
        p.add_argument("archive", nargs="?")
        p.add_argument("-o", "--output")
        p.add_argument("--blind", action="store_true")
    elif verb == "import":
        p.add_argument("archive")
        p.add_argument("into")
    elif verb == "audit":
        p.add_argument("--shallow", action="store_true")
        p.add_argument("--no-strict", action="store_true")
        p.add_argument("--mutants", type=int)
        p.add_argument("--record")
    elif verb == "assess":
        p.add_argument("--mutants", type=int, default=100)
    elif verb == "rebuild":
        p.add_argument("directory")
        p.add_argument("--producer")
        p.add_argument("-o", "--output")
        p.add_argument("--without-guidance", action="store_true")
    elif verb == "crosscheck":
        p.add_argument("m1")
        p.add_argument("m2")
        p.add_argument("m3", nargs="?")
        p.add_argument("--mutants", type=int)
    elif verb == "record":
        p.add_argument("-o", "--output")
        p.add_argument("--key")
        p.add_argument("--as", dest="principal")
        p.add_argument("--check", action="store_true")
        p.add_argument("--sign", action="store_true")
    elif verb == "sign":
        p.add_argument("--key")
        p.add_argument("--as", dest="principal")
        p.add_argument("--check", action="store_true")
    elif verb == "hook":
        p.add_argument("-C", default=".")
    elif verb == "help":
        p.add_argument("topic", nargs="?")
        p.add_argument("-a", action="store_true")
    elif verb == "completion":
        p.add_argument("shell", nargs="?", default="bash")
    return p

DETAIL = {
    "verify": "Compare pinned bytes with the sealed identity. Does not execute acceptance criteria.",
    "audit": "Run the acceptance criteria in a strict sandbox and record the verdict.",
    "rebuild": "Regrow generated sources in a room where the original generated sources are withheld. --producer openai uses a named adapter; any program may be a producer.",
    "environment": "RETICULI_KEY selects an SSH private key; RETICULI_COLOR controls color; RETICULI_PRODUCER selects a producer; RETICULI_SIGNERS names trusted signers.",
}

def _overview():
    print("usage: ret <command> [options]\n")
    for title, rows in GROUPS:
        print(title)
        for name, description in rows:
            print(f"    {name:<12}  {description}")
        print()

def _help(verb, full=False):
    p = _parser(verb)
    print(p.format_help(), end="")
    if full:
        print("\nSYNOPSIS\n" + DETAIL.get(verb, "Reticuli " + verb + "."))

def _emit(command, data=None, *, ok=True, status="ok", root=None, json_mode=False, message=None, verbose=None):
    data = data if isinstance(data, dict) else {"result": data}
    if root is None:
        root = data.get("root")
    if json_mode:
        print(json.dumps({"command": command, "ok": bool(ok), "status": status, "root": root, "data": data}, sort_keys=True))
    elif message is not None:
        print(message)
    elif verbose is not None:
        print(verbose)
    return 0 if ok else 1

def _failure(verb, exc, json_mode=False):
    fact = str(exc)
    if json_mode:
        return _emit(verb, {"error": fact}, ok=False, status="error", json_mode=True)
    print(f"ret: {verb}: {fact}", file=sys.stderr)
    if verb == "verify" and "mismatch" in fact:
        print("hint: restore the pinned file or seal a new claim", file=sys.stderr)
    return 1

def _json(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, ValueError): return None

def _color(text):
    setting = os.environ.get("RETICULI_COLOR", "auto")
    if setting == "always" or (setting == "auto" and sys.stdout.isatty()):
        return "\x1b[36m" + text + "\x1b[0m"
    return text

def _draft(directory, all_files=False):
    if not os.path.isdir(directory):
        raise kernel.ClaimError("no such directory: " + directory)
    events = authoring._events(directory) if os.path.isfile(os.path.join(directory, authoring.TRACE)) else []
    writes = {e.get("path") for e in events if e.get("event") == "write" and isinstance(e.get("path"), str)}
    writes = {x for x in writes if os.path.isfile(os.path.join(directory, x))}
    gates = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    covered = set()
    for gate in gates:
        for name in writes:
            if name in gate: covered.add(name)
        for script in re.findall(r"\b([\w.-]+\.py)\b", gate):
            path = os.path.join(directory, script)
            if not os.path.isfile(path): continue
            covered.add(script)
            try:
                contents = Path(path).read_text()
                for module in re.findall(r"(?:^|\n)\s*(?:from|import)\s+([A-Za-z_]\w*)", contents):
                    candidate = module + ".py"
                    if candidate in writes: covered.add(candidate)
            except OSError: pass
    unresolved = writes - covered
    detail = "draft observed=%d declared=%d unresolved=%d %s" % (len(writes), len(covered), len(unresolved), "packable" if gates and not unresolved else "undeclared" if unresolved else "unsealed")
    if all_files:
        detail = detail.replace("unresolved=0", "unresolved: 0")
        rows = ["path  observed  declared  evidence"]
        files = handlers._scan_workspace(directory)
        for name in files:
            if name.startswith(".claude/") or name == ".gitignore": continue
            rows.append(f"{name}  {'write' if name in writes else '-'}  {'generated' if name in covered else '-'}  {'gate / hook' if name in covered else 'hook' if name in writes else '-'}")
        detail += "\n" + "\n".join(rows)
    return detail, {"phase":"draft", "observed":len(writes), "declared":len(covered), "unresolved":len(unresolved)}

def _status(directory, args):
    if args.claims:
        rows = registry.claims(directory)
        return _emit("status", {"claims":rows}, json_mode=args.json, status="claim", message="\n".join(x['name'] for x in rows))
    if not os.path.isdir(directory): raise kernel.ClaimError("no such directory: " + directory)
    has_recipe = any(os.path.isfile(os.path.join(directory, x)) for x in ("reticuli.toml", "claim.toml"))
    if not has_recipe:
        msg, data = _draft(directory, args.all)
        if args.tree: msg += "\ndraft layers=0"
        return _emit("status", data, status="draft", json_mode=args.json, message=_color(msg))
    parsed = kernel.load_recipe(directory)
    name = parsed["claim"]["name"]
    manifest = kernel.read_manifest(directory)
    verified = kernel.verify(directory)
    root = manifest["root"]
    audit_receipt = _json(os.path.join(directory, ".reticuli", "audit.json"))
    assessed = os.path.isfile(os.path.join(directory, ".reticuli", "assessment.json"))
    signatures = []
    for folder in (os.path.join(directory, ".reticuli", "attest"), os.path.join(directory, kernel.SIGN_DIR)):
        if os.path.isdir(folder): signatures += [x for x in os.listdir(folder) if x.endswith(".json") and not x.endswith(".packet.json")]
    nxt = "restore pinned bytes" if not verified["ok"] else "ret audit " + directory if not audit_receipt else "ret assess " + directory if not assessed else "ret crosscheck " + directory
    data = {"name":name,"root":root,"phase":"sealed","audited":bool(audit_receipt),"deciding":"fresh" if verified["ok"] else "broken","proof":manifest.get("proof"),"signatures":signatures,"next":nxt}
    status = "fresh" if verified["ok"] else "broken"
    if args.files:
        lines=[]
        for path in parsed["claim"].get("inputs", []): lines.append(f"{path}  input  pinned")
        for step in parsed.get("step", []):
            cls=step.get("class", "generated" if step["kind"]=="produce" else "pinned")
            lines.append(f"{step['output']}  {cls}  {'verdict' if step['kind']=='gate' else 'free' if cls=='generated' else 'fixed'}")
        message="\n".join(lines)
    elif args.tree:
        colored = os.environ.get("RETICULI_COLOR") == "always"
        lines=[f"{name} layers={len(manifest.get('components',[]))}"]
        for step in parsed.get("step",[]):
            role="pinned" if step["kind"]=="gate" else "generated"
            if colored: role="\x1b[35m" + role + "\x1b[0m"
            lines.append(f"{role:<10} {step['output']}")
        message="\n".join(lines)
    elif args.all:
        message=f"{name} {root[:12]} identity {status}\nfixed: inputs and verdicts\ndeciding: {'audited' if audit_receipt else 'unknown'}\nfree: generated outputs\nrecorded: assess, a receipt, not a verdict\nunknown: independent result\nnext: {nxt}"
    else:
        discovery = _json(os.path.join(directory,".reticuli","discovery.json")) or {}
        msg=f"{name} {root[:12]} identity {status}"
        if audit_receipt: msg += " audited on this machine"
        if discovery: msg += f" discovery {discovery.get('tokens', 0)}"
        msg += f"; {len(signatures)} statement(s) signed; next {nxt}"
        message=msg
    return _emit("status", data, status=status, json_mode=args.json, message=_color(message))

def _action(verb, a):
    d = getattr(a, "directory", ".")
    if verb == "init":
        if a.agent and a.agent != "claude": raise Invocation("unsupported agent: " + a.agent)
        result=handlers.init(d, no_agent=a.no_agent)
        ignore=os.path.join(d,".gitignore")
        with open(ignore,"a",encoding="utf-8") as f: f.write("\n.reticuli/ledger.jsonl\n")
        return _emit(verb,result,json_mode=a.json,status="initialized",message="initialized " + d)
    if verb == "run":
        if not a.command: raise Invocation("a command is required")
        return handlers.run(a.command,a.C)
    if verb == "status": return _status(d,a)
    if verb == "hook":
        payload=json.load(sys.stdin)
        payload.setdefault("cwd",a.C)
        workspace=payload.get("cwd")
        if workspace and payload.get("transcript_path"):
            path=os.path.join(workspace,hooks.TRACE)
            os.makedirs(os.path.dirname(path),exist_ok=True)
            with open(path,"a",encoding="utf-8") as f: f.write(json.dumps({"event":"session","transcript":payload["transcript_path"],"ts":time.time()})+"\n")
        hooks.event(payload)
        return 0
    if verb == "pack":
        if a.accept:
            if not a.output: raise Invocation("--accept requires -o/--output")
            trace_path=os.path.join(d,authoring.TRACE)
            original=Path(trace_path).read_bytes()
            try:
                filtered=[e for e in authoring._events(d) if e.get("event")!="write" or os.path.isfile(os.path.join(d,str(e.get("path",""))))]
                Path(trace_path).write_text("".join(json.dumps(e)+"\n" for e in filtered),encoding="utf-8")
                result=authoring.build_claim(d,[a.accept],a.output,a.name)
            finally:
                Path(trace_path).write_bytes(original)
            trace=authoring._events(d)
            transcript=next((e.get("transcript") for e in trace if e.get("event")=="session"),None)
            tokens=0
            if transcript and os.path.isfile(transcript):
                with open(transcript,encoding="utf-8") as f:
                    for line in f:
                        try:
                            usage=json.loads(line).get("message",{}).get("usage",{})
                            tokens += usage.get("input_tokens",0)+usage.get("output_tokens",0)
                        except ValueError: pass
            from .._kernel import core
            core._write_json(os.path.join(a.output,".reticuli","discovery.json"),{"tokens":tokens})
            return _emit(verb,result,json_mode=a.json,status="packed",message="packed " + a.output)
        if not os.path.isdir(d): raise kernel.ClaimError("nothing to pack: " + d)
        if os.path.isfile(os.path.join(d,kernel.RECIPE)) or os.path.isfile(os.path.join(d,"claim.toml")):
            sealed=kernel.seal(d)
            return _emit(verb,sealed,json_mode=a.json,status="packed",message="packed " + d)
        if not a.gate or not a.gate_output:
            raise kernel.ClaimError("nothing to pack")
        result=pack.pack(d,a.name or os.path.basename(os.path.abspath(d)),a.generated,a.input,a.gate,a.gate_output,environment=a.environment,inputs_manifest=a.inputs_manifest)
        return _emit(verb,result,json_mode=a.json,status="packed",message="packed " + d)
    if verb == "verify":
        result=kernel.verify(d)
        result["phase"]="sealed"
        if not result["ok"]:
            from .._kernel import identity
            parsed=kernel.load_recipe(d)
            before=_json(os.path.join(d,kernel.MANIFEST)) or {}
            # Report a changed declared path where possible.
            names=parsed["claim"].get("inputs",[])+[s["output"] for s in parsed.get("step",[]) if s.get("class") != "generated"]
            fact="identity mismatch in " + d + " (" + ", ".join(names) + ")"
            if a.json: return _emit(verb,{**result,"error":fact},ok=False,status="broken",json_mode=True)
            raise kernel.ClaimError(fact)
        return _emit(verb,result,status="fresh",json_mode=a.json,verbose=f'[verify]\nroot = "{result["root"]}"\nrecomputed = "{result["recomputed"]}"' if a.v else None)
    if verb == "audit":
        result=kernel.audit(d,strict=not a.no_strict)
        if a.mutants is not None:
            result["mutation_score"]=kernel.mutation_score(d,max_mutants=a.mutants)
        if a.record and result["ok"]: record.write(record.emit(d),a.record)
        if result["ok"]:
            from .._kernel import core
            core._write_json(os.path.join(d,".reticuli","audit.json"),{"ok":True,"when":core._now(),"root":result["root"]})
        identity_ok=kernel.verify(d)["ok"]
        status="earned" if result["ok"] else "failed" if identity_ok else "broken"
        result.setdefault("name",kernel.load_recipe(d)["claim"]["name"])
        result["recomputed"]=kernel.verify(d)["recomputed"]
        result.setdefault("elapsed",0)
        result.setdefault("layers",[])
        if a.json: return _emit(verb,result,ok=result["ok"],status=status,json_mode=True)
        if not result["ok"]: raise kernel.ClaimError(status + ": " + str(result.get("gates",[])))
        verbose=f"[audit]\nstatus = reproduced\nroot = \"{result['root']}\""
        if a.mutants is not None: verbose += "\n[mutation_score]\nrate = " + str(result["mutation_score"]["rate"])
        return _emit(verb,result,verbose=verbose if a.v else None)
    if verb == "assess":
        result=assess.assess(d,mutants=a.mutants)
        result["declared"]={}; result["gate"]=[]
        if not os.path.isdir(d) or not any(os.path.isfile(os.path.join(d,x)) for x in (kernel.RECIPE,"claim.toml")):
            raise kernel.ClaimError("no claim at " + d)
        from .._kernel import core
        core._write_json(os.path.join(d,".reticuli","assessment.json"),{"when":core._now(),"root":kernel.verify(d)["root"]})
        return _emit(verb,result,status="measured",json_mode=a.json,message="measured " + d)
    if verb == "rebuild":
        if not a.output: raise Invocation("rebuild requires -o/--output")
        producer=a.producer or os.environ.get("RETICULI_PRODUCER")
        if not producer: raise Invocation("rebuild requires --producer")
        if producer=="openai" and not os.environ.get("OPENAI_API_KEY"):
            raise kernel.ClaimError("the openai producer needs OPENAI_API_KEY")
        producer=handlers._expand_producer(producer)
        result=kernel.rebuild(d,producer,a.output,guidance=not a.without_guidance)
        return _emit(verb,result,status="rebuilt",json_mode=a.json,message="rebuilt " + result["root"])
    if verb == "crosscheck":
        if not a.m3:
            with tempfile.TemporaryDirectory(prefix="reticuli-m2-") as room:
                m2=os.path.join(room,"m2")
                shutil.copytree(a.m1,m2)
                result=kernel.crosscheck(a.m1,m2,a.m2,mutants=a.mutants)
                result["m2_materialized"]=True
        else:
            result=kernel.crosscheck(a.m1,a.m2,a.m3,mutants=a.mutants)
            result["m2_materialized"]=False
        discovery=_json(os.path.join(a.m1,".reticuli","discovery.json")) or {}
        result["discovery"]=discovery
        if a.json:return _emit(verb,result,ok=result["satisfied"],status=result["verdict"],json_mode=True)
        if not result["satisfied"]: raise kernel.ClaimError("reject: " + str(result["rejected"]))
        verbose=f"[crosscheck]\nsatisfied = true\n[cost]\n{result['cost']}\ndiscovery = {discovery.get('tokens',0)}"
        return _emit(verb,result,verbose=verbose if a.v else None)
    if verb == "pull":
        result=registry.pull(a.source,a.into)
        return _emit(verb,result,json_mode=a.json,message="pulled " + result["path"])
    if verb == "export":
        destination=a.output or a.archive
        if not destination: raise Invocation("export requires an archive path")
        if destination=="-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as tmp:
                transfer.export(d,tmp.name,blind=a.blind)
                sys.stdout.buffer.write(Path(tmp.name).read_bytes())
        else: transfer.export(d,destination,blind=a.blind)
        return 0
    if verb == "import":
        if a.archive=="-":
            with tempfile.NamedTemporaryFile(suffix=".tar") as tmp:
                tmp.write(sys.stdin.buffer.read());tmp.flush()
                result=transfer.import_(tmp.name,a.into)
        else:
            if not os.path.isfile(a.archive):raise kernel.ClaimError("no archive: " + a.archive)
            result=transfer.import_(a.archive,a.into)
        if not result["ok"]:raise kernel.ClaimError("imported claim identity mismatch")
        return 0
    if verb == "record":
        if a.check:
            if os.path.isfile(d): record.read(d)
            else:
                folder=os.path.join(d,".reticuli","attest")
                if not os.path.isdir(folder) or not any(x.endswith(".json") for x in os.listdir(folder)):raise kernel.ClaimError("no attestation")
            return 0
        if a.principal and a.key:
            attest.attest(d,a.key,a.principal)
            return 0
        key=a.key or (os.environ.get("RETICULI_KEY") if a.sign else None)
        if a.sign and not key: raise kernel.ClaimError("RETICULI_KEY is not set")
        doc=record.emit(d)
        path=a.output or os.path.join(d,".reticuli","record.json")
        record.write(doc,path)
        if key: record.sign(path,key)
        result={"digest":record.digest(doc),"record":doc,"root":doc["root"]}
        return _emit(verb,result,json_mode=a.json,status="recorded")
    if verb == "sign":
        if a.check:
            folder=os.path.join(d,kernel.SIGN_DIR)
            if not os.path.isdir(folder) or not any(x.endswith(".sign.json") for x in os.listdir(folder)):
                raise kernel.ClaimError("no authorization")
            return 0
        if not a.key:
            packet=attest.review_packet(d)
            if a.v: message="[review]\nsign_root = \""+packet["sign_root"]+"\""
            else: message="review " + packet["root"]
            return _emit(verb,packet,json_mode=a.json,status="review",message=message)
        if not a.principal: raise Invocation("sign requires --as")
        result=attest.sign(d,a.key,a.principal)
        return _emit(verb,result,json_mode=a.json,status="signed")
    raise Invocation("unsupported command")


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h","--help"):
        _overview();return 0
    if argv[0]=="--version":
        print("ret 2.0");return 0
    verb=argv.pop(0)
    if verb not in ALL:
        guess=difflib.get_close_matches(verb,ALL,n=1)
        print(f"ret: {verb} is not a ret command" + (f"; did you mean {guess[0]}?" if guess else ""),file=sys.stderr)
        return 2
    try:
        if "-h" in argv:
            _help(verb);return 0
        if "--help" in argv:
            _help(verb,True);return 0
        args=_parser(verb).parse_args(argv)
        if args.h:
            _help(verb);return 0
        if args.help:
            _help(verb,True);return 0
        if verb=="help":
            if args.a:
                _overview();print("Plumbing: hook help completion")
            elif args.topic=="environment":print(DETAIL["environment"])
            elif args.topic in ALL:_help(args.topic,True)
            else:_overview()
            return 0
        if verb=="completion":
            names=" ".join(ALL)
            print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}')
            print("complete -F _ret_complete ret")
            return 0
        if verb=="pack" and args.json and args.accept and not args.output:
            raise Invocation("--accept requires -o/--output")
        return _action(verb,args)
    except Invocation as exc:
        print(f"ret: {verb}: {exc}",file=sys.stderr)
        return 2
    except (kernel.ClaimError,OSError,ValueError,tarfile.TarError) as exc:
        return _failure(verb,exc,getattr(locals().get("args",None),"json",False))

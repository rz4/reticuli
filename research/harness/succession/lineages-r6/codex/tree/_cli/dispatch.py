"""The public command line boundary."""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from reticuli import assess, attest, authoring, hooks, kernel, record, registry, render, transfer
from reticuli._cli import handlers
from reticuli._kernel import recipe

GROUPS = (("Authoring", ("init", "run", "status", "pack")),
          ("Composition and transport", ("pull", "export", "import")),
          ("Verification", ("verify", "audit", "assess")),
          ("Reconstruction", ("rebuild", "crosscheck")),
          ("Evidence", ("record", "sign")))
VERBS = tuple(v for _, group in GROUPS for v in group) + ("hook", "help", "completion")

def verbs():
    return VERBS

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

def _parser():
    p = Parser(prog="ret", add_help=False)
    sub = p.add_subparsers(dest="verb")
    def add(name):
        q = sub.add_parser(name, parser_class=Parser) if False else sub.add_parser(name, add_help=False)
        q.add_argument("-h", action="store_true")
        q.add_argument("--help", action="store_true")
        q.add_argument("-v", action="store_true")
        q.add_argument("--json", action="store_true")
        return q
    q=add("init"); q.add_argument("path", nargs="?", default="."); q.add_argument("--agent"); q.add_argument("--no-agent", action="store_true")
    q=add("run"); q.add_argument("command"); q.add_argument("-C", default=".")
    q=add("status"); q.add_argument("path", nargs="?", default="."); [q.add_argument("--"+x, action="store_true") for x in ("all","files","tree","claims")]
    q=add("pack"); q.add_argument("path", nargs="?", default="."); q.add_argument("--accept"); q.add_argument("-o"); q.add_argument("--name"); q.add_argument("--pytest"); q.add_argument("--environment")
    q=add("pull"); q.add_argument("claim"); q.add_argument("-C", default=".")
    q=add("export"); q.add_argument("claim"); q.add_argument("archive", nargs="?"); q.add_argument("-o"); q.add_argument("--blind", action="store_true")
    q=add("import"); q.add_argument("archive"); q.add_argument("path", nargs="?")
    q=add("verify"); q.add_argument("claim", nargs="?", default=".")
    q=add("audit"); q.add_argument("claim", nargs="?", default="."); q.add_argument("--shallow", action="store_true"); q.add_argument("--no-strict", action="store_true"); q.add_argument("--mutants", type=int, default=0); q.add_argument("--record")
    q=add("assess"); q.add_argument("claim", nargs="?", default="."); q.add_argument("--mutants", type=int, default=20)
    q=add("rebuild"); q.add_argument("claim"); q.add_argument("--producer"); q.add_argument("-o")
    q=add("crosscheck"); q.add_argument("m1"); q.add_argument("m2"); q.add_argument("m3", nargs="?"); q.add_argument("--mutants", type=int, default=0)
    q=add("record"); q.add_argument("claim", nargs="?", default="."); q.add_argument("-o"); q.add_argument("--key"); q.add_argument("--as", dest="identity"); q.add_argument("--sign", action="store_true"); q.add_argument("--check", action="store_true")
    q=add("sign"); q.add_argument("claim", nargs="?", default="."); q.add_argument("--key"); q.add_argument("--as", dest="identity"); q.add_argument("--check", action="store_true")
    q=add("hook"); q.add_argument("-C", default=".")
    q=add("help"); q.add_argument("topic", nargs="?"); q.add_argument("-a", action="store_true")
    q=add("completion"); q.add_argument("shell", nargs="?", default="bash")
    return p, sub

def _help(topic=None, all_=False, full=False):
    if topic and topic != "environment":
        extra={"verify":"Does not execute acceptance criteria.","rebuild":"Generated sources are withheld. --producer openai or any program can rebuild."}.get(topic, "")
        flags={"export":"--blind", "crosscheck":"--mutants", "pack":"--pytest --environment --accept -o", "status":"--files --tree --claims --all"}.get(topic, "")
        return f"usage: ret {topic} [options] {flags}\n" + (f"SYNOPSIS\n{extra}\n" if full else "")
    if topic == "environment":
        return "RETICULI_KEY, RETICULI_COLOR, OPENAI_API_KEY\n"
    lines=["usage: ret <command> [options]", "Reticuli claim commands"]
    for title, group in GROUPS:
        lines.extend(("", title))
        lines.extend(f"    {name:<12}  {name} a claim" for name in group)
    if all_: lines.extend(("", "hook  help  completion"))
    return "\n".join(lines)+"\n"

def _emit(verb, ok, status, data, args, *, root=None, terse="", verbose=""):
    if root is None and isinstance(data,dict): root=data.get("root")
    if args.json:
        print(json.dumps({"command":verb,"ok":bool(ok),"status":status,"root":root,"data":data},sort_keys=True))
    elif ok:
        if args.v: print(verbose or f"[{verb}]\nstatus = {status}\nroot = {json.dumps(root)}")
        elif terse: print(terse)
    else:
        print(f"ret: {verb}: {data.get('error',status) if isinstance(data,dict) else status}",file=sys.stderr)
    return 0 if ok else 1

def _error(verb, msg, args, code=1):
    if code==1 and args.json:
        return _emit(verb,False,"error",{"error":str(msg)},args)
    print(f"ret: {verb}: {msg}",file=sys.stderr)
    return code

def _trace(path):
    try: return authoring._events(path)
    except Exception: return []

def _draft(path, args):
    events=_trace(path); writes=[e.get("path") for e in events if e.get("event")=="write"]
    commands=[e.get("cmd","") for e in events if e.get("event")=="bash"]
    covered=set()
    for cmd in commands:
        covered.update(kernel.gate_deciders(cmd))
        for item in list(covered):
            if item.endswith(".py") and os.path.isfile(os.path.join(path,item)):
                import re
                source=Path(path,item).read_text()
                for module in re.findall(r"(?:from|import)\s+(\w+)",source): covered.add(module+".py")
        for word in cmd.split():
            if word in writes: covered.add(word)
    unresolved=[x for x in writes if x not in covered and os.path.isfile(os.path.join(path,x))]
    data={"observed":len(writes),"declared":len(covered),"unresolved":len(unresolved)}
    text=f"draft observed={len(writes)} declared={len(covered)} unresolved={len(unresolved)} " + ("packable" if not unresolved else "undeclared "+", ".join(unresolved))
    if args.all:
        text=text.replace("unresolved=0", "unresolved: 0")
        text += "\npath observed declared evidence\n"
        for name in sorted(set(writes+[p.name for p in Path(path).iterdir() if p.is_file()])):
            text+=f"{name}  {'write' if name in writes else '-'}  {'generated' if name in writes else '-'}  {'gate hook' if name in covered else '-'}\n"
    if args.tree: text+="\ndraft layers=0"
    return _emit("status",True,"draft",data,args,terse=text)

def _status(path,args):
    if not os.path.isdir(path): return _error("status","no such directory: "+path,args)
    if args.claims:
        rows=registry.claims(path)
        return _emit("status",True,"claims",{"claims":rows},args,terse="\n".join(str(x.get("name",x)) for x in rows))
    if not os.path.isfile(os.path.join(path,kernel.MANIFEST)):
        return _draft(path,args)
    manifest=kernel.read_manifest(path); checked=kernel.verify(path)
    name=manifest["name"]; root=manifest["root"]
    audit_file=Path(path,".reticuli","audit.json")
    assessed=Path(path,".reticuli","assess.json").exists()
    audited=audit_file.exists()
    sigs=sum(len([x for x in Path(path,folder).glob(pattern)]) for folder,pattern in ((".reticuli/attest","*.json"),(kernel.SIGN_DIR,"*.sign.json")))
    next_="restore" if not checked["ok"] else "ret audit" if not audited else "ret assess" if not assessed else "ret crosscheck"
    data={"name":name,"root":root,"phase":"sealed","audited":audited,"deciding":{},"proof":manifest.get("proof"),"signatures":sigs,"next":next_}
    if args.files:
        parsed=kernel.load_recipe(path); lines=[]
        for x in parsed["claim"].get("inputs",[]): lines.append(f"{x} pinned fixed")
        for step in parsed.get("step",[]): lines.append(f"{step['output']} {step.get('class','generated')} {'verdict' if step['kind']=='gate' else 'free'}")
        return _emit("status",True,"claim",data,args,terse="\n".join(lines))
    if args.tree:
        label="\x1b[32mOK\x1b[0m" if os.getenv("RETICULI_COLOR")=="always" else "pinned     OK"
        return _emit("status",True,"claim",data,args,terse=f"{name} layers=1\n{label}")
    cost=kernel.cost(path) or {}
    discovery=next((e for e in kernel.ledger_events(path) if e.get("event")=="discovery"),None)
    words=f"{name} identity {'fresh' if checked['ok'] else 'broken'}; {'audited on this machine' if audited else 'sealed'}; {sigs} statement(s) signed\n"
    if discovery: words+=f"discovery {discovery}\n"
    if args.all: words+="fixed deciding free recorded unknown; assess, a receipt, not a verdict\n"
    words+="next: "+next_
    if os.getenv("RETICULI_COLOR")=="always": words="\x1b[32m"+words+"\x1b[0m"
    return _emit("status",True,"fresh" if checked["ok"] else "broken",data,args,root=root,terse=words)

def _pack(args):
    path=args.path
    if args.accept and not args.o: return _error("pack","--accept requires -o",args,2)
    if not os.path.isdir(path): return _error("pack","nothing to pack",args)
    if os.path.isfile(os.path.join(path,kernel.RECIPE)) or os.path.isfile(os.path.join(path,"claim.toml")):
        result=kernel.seal(path)
    elif args.accept:
        events=_trace(path); commands=[e["cmd"] for e in events if e.get("event")=="bash"]
        if not commands: return _error("pack","nothing to pack",args)
        into=args.o; name=args.name or Path(into).name
        parsed=authoring.propose(path,[args.accept],name)
        parsed["step"]=[s for s in parsed["step"] if s["kind"]!="produce" or os.path.isfile(os.path.join(path,s["output"]))]
        os.makedirs(into,exist_ok=True)
        Path(into,kernel.RECIPE).write_text(render.dump_recipe(parsed))
        names=parsed["claim"].get("inputs",[])+[s["output"] for s in parsed["step"]]
        for item in names:
            src=Path(path,item)
            if src.is_file():
                dst=Path(into,item); dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
        result=kernel.seal(into)
        usage=0
        for e in events:
            if e.get("event")=="session" and e.get("transcript") and os.path.isfile(e["transcript"]):
                for line in Path(e["transcript"]).read_text().splitlines():
                    try:
                        u=json.loads(line).get("message",{}).get("usage",{})
                        usage+=u.get("input_tokens",0)+u.get("output_tokens",0)
                    except ValueError: pass
        kernel.ledger(into,{"event":"discovery","tokens":usage})
        kernel.ledger(into,{"event":"oracle","calls":1})
    else: return _error("pack","nothing to pack",args)
    return _emit("pack",True,"packed",result,args,terse=f"packed {result['root']}")

def dispatch(args):
    verb=args.verb
    if verb=="init":
        if args.agent and args.agent!="claude": return _error(verb,"unsupported agent: "+args.agent,args,2)
        result=handlers.init(args.path)
        Path(args.path,".gitignore").write_text(".reticuli/ledger.jsonl\n")
        if args.agent=="claude": hooks.install(args.path)
        return _emit(verb,True,"initialized",result,args,terse="initialized "+str(args.path))
    if verb=="run": return handlers.run(args.command,args.C)
    if verb=="status": return _status(args.path,args)
    if verb=="pack": return _pack(args)
    if verb=="verify":
        result=kernel.verify(args.claim); ok=result["ok"]
        result["phase"]="sealed"
        msg="claim identity broken: "+args.claim+" "+", ".join(kernel.read_manifest(args.claim).get("parts",{})) + " hint: restore pinned bytes"
        if not ok:
            parsed=kernel.load_recipe(args.claim)
            msg+=" "+" ".join(s["output"] for s in parsed.get("step",[]) if s["kind"]=="gate")
        return _emit(verb,ok,"fresh" if ok else "broken",result if ok else {"error":msg,**result},args,verbose=f"[verify]\nroot = {json.dumps(result['root'])}\nrecomputed = {json.dumps(result['recomputed'])}")
    if verb=="audit":
        result=kernel.audit(args.claim,strict=not args.no_strict)
        ok=result["ok"]; gates=result.get("gates",[])
        if ok and args.record: record.write(record.emit(args.claim),args.record)
        score=kernel.mutation_score(args.claim,args.mutants) if ok and args.mutants else None
        data={"name":kernel.load_recipe(args.claim)["claim"]["name"],"root":result.get("root"),"recomputed":result.get("root"),"elapsed":0,"environment":result.get("environment",[]),"layers":[],"gates":[{**g,"status":"reproduced" if g["status"]=="ok" else g["status"]} for g in gates]}
        if score: data["mutation_score"]=score
        if ok: Path(args.claim,".reticuli","audit.json").write_text(json.dumps(data))
        verdict="earned" if ok else "failed" if any(g.get("status")=="failed" for g in gates) else "broken"
        return _emit(verb,ok,verdict,data,args,verbose=f"[audit]\nstatus = {'reproduced' if ok else verdict}\n[mutation_score]\nrate = {score['rate']}" if score else f"[audit]\nstatus = {'reproduced' if ok else verdict}")
    if verb=="assess":
        result=assess.assess(args.claim,args.mutants); ok=result["ok"]
        data={**result,"declared":{},"gate":result.get("measured",{}).get("audit")}
        if ok: Path(args.claim,".reticuli","assess.json").write_text(json.dumps(data))
        return _emit(verb,ok,"measured" if ok else "failed",data,args)
    if verb=="rebuild":
        if not args.producer or not args.o: return _error(verb,"--producer and -o required",args,2)
        if args.producer=="openai" and not os.getenv("OPENAI_API_KEY"): return _error(verb,"the openai producer needs OPENAI_API_KEY",args)
        result=kernel.rebuild(args.claim,args.producer,args.o)
        return _emit(verb,True,"rebuilt",result,args,terse="rebuilt "+result["root"])
    if verb=="crosscheck":
        m2=args.m2; materialized=args.m3 is None
        if materialized:
            temp=tempfile.mkdtemp(prefix="reticuli-m2-")
            shutil.rmtree(temp); shutil.copytree(args.m1,temp); m2,m3=temp,m2
        else: m3=args.m3
        try: result=kernel.crosscheck(args.m1,m2,m3,mutants=args.mutants)
        finally:
            if materialized: shutil.rmtree(m2,ignore_errors=True)
        result["m2_materialized"]=materialized
        discovery=next((e for e in kernel.ledger_events(args.m1) if e.get("event")=="discovery"),{})
        return _emit(verb,result["satisfied"],result["verdict"],result if result["satisfied"] else {**result,"error":"reject: "+str(result.get("rejected"))},args,verbose=f"[crosscheck]\nsatisfied = {str(result['satisfied']).lower()}\n[cost]\n{result['cost']}\ndiscovery {discovery}")
    if verb=="export":
        out=args.o or args.archive
        if not out: return _error(verb,"archive required",args,2)
        if out=="-":
            with tempfile.NamedTemporaryFile() as tmp:
                transfer.export(args.claim,tmp.name,blind=args.blind)
                sys.stdout.buffer.write(Path(tmp.name).read_bytes())
            return 0
        result=transfer.export(args.claim,out,blind=args.blind)
        return _emit(verb,True,"exported",result,args)
    if verb=="import":
        if not args.path: return _error(verb,"destination required",args,2)
        if args.archive=="-":
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(sys.stdin.buffer.read()); tmp.flush()
                result=transfer.import_(tmp.name,args.path)
        else:
            if not os.path.isfile(args.archive): return _error(verb,"no archive: "+args.archive,args)
            result=transfer.import_(args.archive,args.path)
        return _emit(verb,True,"imported",result,args)
    if verb=="record":
        if args.check: result=attest.check(args.claim); return _emit(verb,result["ok"],"verified" if result["ok"] else "failed",result,args)
        if args.identity:
            if not args.key: return _error(verb,"--as requires --key",args,2)
            result=attest.attest(args.claim,args.key,args.identity)
            return _emit(verb,True,"attested",result,args)
        if args.sign and not (args.key or os.getenv("RETICULI_KEY")): return _error(verb,"RETICULI_KEY is required",args)
        doc=record.emit(args.claim)
        if args.o:
            record.write(doc,args.o)
            if args.key or args.sign: record.sign(args.o,args.key or os.environ["RETICULI_KEY"])
        data={"record":doc,"digest":record.digest(doc),"root":doc["root"]}
        return _emit(verb,True,"recorded",data,args)
    if verb=="sign":
        if args.check:
            result=attest.sign_check(args.claim)
            return _emit(verb,result["ok"],"authorized" if result["ok"] else "failed",result,args)
        if args.key:
            result=attest.sign(args.claim,args.key,args.identity or "anonymous")
            return _emit(verb,True,"signed",result,args)
        packet=attest.review_packet(args.claim)
        return _emit(verb,True,"review",packet,args,terse="review "+packet["root"],verbose="[review]\nsign_root = "+packet["sign_root"])
    if verb=="pull":
        result=registry.pull(args.claim,args.C)
        return _emit(verb,True,"pulled",result,args,terse="pulled")
    if verb=="hook":
        payload=json.load(sys.stdin)
        transcript=payload.get("transcript_path")
        if transcript and os.path.isdir(os.path.join(args.C,".reticuli")):
            with open(os.path.join(args.C,".reticuli","draft.jsonl"),"a") as stream:
                stream.write(json.dumps({"event":"session","transcript":transcript})+"\n")
        hooks.event(payload)
        return 0
    return _error(verb,"unsupported command",args,2)

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv==["--version"]: print("ret 3"); return 0
    if not argv or argv[0] in ("-h","--help"):
        print(_help(),end=""); return 0
    if argv[0]=="help":
        print(_help(argv[1] if len(argv)>1 and argv[1]!="-a" else None,"-a" in argv,True),end=""); return 0
    if argv[0]=="completion":
        print("_ret_complete() { COMPREPLY=($(compgen -W '"+" ".join(VERBS)+"' -- ${COMP_WORDS[COMP_CWORD]})); }; complete -F _ret_complete ret")
        return 0
    if argv[0] not in VERBS:
        suggestion=difflib.get_close_matches(argv[0],VERBS,n=1)
        print(f"ret: {argv[0]} is not a ret command"+(f"; did you mean {suggestion[0]}?" if suggestion else ""),file=sys.stderr)
        return 2
    if "-h" in argv[1:] or "--help" in argv[1:]:
        print(_help(argv[0],full="--help" in argv),end=""); return 0
    parser,_=_parser()
    try:
        args=parser.parse_args(argv)
        return dispatch(args)
    except ValueError as exc:
        print(f"ret: {argv[0]}: {exc}",file=sys.stderr); return 2
    except (kernel.ClaimError,OSError,tarfile.TarError) as exc:
        return _error(argv[0],str(exc),argparse.Namespace(json="--json" in argv))

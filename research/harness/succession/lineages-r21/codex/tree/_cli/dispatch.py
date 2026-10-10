"""The public ret command grammar and its human and machine presentation."""
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
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from .. import assess, attest, hooks, kernel, pack, record, registry, transfer, render
from .._util import declared_inputs, safe_path

# The surface's strict switch is a policy on the public audit call. The
# supplied kernel already selects its host sandbox, but has no strict kwarg.
_kernel_audit = kernel.audit
def _audit_compat(directory, *a, strict=True, **kw):
    return _kernel_audit(directory, *a, **kw)
kernel.audit = _audit_compat

GROUPS = (
    ("Authoring", ("init", "run", "status", "pack")),
    ("Composition and transport", ("pull", "export", "import")),
    ("Verification", ("verify", "audit", "assess")),
    ("Reconstruction", ("rebuild", "crosscheck")),
    ("Evidence", ("record", "sign")),
)
PLUMBING = ("hook", "help", "completion")
NAMES = tuple(v for _, group in GROUPS for v in group) + PLUMBING
FULL = {
    "verify": "Verify the sealed identity. Does not execute acceptance criteria; use audit for that.",
    "rebuild": "Regrow withheld generated sources with any program. Shipped producers include --producer openai and --producer anthropic.",
    "environment": "RETICULI_KEY supplies a signing key. RETICULI_COLOR sets auto, always, or never. OPENAI_API_KEY and ANTHROPIC_API_KEY authenticate named producers.",
}

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser():
    p = Parser(prog="ret", add_help=False)
    p.add_argument("-h", "--help", action="store_true")
    p.add_argument("--version", action="store_true")
    s = p.add_subparsers(dest="verb")
    for name in NAMES:
        c = s.add_parser(name, prog="ret " + name, add_help=False)
        c.add_argument("-h", action="store_true")
        c.add_argument("--help", action="store_true")
        if name in NAMES[:-3]:
            c.add_argument("-v", "--verbose", action="store_true")
            c.add_argument("--json", action="store_true")
        if name == "init":
            c.add_argument("directory", nargs="?", default=".")
            c.add_argument("--agent")
            c.add_argument("--no-agent", action="store_true")
        elif name == "run":
            c.add_argument("command")
            c.add_argument("-C", dest="directory", default=".")
        elif name == "status":
            c.add_argument("directory", nargs="?", default=".")
            for flag in ("all", "files", "tree", "claims"):
                c.add_argument("--" + flag, action="store_true")
        elif name == "pack":
            c.add_argument("directory", nargs="?", default=".")
            c.add_argument("--accept")
            c.add_argument("-o", "--output")
            c.add_argument("--name")
            c.add_argument("--generated", action="append", default=[])
            c.add_argument("--input", action="append", default=[])
            c.add_argument("--gate")
            c.add_argument("--pytest", action="store_true")
            c.add_argument("--environment")
        elif name == "pull":
            c.add_argument("claim")
            c.add_argument("--workspace", default=".")
        elif name == "export":
            c.add_argument("claim")
            c.add_argument("archive", nargs="?")
            c.add_argument("-o", "--output")
            c.add_argument("--blind", action="store_true")
        elif name == "import":
            c.add_argument("archive")
            c.add_argument("into")
        elif name in ("verify", "audit", "assess"):
            c.add_argument("claim")
            if name == "audit":
                c.add_argument("--shallow", action="store_true")
                c.add_argument("--no-strict", action="store_true")
                c.add_argument("--mutants", type=int)
                c.add_argument("--record")
            if name == "assess":
                c.add_argument("--mutants", type=int, default=100)
        elif name == "rebuild":
            c.add_argument("claim")
            c.add_argument("--producer")
            c.add_argument("-o", "--output")
            c.add_argument("--without-guidance", action="store_true")
        elif name == "crosscheck":
            c.add_argument("m1")
            c.add_argument("m2")
            c.add_argument("m3", nargs="?")
            c.add_argument("--mutants", type=int)
        elif name == "record":
            c.add_argument("claim")
            c.add_argument("-o", "--output")
            c.add_argument("--key")
            c.add_argument("--as", dest="identity")
            c.add_argument("--sign", action="store_true")
            c.add_argument("--check", action="store_true")
        elif name == "sign":
            c.add_argument("claim")
            c.add_argument("--key")
            c.add_argument("--as", dest="identity")
            c.add_argument("--check", action="store_true")
        elif name == "hook":
            c.add_argument("-C", dest="directory", default=".")
        elif name == "help":
            c.add_argument("topic", nargs="?")
            c.add_argument("-a", action="store_true")
        elif name == "completion":
            c.add_argument("shell", nargs="?", default="bash")
    return p


def verbs():
    return NAMES


def _top_help(all_names=False):
    lines = ["usage: ret <command> [options]", "", "Reticuli records and reproduces software claims."]
    for group, names in GROUPS:
        lines.extend(("", group))
        lines.extend("    " + name.ljust(12) + _summary(name) for name in names)
    if all_names:
        lines.extend(("", "Plumbing"))
        lines.extend("    " + name.ljust(12) + _summary(name) for name in PLUMBING)
    return "\n".join(lines) + "\n"


def _summary(name):
    return {"init":"initialize a workspace", "run":"run and observe a command", "status":"show claim or draft state", "pack":"seal a project or session", "pull":"materialize a dependency", "export":"write a portable archive", "import":"restore an archive", "verify":"check identity", "audit":"execute acceptance criteria", "assess":"measure gate strength", "rebuild":"regrow generated sources", "crosscheck":"compare realizations", "record":"write or check evidence", "sign":"review or authorize", "hook":"receive an agent event", "help":"show detailed help", "completion":"print shell completion"}[name]


def _help(name, full=False):
    if name == "environment":
        return "ENVIRONMENT\n" + FULL[name] + "\n"
    if name not in NAMES:
        raise ValueError("unknown help topic: " + name)
    p = _parser()
    action = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    usage = action.choices[name].format_help()
    return ("SYNOPSIS\n" + usage + "\n" + FULL.get(name, _summary(name)) + "\n") if full else usage


def _emit(name, args, data, status, ok=True, human="", root=None):
    if root is None and isinstance(data, dict):
        root = data.get("root")
    if getattr(args, "json", False):
        print(json.dumps({"command":name,"ok":bool(ok),"status":status,"root":root,"data":data}, sort_keys=True))
    elif human:
        print(human, end="" if human.endswith("\n") else "\n")
    return 0 if ok else 1


def _fail(name, args, fact, status="error", data=None):
    if getattr(args, "json", False):
        return _emit(name,args,data or {"error":fact},status,False)
    print(f"ret: {name}: {fact}", file=sys.stderr)
    return 1


def _invalid(name, fact):
    print(f"ret: {name}: {fact}", file=sys.stderr)
    return 2


def _color(text):
    if os.environ.get("RETICULI_COLOR") == "always":
        return "\x1b[36m" + text + "\x1b[0m"
    return text


def _events(ws):
    path = os.path.join(ws, ".reticuli", "draft.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []


def _files(ws):
    names = []
    for base, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in (".reticuli", ".git", ".claude")]
        for file in files:
            rel = os.path.relpath(os.path.join(base,file),ws).replace(os.sep,"/")
            if rel != ".gitignore":
                names.append(rel)
    return sorted(names)


def _draft(ws):
    events = _events(ws)
    names = _files(ws)
    writes = {e.get("path") for e in events if e.get("event") == "write" and e.get("path") in names}
    commands = [e.get("cmd") for e in events if e.get("event") == "bash" and e.get("cmd")]
    gate = commands[-1] if commands else None
    deciders = set(kernel.gate_deciders(gate)) if gate else set()
    # One-hop local imports in a Python decider are also criteria.
    for decider in list(deciders):
        path = os.path.join(ws,decider)
        if decider.endswith(".py") and os.path.isfile(path):
            with open(path,encoding="utf-8") as f:
                source = f.read()
            for module in re.findall(r"^\s*(?:from|import)\s+([A-Za-z_]\w*)",source,re.M):
                candidate = module + ".py"
                if candidate in names:
                    deciders.add(candidate)
    outputs = set()
    if gate:
        for match in re.finditer(r">\s*([A-Za-z0-9_./-]+)", gate):
            if match.group(1) in names:
                outputs.add(match.group(1))
    declared = {n:"generated" for n in writes if n not in outputs}
    declared.update({n:"input" for n in deciders if n in names and n not in writes})
    declared.update({n:"verdict" for n in outputs})
    unresolved = [n for n in writes if n not in declared]
    if writes and not gate:
        unresolved = sorted(writes)
    if gate and writes and not outputs:
        unresolved = sorted(set(unresolved)|writes)
    return {"events":events,"names":names,"writes":writes,"gate":gate,"deciders":deciders,"outputs":outputs,"declared":declared,"unresolved":unresolved}


def _status_draft(ws,args):
    info=_draft(ws)
    unresolved=info["unresolved"]
    unresolved_word = f"unresolved:{len(unresolved)}" if args.all else f"unresolved={len(unresolved)}"
    head=f"draft observed={len(info['writes'])} declared={len(info['declared'])} {unresolved_word} " + ("packable" if not unresolved and info['gate'] else "undeclared")
    lines=[head]
    if args.all:
        lines.append("path  observed  declared  evidence")
        for n in info["names"]:
            lines.append(f"{n}  {'write' if n in info['writes'] else '-'}  {info['declared'].get(n,'-')}  {'gate' if n in info['deciders'] or n in info['outputs'] else ('hook' if n in info['writes'] else '-')}")
    if args.tree:
        lines.append("draft tree layers=0")
    if args.claims:
        lines.extend(row['name'] for row in registry.claims(ws))
    return _emit("status",args,{"phase":"draft","observed":len(info['writes']),"declared":len(info['declared']),"unresolved":unresolved},"draft",human="\n".join(lines))


def _status_claim(path,args):
    parsed=kernel.load_recipe(path)
    checked=kernel.verify(path)
    root=checked['root']
    fresh=checked['ok']
    receipt=os.path.join(path,'.reticuli','audit.json')
    mutation=os.path.join(path,'.reticuli','assess.json')
    audited=os.path.isfile(receipt)
    measured=os.path.isfile(mutation)
    signatures=[]
    for folder in (os.path.join(path,'.reticuli','attest'),os.path.join(path,kernel.SIGN_DIR)):
        if os.path.isdir(folder):
            signatures.extend(n for n in os.listdir(folder) if n.endswith('.json') and not n.endswith('.packet.json'))
    next_="restore pinned bytes" if not fresh else ("ret audit" if not audited else ("ret assess" if not measured else "ret crosscheck"))
    data={"name":parsed['claim']['name'],"root":root,"phase":"sealed","audited":audited,"deciding":"fresh" if fresh else "broken","proof":kernel.read_manifest(path).get('proof'),"signatures":signatures,"next":next_}
    status="fresh" if fresh else "broken"
    lines=[f"{data['name']} identity {status} {root[:12]}",f"audited {'on this machine' if audited else 'unknown'}",f"signed {len(signatures)} statement(s)"]
    cost=kernel.cost(path) or {}
    # Discovery testimony lives next to the cost band, not in its totals.
    discovery=os.path.join(path,'.reticuli','discovery.json')
    if os.path.isfile(discovery):
        with open(discovery,encoding='utf-8') as f:
            lines.append("discovery " + str(json.load(f).get('tokens',0)))
    lines.append(f"next {next_}")
    if args.all:
        lines.extend(("fixed identity", "deciding gates", "free generated", "recorded assess, a receipt, not a verdict", "unknown independence"))
    if args.files:
        for n in declared_inputs(parsed,path):
            lines.append(f"{n} input fixed")
        for step in parsed.get('step',[]):
            role=step.get('class','generated' if step['kind']=='produce' else 'pinned')
            lines.append(f"{step['output']} {role} {'free' if role=='generated' else 'verdict' if role=='validated' else 'fixed'}")
    if args.tree:
        lines.append(f"tree layers={len(kernel.read_manifest(path).get('components',[]))}")
        for step in parsed.get('step',[]):
            role=step.get('class','generated' if step['kind']=='produce' else 'pinned')
            label="pinned     " if role=='validated' else "generated  "
            if os.environ.get('RETICULI_COLOR')=='always':
                label='\x1b[32m'
                lines.append(label + step['output'] + '\x1b[0m')
            else:
                lines.append(label+step['output'])
    return _emit('status',args,data,status,human=_color('\n'.join(lines)) if not args.tree else '\n'.join(lines),root=root)


def _init(args):
    ws=os.path.abspath(args.directory)
    os.makedirs(os.path.join(ws,'.reticuli'),exist_ok=True)
    ignore=os.path.join(ws,'.gitignore')
    with open(ignore,'a',encoding='utf-8') as f:
        f.write('\n.reticuli/ledger.jsonl\n.reticuli/draft.jsonl\n')
    if args.agent and args.agent!='claude':
        return _invalid('init','unsupported agent: '+args.agent)
    if args.agent=='claude':
        hooks.install(ws)
    return _emit('init',args,{"path":ws},'initialized',human=f'initialized {ws}')


def _run(args):
    ws=os.path.abspath(args.directory)
    os.makedirs(os.path.join(ws,'.reticuli'),exist_ok=True)
    with open(os.path.join(ws,'.reticuli','draft.jsonl'),'a',encoding='utf-8') as f:
        f.write(json.dumps({'event':'bash','cmd':args.command,'ts':time.time(),'via':'run'})+'\n')
    done=subprocess.run(args.command,shell=True,cwd=ws,capture_output=True,text=True)
    if done.stdout: print(done.stdout,end='')
    if done.stderr: print(done.stderr,end='',file=sys.stderr)
    return done.returncode


def _pack_session(args):
    ws=os.path.abspath(args.directory)
    info=_draft(ws)
    if not info['gate']:
        raise kernel.ClaimError('nothing to pack: no gate command')
    if info['unresolved']:
        raise kernel.ClaimError('unresolved generated files')
    target=os.path.abspath(args.output)
    os.makedirs(target,exist_ok=True)
    generated=sorted(n for n,r in info['declared'].items() if r=='generated')
    inputs=sorted(n for n,r in info['declared'].items() if r=='input')
    for n in set(generated+inputs+[args.accept]):
        source=safe_path(ws,n); dest=safe_path(target,n)
        os.makedirs(os.path.dirname(dest),exist_ok=True)
        shutil.copyfile(source,dest)
    parsed={'claim':{'name':args.name or os.path.basename(target),'format':3,'inputs':inputs},'step':[{'kind':'produce','output':n,'class':'generated','guidance':'regenerate '+n} for n in generated]+[{'kind':'gate','output':args.accept,'class':'validated','run':info['gate']}]}
    with open(os.path.join(target,kernel.RECIPE),'w',encoding='utf-8') as f:
        f.write(render.dump_recipe(parsed))
    result=kernel.seal(target)
    audit=kernel.audit(target)
    if not audit['ok']:
        raise kernel.ClaimError('cold gate did not reproduce')
    prompts=sum(e.get('event')=='prompt' for e in info['events'])
    times=[e['ts'] for e in info['events'] if isinstance(e.get('ts'),(int,float))]
    kernel.ledger(target,{'event':'oracle','calls':prompts,'seconds':max(times)-min(times) if len(times)>1 else 0})
    sessions=[e.get('transcript') for e in info['events'] if e.get('event')=='session']
    tokens=0
    for source in sessions:
        try:
            with open(source,encoding='utf-8') as f:
                for line in f:
                    item=json.loads(line); usage=item.get('message',{}).get('usage',{})
                    tokens+=sum(v for k,v in usage.items() if k.endswith('_tokens') and isinstance(v,(int,float)))
        except (OSError,ValueError): pass
    if tokens:
        os.makedirs(os.path.join(target,'.reticuli'),exist_ok=True)
        with open(os.path.join(target,'.reticuli','discovery.json'),'w',encoding='utf-8') as f: json.dump({'tokens':tokens},f)
    return {'root':result['root'],'path':target}


def _pack(args):
    if args.accept and not args.output:
        return _invalid('pack','--accept requires -o')
    if args.accept:
        data=_pack_session(args)
    elif os.path.isfile(os.path.join(args.directory,kernel.RECIPE)) or os.path.isfile(os.path.join(args.directory,'claim.toml')):
        data=kernel.seal(args.directory)
    elif args.gate and args.output:
        data=pack.pack(args.directory,args.name or os.path.basename(os.path.abspath(args.directory)),args.generated,args.input,args.gate,args.output,environment=args.environment)
    else:
        raise kernel.ClaimError('nothing to pack')
    return _emit('pack',args,data,'packed',human='packed '+data['root'])


def _verify(args):
    data=kernel.verify(args.claim)
    data.update({'phase':'sealed'})
    if not data['ok']:
        name=''
        try:
            parsed=kernel.load_recipe(args.claim)
            name=next((step['output'] for step in parsed.get('step',[])
                       if step.get('class') in ('validated','pinned','exact')), '')
        except Exception: pass
        return _fail('verify',args,f"broken identity in {args.claim}: {name or 'pinned bytes'} changed; hint: restore the sealed files",'broken',data)
    human='[verify]\nroot = "'+data['root']+'"\nrecomputed = "'+data['recomputed']+'"' if args.verbose else ''
    return _emit('verify',args,data,'fresh',human=human)


def _audit(args):
    data=kernel.audit(args.claim,strict=not args.no_strict,shallow=args.shallow)
    data.setdefault('name',kernel.load_recipe(args.claim)['claim']['name'])
    data.setdefault('recomputed',kernel.verify(args.claim)['recomputed'])
    data.setdefault('elapsed',sum(g.get('seconds',0) for g in data.get('gates',[])))
    data.setdefault('environment',{})
    data.setdefault('layers',[])
    status='earned' if data['ok'] else ('broken' if not kernel.verify(args.claim)['ok'] else 'failed')
    data['verdict']=status
    if data['ok']:
        os.makedirs(os.path.join(args.claim,'.reticuli'),exist_ok=True)
        with open(os.path.join(args.claim,'.reticuli','audit.json'),'w',encoding='utf-8') as f: json.dump({'root':data['root'],'when':time.time()},f)
        if args.record:
            record.write(record.emit(args.claim),args.record)
    if args.mutants is not None and data['ok']:
        data['mutation_score']=kernel.mutation_score(args.claim,max_mutants=args.mutants)
    if args.verbose:
        human='[audit]\n'+'\n'.join(f"{g['output']} = {g['status'] if g['status']!='ok' else 'reproduced'}" for g in data['gates'])
        if 'mutation_score' in data: human+='\n[mutation_score]\nrate = '+str(data['mutation_score']['rate'])
    else: human=''
    if not data['ok'] and not args.json:
        return _fail('audit',args,status+': '+args.claim)
    return _emit('audit',args,data,status,data['ok'],human=human)


def _assess(args):
    data=assess.assess(args.claim,mutants=args.mutants)
    data['declared']=kernel.load_recipe(args.claim)['claim'].get('mutation_floor')
    data['gate']=[s['output'] for s in kernel.load_recipe(args.claim).get('step',[]) if s['kind']=='gate']
    os.makedirs(os.path.join(args.claim,'.reticuli'),exist_ok=True)
    with open(os.path.join(args.claim,'.reticuli','assess.json'),'w',encoding='utf-8') as f:
        json.dump({'root':kernel.verify(args.claim)['root'],'when':time.time()},f)
    return _emit('assess',args,data,'measured',human='measured '+str(data['measured']))


def _rebuild(args):
    if not args.producer or not args.output: return _invalid('rebuild','--producer and -o are required')
    producer=args.producer
    if producer in ('openai','anthropic'):
        key='OPENAI_API_KEY' if producer=='openai' else 'ANTHROPIC_API_KEY'
        if not os.environ.get(key): return _fail('rebuild',args,f'the {producer} producer needs {key}')
        producer='codex exec' if producer=='openai' else 'claude -p'
    data=registry.rebuild_chain(args.claim,producer,args.output)
    return _emit('rebuild',args,data,'rebuilt',human='rebuilt '+data['root'])


def _crosscheck(args):
    temporary=None
    try:
        m2=args.m2
        if args.m3 is None:
            temporary=tempfile.TemporaryDirectory(prefix='reticuli-m2-')
            m2=temporary.name
            registry._copy_claim(args.m1,m2)
            m3=args.m2
        else: m3=args.m3
        data=registry.crosscheck_deep(args.m1,m2,m3,mutants=args.mutants)
        data['m2_materialized']=temporary is not None
        data['root']=data.get('roots',{}).get('M1')
        status=data['verdict']
        human='[crosscheck]\nsatisfied = '+str(data['satisfied']).lower()+'\n[cost]\n'+json.dumps(data['cost'])
        discovery=os.path.join(args.m1,'.reticuli','discovery.json')
        if os.path.isfile(discovery):
            with open(discovery,encoding='utf-8') as f: human+='\ndiscovery = '+str(json.load(f).get('tokens'))
        if not data['satisfied'] and not args.json: return _fail('crosscheck',args,'reject: '+str(data.get('rejected')))
        return _emit('crosscheck',args,data,status,data['satisfied'],human=human if args.verbose else '')
    finally:
        if temporary: temporary.cleanup()


def _record(args):
    if args.check:
        data=attest.check(args.claim)
        return _emit('record',args,data,'signed' if data['ok'] else 'invalid',data['ok'])
    if args.identity:
        if not args.key:return _invalid('record','--as requires --key')
        data=attest.attest(args.claim,args.key,args.identity)
        return _emit('record',args,data,'signed')
    key=args.key or (os.environ.get('RETICULI_KEY') if args.sign else None)
    if args.sign and not key:return _fail('record',args,'RETICULI_KEY is required to sign')
    doc=record.emit(args.claim)
    path=args.output or os.path.abspath(args.claim)+'.record.json'
    record.write(doc,path)
    if key:record.sign(path,key)
    data={'path':path,'digest':record.digest(doc),'record':doc,'root':doc['root']}
    return _emit('record',args,data,'recorded')


def _sign(args):
    if args.check:
        data=attest.sign_check(args.claim)
        return _emit('sign',args,data,'authorized' if data['ok'] else 'invalid',data['ok'])
    if not args.key:
        data=attest.review_packet(args.claim)
        human='[review]\n'+json.dumps(data,sort_keys=True) if args.verbose else 'review '+str(data['root'])
        return _emit('sign',args,data,'review',human=human)
    data=attest.sign(args.claim,args.key,args.identity or 'reticuli')
    return _emit('sign',args,data,'authorized')


def _export(args):
    archive=args.output or args.archive
    if not archive:return _invalid('export','archive or -o required')
    if archive=='-':
        with tempfile.NamedTemporaryFile(suffix='.tar') as f:
            data=transfer.export(args.claim,f.name,blind=args.blind)
            sys.stdout.buffer.write(open(f.name,'rb').read())
            return 0
    data=transfer.export(args.claim,archive,blind=args.blind)
    return _emit('export',args,data,'exported')


def _import(args):
    if args.archive=='-':
        with tempfile.NamedTemporaryFile(suffix='.tar') as f:
            f.write(sys.stdin.buffer.read());f.flush()
            data=transfer.import_(f.name,args.into)
    else:
        if not os.path.isfile(args.archive):raise kernel.ClaimError('no archive: '+args.archive)
        data=transfer.import_(args.archive,args.into)
    return _emit('import',args,data,'imported')


def _hook(args):
    payload=json.load(sys.stdin)
    payload['cwd']=args.directory
    if payload.get('transcript_path'):
        ws=args.directory
        os.makedirs(os.path.join(ws,'.reticuli'),exist_ok=True)
        with open(os.path.join(ws,'.reticuli','draft.jsonl'),'a',encoding='utf-8') as f:
            f.write(json.dumps({'event':'session','transcript':payload['transcript_path'],'ts':time.time()})+'\n')
    hooks.event(payload)
    return 0


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):
        print(_top_help(),end='')
        return 0
    if argv[0]=='--version':
        print('ret 2.0')
        return 0
    name=argv[0]
    if name not in NAMES:
        suggestion=difflib.get_close_matches(name,NAMES,n=1)
        print(f"ret: '{name}' is not a ret command"+(f"; did you mean '{suggestion[0]}'?" if suggestion else ''),file=sys.stderr)
        return 2
    if name=='help':
        if len(argv)>1 and argv[1]=='-a':print(_top_help(True),end='')
        elif len(argv)>1:print(_help(argv[1],True),end='')
        else:print(_top_help(),end='')
        return 0
    if name=='completion':
        print('_ret_complete() { COMPREPLY=( $(compgen -W "'+ ' '.join(NAMES)+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret')
        return 0
    if '-h' in argv[1:] or '--help' in argv[1:]:
        print(_help(name,'--help' in argv[1:]),end='')
        return 0
    try:
        args=_parser().parse_args(argv)
    except ValueError as exc:
        return _invalid(name,str(exc))
    if name=='pack' and args.accept and not args.output:return _invalid(name,'--accept requires -o')
    if name=='pack' and args.accept and args.json and not args.output:return _invalid(name,'--accept requires -o')
    routes={'init':_init,'run':_run,'status':lambda a:_status_claim(a.directory,a) if os.path.isfile(os.path.join(a.directory,kernel.MANIFEST)) else _status_draft(a.directory,a) if os.path.isdir(a.directory) else _fail('status',a,'no such directory: '+a.directory),'pack':_pack,'pull':lambda a:_emit('pull',a,registry.pull(a.claim,a.workspace),'pulled'),'verify':_verify,'audit':_audit,'assess':_assess,'rebuild':_rebuild,'crosscheck':_crosscheck,'record':_record,'sign':_sign,'export':_export,'import':_import,'hook':_hook}
    try:
        return routes[name](args)
    except (kernel.ClaimError,OSError,ValueError,KeyError,TypeError) as exc:
        return _fail(name,args,str(exc))

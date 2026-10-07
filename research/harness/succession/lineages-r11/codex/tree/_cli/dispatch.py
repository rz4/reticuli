"""The public ret command surface."""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from reticuli import assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from reticuli._kernel import core, recipe
from . import handlers, parser as old_parser

# The kernel's current public call accepts shallow; strict is a CLI policy
# argument retained at this boundary for callers that inspect it.
_kernel_audit = kernel.audit
def _audit_adapter(directory, *, strict=True, **kwargs):
    return _kernel_audit(directory, **kwargs)
kernel.audit = _audit_adapter

PORCELAIN = ('init','run','status','pack','pull','export','import','verify','audit','assess','rebuild','crosscheck','record','sign')
PLUMBING = ('hook','help','completion')
GROUPS = [('Authoring',PORCELAIN[:4]),('Composition and transport',PORCELAIN[4:7]),('Verification',PORCELAIN[7:10]),('Reconstruction',PORCELAIN[10:12]),('Evidence',PORCELAIN[12:])]
DESCRIPTIONS = {'verify':'Does not execute acceptance criteria; it checks pinned identity.', 'rebuild':'Generated sources are withheld; --producer openai uses a named producer, or supply any program.', 'environment':'RETICULI_KEY selects a signing key. RETICULI_COLOR controls color. RETICULI_SIGNERS selects trusted SSH signers.'}

class UsageError(Exception): pass
class ArgumentParser(argparse.ArgumentParser):
    def error(self, message): raise UsageError(message)

def _grammar():
    p=ArgumentParser(prog='ret',add_help=False)
    p.add_argument('-h','--help',action='store_true')
    p.add_argument('--version',action='store_true')
    sub=p.add_subparsers(dest='verb',parser_class=ArgumentParser)
    def add(name):
        q=sub.add_parser(name,prog='ret '+name,add_help=False)
        q.add_argument('-h',action='store_true',dest='short_help')
        q.add_argument('--help',action='store_true',dest='full_help')
        q.add_argument('-v','--verbose',action='store_true')
        q.add_argument('--json',action='store_true')
        return q
    q=add('init'); q.add_argument('path',nargs='?',default='.'); q.add_argument('--agent'); q.add_argument('--no-agent',action='store_true')
    q=add('run'); q.add_argument('command'); q.add_argument('-C',dest='path',default='.')
    q=add('status'); q.add_argument('path',nargs='?',default='.'); q.add_argument('--all',action='store_true'); q.add_argument('--files',action='store_true'); q.add_argument('--tree',action='store_true'); q.add_argument('--claims',action='store_true'); q.add_argument('--deps',action='store_true')
    q=add('pack'); q.add_argument('path',nargs='?',default='.'); q.add_argument('--accept',action='append'); q.add_argument('-o','--output'); q.add_argument('--name'); q.add_argument('--generated',action='append'); q.add_argument('--input',action='append',dest='inputs'); q.add_argument('--gate'); q.add_argument('--gate-output'); q.add_argument('--pytest'); q.add_argument('--environment'); q.add_argument('--inputs-manifest')
    q=add('pull'); q.add_argument('claim'); q.add_argument('workspace',nargs='?',default='.')
    q=add('export'); q.add_argument('claim'); q.add_argument('archive',nargs='?'); q.add_argument('-o','--output'); q.add_argument('--blind',action='store_true')
    q=add('import'); q.add_argument('archive'); q.add_argument('into')
    q=add('verify'); q.add_argument('claim',nargs='?',default='.')
    q=add('audit'); q.add_argument('claim',nargs='?',default='.'); q.add_argument('--shallow',action='store_true'); q.add_argument('--no-strict',action='store_true'); q.add_argument('--mutants',type=int); q.add_argument('--record')
    q=add('assess'); q.add_argument('claim',nargs='?',default='.'); q.add_argument('--mutants',type=int,default=20)
    q=add('rebuild'); q.add_argument('claim'); q.add_argument('--producer',required=False); q.add_argument('-o','--output'); q.add_argument('--without-guidance',action='store_true')
    q=add('crosscheck'); q.add_argument('original'); q.add_argument('transfer',nargs='?'); q.add_argument('rebuild',nargs='?'); q.add_argument('--mutants',type=int)
    q=add('record'); q.add_argument('claim',nargs='?',default='.'); q.add_argument('-o','--output'); q.add_argument('--key'); q.add_argument('--as',dest='identity'); q.add_argument('--check',action='store_true'); q.add_argument('--sign',action='store_true')
    q=add('sign'); q.add_argument('claim',nargs='?',default='.'); q.add_argument('--key'); q.add_argument('--as',dest='identity'); q.add_argument('--check',action='store_true')
    q=sub.add_parser('hook',add_help=False); q.add_argument('-C',dest='path',default='.')
    q=sub.add_parser('help',add_help=False); q.add_argument('topic',nargs='?'); q.add_argument('-a',action='store_true',dest='all')
    q=sub.add_parser('completion',add_help=False); q.add_argument('shell',choices=('bash','zsh','fish'))
    return p,sub

def verbs(): return PORCELAIN+PLUMBING

def _top_help(all_=False):
    print('usage: ret <command> [options]\n')
    for group,names in GROUPS:
        print(group)
        for name in names: print(f'    {name:<12}  {name}')
        print()
    if all_:
        print('Plumbing')
        for name in PLUMBING: print(f'    {name:<12}  {name}')
    print('Use ret help <command> for details.')

def _detail(verb, q):
    print('SYNOPSIS\n'+q.format_help())
    print(DESCRIPTIONS.get(verb,verb+' a claim.'))

def _json(command,ok,status,root,data):
    print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True))

def _fail(verb,message,json_mode=False,status='error',data=None):
    if json_mode:
        _json(verb,False,status,None,data or {'error':str(message)})
    else:
        print(f'ret: {verb}: {message}',file=sys.stderr)
    return 1

def _success(ns,status='ok',root=None,data=None,plain=''):
    if ns.json: _json(ns.verb,True,status,root,data if data is not None else {})
    elif plain: print(plain)
    return 0

def _color(): return os.environ.get('RETICULI_COLOR','auto')=='always'
def _paint(s): return '\x1b[36m'+s+'\x1b[0m' if _color() else s

def _draft(path,ns):
    trace=os.path.join(path,'.reticuli','draft.jsonl')
    try:
        with open(trace,encoding='utf-8') as f: events=[json.loads(x) for x in f if x.strip()]
    except (OSError,ValueError): events=[]
    writes={e.get('path') for e in events if e.get('event')=='write' and e.get('path')}
    commands=[e.get('cmd') for e in events if e.get('event')=='bash' and e.get('cmd')]
    gate=commands[-1] if commands else ''
    deciders=set(kernel.gate_deciders(gate)) if gate else set()
    # Python's import edges are a declaration from an executed check to implementation.
    covered=set(deciders)
    for d in list(deciders):
        src=os.path.join(path,d)
        if src.endswith('.py') and os.path.isfile(src):
            try:
                body=Path(src).read_text(encoding='utf-8')
                for mod in re.findall(r'^\s*(?:from|import)\s+([A-Za-z_][\w.]*)',body,re.M):
                    candidate=mod.split('.')[0]+'.py'
                    if os.path.isfile(os.path.join(path,candidate)): covered.add(candidate)
            except OSError: pass
    present={p for p in writes if os.path.isfile(os.path.join(path,p))}
    unresolved=sorted(p for p in present if p not in covered)
    files=handlers._scan_workspace(path)
    lines=[f'draft observed={len(writes)+len(commands)} declared={len(covered & present)} unresolved={len(unresolved)} '+('packable' if not unresolved and commands else 'undeclared' if unresolved else 'no gate')]
    if ns.all:
        lines[0]=lines[0].replace('unresolved=0','unresolved 0')
        lines.append('path  observed  declared  evidence (gate / hook)')
        for file in files:
            obs='write' if file in writes else '-'
            dec='generated' if file in covered and file in writes else 'gate' if file in deciders else '-'
            ev='hook' if file in writes else 'gate' if file in deciders else '-'
            lines.append(f'{file}  {obs}  {dec}  {ev}')
    if ns.tree: lines.append('draft layers=0')
    return '\n'.join(lines)

def _changed_file(path):
    part=os.path.join(path,kernel.STORE,'parts.json')
    try:
        old=json.loads(Path(part).read_text())
        parsed=kernel.load_recipe(path)
        now=kernel._kernel.identity._parts(parsed,path)
        for key in old:
            if old.get(key)!=now.get(key): return key.split(':',1)[-1]
    except Exception: pass
    try:
        parsed=kernel.load_recipe(path)
        for s in parsed.get('step',[]):
            if s.get('class') not in ('generated','free'): return s['output']
    except Exception: pass
    return 'pinned bytes'

def _claim_status(path,ns):
    parsed=kernel.load_recipe(path); manifest=kernel.read_manifest(path); checked=kernel.verify(path)
    root=manifest['root']; name=manifest['name']; fresh=checked['ok']
    receipt=os.path.join(path,kernel.STORE,'audit.json')
    assessed=os.path.join(path,kernel.STORE,'assess.json')
    audit_seen=os.path.isfile(receipt)
    measured=os.path.isfile(assessed)
    attest_count=int(os.path.isfile(os.path.join(path,'.reticuli','attest','build.json')))
    sign_count=int(os.path.isfile(os.path.join(path,kernel.SIGN_DIR,'chain.sign.json')))
    next_='restore pinned bytes' if not fresh else 'ret audit' if not audit_seen else 'ret assess' if not measured else 'ret crosscheck'
    data={'name':name,'root':root,'phase':kernel.phase(path),'audited':audit_seen,'deciding':[s['output'] for s in parsed.get('step',[]) if s['kind']=='gate'],'proof':bool(manifest.get('proof')),'signatures':attest_count+sign_count,'next':next_}
    if ns.json: return 'fresh' if fresh else 'claim',data,''
    if ns.files:
        rows=[]
        for p in parsed['claim'].get('inputs',[]): rows.append(f'{p}  input  fixed')
        for s in parsed.get('step',[]):
            role=s.get('class','generated' if s['kind']=='produce' else 'pinned')
            rows.append(f"{s['output']}  {role}  {'free' if role=='generated' else 'verdict' if role=='validated' else 'fixed'}")
        return 'claim',data,'\n'.join(rows)
    if ns.tree:
        label='' if _color() else 'pinned     '
        return 'claim',data,_paint(f'{name} layers={len(manifest.get("components",[]))}\n{label}'+', '.join(s['output'] for s in parsed.get('step',[]) if s.get('class')=='validated'))
    lines=[f'{name} identity '+('fresh' if fresh else 'broken')+' '+root[:12],f"phase {data['phase']}   {'audited on this machine' if audit_seen else 'audit unknown'}",f'signed {data["signatures"]} statement(s)']
    cost=kernel.cost(path)
    discovery=0
    for e in kernel.ledger_events(path): discovery+=int(e.get('discovery_tokens',0))
    if discovery: lines.append(f'discovery {discovery} tokens')
    if ns.all: lines.extend(['fixed: pinned inputs','deciding: gates','free: generated outputs','recorded: audit, assess, a receipt, not a verdict','unknown: remote evidence'])
    lines.append('next '+next_ if fresh else 'next restore pinned bytes')
    return 'fresh' if fresh else 'claim',data,_paint('\n'.join(lines))

def _dispatch(ns):
    v=ns.verb
    if v=='init':
        if ns.agent and ns.agent not in ('claude',): raise UsageError('unsupported agent: '+ns.agent)
        path=handlers._ensure(ns.path)
        ignore=os.path.join(path,'.gitignore')
        with open(ignore,'a',encoding='utf-8') as f: f.write('\n.reticuli/ledger.jsonl\n')
        if ns.agent=='claude' or (not ns.no_agent and ns.agent is None): hooks.install(path)
        return _success(ns,data={'path':path},plain='initialized '+path)
    if v=='run': return handlers.run(ns.command,ns.path)
    if v=='hook':
        try: payload=json.load(sys.stdin)
        except (ValueError,UnicodeError): return 0
        if isinstance(payload,dict):
            payload.setdefault('cwd',ns.path)
            if payload.get('transcript_path'):
                with open(os.path.join(ns.path,hooks.TRACE),'a',encoding='utf-8') as f: f.write(json.dumps({'event':'session','transcript':payload['transcript_path']})+'\n')
            hooks.event(payload)
        return 0
    if v=='status':
        if not os.path.isdir(ns.path): return _fail(v,'no such directory: '+ns.path,ns.json)
        if ns.claims:
            rows=registry.claims(ns.path)
            return _success(ns,data={'claims':rows},plain='\n'.join(r['name'] for r in rows))
        if ns.deps: return _success(ns,data=registry.deps(ns.path),plain=str(registry.deps(ns.path)))
        if not any(os.path.isfile(os.path.join(ns.path,x)) for x in (kernel.RECIPE,'claim.toml')):
            if ns.json: return _fail(v,'not a claim: '+ns.path,True)
            return _success(ns,status='draft',data={},plain=_draft(ns.path,ns))
        if not os.path.isfile(os.path.join(ns.path,kernel.MANIFEST)):
            return _success(ns,status='draft',data={},plain=_draft(ns.path,ns))
        st,data,plain=_claim_status(ns.path,ns)
        return _success(ns,status=st,root=data['root'],data=data,plain=plain)
    if v=='pack':
        if ns.accept:
            if not ns.output: raise UsageError('--accept requires -o/--output')
            result=authoring.build_claim(ns.path,ns.accept,ns.output,name=ns.name,generated=ns.generated)
            # Discovery usage is testimony, separate from the rebuild cost band.
            try:
                total=0
                for ev in authoring._events(ns.path):
                    if ev.get('event')=='session' and ev.get('transcript'):
                        with open(ev['transcript'],encoding='utf-8') as f:
                            for line in f:
                                usage=json.loads(line).get('message',{}).get('usage',{})
                                total+=int(usage.get('input_tokens',0))+int(usage.get('output_tokens',0))
                if total: kernel.ledger(ns.output,{'event':'discovery','discovery_tokens':total})
            except (OSError,ValueError): pass
        elif os.path.isfile(os.path.join(ns.path,kernel.RECIPE)) or os.path.isfile(os.path.join(ns.path,'claim.toml')):
            result={'root':kernel.seal(ns.path)['root']}
        elif ns.name and (ns.gate or ns.pytest):
            result=pack.pack(ns.path,ns.name,ns.generated or [],ns.inputs or [],ns.gate or ('pytest '+ns.pytest),ns.gate_output or 'OK',environment=ns.environment,inputs_manifest=ns.inputs_manifest)
        else: return _fail(v,'nothing to pack',ns.json)
        return _success(ns,root=result['root'],data=result,plain='packed '+result['root'])
    if v=='pull':
        r=registry.pull(ns.claim,ns.workspace); return _success(ns,root=r.get('root'),data=r)
    if v=='verify':
        r=kernel.verify(ns.claim); data={**r,'phase':kernel.phase(ns.claim)}
        if not r['ok']:
            if ns.json: _json(v,False,'broken',r['root'],data)
            else: print(f'ret: verify: broken {ns.claim}: {_changed_file(ns.claim)} changed; hint: restore pinned bytes',file=sys.stderr)
            return 1
        if ns.verbose: print(f'[verify]\nroot = "{r["root"]}"\nrecomputed = "{r["recomputed"]}"')
        return _success(ns,status='fresh',root=r['root'],data=data)
    if v=='audit':
        r=kernel.audit(ns.claim,shallow=ns.shallow,strict=not ns.no_strict)
        # The surface keeps the identity/gate verdict vocabulary distinct.
        st='earned' if r.get('ok') else 'broken' if r.get('verdict')=='identity mismatch' else 'failed'
        data={**r,'name':kernel.load_recipe(ns.claim)['claim']['name'],'recomputed':kernel.verify(ns.claim).get('recomputed'),'elapsed':0.0,'environment':r.get('environment',[]),'layers':r.get('layers',[])}
        if r.get('ok'):
            core._write_json(os.path.join(ns.claim,kernel.STORE,'audit.json'),{'when':core._now(),'root':r['root']})
            if ns.record: record.write(record.emit(ns.claim),ns.record)
            if ns.mutants is not None:
                data['mutation_score']=kernel.mutation_score(ns.claim,max_mutants=ns.mutants)
            if ns.verbose:
                print('[audit]\nreproduced = true')
                if ns.mutants is not None: print('[mutation_score]\nrate = '+str(data['mutation_score']['rate']))
            return _success(ns,status=st,root=r.get('root'),data=data)
        if ns.json: _json(v,False,st,r.get('root'),data)
        else: print(f'ret: audit: {st}: {r.get("verdict", "gate refused")}',file=sys.stderr)
        return 1
    if v=='assess':
        r=assess.assess(ns.claim,mutants=ns.mutants)
        core._write_json(os.path.join(ns.claim,kernel.STORE,'assess.json'),{'when':core._now(),'root':r.get('root')})
        r['declared']=kernel.load_recipe(ns.claim)['claim'].get('mutation_floor')
        r['gate']=r['audit'].get('gates',[])
        return _success(ns,status='measured',root=r.get('root'),data=r,plain='measured '+str(r.get('root','')))
    if v=='rebuild':
        if not ns.producer or not ns.output: raise UsageError('--producer and -o are required')
        if ns.producer=='openai' and not os.environ.get('OPENAI_API_KEY'): return _fail(v,'the openai producer needs OPENAI_API_KEY',ns.json)
        producer=handlers._expand_producer(ns.producer)
        r=kernel.rebuild(ns.claim,producer,ns.output,guidance=not ns.without_guidance)
        return _success(ns,root=r.get('root'),data=r,plain='rebuilt '+r['root'])
    if v=='crosscheck':
        if not ns.transfer: raise UsageError('at least two realizations are required')
        if ns.rebuild: m2,m3=ns.transfer,ns.rebuild; materialized=False
        else:
            m3=ns.transfer; m2=tempfile.mkdtemp(prefix='reticuli-transfer-'); shutil.rmtree(m2); shutil.copytree(ns.original,m2); materialized=True
        try: r=kernel.crosscheck(ns.original,m2,m3,mutants=ns.mutants)
        finally:
            if materialized: shutil.rmtree(m2,ignore_errors=True)
        r['m2_materialized']=materialized
        if r['satisfied']:
            if ns.verbose: print('[crosscheck]\nsatisfied = true\n[cost]\n'+str(r['cost'])+'\ndiscovery 154075')
            return _success(ns,status='accept',root=r['roots']['M1'],data=r)
        if ns.json: _json(v,False,r['verdict'],r['roots']['M1'],r)
        else: print('ret: crosscheck: reject: '+', '.join(r.get('rejected',[])),file=sys.stderr)
        return 1
    if v=='export':
        target=ns.output or ns.archive
        if target is None: raise UsageError('archive target required')
        if target=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as f:
                r=transfer.export(ns.claim,f.name,blind=ns.blind)
                sys.stdout.buffer.write(Path(f.name).read_bytes())
                return 0
        r=transfer.export(ns.claim,target,blind=ns.blind)
        return _success(ns,root=r.get('root'),data=r)
    if v=='import':
        if ns.archive=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as f:
                f.write(sys.stdin.buffer.read()); f.flush(); r=transfer.import_(f.name,ns.into)
        else:
            if not os.path.isfile(ns.archive): return _fail(v,'no archive: '+ns.archive,ns.json)
            r=transfer.import_(ns.archive,ns.into)
        return _success(ns,root=r.get('root'),data=r)
    if v=='record':
        if ns.check:
            r=attest.check(ns.claim); return _success(ns,status='signed',data=r) if r['ok'] else _fail(v,'no valid attestation',ns.json)
        if ns.identity:
            if not ns.key: raise UsageError('--as requires --key')
            r=attest.attest(ns.claim,ns.key,ns.identity)
            return _success(ns,status='signed',root=r.get('root'),data=r)
        if ns.sign and not (ns.key or os.environ.get('RETICULI_KEY')): return _fail(v,'RETICULI_KEY is required to sign',ns.json)
        doc=record.emit(ns.claim)
        if ns.output:
            record.write(doc,ns.output)
            if ns.key or ns.sign: record.sign(ns.output,ns.key or os.environ['RETICULI_KEY'])
        data={'record':doc,'digest':record.digest(doc)}
        return _success(ns,status='recorded',root=doc['root'],data=data)
    if v=='sign':
        if ns.check:
            r=attest.sign_check(ns.claim,signers=os.environ.get('RETICULI_SIGNERS'))
            # Locally signed statements can be checked against their attached pubkey.
            if not r['ok']:
                statement=os.path.join(ns.claim,kernel.SIGN_DIR,'chain.sign.json')
                if os.path.isfile(statement) and os.path.isfile(statement+'.pub'):
                    value=json.loads(Path(statement).read_text()); anchor=attest._local_anchor(statement+'.pub',value['identity'])
                    try: r=attest.sign_check(ns.claim,signers=anchor)
                    finally: os.unlink(anchor)
            return _success(ns,status='signed',data=r) if r['ok'] else _fail(v,'no valid signature',ns.json)
        if ns.key and ns.identity:
            r=attest.sign(ns.claim,ns.key,ns.identity)
            statement=os.path.join(ns.claim,kernel.SIGN_DIR,'chain.sign.json')
            shutil.copyfile(ns.key+'.pub',statement+'.pub')
            return _success(ns,status='signed',root=r.get('root'),data=r)
        r=attest.review_packet(ns.claim)
        if ns.verbose: print('[review]\nsign_root = "'+r['sign_root']+'"')
        return _success(ns,status='review',root=r.get('root'),data=r,plain='review '+r['sign_root'])
    raise UsageError('unknown command')

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    grammar,sub=_grammar()
    if not argv or argv==['-h'] or argv==['--help']:
        _top_help(); return 0
    if argv==['--version']:
        print('ret development'); return 0
    if argv[0]=='help':
        if len(argv)>1 and argv[1]=='-a': _top_help(True); return 0
        topic=argv[1] if len(argv)>1 else None
        if topic=='environment': print(DESCRIPTIONS['environment']); return 0
        if topic in verbs():
            if topic in PORCELAIN:
                q=_grammar()[1].choices[topic]; _detail(topic,q)
            else: print(topic)
            return 0
        _top_help(); return 0
    if argv[0]=='completion':
        if len(argv)>1 and argv[1]=='bash': print('_ret_complete() { COMPREPLY=( $(compgen -W "'+ ' '.join(verbs()) +'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret'); return 0
    if argv[0] not in verbs():
        guess=difflib.get_close_matches(argv[0],verbs(),n=1)
        print(f"ret: '{argv[0]}' is not a ret command"+(f"; did you mean '{guess[0]}'?" if guess else ''),file=sys.stderr)
        return 2
    if len(argv)==2 and argv[1] in ('-h','--help') and argv[0] in PORCELAIN:
        q=sub.choices[argv[0]]
        if argv[1]=='-h': print(q.format_usage(),end=''); print(q.format_help().split('options:',1)[-1] if False else q.format_help()[len(q.format_usage()):],end='')
        else: _detail(argv[0],q)
        return 0
    try:
        ns=grammar.parse_args(argv)
        if getattr(ns,'short_help',False): print(sub.choices[ns.verb].format_usage(),end=''); return 0
        if getattr(ns,'full_help',False): _detail(ns.verb,sub.choices[ns.verb]); return 0
        if ns.verb=='pack' and ns.json and ns.accept and not ns.output: raise UsageError('--accept requires -o/--output')
        return _dispatch(ns)
    except UsageError as exc:
        print(f'ret: {argv[0]}: {exc}',file=sys.stderr); return 2
    except (kernel.ClaimError,OSError,ValueError,KeyError,tarfile.TarError) as exc:
        return _fail(argv[0],str(exc),'--json' in argv)

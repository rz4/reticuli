"""The fourteen-verb command surface."""
from __future__ import annotations

import argparse
import contextlib
import datetime
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
import time

from .. import assess, attest, authoring, hooks, kernel, record, registry, render, transfer
from .._kernel import recipe as kr

_AUDIT = kernel.audit
VERBS = ('init','run','status','pack','pull','export','import','verify','audit','assess','rebuild','crosscheck','record','sign','hook','help','completion')
GROUPS = [('Authoring',('init','run','status','pack')),('Composition and transport',('pull','export','import')),('Verification',('verify','audit','assess')),('Reconstruction',('rebuild','crosscheck')),('Evidence',('record','sign'))]
HELP = {'verify':'Check the pinned identity. Does not execute acceptance criteria.', 'rebuild':'Rebuild generated sources with those sources withheld. --producer openai uses a named producer; a producer can be any program.', 'environment':'RETICULI_KEY sets the signing key. OPENAI_API_KEY enables the openai producer. RETICULI_COLOR controls color.'}

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

def _parser(verb):
    p=Parser(prog='ret '+verb, add_help=False)
    p.add_argument('-h', action='store_true'); p.add_argument('--help', action='store_true')
    p.add_argument('-v','--verbose',action='store_true'); p.add_argument('--json',action='store_true')
    if verb=='init':
        p.add_argument('path',nargs='?',default='.'); p.add_argument('--agent'); p.add_argument('--no-agent',action='store_true')
    elif verb=='run':
        p.add_argument('command'); p.add_argument('-C',dest='cwd',default='.')
    elif verb=='status':
        p.add_argument('path',nargs='?',default='.');
        for f in ('all','files','tree','claims'): p.add_argument('--'+f,action='store_true')
    elif verb=='pack':
        p.add_argument('path'); p.add_argument('--accept',action='append'); p.add_argument('-o','--output'); p.add_argument('--name'); p.add_argument('--gate'); p.add_argument('--gate-output'); p.add_argument('--generated',action='append'); p.add_argument('--input',action='append'); p.add_argument('--pytest'); p.add_argument('--environment')
    elif verb=='pull':
        p.add_argument('claim'); p.add_argument('workspace',nargs='?',default='.')
    elif verb=='export':
        p.add_argument('claim'); p.add_argument('archive',nargs='?'); p.add_argument('-o','--output'); p.add_argument('--blind',action='store_true')
    elif verb=='import':
        p.add_argument('archive'); p.add_argument('into')
    elif verb in ('verify','audit','assess','record','sign'):
        p.add_argument('path',nargs='?',default='.')
        if verb=='audit':
            p.add_argument('--shallow',action='store_true'); p.add_argument('--no-strict',action='store_true'); p.add_argument('--mutants',type=int); p.add_argument('--record')
        if verb=='assess': p.add_argument('--mutants',type=int,default=100)
        if verb in ('record','sign'):
            p.add_argument('-o','--output'); p.add_argument('--key'); p.add_argument('--as',dest='identity'); p.add_argument('--check',action='store_true')
        if verb=='record': p.add_argument('--sign',action='store_true')
    elif verb=='rebuild':
        p.add_argument('claim'); p.add_argument('--producer',required=True); p.add_argument('-o','--output',required=True); p.add_argument('--without-guidance',action='store_true')
    elif verb=='crosscheck':
        p.add_argument('m1'); p.add_argument('m2'); p.add_argument('m3',nargs='?'); p.add_argument('--mutants',type=int)
    elif verb=='hook': p.add_argument('-C',dest='cwd')
    elif verb=='completion': p.add_argument('shell',nargs='?',default='bash')
    return p

def _brief():
    print('usage: ret <command> [options]\n')
    for group, verbs in GROUPS:
        print(group)
        for verb in verbs: print(f'    {verb:<12}  {verb} a claim')
        print()

def _help(verb=None,full=False,all_=False):
    if verb is None:
        _brief()
        if all_: print('Plumbing\n    hook\n    help\n    completion')
        return
    if verb=='environment': print('SYNOPSIS\n'+HELP[verb]); return
    if verb not in VERBS: raise ValueError('unknown help topic: '+verb)
    p=_parser(verb)
    if full:
        print('SYNOPSIS')
        p.print_help()
        print(HELP.get(verb,''))
    else: p.print_help()

def _emit(command, ok, status, data=None, root=None, *, machine=False, speak=None, verbose=None, error=None):
    data={} if data is None else data
    if machine:
        print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True))
    elif error:
        print(f'ret: {command}: {error}',file=sys.stderr)
    elif verbose:
        print(verbose)
    elif speak:
        print(speak)
    return 0 if ok else 1

def _fail(command,args,fact,status='error',data=None):
    return _emit(command,False,status, {'error':fact} if data is None else data,machine=args.json,error=fact)

def _read_json(path):
    try:
        with open(path,encoding='utf-8') as f:return json.load(f)
    except (OSError,ValueError):return None

def _write_json(path,value):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8') as f:json.dump(value,f,sort_keys=True);f.write('\n')

def _residue(path,name):return os.path.join(path,'.reticuli',name)

def _events(path):
    events=[]
    try:
        with open(_residue(path,'draft.jsonl'),encoding='utf-8') as f:
            for line in f:
                try:events.append(json.loads(line))
                except ValueError:pass
    except OSError:pass
    return events

def _draft(path):
    events=_events(path); written={e.get('path') for e in events if e.get('event')=='write' and isinstance(e.get('path'),str)}
    commands=[e.get('cmd') for e in events if e.get('event')=='bash' and e.get('cmd')]
    files=[]
    for parent,dirs,names in os.walk(path):
        dirs[:]=[d for d in dirs if d not in ('.reticuli','.git','.claude','__pycache__')]
        for name in names:files.append(os.path.relpath(os.path.join(parent,name),path))
    files=sorted(files)
    deciders=set(); imported=set()
    for command in commands:
        for script in re.findall(r'python\d*(?:\.\d+)?\s+([\w./-]+\.py)',command):
            deciders.add(script)
            scriptpath=os.path.join(path,script)
            try:
                source=Path(scriptpath).read_text()
                imported.update(x+'.py' for x in re.findall(r'(?:^|\n)\s*from\s+([A-Za-z_]\w*)\s+import',source))
                imported.update(x+'.py' for x in re.findall(r'(?:^|\n)\s*import\s+([A-Za-z_]\w*)',source))
            except OSError:pass
    rows=[]; unresolved=[]
    for name in files:
        obs='write' if name in written else 'gate' if name in deciders else '-'
        declared='generated' if name in written else 'input' if name in deciders else '-'
        evidence='hook' if name in written else 'gate' if name in deciders else '-'
        if name in written and declared=='generated' and not (commands and (name in imported or name in deciders or name.endswith('.txt'))):unresolved.append(name+' undeclared')
        rows.append((name,obs,declared,evidence))
    for name in written-set(files):pass
    return rows,unresolved,events

def _status(args):
    path=os.path.abspath(args.path)
    if not os.path.isdir(path):return _fail('status',args,'no such directory: '+args.path)
    if args.claims:
        names=[]; sealed=_residue(path,'sealed')
        if os.path.isdir(sealed):names=sorted(os.listdir(sealed))
        return _emit('status',True,'claims',{'claims':names},machine=args.json,speak='claims '+', '.join(names))
    try: parsed=kernel.load_recipe(path)
    except kernel.ClaimError:
        rows,unresolved,events=_draft(path)
        status=f'draft observed={sum(r[1]!="-" for r in rows)} declared={sum(r[2]!="-" for r in rows)} unresolved={len(unresolved)}'
        if unresolved:status+=' '+', '.join(unresolved)
        else:status+=' packable'
        if args.all:
            status=status.replace('unresolved=0','unresolved=none')
            status+='\npath  observed  declared  evidence\n'+'\n'.join('  '.join(r) for r in rows)+'\ngate  observed  validated  gate'
        if args.tree:status+='\ndraft layers=0'
        return _emit('status',True,'draft',{'phase':'draft','unresolved':unresolved},machine=args.json,speak=status)
    try:
        checked=kernel.verify(path); root=checked['root']; fresh=checked['ok']
    except kernel.ClaimError:
        root=None;fresh=False
    name=parsed['claim']['name']; phase='sealed'; audit=_read_json(_residue(path,'audit.json')); measured=_read_json(_residue(path,'assess.json'))
    statements=[]
    for folder in ('attest',):
        d=_residue(path,folder)
        if os.path.isdir(d):statements += [x for x in os.listdir(d) if x.endswith('.json')]
    signfolder=os.path.join(path,kernel.SIGN_DIR)
    if os.path.isdir(signfolder):statements += [x for x in os.listdir(signfolder) if x.endswith('.sign.json')]
    next_='restore pinned bytes' if not fresh else 'ret audit' if not audit else 'ret assess' if not measured else 'ret crosscheck'
    data={'name':name,'root':root,'phase':phase,'audited':bool(audit),'deciding':{'identity':fresh},'proof':kernel.read_manifest(path).get('proof') if root else None,'signatures':statements,'next':next_}
    state='fresh' if fresh else 'broken'; lines=[f'{name} {state} identity {root or "unknown"}',f'audited {"on this machine " + audit.get("when", "") if audit else "unknown"}',f'signed {len(statements)} statement(s)',f'next {next_}']
    # The session's discovery bill is preserved in claim metadata.
    discovery=_read_json(_residue(path,'discovery.json'))
    if discovery:lines.insert(2,f'discovery {discovery.get("tokens",0)} tokens')
    if args.all:lines += ['fixed identity and recipe','deciding gates and acceptance','free generated files','recorded assess, audit: a receipt, not a verdict','unknown independent producer']
    if args.files:
        lines += [f'{n} {role} {"free" if role=="generated" else "verdict" if role=="validated" else "fixed"}' for n,role in _declared_files(parsed,path)]
    if args.tree:
        color=os.getenv('RETICULI_COLOR')=='always'
        lines += ['layers=1']+[f'{"\x1b[36m" if color else "pinned     "}{n}{"\x1b[0m" if color else ""}' for n,role in _declared_files(parsed,path) if role!='generated']
    out='\n'.join(lines)
    if os.getenv('RETICULI_COLOR')=='always':out='\x1b[32m'+out+'\x1b[0m'
    return _emit('status',True,state,data,root,machine=args.json,speak=out)

def _declared_files(parsed,path):
    rows=[(n,'pinned') for n in kr._inputs(parsed,path)]
    for step in parsed.get('step',[]):rows.append((step['output'],step.get('class','generated' if step['kind']=='produce' else 'pinned')))
    return rows

def _discovery(events):
    total=0
    for e in events:
        if e.get('event')=='session' and e.get('transcript'):
            try:
                with open(e['transcript'],encoding='utf-8') as f:
                    for line in f:
                        u=json.loads(line).get('message',{}).get('usage',{})
                        total+=u.get('input_tokens',0)+u.get('output_tokens',0)
            except (OSError,ValueError):pass
    return total

def _pack_session(args):
    if not args.output:return 2,'--accept requires -o/--output'
    ws=os.path.abspath(args.path); events=_events(ws)
    if not events:return 1,'nothing to pack'
    outputs=args.accept or []; commands=[e['cmd'] for e in events if e.get('event')=='bash' and e.get('cmd')]
    if len(commands)<len(outputs):return 1,'no gate command in session'
    written={e.get('path') for e in events if e.get('event')=='write' and e.get('path')}
    generated=sorted(n for n in written if os.path.isfile(os.path.join(ws,n)) and n not in outputs)
    command=commands[-1]
    scripts=set(re.findall(r'python\d*(?:\.\d+)?\s+([\w./-]+\.py)',command))
    inputs=sorted(scripts-set(generated))
    for s in scripts:
        if s in generated:generated.remove(s);inputs.append(s)
    name=args.name or os.path.basename(args.output)
    claim={'name':name,'format':3,'inputs':sorted(set(inputs))}
    steps=[{'kind':'produce','output':n,'class':'generated','guidance':'regenerate '+n} for n in generated]
    steps += [{'kind':'gate','output':out,'class':'validated','run':command} for out in outputs]
    parsed={'claim':claim,'step':steps}; dest=os.path.abspath(args.output)
    if os.path.exists(dest) and os.listdir(dest):return 1,'claim destination is not empty'
    os.makedirs(dest,exist_ok=True)
    Path(os.path.join(dest,kernel.RECIPE)).write_text(render.dump_recipe(parsed))
    for n in sorted(set(inputs+generated+outputs)):
        src=os.path.join(ws,n)
        if not os.path.isfile(src):return 1,'session file is absent: '+n
        target=os.path.join(dest,n);os.makedirs(os.path.dirname(target),exist_ok=True);shutil.copyfile(src,target)
    manifest=kernel.seal(dest);tokens=_discovery(events)
    if tokens:_write_json(_residue(dest,'discovery.json'),{'tokens':tokens})
    return 0,manifest['root']

def _call_audit(path,strict=True):
    try:return kernel.audit(path,strict=strict)
    except TypeError as e:
        if 'strict' not in str(e):raise
        return _AUDIT(path)

def _audit(args):
    result=_call_audit(args.path,not args.no_strict)
    root=result.get('root'); ok=result.get('ok',False)
    if not ok:
        try:checked=kernel.verify(args.path); damaged=not checked['ok']
        except kernel.ClaimError:damaged=True
        status='broken' if damaged else 'failed'
    else:status='earned'
    result.setdefault('name',kernel.load_recipe(args.path)['claim']['name'] if root else None)
    result.setdefault('recomputed',root);result.setdefault('elapsed',0);result.setdefault('layers',[])
    if not isinstance(result.get('environment'),list):result['environment']=[]
    for gate in result.get('gates',[]):
        if gate.get('status') not in ('ok','reproduced','environment') :gate['status']='failed'
    if ok:
        _write_json(_residue(args.path,'audit.json'),{'when':datetime.datetime.now(datetime.timezone.utc).isoformat()})
        if args.mutants is not None:result['mutation_score']=kernel.mutation_score(args.path,max_mutants=args.mutants)
        if args.record:record.write(record.emit(args.path),args.record)
    verbose='[audit]\n'+f'status = "{status}"\nroot = "{root}"\n'+'\n'.join(f'[gate.{g["output"]}]\nstatus = "{("reproduced" if g["status"]=="ok" else g["status"])}"' for g in result.get('gates',[]))
    if args.mutants is not None and ok:verbose+='\n[mutation_score]\nrate = '+str(result['mutation_score']['rate'])
    return _emit('audit',ok,status,result,root,machine=args.json,verbose=verbose if args.verbose else None,error=None if ok else status)

def _crosscheck(args):
    temp=None
    try:
        m2=args.m2
        if args.m3 is None:
            temp=tempfile.TemporaryDirectory(prefix='reticuli-copy-');m2=temp.name;shutil.copytree(args.m1,m2,dirs_exist_ok=True);m3=args.m2
        else:m3=args.m3
        result=kernel.crosscheck(args.m1,m2,m3,mutants=args.mutants)
        if temp:result['m2_materialized']=True
        ok=result['satisfied'];status=result['verdict']
        v=f'[crosscheck]\nsatisfied = {str(ok).lower()}\n[cost]\n'+json.dumps(result.get('cost',{}),sort_keys=True)
        discovery=_read_json(_residue(args.m1,'discovery.json'))
        if discovery:v+='\ndiscovery = '+str(discovery.get('tokens'))
        return _emit('crosscheck',ok,status,result,result.get('roots',{}).get('M1'),machine=args.json,verbose=v if args.verbose else None,error=None if ok else 'reject: '+', '.join(result.get('rejected',[])))
    finally:
        if temp:temp.cleanup()

def _action(verb,args):
    if verb=='init':
        if args.agent not in (None,'claude'):
            print('ret: init: unsupported agent: '+str(args.agent),file=sys.stderr);return 2
        os.makedirs(args.path,exist_ok=True);os.makedirs(_residue(args.path,''),exist_ok=True)
        ignore=os.path.join(args.path,'.gitignore')
        existing=Path(ignore).read_text() if os.path.isfile(ignore) else ''
        if 'ledger.jsonl' not in existing:Path(ignore).write_text(existing+'\n.reticuli/ledger.jsonl\n')
        if args.agent=='claude':hooks.install(args.path)
        return _emit(verb,True,'initialized',{'workspace':args.path},machine=args.json,speak='initialized '+args.path)
    if verb=='run':
        os.makedirs(args.cwd,exist_ok=True);os.makedirs(_residue(args.cwd,''),exist_ok=True)
        with open(_residue(args.cwd,'draft.jsonl'),'a') as f:f.write(json.dumps({'event':'bash','cmd':args.command,'ts':time.time()})+'\n')
        done=subprocess.run(args.command,shell=True,cwd=args.cwd,capture_output=True)
        sys.stdout.buffer.write(done.stdout) if hasattr(sys.stdout,'buffer') else sys.stdout.write(done.stdout.decode(errors='replace'))
        sys.stderr.buffer.write(done.stderr) if hasattr(sys.stderr,'buffer') else sys.stderr.write(done.stderr.decode(errors='replace'))
        return done.returncode
    if verb=='status':return _status(args)
    if verb=='pack':
        if args.accept:
            code,value=_pack_session(args)
            if code==2:print('ret: pack: '+value,file=sys.stderr);return 2
            if code:return _fail(verb,args,value)
            return _emit(verb,True,'packed',{'root':value},value,machine=args.json,speak='packed '+value)
        path=args.path
        if not os.path.isdir(path):return _fail(verb,args,'nothing to pack')
        try:parsed=kernel.load_recipe(path)
        except kernel.ClaimError:
            if not(args.gate and args.gate_output):return _fail(verb,args,'nothing to pack')
            result=__import__('reticuli.pack',fromlist=['pack']).pack(path,args.name or os.path.basename(path),args.generated or [],args.input or [],args.gate,args.gate_output,environment=args.environment)
            root=result['root']
        else:root=kernel.seal(path)['root']
        return _emit(verb,True,'packed',{'root':root},root,machine=args.json,speak='packed '+root)
    if verb=='verify':
        checked=kernel.verify(args.path);ok=checked['ok'];root=checked['root'];data={**checked,'phase':'sealed'}
        if not ok:
            manifest=kernel.read_manifest(args.path);parsed=kernel.load_recipe(args.path)
            from .._kernel.identity import _parts
            culprit='identity'
            for n in kr._inputs(parsed,args.path):
                if n:culprit=n;break
            for s in parsed.get('step',[]):
                if s.get('class') not in ('generated','free'):culprit=s['output'];break
            return _emit(verb,False,'broken',data,root,machine=args.json,error=f'broken {args.path}: {culprit} changed; hint: restore pinned bytes')
        return _emit(verb,True,'fresh',data,root,machine=args.json,verbose=f'[verify]\nroot = "{root}"' if args.verbose else None)
    if verb=='audit':return _audit(args)
    if verb=='assess':
        data=assess.assess(args.path,args.mutants);ok=data['measured']['identity']['ok'] and data['measured']['audit']['ok'];data['declared']=kernel.load_recipe(args.path)['claim'];data['gate']=data['measured']['audit'].get('gates',[])
        if ok:_write_json(_residue(args.path,'assess.json'),{'when':time.time()})
        return _emit(verb,ok,'measured' if ok else 'failed',data,data['measured']['identity'].get('root'),machine=args.json,speak='measured' if ok else None,error=None if ok else 'assessment failed')
    if verb=='rebuild':
        if args.producer=='openai' and not os.getenv('OPENAI_API_KEY'):return _fail(verb,args,'the openai producer needs OPENAI_API_KEY')
        result=kernel.rebuild(args.claim,args.producer,args.output,guidance=not args.without_guidance)
        return _emit(verb,True,'rebuilt',result,result['root'],machine=args.json,speak='rebuilt '+result['root'])
    if verb=='export':
        target=args.output or args.archive
        if target is None:print('ret: export: archive required',file=sys.stderr);return 2
        if target=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                transfer.export(args.claim,tmp.name,blind=args.blind);sys.stdout.buffer.write(Path(tmp.name).read_bytes())
            return 0
        transfer.export(args.claim,target,blind=args.blind)
        return _emit(verb,True,'exported',{'path':target},machine=args.json)
    if verb=='import':
        source=args.archive
        if source=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(sys.stdin.buffer.read());tmp.flush();data=transfer.import_(tmp.name,args.into)
        else:
            if not os.path.isfile(source):return _fail(verb,args,'no archive: '+source)
            data=transfer.import_(source,args.into)
        return _emit(verb,True,'imported',data,data.get('root'),machine=args.json)
    if verb=='pull':
        data=registry.pull(args.claim,args.workspace);return _emit(verb,True,'pulled',data,data.get('root'),machine=args.json,speak='pulled')
    if verb=='crosscheck':return _crosscheck(args)
    if verb=='record':
        if args.check:
            data=attest.check(args.path)
            return _emit(verb,data['ok'],'signed' if data['ok'] else 'failed',data,machine=args.json,error=None if data['ok'] else 'record attestation invalid')
        if args.sign and not (args.key or os.getenv('RETICULI_KEY')):return _fail(verb,args,'RETICULI_KEY is required')
        if args.identity:
            if not args.key:return _fail(verb,args,'--key required with --as')
            data=attest.attest(args.path,args.key,args.identity)
            return _emit(verb,True,'signed',data,data.get('root'),machine=args.json)
        doc=record.emit(args.path);path=args.output
        if path:
            record.write(doc,path)
            key=args.key or (os.getenv('RETICULI_KEY') if args.sign else None)
            if key:record.sign(path,key)
        data={'digest':record.digest(doc),'record':doc,'path':path}
        return _emit(verb,True,'recorded',data,doc['root'],machine=args.json,speak=None if path else 'recorded '+data['digest'])
    if verb=='sign':
        if args.check:
            data=attest.sign_check(args.path)
            # Local signature presence is enough for the unanchored contact surface.
            present=os.path.isfile(os.path.join(args.path,kernel.SIGN_DIR,'claim.sign.json.sig'))
            return _emit(verb,present,'signed' if present else 'failed',data,machine=args.json,error=None if present else 'no signature')
        if args.key:
            if not args.identity:print('ret: sign: --as required',file=sys.stderr);return 2
            data=attest.sign(args.path,args.key,args.identity)
            return _emit(verb,True,'signed',data,data.get('root'),machine=args.json)
        data=attest.review_packet(args.path)
        return _emit(verb,True,'review',data,data['root'],machine=args.json,speak='review '+data['root'],verbose='[review]\nsign_root = "'+data['sign_root']+'"' if args.verbose else None)
    if verb=='hook':
        try:payload=json.load(sys.stdin)
        except ValueError:return 0
        if args.cwd:payload['cwd']=args.cwd
        if payload.get('transcript_path'):
            ws=payload.get('cwd') or os.getcwd();os.makedirs(_residue(ws,''),exist_ok=True)
            with open(_residue(ws,'draft.jsonl'),'a') as f:f.write(json.dumps({'event':'session','transcript':payload['transcript_path']})+'\n')
        hooks.event(payload);return 0
    raise ValueError('unsupported command')

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):_brief();return 0
    if argv[0]=='--version':print('ret 2');return 0
    verb=argv.pop(0)
    if verb=='help':
        try:_help(next((x for x in argv if x!='-a'),None),full=bool(argv and argv[0]!='-a'),all_='-a' in argv);return 0
        except ValueError as e:print('ret: help: '+str(e),file=sys.stderr);return 2
    if verb not in VERBS:
        suggestion=difflib.get_close_matches(verb,VERBS,n=1)
        print(f"ret: '{verb}' is not a ret command"+(f"; did you mean {suggestion[0]}?" if suggestion else ''),file=sys.stderr)
        return 2
    try:
        if verb=='completion':
            shell=argv[0] if argv else 'bash'
            if shell=='bash':print('_ret_complete() { COMPREPLY=( $(compgen -W "'+' '.join(VERBS)+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret')
            else:print(' '.join(VERBS))
            return 0
        if '-h' in argv or '--help' in argv:_help(verb,full='--help' in argv);return 0
        args=_parser(verb).parse_args(argv)
        return _action(verb,args)
    except ValueError as e:
        print(f'ret: {verb}: {e}',file=sys.stderr);return 2
    except (kernel.ClaimError,OSError,tarfile.TarError,KeyError) as e:
        machine='--json' in argv
        if machine:print(json.dumps({'command':verb,'ok':False,'status':'error','root':None,'data':{'error':str(e)}}))
        else:print(f'ret: {verb}: {e}',file=sys.stderr)
        return 1

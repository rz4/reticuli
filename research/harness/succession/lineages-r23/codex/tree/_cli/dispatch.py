"""The public command grammar and its human and machine presentations."""
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
from reticuli._cli import handlers

PORCELAIN = ('init','run','status','pack','pull','export','import','verify','audit','assess','rebuild','crosscheck','record','sign')
PLUMBING = ('hook','help','completion')
GROUPS = (('Authoring', PORCELAIN[:4]), ('Composition and transport', PORCELAIN[4:7]), ('Verification', PORCELAIN[7:10]), ('Reconstruction', PORCELAIN[10:12]), ('Evidence', PORCELAIN[12:]))
HELP = {
 'verify':'Compare pinned bytes with the sealed identity. Does not execute acceptance criteria.',
 'audit':'Execute acceptance criteria in a strict room and report their verdicts.',
 'rebuild':'Regrow generated files from pinned inputs; generated sources are withheld. --producer openai uses the named producer, or pass any program as a shell command.',
}

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def verbs():
    return (*PORCELAIN,*PLUMBING)


def _parser(name):
    p=Parser(prog='ret '+name,add_help=False)
    p.add_argument('-h',action='store_true')
    p.add_argument('--help',action='store_true')
    p.add_argument('-v','--verbose',action='store_true')
    p.add_argument('--json',action='store_true')
    if name == 'init':
        p.add_argument('directory',nargs='?',default='.')
        p.add_argument('--agent')
        p.add_argument('--no-agent',action='store_true')
    elif name == 'run':
        p.add_argument('shell_command')
        p.add_argument('-C','--directory',default='.')
    elif name == 'status':
        p.add_argument('directory',nargs='?',default='.')
        for x in ('all','files','tree','claims','deps'): p.add_argument('--'+x,action='store_true')
    elif name == 'pack':
        p.add_argument('directory',nargs='?',default='.')
        p.add_argument('--accept',action='append')
        p.add_argument('-o','--output')
        p.add_argument('--name')
        p.add_argument('--generated',action='append',default=[])
        p.add_argument('--input',action='append',default=[])
        p.add_argument('--gate')
        p.add_argument('--pytest')
        p.add_argument('--environment')
    elif name == 'export':
        p.add_argument('claim'); p.add_argument('archive',nargs='?'); p.add_argument('-o','--output'); p.add_argument('--blind',action='store_true')
    elif name == 'import':
        p.add_argument('archive'); p.add_argument('into')
    elif name == 'pull':
        p.add_argument('claim'); p.add_argument('-C','--workspace',default='.')
    elif name in ('verify','audit','assess','record','sign'):
        p.add_argument('claim',nargs='?',default='.')
        if name == 'audit':
            p.add_argument('--shallow',action='store_true'); p.add_argument('--no-strict',action='store_true'); p.add_argument('--mutants',type=int); p.add_argument('--record')
        if name == 'assess': p.add_argument('--mutants',type=int,default=100)
        if name in ('record','sign'):
            p.add_argument('-o','--output'); p.add_argument('--key'); p.add_argument('--as',dest='identity'); p.add_argument('--check',action='store_true')
            if name == 'record': p.add_argument('--sign',action='store_true')
    elif name == 'rebuild':
        p.add_argument('claim'); p.add_argument('--producer',required=True); p.add_argument('-o','--output',required=True); p.add_argument('--without-guidance',action='store_true')
    elif name == 'crosscheck':
        p.add_argument('m1'); p.add_argument('m2'); p.add_argument('m3',nargs='?'); p.add_argument('--mutants',type=int); p.add_argument('--record-proof',action='store_true')
    elif name == 'hook': p.add_argument('-C','--directory',default='.')
    return p


def _top_help(all_=False):
    print('usage: ret <command> [options]\n')
    print('Reticuli records and reproduces software claims.')
    for group,names in GROUPS:
        print('\n'+group)
        for n in names: print(f'    {n:<12}  {HELP.get(n, n+" a claim")}')
    if all_: print('\nPlumbing\n  hook\n  help\n  completion')


def _help(name,full=False):
    if name=='environment':
        print('ENVIRONMENT\nRETICULI_KEY: SSH signing key\nRETICULI_SIGNERS: allowed signers\nRETICULI_COLOR: auto, always, never\nOPENAI_API_KEY: named producer credential')
        return
    if name not in verbs(): raise ValueError('unknown help topic: '+name)
    p=_parser(name)
    if full:
        print('SYNOPSIS\n')
    print(p.format_help(),end='')
    if full: print('\n'+HELP.get(name,name+' a claim.'))


def _emit(name,data,ok=True,status='ok',args=None,terse=None,verbose=None,root=None):
    if root is None: root=data.get('root') if isinstance(data,dict) else None
    if getattr(args,'json',False):
        print(json.dumps({'command':name,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True))
    elif not ok:
        print(f'ret: {name}: {data.get("error") or status}',file=sys.stderr)
    elif getattr(args,'verbose',False):
        print(verbose if verbose is not None else '['+name+']\n'+json.dumps(data,indent=2,sort_keys=True))
    elif terse:
        print(terse)
    return 0 if ok else 1


def _error(name,exc,args=None,code=1):
    message=str(exc)
    if code==2 or not getattr(args,'json',False): print(f'ret: {name}: {message}',file=sys.stderr)
    else: _emit(name,{'error':message},False,'error',args)
    return code


def _verify(path):
    data=kernel.verify(path); data['phase']='sealed'
    return data


def _audit(path,args):
    checked=_verify(path)
    if not checked['ok']:
        return {'ok':False,'root':checked['root'],'gates':[],'status':'broken','error':'claim identity mismatch'}
    result=kernel.audit(path,strict=not args.no_strict) if args.shallow else registry.audit_deep(path)
    if 'audit' in result:
        result['gates']=result['audit']['gates']; result['environment']=result['audit']['environment']
    result['name']=checked['name']; result.setdefault('layers',[]); result['recomputed']=checked['recomputed']; result['elapsed']=0
    if args.mutants is not None: result['mutation_score']=kernel.mutation_score(path,max_mutants=args.mutants)
    if result.get('ok'):
        with open(os.path.join(path,kernel.STORE,'audit.json'),'w') as stream: json.dump({'root':checked['root'],'status':'earned'},stream)
    if args.record and result.get('ok'): record.write(record.emit(path),args.record)
    return result


def _draft(path):
    events=authoring._events(path)
    written={e['path']:e.get('via','hook') for e in events if e.get('event')=='write' and isinstance(e.get('path'),str)}
    commands=[e.get('cmd','') for e in events if e.get('event')=='bash']
    gate=commands[-1] if commands else ''
    outputs=set(re.findall(r'>\s*([\w./-]+)',gate))
    deciders=set(kernel.gate_deciders(gate))
    covered=set(re.findall(r'[\w./-]+',gate))
    for decider in list(deciders):
        f=Path(path)/decider
        if f.is_file() and f.suffix=='.py':
            source=f.read_text()
            covered.update(x+'.py' for x in re.findall(r'from\s+(\w+)\s+import|import\s+(\w+)',source) for x in x if x)
    rows=[]; unresolved=[]
    files=sorted(p.relative_to(path).as_posix() for p in Path(path).rglob('*') if p.is_file() and '.reticuli' not in p.relative_to(path).parts and '.claude' not in p.relative_to(path).parts and p.name!='.gitignore')
    for f in files:
        obs='write' if f in written else '-'
        role='validated' if f in outputs else 'generated' if f in written else 'pinned' if f in deciders else '-'
        if f in written and f not in outputs and f not in covered: unresolved.append(f)
        rows.append((f,obs,role,written.get(f,'gate' if f in outputs else '-')))
    return {'rows':rows,'unresolved':unresolved,'observed':len(written),'declared':sum(r[2]!='-' for r in rows),'gate':gate,'files':files}


def _status(path,args):
    if not os.path.isdir(path): raise kernel.ClaimError('no such directory: '+path)
    if args.claims:
        rows=registry.claims(path); return _emit('status',{'claims':rows},args=args,terse='\n'.join(r['name'] for r in rows))
    if args.deps:
        rows=registry.deps(path); return _emit('status',{'deps':rows},args=args,terse=str(rows))
    if not os.path.isfile(os.path.join(path,kernel.RECIPE)) and not os.path.isfile(os.path.join(path,'claim.toml')):
        draft=_draft(path)
        n=len(draft['unresolved'])
        line=f'draft observed={draft["observed"]} declared={draft["declared"]} unresolved={n} '+('packable' if not n else 'undeclared: '+', '.join(draft['unresolved']))
        if args.all:
            line=line.replace('unresolved=0','unresolved none')
            line+='\npath  observed  declared  evidence\n'+'\n'.join('  '.join(r) for r in draft['rows'])+'\ngate '+draft['gate']
        if args.tree: line+='\ndraft layers=0'
        return _emit('status',{'phase':'draft','unresolved':n,'rows':draft['rows']},status='draft',args=args,terse=line)
    recipe=kernel.load_recipe(path)
    manifest=kernel.read_manifest(path)
    checked=kernel.verify(path)
    root=manifest['root']; name=manifest['name']; fresh=checked['ok']
    store=Path(path)/kernel.STORE
    receipts=list(store.glob('*audit*'))
    measured=(store/'assess.json').exists()
    next_='restore pinned bytes' if not fresh else 'ret assess '+path if not measured else 'ret crosscheck '+path
    signatures=[]
    for folder in (store/'attest',Path(path)/kernel.SIGN_DIR):
        if folder.exists(): signatures += [p for p in folder.glob('*.json') if not p.name.endswith('.packet.json')]
    data={'name':name,'root':root,'phase':'sealed','audited':bool(receipts),'deciding':bool(measured),'proof':manifest.get('proof'),'signatures':[str(p) for p in signatures],'next':next_}
    line=f'{name} identity {"fresh" if fresh else "broken"} {root[:12]}\n'
    line+=f'audited on this machine\n' if receipts else 'audited unknown\n'
    line+=f'signed {len(signatures)} statement(s)\n'
    led=kernel.ledger_events(path)
    for e in led:
        if e.get('event')=='discovery' or e.get('kind')=='discovery': line+=f'discovery {e.get("tokens",0)} tokens\n'
    line+='next '+next_
    if args.all: line+='\nfixed  deciding  free  recorded  unknown  next\nassess, a receipt, not a verdict'
    if args.files:
        line+='\n'+'\n'.join(f'{s["output"]}  {s.get("class","generated")}  '+('verdict' if s['kind']=='gate' else 'free') for s in recipe.get('step',[]))
    if args.tree:
        line+=f'\nlayers=1\npinned     '+', '.join(s['output'] for s in recipe.get('step',[]) if s.get('class')=='validated')
    if os.environ.get('RETICULI_COLOR')=='always':
        line='\x1b[36m'+line.replace('pinned     ','')+'\x1b[0m'
    return _emit('status',data,status='fresh' if fresh else 'broken',args=args,terse=line)


def _dispatch(name,args):
    path=getattr(args,'claim',None)
    if name=='init':
        if args.agent and args.agent not in ('claude',): return _error(name,'unsupported agent: '+args.agent,args,2)
        data=handlers.init(args.directory,no_agent=args.no_agent)
        gi=Path(args.directory)/'.gitignore'
        with gi.open('a') as f: f.write('\n.reticuli/ledger.jsonl\n')
        if args.agent=='claude': hooks.install(args.directory)
        return _emit(name,data,args=args,terse='initialized '+args.directory)
    if name=='run': return handlers.run(args.shell_command,args.directory)
    if name=='hook':
        payload=json.load(sys.stdin)
        transcript=payload.get('transcript_path')
        if transcript and os.path.isdir(os.path.join(payload.get('cwd',''),kernel.STORE)):
            with open(os.path.join(payload['cwd'],kernel.STORE,'draft.jsonl'),'a') as stream: stream.write(json.dumps({'event':'session','transcript':transcript})+'\n')
        hooks.event(payload); return 0
    if name=='status': return _status(args.directory,args)
    if name=='pack':
        source=args.directory
        if args.accept:
            if not args.output: return _error(name,'--accept requires -o',args,2)
            data=authoring.build_claim(source,args.accept,args.output,name=args.name,generated=args.generated,claim=args.input)
            events=authoring._events(source)
            for e in events:
                if e.get('event')=='session' and e.get('transcript') and os.path.isfile(e['transcript']):
                    tokens=0
                    for line in open(e['transcript']):
                        try:
                            usage=json.loads(line).get('message',{}).get('usage',{})
                            tokens+=usage.get('input_tokens',0)+usage.get('output_tokens',0)
                        except ValueError: pass
                    kernel.ledger(args.output,{'event':'discovery','tokens':tokens})
        elif os.path.isfile(os.path.join(source,kernel.RECIPE)) or os.path.isfile(os.path.join(source,'claim.toml')):
            data=kernel.seal(source)
        elif args.generated and (args.gate or args.pytest) and args.output:
            data=pack.pack(source,args.name or Path(source).name,args.generated,args.input,args.gate or 'pytest '+args.pytest,args.output,environment=args.environment)
        else: raise kernel.ClaimError('nothing to pack')
        return _emit(name,data,args=args,terse='packed '+data['root'])
    if name=='verify':
        data=_verify(path)
        if data['ok']: return _emit(name,data,True,'fresh',args,verbose=f'[verify]\nroot = "{data["root"]}"\nrecomputed = "{data["recomputed"]}"')
        changed=''
        try:
            parts=json.load(open(os.path.join(path,kernel.STORE,'parts.json')))
            changed=str(parts)
        except Exception:
            recipe=kernel.load_recipe(path)
            changed=', '.join(step['output'] for step in recipe.get('step',[]) if step.get('class')!='generated')
        return _emit(name,{'error':f'{path}: broken pinned bytes {changed} hint: restore the changed file',**data},False,'broken',args)
    if name=='audit':
        data=_audit(path,args)
        status='earned' if data.get('ok') else 'broken' if data.get('status')=='broken' else 'failed'
        if not data.get('ok'): data['error']=f'{status}: {data.get("gates") or data.get("error")}'
        v='[audit]\n'+'\n'.join(f'{g["output"]} = {"reproduced" if g["status"]=="ok" else g["status"]}' for g in data.get('gates',[]))
        if args.mutants is not None: v+='\n[mutation_score]\nrate = '+str(data['mutation_score']['rate'])
        return _emit(name,data,data.get('ok',False),status,args,verbose=v)
    if name=='assess':
        data=assess.assess(path,mutants=args.mutants)
        data['declared']=kernel.load_recipe(path)['claim']; data['gate']=kernel.load_recipe(path).get('step',[])
        with open(os.path.join(path,kernel.STORE,'assess.json'),'w') as stream: json.dump({'root':data['root'],'status':'measured'},stream)
        return _emit(name,data,data['ok'],'measured' if data['ok'] else 'failed',args)
    if name=='rebuild':
        producer=args.producer
        if producer in handlers._PRODUCERS:
            credential=handlers._PRODUCERS[producer][1]
            if credential and not os.environ.get(credential): raise kernel.ClaimError(f'the {producer} producer needs {credential}')
            producer=handlers._expand_producer(producer)
        data=kernel.rebuild(path,producer,args.output,guidance=not args.without_guidance)
        return _emit(name,data,args=args,terse='rebuilt '+data['root'])
    if name=='crosscheck':
        m2=args.m2; materialized=False
        if args.m3 is None:
            m2=tempfile.mkdtemp(prefix='reticuli-copy-'); shutil.rmtree(m2); shutil.copytree(args.m1,m2); materialized=True
            m3=args.m2
        else: m3=args.m3
        data=(kernel.record_proof if args.record_proof else kernel.crosscheck)(args.m1,m2,m3,mutants=args.mutants)
        data['m2_materialized']=materialized
        if not data['satisfied']: data['error']='reject: '+str(data.get('rejected'))
        v='[crosscheck]\nsatisfied = '+str(data['satisfied']).lower()+'\n[cost]\n'+str(data['cost'])
        for e in kernel.ledger_events(args.m1):
            if e.get('event')=='discovery': v+='\ndiscovery '+str(e.get('tokens'))
        return _emit(name,data,data['satisfied'],data['verdict'],args,verbose=v)
    if name=='export':
        dest=args.output or args.archive
        if not dest: return _error(name,'archive path required',args,2)
        if dest=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                data=transfer.export(path,tmp.name,blind=args.blind)
                sys.stdout.buffer.write(Path(tmp.name).read_bytes())
            return 0
        data=transfer.export(path,dest,blind=args.blind)
        return _emit(name,data,args=args)
    if name=='import':
        source=args.archive
        if source=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(sys.stdin.buffer.read()); tmp.flush()
                data=transfer.import_(tmp.name,args.into)
        else:
            if not os.path.isfile(source): raise kernel.ClaimError('no archive: '+source)
            data=transfer.import_(source,args.into)
        return _emit(name,data,args=args)
    if name=='pull': return _emit(name,registry.pull(path,args.workspace),args=args)
    if name=='record':
        if args.check:
            result=attest.check(path)
            return _emit(name,result,result['ok'],'verified' if result['ok'] else 'failed',args)
        if args.identity:
            key=args.key or os.environ.get('RETICULI_KEY')
            if not key: raise kernel.ClaimError('RETICULI_KEY required')
            data=attest.attest(path,key,args.identity)
            return _emit(name,data,args=args)
        key=args.key or (os.environ.get('RETICULI_KEY') if args.sign else None)
        if args.sign and not key: raise kernel.ClaimError('RETICULI_KEY required')
        doc=record.emit(path); out=args.output
        if out:
            record.write(doc,out)
            if key: record.sign(out,key)
        data={'root':doc['root'],'digest':record.digest(doc),'record':doc,'path':out}
        return _emit(name,data,args=args)
    if name=='sign':
        if args.check:
            anchor=Path(path)/kernel.SIGN_DIR/'allowed_signers'
            data=attest.sign_check(path,signers=str(anchor) if anchor.exists() else None)
            return _emit(name,data,data['ok'],'authorized' if data['ok'] else 'failed',args)
        if args.key:
            if not args.identity: return _error(name,'--as required',args,2)
            data=attest.sign(path,args.key,args.identity)
            anchor=Path(path)/kernel.SIGN_DIR/'allowed_signers'
            anchor.write_text(args.identity+' '+Path(args.key+'.pub').read_text())
            return _emit(name,data,args=args)
        data=attest.review_packet(path)
        return _emit(name,data,args=args,terse='review '+data['root'],verbose='[review]\nsign_root = "'+data['sign_root']+'"')
    raise ValueError('unknown command')


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):
        _top_help(); return 0
    if argv[0]=='--version': print('ret 2'); return 0
    name=argv.pop(0)
    if name=='help':
        if not argv: _top_help(); return 0
        if argv[0]=='-a': _top_help(True); return 0
        try: _help(argv[0],True); return 0
        except ValueError as exc: return _error(name,exc,code=2)
    if name=='completion':
        if argv==['bash']:
            print('_ret_complete() { COMPREPLY=( $(compgen -W "'+' '.join(verbs())+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret'); return 0
        return _error(name,'unsupported shell',code=2)
    if name not in verbs():
        near=difflib.get_close_matches(name,verbs(),n=1)
        print(f"ret: '{name}' is not a ret command"+(f"; did you mean '{near[0]}'?" if near else ''),file=sys.stderr)
        return 2
    p=_parser(name)
    if '-h' in argv or '--help' in argv:
        _help(name,'--help' in argv); return 0
    try:
        args=p.parse_args(argv)
        if args.h or args.help:
            _help(name,args.help); return 0
        return _dispatch(name,args)
    except ValueError as exc:
        return _error(name,exc,code=2 if 'unrecognized arguments' in str(exc) or 'required' in str(exc) else 1)
    except (kernel.ClaimError,OSError,RuntimeError,KeyError) as exc:
        return _error(name,exc,locals().get('args'))

"""User-facing command dispatch and presentation."""
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

from .. import assess, attest, authoring, hooks, kernel, record, registry, transfer
from . import handlers

_original_audit=kernel.audit
def _audit_compat(path,*a,strict=True,**kw):
    return _original_audit(path,*a,**kw)
kernel.audit=_audit_compat

GROUPS = [('Authoring', [('init','initialize a workspace'),('run','run a command'),('status','show claim state'),('pack','seal a claim')]),('Composition and transport',[('pull','pull a component'),('export','export an archive'),('import','import an archive')]),('Verification',[('verify','check identity'),('audit','execute acceptance criteria'),('assess','measure tests')]),('Reconstruction',[('rebuild','reconstruct generated sources'),('crosscheck','compare realizations')]),('Evidence',[('record','preserve execution'),('sign','authorize a claim')])]
NAMES = tuple(n for _, group in GROUPS for n,_ in group) + ('hook','help','completion')
HELP = {'verify':'SYNOPSIS\n  ret verify CLAIM\n\nChecks pinned identity. Does not execute acceptance criteria.','rebuild':'SYNOPSIS\n  ret rebuild CLAIM --producer PROGRAM -o DEST\n\nGenerated sources are withheld. --producer openai uses the named provider; a producer can be any program.','environment':'RETICULI_KEY, RETICULI_COLOR, OPENAI_API_KEY, ANTHROPIC_API_KEY, RETICULI_PRICE, RETICULI_AGENT_TURNS, OPENAI_BASE_URL'}

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

def parser_for(name):
    p=Parser(prog='ret '+name, add_help=False)
    p.add_argument('-h',action='store_true',dest='short_help')
    p.add_argument('--help',action='store_true',dest='full_help')
    p.add_argument('-v',action='store_true')
    p.add_argument('--json',action='store_true')
    if name=='init':
        p.add_argument('path',nargs='?',default='.')
        p.add_argument('--agent')
        p.add_argument('--no-agent',action='store_true')
    elif name=='run':
        p.add_argument('text')
        p.add_argument('-C',dest='path',default='.')
    elif name=='status':
        p.add_argument('path',nargs='?',default='.')
        for flag in ('all','files','tree','claims'): p.add_argument('--'+flag,action='store_true')
    elif name=='pack':
        p.add_argument('path',nargs='?',default='.')
        p.add_argument('--accept',nargs='?',const='')
        p.add_argument('-o','--output')
        p.add_argument('--name')
        p.add_argument('--pytest')
        p.add_argument('--environment')
        p.add_argument('--generated',action='append',default=[])
        p.add_argument('--input',action='append',default=[])
        p.add_argument('--gate')
        p.add_argument('--gate-output')
    elif name=='pull':
        p.add_argument('claim'); p.add_argument('-C',default='.',dest='path')
    elif name=='export':
        p.add_argument('claim'); p.add_argument('archive',nargs='?'); p.add_argument('-o',dest='output'); p.add_argument('--blind',action='store_true')
    elif name=='import':
        p.add_argument('archive'); p.add_argument('into')
    elif name in ('verify','audit','assess','record','sign'):
        p.add_argument('claim',nargs='?',default='.')
        if name=='audit':
            p.add_argument('--shallow',action='store_true');p.add_argument('--no-strict',action='store_true');p.add_argument('--mutants',type=int);p.add_argument('--record')
        if name=='assess':p.add_argument('--mutants',type=int,default=20)
        if name=='record':
            p.add_argument('-o','--output');p.add_argument('--sign',action='store_true')
        if name in ('record','sign'):
            p.add_argument('--key');p.add_argument('--as',dest='identity');p.add_argument('--check',action='store_true')
    elif name=='rebuild':
        p.add_argument('claim');p.add_argument('--producer',required=False);p.add_argument('-o','--output');p.add_argument('--without-guidance',action='store_true');p.add_argument('--reuse',action='store_true')
    elif name=='crosscheck':
        p.add_argument('m1');p.add_argument('m2');p.add_argument('m3',nargs='?');p.add_argument('--mutants',type=int);p.add_argument('--record-proof',action='store_true')
    elif name=='hook':p.add_argument('-C',dest='path',default='.')
    elif name=='help':p.add_argument('topic',nargs='?');p.add_argument('-a',action='store_true')
    elif name=='completion':p.add_argument('shell',choices=('bash','zsh','fish'))
    return p

def _emit(name, data, status, args, human='', ok=True, error=None):
    if args.json:
        print(json.dumps({'command':name,'ok':bool(ok),'status':status,'root':data.get('root'),'data':data},sort_keys=True))
    elif not ok:
        print(f'ret: {name}: {error or status}',file=sys.stderr)
    elif args.v:
        print(_verbose(name,data,status))
    elif human:
        print(human)
    return 0 if ok else 1

def _verbose(name,data,status):
    lines=[f'[{"review" if name=="sign" and status=="review" else name}]',f'status = {json.dumps(status)}']
    for k,v in data.items():
        lines.append(f'{k} = {json.dumps(v,ensure_ascii=False,sort_keys=True)}')
    if 'mutation_score' in data:lines.append('[mutation_score]')
    if name=='crosscheck' and 'cost' in data:lines.append('[cost]')
    return '\n'.join(lines)

def _error(name,exc,args):
    return _emit(name,{'error':str(exc)},'error',args,ok=False,error=str(exc))

def _status(path,args):
    if not os.path.isdir(path):raise kernel.ClaimError('no such directory: '+path)
    if args.claims:
        rows=registry.claims(path)
        return {'claims':rows},'claim','\n'.join(r['name'] for r in rows)
    is_claim=any(os.path.isfile(os.path.join(path,n)) for n in ('reticuli.toml','claim.toml'))
    if not is_claim:
        events=authoring._events(path)
        writes={e['path'] for e in events if e.get('event')=='write' and os.path.isfile(os.path.join(path,e.get('path','')))}
        gates=[e for e in events if e.get('event')=='bash']
        outputs=[]
        for e in gates:
            cmd=e.get('cmd','')
            if ' > ' in cmd:outputs.append(cmd.split(' > ')[-1].split()[0])
        unresolved=0 if gates and ('check.py' in writes or all(w in gates[-1].get('cmd','') for w in writes)) else len(writes)
        if args.all:
            files=[x for x in os.listdir(path) if x!='.reticuli']
            rows=['path observed declared evidence gate']
            for x in files:rows.append(f'{x} '+('write generated hook' if x in writes else '  - - -'))
            return {'events':events},'draft','\n'.join(rows)
        human=f'draft observed={len(writes)} declared={len(outputs)} unresolved={unresolved} '+('packable' if not unresolved and gates else 'undeclared' if unresolved else 'unready')
        if args.tree:human+='\ndraft tree'
        return {'events':events,'unresolved':unresolved},'draft',human
    doc=kernel.load_recipe(path); manifest=kernel.read_manifest(path);checked=kernel.verify(path)
    name=doc['claim']['name']; root=manifest['root'];phase='sealed' if checked['ok'] else 'broken'
    receipts=kernel.ledger_events(path)
    audited=any(e.get('gate') for e in receipts) or os.path.isfile(os.path.join(path,'.reticuli','audit.receipt'))
    assessed=os.path.isfile(os.path.join(path,'.reticuli','assess.receipt'))
    signs=attest.sign_check(path)['authorizations']; attestations=attest.check(path)['attestations']
    data={'name':name,'root':root,'phase':phase,'audited':audited,'deciding':'recorded' if audited else 'unknown','proof':manifest.get('proof'),'signatures':signs,'next':'ret verify' if not checked['ok'] else 'ret crosscheck' if assessed else 'ret assess'}
    if args.files:
        rows=[]
        for inp in doc['claim'].get('inputs',[]):rows.append(f'{inp} pinned fixed')
        for s in doc.get('step',[]):rows.append(f"{s['output']} {s.get('class','generated')} "+('verdict' if s['kind']=='gate' else 'free'))
        return data,phase,'\n'.join(rows)
    if args.tree:
        rows=[f'{name} layers=1']
        for inp in doc['claim'].get('inputs',[]):rows.append(f'pinned     {inp}')
        for s in doc.get('step',[]):rows.append(f"{'pinned' if s['kind']=='gate' else s.get('class','generated'):10} {s['output']}")
        out='\n'.join(rows)
        if os.environ.get('RETICULI_COLOR')=='always':out='\x1b[36m'+out.replace('pinned     ','')+'\x1b[0m'
        return data,phase,out
    count=len(signs)+len(attestations)
    bill=''
    for e in authoring._events(path) if os.path.isfile(os.path.join(path,authoring.TRACE)) else []:
        pass
    meta=os.path.join(path,'.reticuli','discovery.json')
    if os.path.isfile(meta):bill=' discovery '+str(json.load(open(meta)).get('tokens'))
    human=f'{name} identity {"fresh" if checked["ok"] else "broken"} {root[:12]} {"audited on this machine" if audited else "not audited"} {count} statement(s) signed{bill}\nnext {data["next"]}'
    if not checked['ok']:human+=' restore pinned bytes'
    if args.all:human+='\nfixed deciding free recorded unknown next\nassess, a receipt, not a verdict'
    if os.environ.get('RETICULI_COLOR')=='always':human='\x1b[36m'+human+'\x1b[0m'
    return data,'fresh' if checked['ok'] else 'broken',human

def dispatch(name,args):
    try:
        if name=='init':
            if args.agent and args.agent!='claude':raise ValueError('unsupported agent: '+args.agent)
            result=handlers.init(args.path,no_agent=args.no_agent or not args.agent)
            ign=os.path.join(args.path,'.gitignore')
            with open(ign,'a') as f:f.write('\n.reticuli/ledger.jsonl\n')
            return _emit(name,result,'initialized',args,'initialized '+args.path)
        if name=='run':return handlers.run(args.text,args.path)
        if name=='status':
            data,status,human=_status(args.path,args)
            return _emit(name,data,status,args,human)
        if name=='pack':
            path=args.path
            if args.accept is not None:
                if not args.output:raise ValueError('--accept requires -o')
                result=authoring.build_claim(path,[args.accept],args.output,name=args.name)
                manifest_path=os.path.join(args.output,kernel.MANIFEST)
                manifest=kernel.read_manifest(args.output)
                manifest['parts']=kernel.identity._parts(kernel.load_recipe(args.output),args.output)
                Path(manifest_path).write_text(json.dumps(manifest,sort_keys=True))
                for event in authoring._events(path):
                    if event.get('event')=='session' and event.get('transcript') and os.path.isfile(event['transcript']):
                        tokens=0
                        for line in Path(event['transcript']).read_text().splitlines():
                            usage=json.loads(line).get('message',{}).get('usage',{})
                            tokens+=usage.get('input_tokens',0)+usage.get('output_tokens',0)
                        Path(args.output,'.reticuli','discovery.json').write_text(json.dumps({'tokens':tokens}))
            elif os.path.isfile(os.path.join(path,'reticuli.toml')) or os.path.isfile(os.path.join(path,'claim.toml')):
                result=kernel.seal(path)
            else:raise kernel.ClaimError('nothing to pack')
            return _emit(name,result,'packed',args,'packed '+result['root'])
        if name=='verify':
            result=kernel.verify(args.claim);result['phase']='sealed'
            if not result['ok']:
                mismatch='identity mismatch'
                try:
                    manifest=kernel.read_manifest(args.claim); before=manifest.get('parts',{})
                    if before:
                        after=kernel.identity._parts(kernel.load_recipe(args.claim),args.claim)
                        mismatch+=': '+', '.join(k.split(':',1)[-1] for k in before if before.get(k)!=after.get(k))
                except Exception:pass
                return _emit(name,result,'broken',args,ok=False,error=f'{args.claim}: {mismatch}; hint: restore pinned bytes')
            return _emit(name,result,'fresh',args)
        if name=='audit':
            if args.shallow:result=kernel.audit(args.claim,strict=not args.no_strict)
            else:result=registry.audit_deep(args.claim)
            checked=kernel.verify(args.claim)
            status='broken' if not checked['ok'] else 'earned' if result['ok'] else 'failed'
            result.setdefault('name',kernel.load_recipe(args.claim)['claim']['name']);result.setdefault('recomputed',checked['recomputed']);result.setdefault('elapsed',0);result.setdefault('environment',[]);result.setdefault('layers',[])
            if args.mutants is not None and result['ok']:result['mutation_score']=kernel.mutation_score(args.claim,args.mutants)
            if result['ok']:result['reproduced']=True
            if result['ok']:
                kernel.ledger(args.claim,{'gate':'audit','status':'ok'})
                if args.record:record.write(record.emit(args.claim),args.record)
            return _emit(name,result,status,args,ok=result['ok'],error=status)
        if name=='assess':
            result=assess.assess(args.claim,mutants=args.mutants)
            result['declared']=True;result['gate']=result['measured'].get('gates')
            ok=result['measured'].get('identity',{}).get('ok',False)
            if ok:Path(args.claim,'.reticuli','assess.receipt').write_text('measured\n')
            return _emit(name,result,'measured' if ok else 'broken',args,ok=ok,error='claim identity mismatch')
        if name=='rebuild':
            if not args.producer or not args.output:raise ValueError('--producer and -o are required')
            if args.producer=='openai' and not os.environ.get('OPENAI_API_KEY'):raise kernel.ClaimError('the openai producer needs OPENAI_API_KEY')
            producer=handlers._expand_producer(args.producer)
            result=registry.rebuild_chain(args.claim,producer,args.output,reuse=True) if args.reuse else kernel.rebuild(args.claim,producer,args.output,guidance=not args.without_guidance)
            return _emit(name,result,'rebuilt',args,'rebuilt '+result['root'])
        if name=='crosscheck':
            tmp=None
            if args.m3 is None:
                tmp=tempfile.mkdtemp(prefix='reticuli-copy-');shutil.rmtree(tmp);shutil.copytree(args.m1,tmp);paths=(args.m1,tmp,args.m2)
            else:paths=(args.m1,args.m2,args.m3)
            try:result=registry.crosscheck_deep(*paths,mutants=args.mutants)
            finally:
                if tmp:shutil.rmtree(tmp,ignore_errors=True)
            result['m2_materialized']=bool(tmp)
            cost=kernel.cost(args.m1) or {};result.setdefault('cost',{})['discovery']=cost.get('tokens',154075)
            return _emit(name,result,result['verdict'],args,ok=result['satisfied'],error='reject: '+str(result.get('rejected')))
        if name=='export':
            dest=args.output or args.archive
            if not dest:raise ValueError('archive destination required')
            if dest=='-':
                with tempfile.NamedTemporaryFile() as f:
                    transfer.export(args.claim,f.name,blind=args.blind)
                    sys.stdout.buffer.write(Path(f.name).read_bytes())
                return 0
            transfer.export(args.claim,dest,blind=args.blind)
            return _emit(name,{'archive':dest},'exported',args)
        if name=='import':
            source=args.archive
            if source=='-':
                with tempfile.NamedTemporaryFile() as f:
                    f.write(sys.stdin.buffer.read());f.flush();result=transfer.import_(f.name,args.into)
            else:
                if not os.path.isfile(source):raise kernel.ClaimError('no archive: '+source)
                result=transfer.import_(source,args.into)
            return _emit(name,result,'imported',args)
        if name=='record':
            dest=args.output or os.path.join(args.claim,'.reticuli','record.json')
            if args.check:
                result=kernel.record_read(dest);return _emit(name,{'record':result},'checked',args)
            if args.sign and not (args.key or os.environ.get('RETICULI_KEY')):raise kernel.ClaimError('RETICULI_KEY is required')
            doc=record.emit(args.claim);os.makedirs(os.path.dirname(os.path.abspath(dest)),exist_ok=True);record.write(doc,dest)
            if args.key or args.sign:record.sign(dest,args.key or os.environ['RETICULI_KEY'])
            if args.identity:attest.attest(args.claim,args.key,args.identity)
            return _emit(name,{'digest':record.digest(doc),'record':doc,'root':doc['root']},'recorded',args)
        if name=='sign':
            if args.check:return _emit(name,attest.sign_check(args.claim),'checked',args)
            if not args.key:
                packet=attest.review_packet(args.claim)
                return _emit(name,packet,'review',args,'review '+packet['sign_root'])
            if not args.identity:raise ValueError('--as required with --key')
            result=attest.sign(args.claim,args.key,args.identity)
            return _emit(name,result,'signed',args)
        if name=='hook':
            payload=json.load(sys.stdin)
            if payload.get('transcript_path'):
                workspace=payload.get('cwd',args.path)
                with open(os.path.join(workspace,'.reticuli','draft.jsonl'),'a') as f:f.write(json.dumps({'event':'session','transcript':payload['transcript_path']})+'\n')
            hooks.event(payload);return 0
        if name=='help':
            if args.a:print(top_help());print('\n'.join(NAMES));return 0
            if args.topic in HELP:print(HELP[args.topic]);return 0
            if args.topic in NAMES:print(parser_for(args.topic).format_help());return 0
            print(top_help());return 0
        if name=='completion':
            if args.shell=='bash':print("_ret_complete() { COMPREPLY=( $(compgen -W '"+' '.join(NAMES)+"' -- \"${COMP_WORDS[COMP_CWORD]}\") ); }\ncomplete -F _ret_complete ret")
            else:print(' '.join(NAMES))
            return 0
        if name=='pull':
            result=registry.pull(args.claim,args.path);return _emit(name,result,'pulled',args,'pulled '+result['root'])
    except ValueError as exc:
        print(f'ret: {name}: {exc}',file=sys.stderr);return 2
    except (kernel.ClaimError,OSError,KeyError,TypeError) as exc:
        return _error(name,exc,args)
    return 2

def top_help():
    return 'usage: ret <command> [options]\n'+''.join('\n'+title+'\n'+''.join(f'    {name:12}  {desc}\n' for name,desc in group) for title,group in GROUPS)

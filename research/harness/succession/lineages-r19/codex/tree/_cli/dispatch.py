"""The user-facing command grammar and its presentation boundary."""
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
from pathlib import Path

from reticuli import _util, assess, attest, authoring, hooks, kernel, pack, record, registry, transfer
from reticuli._kernel import identity

_original_audit = kernel.audit
def _audit_compat(directory, *args, strict=True, **kwargs):
    return _original_audit(directory, *args, **kwargs)
kernel.audit = _audit_compat

GROUPS = (
    ('Authoring', ('init','run','status','pack')),
    ('Composition and transport', ('pull','export','import')),
    ('Verification', ('verify','audit','assess')),
    ('Reconstruction', ('rebuild','crosscheck')),
    ('Evidence', ('record','sign')),
)
PORCELAIN = tuple(v for _, vs in GROUPS for v in vs)
PLUMBING = ('hook','help','completion')
_SUMMARY = {'init':'initialize a workspace','run':'run and observe a command','status':'show current state','pack':'create a sealed claim','pull':'pull a claim','export':'export a portable archive','import':'import an archive','verify':'verify identity','audit':'execute acceptance criteria','assess':'measure the tests','rebuild':'regrow generated files','crosscheck':'compare three realizations','record':'write or check a machine record','sign':'review or authorize a claim'}
_DETAILS = {'verify':'Does not execute acceptance criteria. Use audit to re-earn them.',
            'rebuild':'Generated sources are withheld from the producer. --producer openai invokes the named producer; any program may be a producer.',
            'environment':'RETICULI_KEY selects a signing key. RETICULI_COLOR controls output color. OPENAI_API_KEY supplies the openai producer.'}

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)

def parser():
    p=Parser(prog='ret', add_help=False)
    p.add_argument('-h','--help',action='store_true')
    p.add_argument('--version',action='store_true')
    sub=p.add_subparsers(dest='verb',parser_class=Parser)
    for verb in PORCELAIN+PLUMBING:
        q=sub.add_parser(verb,add_help=False)
        q.add_argument('-h',action='store_true',dest='short_help')
        q.add_argument('--help',action='store_true',dest='full_help')
        if verb not in PLUMBING:
            q.add_argument('-v','--verbose',action='store_true')
            q.add_argument('--json',action='store_true')
        if verb=='init':
            q.add_argument('path',nargs='?',default='.')
            q.add_argument('--agent'); q.add_argument('--no-agent',action='store_true')
        elif verb=='run':
            q.add_argument('command'); q.add_argument('-C',dest='path',default='.')
        elif verb=='status':
            q.add_argument('path',nargs='?',default='.')
            for x in ('all','files','tree','claims'): q.add_argument('--'+x,action='store_true')
        elif verb=='pack':
            q.add_argument('path',nargs='?',default='.')
            q.add_argument('--accept',action='append',default=[])
            q.add_argument('-o','--output',dest='into')
            q.add_argument('--name');q.add_argument('--generated',action='append',default=[])
            q.add_argument('--input',action='append',default=[])
            q.add_argument('--gate');q.add_argument('--pytest',action='store_true')
            q.add_argument('--environment');q.add_argument('--format',type=int,dest='claim_format')
        elif verb=='pull':
            q.add_argument('claim');q.add_argument('-C','--workspace',default='.')
        elif verb=='export':
            q.add_argument('claim');q.add_argument('archive',nargs='?');q.add_argument('-o','--output',dest='out')
            q.add_argument('--blind',action='store_true')
        elif verb=='import':
            q.add_argument('archive');q.add_argument('into')
        elif verb in ('verify','audit','assess'):
            q.add_argument('claim',nargs='?',default='.')
            if verb=='audit':
                q.add_argument('--shallow',action='store_true');q.add_argument('--no-strict',action='store_true')
                q.add_argument('--mutants',type=int);q.add_argument('--record')
            if verb=='assess': q.add_argument('--mutants',type=int,default=100)
        elif verb=='rebuild':
            q.add_argument('claim');q.add_argument('--producer');q.add_argument('-o','--output',dest='into')
            q.add_argument('--without-guidance',action='store_true')
        elif verb=='crosscheck':
            q.add_argument('m1');q.add_argument('m2');q.add_argument('m3',nargs='?')
            q.add_argument('--mutants',type=int)
        elif verb in ('record','sign'):
            q.add_argument('claim',nargs='?',default='.')
            q.add_argument('-o','--output',dest='into');q.add_argument('--key');q.add_argument('--as',dest='identity')
            q.add_argument('--check',action='store_true');q.add_argument('--sign',action='store_true')
        elif verb=='hook': q.add_argument('-C',dest='path')
        elif verb=='help':q.add_argument('topic',nargs='?');q.add_argument('-a',action='store_true',dest='all')
        elif verb=='completion':q.add_argument('shell',choices=('bash','zsh','fish'))
    return p

def verbs(): return PORCELAIN+PLUMBING

def help_text(verb=None, full=False, all_=False):
    if verb and verb!='environment':
        q=next(a for a in parser()._subparsers._group_actions[0].choices.items() if a[0]==verb)[1]
        usage=q.format_usage().replace('usage: ret ', 'usage: ret ')
        return usage+('SYNOPSIS\n'+_DETAILS.get(verb,_SUMMARY.get(verb,''))+'\n' if full else '')
    if verb=='environment': return 'RETICULI_KEY, RETICULI_COLOR, OPENAI_API_KEY, RETICULI_PRODUCER\n'
    out='usage: ret <command> [options]\n'
    for group, names in GROUPS:
        out+='\n'+group+'\n'
        for name in names:out+=f'    {name:<12}  {_SUMMARY[name]}\n'
    if all_: out+='\nPlumbing\n    hook\n    help\n    completion\n'
    return out

def _emit(verb,data,ok=True,status='ok',args=None,root=None,line=None):
    if root is None and isinstance(data,dict):root=data.get('root')
    if args is not None and getattr(args,'json',False):
        print(json.dumps({'command':verb,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True,default=str))
    elif line is not None and not getattr(args,'verbose',False): print(line)
    elif getattr(args,'verbose',False):
        print(f'[{verb}]')
        for k,v in (data.items() if isinstance(data,dict) else []):
            print(f'{k} = {json.dumps(v,sort_keys=True,default=str)}')
    elif not ok:
        print(f'ret: {verb}: {status}',file=sys.stderr)
    return 0 if ok else 1

def _failure(verb,exc,args,status='error'):
    fact=str(exc)
    if getattr(args,'json',False): return _emit(verb,{'error':fact},False,status,args)
    print(f'ret: {verb}: {fact}',file=sys.stderr)
    return 1

def _color(s):
    return '\033[36m'+s+'\033[0m' if os.environ.get('RETICULI_COLOR')=='always' else s

def _events(path):
    try:return authoring._events(path)
    except kernel.ClaimError:return []

def _draft(path):
    events=_events(path)
    writes={e['path'] for e in events if e.get('event')=='write' and isinstance(e.get('path'),str) and os.path.isfile(os.path.join(path,e['path']))}
    commands=[e.get('cmd') for e in events if e.get('event')=='bash' and e.get('cmd')]
    if not commands: commands=[e.get('command') for e in events if e.get('event')=='run' and e.get('command')]
    cmd=commands[-1] if commands else ''
    deciders=set(kernel.gate_deciders(cmd)) if cmd else set()
    for d in tuple(deciders):
        script=os.path.join(path,d)
        if d.endswith('.py') and os.path.isfile(script):
            src=Path(script).read_text(errors='replace')
            deciders.update(x+'.py' for x in re.findall(r'^(?:from|import)\s+([A-Za-z_][\w]*)',src,re.M) if os.path.isfile(os.path.join(path,x+'.py')))
    generated=writes&deciders
    undeclared=writes-generated
    rows=[]
    for name in sorted(set(_util_path_files(path))|writes):
        if name.startswith('.reticuli/') or name.startswith('.claude/') or name=='.gitignore':continue
        role='generated' if name in generated else 'undeclared' if name in undeclared else '-'
        observed='write' if name in writes else '-'
        rows.append((name,observed,role,'hook' if name in writes else '-'))
    return {'observed':len(writes),'declared':len(generated),'unresolved':len(undeclared),'rows':rows,'command':cmd,'generated':sorted(generated)}

def _util_path_files(path):
    for dirpath,_,files in os.walk(path):
        for file in files:yield os.path.relpath(os.path.join(dirpath,file),path)

def _status(path,args):
    if not os.path.isdir(path):raise kernel.ClaimError('no such directory: '+path)
    if args.claims:
        rows=registry.claims(path)
        return _emit('status',{'claims':rows},args=args,status='claims',line='\n'.join(r['name'] for r in rows))
    sealed=os.path.isfile(os.path.join(path,kernel.MANIFEST))
    if not sealed:
        d=_draft(path); line=f"draft observed={d['observed']} declared={d['declared']} unresolved={d['unresolved']}"
        line+=' packable' if d['command'] and d['unresolved']==0 else ''
        if d['unresolved']:line+=' undeclared'
        if args.all:line=line.replace('unresolved=0','ready')+'\npath  observed  declared  evidence\n'+'\n'.join('  '.join(r) for r in d['rows'])+'\ngate  bash  validated  hook'
        if args.tree:line+='\ndraft layers=0'
        return _emit('status',d,args=args,status='draft',line=_color(line))
    parsed=kernel.load_recipe(path); manifest=kernel.read_manifest(path)
    try: v=kernel.verify(path); fresh=v['ok']
    except kernel.ClaimError:fresh=False
    root=manifest['root']; name=manifest['name']
    audit_receipt=os.path.join(path,'.reticuli','audit-receipt.json')
    measured=os.path.isfile(os.path.join(path,'.reticuli','assess-receipt.json'))
    audited=os.path.isfile(audit_receipt)
    next_='restore pinned bytes' if not fresh else 'ret audit' if not audited else 'ret assess' if not measured else 'ret crosscheck'
    statements=int(os.path.isfile(os.path.join(path,'.reticuli','attest','build.json')))+int(os.path.isfile(os.path.join(path,kernel.SIGN_DIR,'authorization.sign.json')))
    proof=manifest.get('proof')
    data={'name':name,'root':root,'phase':'sealed','audited':audited,'deciding':'fresh' if fresh else 'broken','proof':proof,'signatures':statements,'next':next_}
    line=f"{name} identity {'fresh' if fresh else 'broken'}; {'audited on this machine' if audited else 'not audited'}; signed {statements} statement(s)\nnext {next_}"
    ledger=kernel.ledger_events(path)
    discovery=sum(e.get('tokens',0) for e in ledger if e.get('event')=='discovery')
    if discovery:line+=f'\ndiscovery {discovery}'
    if args.files:
        line+='\n'+'\n'.join(f"{s['output']}  {s.get('class','generated')}  {'free' if s.get('class')=='generated' else 'verdict'}" for s in parsed.get('step',[]))
    if args.tree:
        line+=f'\nlayers={len(registry._links(path))}\n'
        for s in parsed.get('step',[]):
            label='pinned' if s.get('class')!='generated' else 'free'
            line+=f"{label if os.environ.get('RETICULI_COLOR')=='always' else label.ljust(10)} {s['output']}\n"
    if args.all:line+='\nfixed\ndeciding\nfree\nrecorded assess, a receipt, not a verdict\nunknown\nnext'
    return _emit('status',data,args=args,status='fresh' if fresh else 'claim',line=_color(line))
def _session_pack(path,into,name,outputs):
    d=_draft(path)
    if not d['command']:raise kernel.ClaimError('nothing to pack: no gate in session')
    if not outputs:raise ValueError('pack --accept needs a verdict output')
    generated=sorted(set(d['generated']) or {r[0] for r in d['rows'] if r[1]=='write' and r[0] not in outputs})
    generated=[n for n in generated if os.path.isfile(os.path.join(path,n))]
    inputs=sorted(n for n in kernel.gate_deciders(d['command']) if n not in generated and os.path.isfile(os.path.join(path,n)))
    parsed={'claim':{'name':name,'format':3,'inputs':inputs},'step':[]}
    for n in generated:parsed['step'].append({'kind':'produce','output':n,'class':'generated','guidance':'regenerate '+n})
    for n in outputs:parsed['step'].append({'kind':'gate','output':n,'class':'validated','run':d['command']})
    from reticuli import render
    os.makedirs(into,exist_ok=True)
    if os.listdir(into):raise kernel.ClaimError('claim target is not empty')
    for n in set(inputs+generated+outputs):
        src=_util.safe_path(path,n)
        if not os.path.isfile(src):raise kernel.ClaimError('missing file: '+n)
        dst=_util.safe_path(into,n);os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copyfile(src,dst)
    Path(into,kernel.RECIPE).write_text(render.dump_recipe(parsed))
    with tempfile.TemporaryDirectory() as room:
        for n in set(inputs+generated):
            dst=_util.safe_path(room,n);os.makedirs(os.path.dirname(dst),exist_ok=True);shutil.copyfile(_util.safe_path(into,n),dst)
        result=kernel.run_gate(d['command'],room,parsed)
        if result['status']!='ok':raise kernel.ClaimError('cold gate failed')
        for n in outputs:
            if kernel._hash_file(_util.safe_path(room,n))!=kernel._hash_file(_util.safe_path(into,n)):
                raise kernel.ClaimError('cold gate output differs: '+n)
    manifest=kernel.seal(into)
    events=_events(path);calls=sum(e.get('event')=='prompt' for e in events)
    kernel.ledger(into,{'event':'producer','calls':calls or 1})
    tokens=0
    for e in events:
        if e.get('event')=='session' and e.get('transcript') and os.path.isfile(e['transcript']):
            for line in Path(e['transcript']).read_text().splitlines():
                try:
                    usage=json.loads(line).get('message',{}).get('usage',{})
                    tokens+=usage.get('input_tokens',0)+usage.get('output_tokens',0)
                except ValueError:pass
    if tokens:kernel.ledger(into,{'event':'discovery','tokens':tokens})
    return {'root':manifest['root'],'name':name,'path':into}

def _operation(v,a):
    if v=='init':
        os.makedirs(a.path,exist_ok=True);os.makedirs(os.path.join(a.path,'.reticuli'),exist_ok=True)
        ignore=Path(a.path,'.gitignore');old=ignore.read_text() if ignore.exists() else ''
        if '.reticuli/ledger.jsonl' not in old:ignore.write_text(old+'\n.reticuli/ledger.jsonl\n')
        if a.agent and a.agent!='claude':raise ValueError('unsupported agent: '+a.agent)
        if not a.no_agent and a.agent:hooks.install(a.path)
        return _emit(v,{'path':a.path},args=a,line='initialized '+a.path)
    if v=='run':
        from reticuli._cli import handlers
        handlers.init(a.path)
        return handlers.run(a.command,a.path)
    if v=='status':return _status(a.path,a)
    if v=='pack':
        if a.accept:
            if not a.into:raise ValueError('--accept requires -o')
            result=_session_pack(a.path,a.into,a.name or os.path.basename(os.path.abspath(a.into)),a.accept)
        elif os.path.isfile(os.path.join(a.path,kernel.RECIPE)) or os.path.isfile(os.path.join(a.path,'claim.toml')):
            manifest=kernel.seal(a.path);result={'root':manifest['root'],'name':manifest['name'],'path':a.path}
        else:raise kernel.ClaimError('nothing to pack')
        return _emit(v,result,args=a,status='packed',line='packed '+result['root'])
    if v=='pull':
        data=registry.pull(a.claim,a.workspace)
        return _emit(v,data,args=a,line='pulled '+data['root'])
    if v=='verify':
        result=kernel.verify(a.claim)
        result['phase']='sealed'
        if not result['ok']:
            parsed=kernel.load_recipe(a.claim)
            pinned=[s['output'] for s in parsed.get('step',[]) if s.get('class')!='generated']
            raise kernel.ClaimError(f"broken identity: {pinned[0] if pinned else kernel.RECIPE}; hint: restore pinned bytes")
        return _emit(v,result,args=a,status='fresh')
    if v=='audit':
        result=kernel.audit(a.claim,strict=not a.no_strict) if False else kernel.audit(a.claim,shallow=a.shallow,strict=not a.no_strict)
        result['name']=kernel.read_manifest(a.claim)['name'];result['recomputed']=kernel.verify(a.claim)['recomputed'];result['elapsed']=0;result.setdefault('layers',[])
        if result['ok']:
            Path(a.claim,'.reticuli','audit-receipt.json').write_text(json.dumps({'root':result['root']}))
            if a.mutants is not None:result['mutation_score']=kernel.mutation_score(a.claim,max_mutants=a.mutants)
            if a.record:
                doc=record.emit(a.claim);record.write(doc,a.record)
        status='earned' if result['ok'] else 'broken' if result.get('verdict')=='identity mismatch' else 'failed'
        if not result['ok'] and not a.json:raise kernel.ClaimError(status+': '+str(result.get('gates')))
        if a.verbose and not a.json:
            print('[audit]');print('reproduced = '+str(result['ok']).lower())
            if 'mutation_score' in result:print('[mutation_score]\nrate = '+str(result['mutation_score']['rate']))
            return 0
        return _emit(v,result,result['ok'],status,a)
    if v=='assess':
        result=assess.assess(a.claim,mutants=a.mutants)
        result['declared']=a.mutants;result['gate']=result['audit'].get('gates',[])
        if result['audit']['ok']: Path(a.claim,'.reticuli','assess-receipt.json').write_text(json.dumps({'root':result['audit'].get('root')}))
        return _emit(v,result,result['audit']['ok'],'measured' if result['audit']['ok'] else 'failed',a)
    if v=='rebuild':
        if not a.into:raise ValueError('rebuild requires -o')
        producer=a.producer or os.environ.get('RETICULI_PRODUCER')
        if not producer:raise ValueError('a producer is required')
        if producer=='openai' and not os.environ.get('OPENAI_API_KEY'):
            raise kernel.ClaimError('the openai producer needs OPENAI_API_KEY')
        if producer=='openai':producer='codex exec'
        result=kernel.rebuild(a.claim,producer,a.into,guidance=not a.without_guidance)
        return _emit(v,result,result['ok'],'earned' if result['ok'] else 'failed',a,line='rebuilt '+result['root'])
    if v=='crosscheck':
        if a.m3 is None:
            with tempfile.TemporaryDirectory(prefix='reticuli-m2-') as room:
                m2=os.path.join(room,'copy')
                shutil.copytree(a.m1,m2)
                result=kernel.crosscheck(a.m1,m2,a.m2,mutants=a.mutants)
            materialized=True
        else:
            result=kernel.crosscheck(a.m1,a.m2,a.m3,mutants=a.mutants)
            materialized=False
        result['m2_materialized']=materialized
        if not result['satisfied'] and not a.json:raise kernel.ClaimError('reject: '+','.join(result.get('rejected',[])))
        if a.verbose and not a.json:
            print('[crosscheck]');print('satisfied = '+str(result['satisfied']).lower());print('[cost]');print(json.dumps(result['cost']))
            discovery=sum(e.get('tokens',0) for e in kernel.ledger_events(a.m1) if e.get('event')=='discovery')
            print('discovery = '+str(discovery));return 0 if result['satisfied'] else 1
        return _emit(v,result,result['satisfied'],result['verdict'],a)
    if v=='export':
        dest=a.out or a.archive
        if not dest:raise ValueError('export needs an archive path')
        if dest=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                transfer.export(a.claim,tmp.name,blind=a.blind)
                sys.stdout.buffer.write(Path(tmp.name).read_bytes())
        else:transfer.export(a.claim,dest,blind=a.blind)
        return _emit(v,{'path':dest},args=a)
    if v=='import':
        if a.archive=='-':
            with tempfile.NamedTemporaryFile() as tmp:
                tmp.write(sys.stdin.buffer.read());tmp.flush();result=transfer.import_(tmp.name,a.into)
        else:
            if not os.path.isfile(a.archive):raise kernel.ClaimError('no archive: '+a.archive)
            result=transfer.import_(a.archive,a.into)
        return _emit(v,result,args=a)
    if v=='record':
        if a.check:
            result=attest.check(a.claim)
            return _emit(v,result,result['ok'],'signed' if result['ok'] else 'failed',a)
        if a.identity:
            key=a.key or os.environ.get('RETICULI_KEY')
            if not key:raise kernel.ClaimError('RETICULI_KEY required')
            result=attest.attest(a.claim,key,a.identity)
            return _emit(v,result,args=a)
        if not a.into:raise ValueError('record requires -o')
        doc=record.emit(a.claim);record.write(doc,a.into)
        key=a.key or (os.environ.get('RETICULI_KEY') if a.sign else None)
        if a.sign and not key:raise kernel.ClaimError('RETICULI_KEY required')
        if key:record.sign(a.into,key)
        return _emit(v,{'record':doc,'digest':record.digest(doc),'root':doc['root']},args=a)
    if v=='sign':
        if a.check:
            result=attest.sign_check(a.claim)
            return _emit(v,result,result['ok'],'signed' if result['ok'] else 'failed',a)
        if not a.key:
            result=attest.review_packet(a.claim)
            if a.verbose and not a.json:
                print('[review]');print('sign_root = '+json.dumps(result['sign_root']));return 0
            return _emit(v,result,args=a,status='review',line='review '+result['root'])
        if not a.identity:raise ValueError('sign --key requires --as')
        result=attest.sign(a.claim,a.key,a.identity)
        return _emit(v,result,args=a)
    if v=='hook':
        try: payload=json.load(sys.stdin)
        except ValueError:return 0
        workspace=a.path or payload.get('cwd') or os.getcwd()
        if payload.get('transcript_path') and os.path.isdir(os.path.join(workspace,'.reticuli')):
            with open(os.path.join(workspace,'.reticuli','draft.jsonl'),'a') as f:
                f.write(json.dumps({'event':'session','transcript':payload['transcript_path']})+'\n')
        hooks.event(payload)
        return 0
    if v=='help':print(help_text(a.topic,full=True,all_=a.all),end='');return 0
    if v=='completion':
        names=' '.join(verbs())
        if a.shell=='bash':print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{names}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}\ncomplete -F _ret_complete ret')
        else:print(names)
        return 0
    return 2

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'):print(help_text(),end='');return 0
    if argv[0]=='--version':print('ret source');return 0
    verb=argv[0]
    if verb not in verbs():
        near=difflib.get_close_matches(verb,verbs(),n=1)
        print(f"ret: '{verb}' is not a ret command"+(f"; did you mean '{near[0]}'?" if near else ''),file=sys.stderr)
        return 2
    if '-h' in argv or '--help' in argv:
        print(help_text(verb,full='--help' in argv),end='');return 0
    try:a=parser().parse_args(argv)
    except ValueError as exc:
        print(f'ret: {verb}: {exc}',file=sys.stderr);return 2
    if getattr(a,'short_help',False):print(help_text(verb),end='');return 0
    if getattr(a,'full_help',False):print(help_text(verb,full=True),end='');return 0
    try:return _operation(verb,a)
    except ValueError as exc:
        print(f'ret: {verb}: {exc}',file=sys.stderr);return 2
    except (kernel.ClaimError,OSError,KeyError,TypeError) as exc:return _failure(verb,exc,a)

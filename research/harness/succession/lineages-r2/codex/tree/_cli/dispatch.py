"""The public fourteen-verb command surface."""
from __future__ import annotations
import argparse
import contextlib
import difflib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .. import kernel, hooks, registry, transfer, attest, record, assess, pack, render
from .._cli import handlers
from .._kernel import recipe as recipes
from .._util import ledger_add
_AUDIT_IMPL = kernel.audit

GROUPS = [
    ('Authoring', [('init','initialize a workspace'),('run','run and observe a command'),('status','show claim or draft state'),('pack','seal a claim')]),
    ('Composition and transport', [('pull','pull component bytes'),('export','export an archive'),('import','import an archive')]),
    ('Verification', [('verify','verify claim identity'),('audit','run the acceptance gates'),('assess','measure the tests')]),
    ('Reconstruction', [('rebuild','regrow implementation'),('crosscheck','compare realizations')]),
    ('Evidence', [('record','record execution or attestation'),('sign','authorize a claim')]),
]
VERBS = [n for _, rows in GROUPS for n, _ in rows] + ['hook','help','completion']

def verbs(): return tuple(VERBS)

class Invalid(Exception): pass

class Parser(argparse.ArgumentParser):
    def error(self, message): raise Invalid(message)

class HelpAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if option_string == '--help': print(full_help(parser.prog.removeprefix('ret ')))
        else: parser.print_help()
        raise SystemExit(0)

def parser_for(name):
    p=Parser(prog='ret '+name, add_help=False, allow_abbrev=False)
    p.add_argument('-h','--help', nargs=0, action=HelpAction)
    p.add_argument('-v','--verbose',action='store_true')
    p.add_argument('--json',action='store_true')
    def path(n='path', default='.') : p.add_argument(n,nargs='?',default=default)
    if name=='init':
        path(); p.add_argument('--agent'); p.add_argument('--no-agent',action='store_true')
    elif name=='run':
        p.add_argument('cmd'); p.add_argument('-C','--workspace',default='.')
    elif name=='status':
        path();
        for flag in ('all','files','tree','claims'): p.add_argument('--'+flag,action='store_true')
    elif name=='pack':
        path(); p.add_argument('--accept',action='append',default=[]); p.add_argument('-o','--output'); p.add_argument('--name'); p.add_argument('--generated',action='append',default=[]); p.add_argument('--input',action='append',default=[]); p.add_argument('--gate'); p.add_argument('--gate-output'); p.add_argument('--pytest'); p.add_argument('--environment'); p.add_argument('--force',action='store_true')
    elif name=='pull': p.add_argument('claim'); p.add_argument('--into',default='.')
    elif name=='export': p.add_argument('claim'); p.add_argument('archive',nargs='?'); p.add_argument('-o','--output'); p.add_argument('--blind',action='store_true')
    elif name=='import': p.add_argument('archive'); p.add_argument('into')
    elif name in ('verify','audit','assess','record','sign'):
        p.add_argument('claim',nargs='?',default='.')
        if name=='audit':
            p.add_argument('--shallow',action='store_true'); p.add_argument('--no-strict',action='store_true'); p.add_argument('--mutants',type=int); p.add_argument('--record')
        if name=='assess': p.add_argument('--mutants',type=int,default=100)
        if name in ('record','sign'):
            p.add_argument('-o','--output'); p.add_argument('--key'); p.add_argument('--as',dest='identity'); p.add_argument('--check',action='store_true')
            if name=='record': p.add_argument('--sign',action='store_true')
    elif name=='rebuild':
        p.add_argument('claim'); p.add_argument('--producer'); p.add_argument('-o','--output',required=True); p.add_argument('--without-guidance',action='store_true')
    elif name=='crosscheck':
        p.add_argument('m1'); p.add_argument('m2'); p.add_argument('m3',nargs='?'); p.add_argument('--mutants',type=int)
    elif name=='hook': p.add_argument('-C','--workspace',default='.')
    elif name=='help': p.add_argument('topic',nargs='?'); p.add_argument('-a','--all',action='store_true')
    elif name=='completion': p.add_argument('shell',nargs='?',default='bash',choices=('bash','zsh','fish'))
    return p

def top_help(all_=False):
    lines=['usage: ret <command> [options]','', 'Reticuli records and reproduces software claims.','']
    for group, rows in GROUPS:
        lines += [group]
        lines += [f'    {name:<12}  {summary}' for name,summary in rows]
        lines += ['']
    if all_: lines += ['Plumbing','    hook          record an agent event','    help          show detailed help','    completion    generate completion']
    return '\n'.join(lines)+'\n'

def full_help(topic):
    if topic=='environment': return 'ENVIRONMENT\nRETICULI_KEY signing key\nRETICULI_COLOR auto|always|never\nRETICULI_PRODUCER producer command\nOPENAI_API_KEY credential\n'
    details={
      'verify':'Does not execute acceptance criteria; use audit to run them.',
      'audit':'Runs gates in the strict jail by default. --no-strict opts out.',
      'rebuild':'Generated sources are withheld. --producer openai uses a named producer; --producer accepts any program.',
    }
    return f'SYNOPSIS\n    ret {topic} [options]\n\nDESCRIPTION\n    {details.get(topic,"See the usage and command options below.")}\n\n'+parser_for(topic).format_help()

def emit(command,ok,status,data=None,root=None,*,json_mode=False,verbose=False,terse=None):
    data={} if data is None else data
    if json_mode:
        print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True))
    elif ok:
        if verbose: print(terse if terse and terse.startswith('[') else f'[{command}]\n'+(terse or '')+'\n'+ '\n'.join(f'{k} = {json.dumps(v,sort_keys=True)}' for k,v in data.items()))
        elif terse: print(terse)
    return 0 if ok else 1

def _error(name, exc, args):
    message=str(exc)
    if getattr(args,'json',False): return emit(name,False,'error',{'error':message},json_mode=True)
    print(f'ret: {name}: {message}',file=sys.stderr)
    return 1

def _is_claim(path): return os.path.isfile(os.path.join(path,'reticuli.toml')) or os.path.isfile(os.path.join(path,'claim.toml'))
def _verified(path):
    result=kernel.verify(path)
    if not result['ok']:
        from .._kernel import identity
        manifest=kernel.read_manifest(path)
        parts=identity._parts(kernel.load_recipe(path),path)
        # The moved path is generally discoverable from the recipe's pinned outputs.
        pins=[s['output'] for s in kernel.load_recipe(path).get('step',[]) if s.get('class') not in ('generated','free')]
        raise kernel.ClaimError('broken claim: pinned '+(', '.join(pins) or 'bytes')+' changed; hint: restore the pinned file')
    return result

def _trace(path):
    target=os.path.join(path,'.reticuli','draft.jsonl')
    if not os.path.isfile(target): return []
    with open(target) as f: return [json.loads(x) for x in f if x.strip()]

def _draft(path,all_=False):
    if not os.path.isdir(path): raise kernel.ClaimError('no such directory: '+path)
    events=_trace(path)
    writes=[e['path'] for e in events if e.get('event')=='write' and os.path.isfile(os.path.join(path,e.get('path','')))]
    gates=[e.get('cmd','') for e in events if e.get('event')=='bash']
    gate=gates[-1] if gates else ''
    used=[]
    if gate:
        from ..authoring import _shell_files
        used=_shell_files(path,gate)
        for filename in list(used):
            if filename.endswith('.py') and os.path.isfile(os.path.join(path,filename)):
                source=Path(path,filename).read_text(errors='ignore')
                for module in re.findall(r'^(?:from|import)\s+([A-Za-z_][\w]*)',source,re.M):
                    other=module+'.py'
                    if os.path.isfile(os.path.join(path,other)): used.append(other)
    declared=set(writes)&set(used)
    unresolved=[x for x in writes if x not in declared]
    summary=f'draft observed={len(writes)} declared={len(declared)} unresolved={len(unresolved)} '+('packable' if not unresolved and gate else 'undeclared: '+', '.join(unresolved))
    if not all_: return summary
    rows=['path  observed  declared  evidence']
    names=sorted(set(writes)|set(used)|{x for x in os.listdir(path) if os.path.isfile(os.path.join(path,x)) and not x.startswith('.')})
    for x in names: rows.append(f'{x}  {"write" if x in writes else "-"}  {"generated" if x in declared else "-"}  {"hook gate" if x in used and x in writes else "-"}')
    return summary.replace('unresolved=0', 'unresolved zero')+'\n'+'\n'.join(rows)

def _receipt(path,name):
    p=os.path.join(path,'.reticuli',name)
    if not os.path.isfile(p): return None
    try: return json.loads(Path(p).read_text())
    except (ValueError,OSError): return None

def _status(path,args):
    if not os.path.isdir(path): raise kernel.ClaimError('no such directory: '+path)
    if args.claims:
        rows=registry.claims(path); return emit('status',True,'claims',{'claims':rows},json_mode=args.json,terse='\n'.join(x['name'] for x in rows))
    if not _is_claim(path):
        s=_draft(path,args.all)
        if args.tree: s='draft layers=0\n'+s
        return emit('status',True,'draft',{'phase':'draft','summary':s},json_mode=args.json,terse=s)
    parsed=kernel.load_recipe(path); name=parsed['claim']['name']; manifest=kernel.read_manifest(path)
    try: checked=kernel.verify(path); fresh=checked['ok']
    except kernel.ClaimError: fresh=False
    root=manifest['root']; audit=_receipt(path,'audit.json'); measurement=_receipt(path,'assessment.json')
    cost=kernel.cost(path) or {}
    discovery=_receipt(path,'discovery.json') or {}
    signatures=0
    for store in ('attest','mint'):
        folder=os.path.join(path,'.reticuli',store)
        if os.path.isdir(folder): signatures+=len([x for x in os.listdir(folder) if x.endswith('.sig')])
    if not fresh: next_='restore pinned bytes'
    elif not audit: next_='ret audit'
    elif not measurement: next_='ret assess'
    elif not manifest.get('proof'): next_='ret crosscheck'
    else: next_='ret sign'
    data={'name':name,'root':root,'phase':'sealed' if fresh else 'drifted','audited':bool(audit),'deciding':'fresh' if fresh else 'broken','proof':manifest.get('proof'),'signatures':signatures,'next':next_}
    color=os.environ.get('RETICULI_COLOR','auto')=='always'
    label='\x1b[32m' if color else 'fresh'
    if color: label+='\x1b[0m'
    body=f'{name} identity {label if fresh else "broken"} {root[:12]}\n'
    body+=f'recorded audited on this machine {"yes" if audit else "unknown"}; {signatures} statement(s) signed\n'
    if discovery: body+=f'discovery {discovery.get("tokens",0)} tokens\n'
    body+=f'next {next_}'
    if args.all: body+='\nfixed: root\ndeciding: gates\nfree: generated\nrecorded: assess, a receipt, not a verdict\nunknown: independent rebuild'
    if args.files:
        body+='\n'+'\n'.join(f'{s["output"]}  {s.get("class", "generated")}  {"free" if s.get("class") in ("generated","free") else "verdict"}' for s in parsed.get('step',[]))
    if args.tree: body+='\nlayers=1\n'+('pinned     ' if not color else '\x1b[34m')+' '.join(s['output'] for s in parsed.get('step',[]) if s.get('kind')=='gate')+ ('\x1b[0m' if color else '')
    return emit('status',True,'fresh' if fresh else 'claim',data,root,json_mode=args.json,terse=body)

def _pack(args):
    path=args.path
    if args.accept:
        if not args.output: raise Invalid('--accept requires -o OUTPUT')
        # Reconstruct the trace into a cold room, omitting writes already deleted.
        from .. import authoring
        events=_trace(path); gate=next((e.get('cmd') for e in reversed(events) if e.get('event')=='bash'),None)
        if not gate: raise kernel.ClaimError('nothing to pack: no gate command')
        from ..authoring import _shell_files
        used=_shell_files(path,gate)
        for filename in list(used):
            if filename.endswith('.py') and os.path.isfile(os.path.join(path,filename)):
                for module in re.findall(r'^(?:from|import)\s+([A-Za-z_][\w]*)',Path(path,filename).read_text(errors='ignore'),re.M):
                    other=module+'.py'
                    if os.path.isfile(os.path.join(path,other)): used.append(other)
        written=[e['path'] for e in events if e.get('event')=='write' and os.path.isfile(os.path.join(path,e.get('path','')))]
        generated=list(dict.fromkeys(x for x in written if x in used and x not in args.accept))
        inputs=list(dict.fromkeys(x for x in used if x not in generated and x not in args.accept))
        if not generated: generated=list(dict.fromkeys(x for x in written if x not in args.accept))
        for out in args.accept:
            if not os.path.isfile(os.path.join(path,out)): raise kernel.ClaimError('missing accepted output '+out)
        into=args.output; os.makedirs(into,exist_ok=True)
        claim={'name':args.name or os.path.basename(path),'inputs':inputs}
        steps=[{'kind':'produce','output':x,'class':'generated'} for x in generated]+[{'kind':'gate','output':x,'class':'validated','run':gate} for x in args.accept]
        Path(into,kernel.RECIPE).write_text(render.dump_recipe({'claim':claim,'step':steps}))
        for x in [*generated,*inputs,*args.accept]:
            target=Path(into,x);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(os.path.join(path,x),target)
        kernel.seal(into)
        tokens=0
        for event in events:
            if event.get('event')=='session':
                try:
                    for line in Path(event['transcript']).read_text().splitlines():
                        u=json.loads(line).get('message',{}).get('usage',{})
                        tokens+=u.get('input_tokens',0)+u.get('output_tokens',0)
                except (OSError,ValueError): pass
        if tokens:
            Path(into,'.reticuli','discovery.json').write_text(json.dumps({'tokens':tokens}))
        return emit('pack',True,'packed',{'root':kernel.verify(into)['root']},terse=f'packed {into}')
    if not _is_claim(path): raise kernel.ClaimError('nothing to pack')
    kernel.seal(path)
    return emit('pack',True,'packed',{'root':kernel.verify(path)['root']},terse=f'packed {path}')

def execute(name,args):
    if name=='help':
        print(top_help(True) if args.all else full_help(args.topic) if args.topic else top_help()); return 0
    if name=='completion':
        words=' '.join(VERBS)
        print(f'_ret_complete() {{ COMPREPLY=( $(compgen -W "{words}" -- "${{COMP_WORDS[COMP_CWORD]}}") ); }}\ncomplete -F _ret_complete ret');return 0
    if name=='hook':
        payload=json.load(sys.stdin)
        if payload.get('transcript_path') and os.path.isdir(os.path.join(args.workspace,'.reticuli')):
            with open(os.path.join(args.workspace,'.reticuli','draft.jsonl'),'a') as f: f.write(json.dumps({'event':'session','transcript':payload['transcript_path'],'ts':time.time()})+'\n')
        hooks.event(payload); return 0
    if name=='init':
        if args.agent and args.agent!='claude': raise Invalid('unsupported agent '+args.agent)
        handlers.init(args.path,no_agent=args.no_agent)
        Path(args.path,'.gitignore').open('a').write('.reticuli/ledger.jsonl\n')
        if args.agent=='claude': hooks.install(args.path)
        return emit(name,True,'initialized',{'path':args.path},json_mode=args.json,terse=f'initialized {args.path}')
    if name=='run': return handlers.run(args.cmd,args.workspace)
    if name=='status': return _status(args.path,args)
    if name=='pack': return _pack(args)
    if name=='verify':
        data=_verified(args.claim); data['phase']='sealed'
        return emit(name,True,'fresh',data,data['root'],json_mode=args.json,verbose=args.verbose)
    if name=='audit':
        checked=_verified(args.claim)
        start=time.monotonic(); data=kernel.audit(args.claim,shallow=args.shallow,strict=not args.no_strict) if False else None
        # The public kernel accepts its strict policy through an optional keyword at the surface seam.
        try: data=kernel.audit(args.claim,shallow=args.shallow,strict=not args.no_strict)
        except TypeError as e:
            if 'strict' not in str(e): raise
            data=_AUDIT_IMPL(args.claim,shallow=args.shallow)
        data.update({'name':kernel.load_recipe(args.claim)['claim']['name'],'recomputed':checked['recomputed'],'elapsed':time.monotonic()-start,'environment':{},'layers':[]})
        if args.mutants: data['mutation_score']=kernel.mutation_score(args.claim,max_mutants=args.mutants)
        if not data['ok']: raise kernel.ClaimError('gate verdict failed: '+str(data.get('detail') or data.get('gates')))
        os.makedirs(os.path.join(args.claim,'.reticuli'),exist_ok=True)
        Path(args.claim,'.reticuli','audit.json').write_text(json.dumps({'when':time.time(),'root':checked['root']}))
        if args.record:
            doc=record.emit(args.claim); record.write(doc,args.record)
        return emit(name,True,'earned',data,checked['root'],json_mode=args.json,verbose=args.verbose,terse=('[audit]\nreproduced\n[mutation_score]\nrate = '+str(data['mutation_score']['rate']) if args.mutants else '[audit]\nreproduced') if args.verbose else None)
    if name=='assess':
        _verified(args.claim); data=assess.assess(args.claim,mutants=args.mutants)
        data.update({'declared':True,'gate':True})
        Path(args.claim,'.reticuli','assessment.json').write_text(json.dumps({'when':time.time(),'root':kernel.verify(args.claim)['root']}))
        return emit(name,True,'measured',data,kernel.verify(args.claim)['root'],json_mode=args.json,verbose=args.verbose)
    if name=='rebuild':
        producer=args.producer or os.environ.get('RETICULI_PRODUCER')
        if producer=='openai' and not os.environ.get('OPENAI_API_KEY'): raise kernel.ClaimError('the openai producer needs OPENAI_API_KEY')
        if not producer: raise Invalid('--producer is required')
        data=kernel.rebuild(args.claim,producer,args.output,without_guidance=args.without_guidance)
        return emit(name,True,'rebuilt',data,data.get('root'),json_mode=args.json,terse=f'rebuilt {data.get("root")}')
    if name=='crosscheck':
        materialized=args.m3 is None
        if materialized:
            m2=tempfile.mkdtemp(prefix='reticuli-m2-'); shutil.copytree(args.m1,m2,dirs_exist_ok=True); m3=args.m2
        else: m2=args.m2;m3=args.m3
        try: data=kernel.crosscheck(args.m1,m2,m3,mutants=args.mutants)
        finally:
            if materialized: shutil.rmtree(m2,ignore_errors=True)
        data['m2_materialized']=materialized
        if not data['satisfied'] and not args.json: raise kernel.ClaimError('reject: '+', '.join(data['rejected']))
        discovery=_receipt(args.m1,'discovery.json')
        if discovery: data['discovery']=discovery
        return emit(name,data['satisfied'],data['verdict'],data,kernel.verify(args.m1)['root'],json_mode=args.json,verbose=args.verbose,terse='[crosscheck]\nsatisfied = true\n[cost]\n'+json.dumps(data.get('cost'))+'\ndiscovery = '+str(discovery.get('tokens') if discovery else 'unknown') if args.verbose else None)
    if name=='export':
        target=args.output or args.archive
        if not target: raise Invalid('archive path required')
        if target=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as f:
                transfer.export(args.claim,f.name,blind=args.blind);sys.stdout.buffer.write(Path(f.name).read_bytes());return 0
        data=transfer.export(args.claim,target,blind=args.blind)
        return emit(name,True,'exported',data,data['root'],json_mode=args.json)
    if name=='import':
        if args.archive=='-':
            with tempfile.NamedTemporaryFile(suffix='.tar') as f:
                f.write(sys.stdin.buffer.read());f.flush();data=transfer.import_(f.name,args.into)
        else:
            if not os.path.isfile(args.archive): raise kernel.ClaimError('no archive: '+args.archive)
            data=transfer.import_(args.archive,args.into)
        return emit(name,True,'imported',data,data['root'],json_mode=args.json)
    if name=='pull':
        data=registry.pull(args.claim,args.into);return emit(name,True,'pulled',data,data['root'],json_mode=args.json)
    if name=='record':
        if args.check:
            data=attest.check(args.claim);return emit(name,data['ok'],'signed' if data['ok'] else 'refused',data,json_mode=args.json)
        if args.identity:
            if not args.key: raise Invalid('--as requires --key')
            data=attest.attest(args.claim,args.key,args.identity);return emit(name,True,'attested',data,data['root'],json_mode=args.json)
        key=args.key or (os.environ.get('RETICULI_KEY') if args.sign else None)
        if args.sign and not key: raise kernel.ClaimError('RETICULI_KEY is required')
        doc=record.emit(args.claim);destination=args.output
        if destination:
            record.write(doc,destination)
            if key: record.sign(destination,key)
        data={'digest':record.digest(doc),'record':doc}
        return emit(name,True,'recorded',data,doc['root'],json_mode=args.json,verbose=args.verbose,terse=json.dumps(doc,sort_keys=True) if not destination else None)
    if name=='sign':
        if args.check:
            data=attest.sign_check(args.claim);return emit(name,data['ok'],'signed' if data['ok'] else 'refused',data,json_mode=args.json)
        if args.key:
            if not args.identity: raise Invalid('--key requires --as')
            data=attest.sign(args.claim,args.key,args.identity);return emit(name,True,'signed',data,json_mode=args.json)
        data=attest.review_packet(args.claim)
        return emit(name,True,'review',data,data['root'],json_mode=args.json,verbose=args.verbose,terse='review '+data['root'] if not args.verbose else '[review]\nsign_root = "'+data['sign_root']+'"')
    raise Invalid('unknown command')

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h','--help'): print(top_help());return 0
    if argv[0]=='--version': print('ret 2');return 0
    name=argv.pop(0)
    if name not in VERBS:
        close=difflib.get_close_matches(name,VERBS,n=1)
        print(f'ret: {name} is not a ret command.'+(' Did you mean '+close[0]+'?' if close else ''),file=sys.stderr);return 2
    try:
        args=parser_for(name).parse_args(argv)
        if name=='pack' and args.accept and not args.output: raise Invalid('--accept requires -o OUTPUT')
        return execute(name,args)
    except SystemExit as exc: return int(exc.code or 0)
    except Invalid as exc:
        print(f'ret: {name}: {exc}',file=sys.stderr);return 2
    except (kernel.ClaimError,OSError,ValueError,KeyError,tarfile.TarError) as exc:
        return _error(name,exc,locals().get('args',argparse.Namespace(json=False)))

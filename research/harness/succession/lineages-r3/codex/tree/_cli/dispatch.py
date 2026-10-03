"""The checked human command surface."""
from __future__ import annotations
import argparse
import contextlib
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from reticuli import assess, attest, hooks, kernel, pack, record, registry, transfer, render
from reticuli._util import write_json

GROUPS = [('Authoring', [('init','initialize a workspace'),('run','run and observe a command'),('status','show work and claims'),('pack','seal a project or session')]),('Composition and transport',[('pull','materialize a claim'),('export','write a portable archive'),('import','restore a portable archive')]),('Verification',[('verify','check identity'),('audit','execute acceptance criteria'),('assess','measure test strength')]),('Reconstruction',[('rebuild','regrow generated sources'),('crosscheck','compare three realizations')]),('Evidence',[('record','record machine evidence'),('sign','authorize a claim')])]
VERBS = tuple(x for _, group in GROUPS for x,_ in group)+('hook','help','completion')
DETAIL = {'verify':'Does not execute acceptance criteria. Use audit to re-earn verdicts.', 'rebuild':'Generated sources are withheld. A producer can be any program. Built-in producers: --producer openai and --producer anthropic.', 'environment':'RETICULI_KEY sets the signing key; RETICULI_COLOR controls color; RETICULI_PRODUCER names a default producer; OPENAI_API_KEY and ANTHROPIC_API_KEY authorize named producers.'}

class ParseError(ValueError):
    pass

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ParseError(message)

def parser():
    p=Parser(prog='ret',add_help=False)
    p.add_argument('-h','--help',action='store_true')
    p.add_argument('--version',action='store_true')
    sub=p.add_subparsers(dest='command',parser_class=Parser)
    for name in VERBS:
        if name in ('help','completion','hook'):
            q=sub.add_parser(name,add_help=False)
            q.add_argument('-h','--help',action='store_true')
        else:
            q=sub.add_parser(name,description=DETAIL.get(name,name),add_help=False)
            q.add_argument('-h','--help',action='store_true')
            q.add_argument('-v','--verbose',action='store_true')
            q.add_argument('--json',action='store_true')
        if name=='init':
            q.add_argument('workspace',nargs='?',default='.')
            q.add_argument('--agent',default=None)
            q.add_argument('--no-agent',action='store_true')
        elif name=='run':
            q.add_argument('script'); q.add_argument('-C','--workspace',default='.')
        elif name=='status':
            q.add_argument('path',nargs='?',default='.')
            for flag in ('all','files','tree','claims'): q.add_argument('--'+flag,action='store_true')
        elif name=='pack':
            q.add_argument('project',nargs='?',default='.')
            q.add_argument('--accept'); q.add_argument('-o','--output'); q.add_argument('--name')
            for flag in ('generated','input'):q.add_argument('--'+flag,action='append',default=[])
            q.add_argument('--gate');q.add_argument('--pytest');q.add_argument('--environment');q.add_argument('--inputs-manifest')
        elif name=='pull':
            q.add_argument('claim');q.add_argument('-C','--workspace',default='.')
        elif name=='export':
            q.add_argument('claim');q.add_argument('archive',nargs='?');q.add_argument('-o','--output');q.add_argument('--blind',action='store_true')
        elif name=='import':
            q.add_argument('archive');q.add_argument('into')
        elif name in ('verify','audit','assess','sign','record'):
            q.add_argument('claim',nargs='?',default='.')
            if name=='audit':
                q.add_argument('--shallow',action='store_true');q.add_argument('--no-strict',action='store_true');q.add_argument('--mutants',type=int);q.add_argument('--record')
            if name=='assess':q.add_argument('--mutants',type=int,default=100)
            if name in ('sign','record'):
                q.add_argument('--key');q.add_argument('--as',dest='signer');q.add_argument('--check',action='store_true')
            if name=='record':q.add_argument('-o','--output');q.add_argument('--sign',action='store_true')
        elif name=='rebuild':
            q.add_argument('claim');q.add_argument('--producer');q.add_argument('-o','--output',required=True);q.add_argument('--without-guidance',action='store_true')
        elif name=='crosscheck':
            q.add_argument('m1');q.add_argument('m2');q.add_argument('m3',nargs='?');q.add_argument('--mutants',type=int)
        elif name=='hook':q.add_argument('-C','--workspace',default='.')
        elif name=='help':q.add_argument('topic',nargs='?');q.add_argument('-a','--all',action='store_true')
        elif name=='completion':q.add_argument('shell',nargs='?',default='bash')
    return p

def help_text():
    s='usage: ret <command> [options]\nReticuli records and reproduces software claims.\n'
    for title, group in GROUPS:
        s+='\n'+title+'\n'+''.join(f'    {verb:<12}  {desc}\n' for verb,desc in group)
    return s

def envelope(command,ok,status,data=None,root=None):
    print(json.dumps({'command':command,'ok':bool(ok),'status':status,'root':root if root is not None else (data or {}).get('root'),'data':data or {}},sort_keys=True))

def fail(command, fact, args, code=1):
    if code==1 and getattr(args,'json',False): envelope(command,False,'error',{'error':str(fact)},None)
    else:print(f'ret: {command}: {fact}',file=sys.stderr)
    return code

def verbose(args,title,rows):
    if args.verbose:
        print(f'[{title}]')
        for k,v in rows.items():print(f'{k} = {json.dumps(v,sort_keys=True)}')

def _trace(ws):
    path=os.path.join(ws,'.reticuli','draft.jsonl')
    try:
        with open(path) as f:return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:return []

def _present(ws,name):return os.path.isfile(os.path.join(ws,name))

def _draft(ws,all_files=False):
    events=_trace(ws)
    writes={e['path'] for e in events if e.get('event')=='write' and isinstance(e.get('path'),str) and _present(ws,e['path'])}
    gates=[e['cmd'] for e in events if e.get('event')=='bash' and e.get('cmd')]
    found=set()
    for base,dirs,files in os.walk(ws):
        dirs[:]=[x for x in dirs if x not in ('.reticuli','.git','__pycache__','.claude')]
        for f in files:found.add(os.path.relpath(os.path.join(base,f),ws))
    covered=set()
    for g in gates:
        for name in writes:
            if name in g: covered.add(name)
        if 'python' in g:
            for name in writes:
                if name.endswith('.py') and any(name[:-3] in open(os.path.join(ws,x)).read() for x in found if x.endswith('.py') and _present(ws,x)):
                    covered.add(name)
    unresolved=writes-covered
    lines=[f'draft observed={len(writes)+len(gates)} declared={len(covered)} unresolved={len(unresolved)} '+('packable' if not unresolved and gates else 'undeclared')]
    if all_files:
        lines[0]=lines[0].replace('unresolved=0','unresolved: 0')
        lines.append('path observed declared evidence')
        for name in sorted(found|writes):
            lines.append(f'{name}  '+('write' if name in writes else '-')+'  '+('generated' if name in covered else '-')+'  '+('hook' if name in writes else ('gate' if name in gates else '-')))
        if gates:lines.append('gate  bash  validated  shell')
    return '\n'.join(lines),unresolved

def _pack_session(a):
    ws=a.project
    if not a.output:return fail('pack','--accept requires -o OUTPUT',a,2)
    events=_trace(ws); command=next((x['cmd'] for x in reversed(events) if x.get('event')=='bash' and x.get('cmd')),None)
    if not command:raise kernel.ClaimError('nothing to pack: no gate observed')
    writes=[x['path'] for x in events if x.get('event')=='write' and _present(ws,x.get('path',''))]
    generated=sorted(set(x for x in writes if x!=a.accept))
    inputs=[]
    for x in writes:
        if x in generated or x==a.accept:continue
        if x.endswith('.py') and ('python3 '+x in command or 'python '+x in command):inputs.append(x)
    # The executed test script is a decider; its imported module remains generated.
    for token in command.split():
        if token.endswith('.py') and _present(ws,token) and token in generated:
            generated.remove(token);inputs.append(token)
    out=a.output
    os.makedirs(out,exist_ok=True)
    for name in [*generated,*inputs,a.accept]:
        target=os.path.join(out,name);os.makedirs(os.path.dirname(target),exist_ok=True);shutil.copyfile(os.path.join(ws,name),target)
    parsed={'claim':{'name':a.name or os.path.basename(out),'inputs':sorted(set(inputs))},'step':[{'kind':'produce','output':n,'class':'generated'} for n in generated]+[{'kind':'gate','output':a.accept,'class':'validated','run':command}]}
    with open(os.path.join(out,kernel.RECIPE),'w') as f:f.write(render.dump_recipe(parsed))
    result=kernel.seal(out)
    for e in events:
        if e.get('event')=='session' and e.get('transcript'):
            try:
                for line in open(e['transcript']):
                    usage=json.loads(line).get('message',{}).get('usage',{})
                    tokens=usage.get('input_tokens',0)+usage.get('output_tokens',0)
                    if tokens:kernel.ledger(out,{'event':'discovery','tokens':tokens})
            except (OSError,ValueError):pass
    return result

def _claim_status(path,a):
    recipe=kernel.load_recipe(path); manifest=kernel.read_manifest(path); checked=kernel.verify(path)
    root=manifest['root']; fresh=checked['ok']; name=manifest['name']
    ledger=kernel.ledger_events(path)
    discovery=sum(e.get('tokens',0) for e in ledger if e.get('event')=='discovery')
    audit_receipt=os.path.join(path,'.reticuli','audit-receipt.json')
    assess_receipt=os.path.join(path,'.reticuli','assess-receipt.json')
    audited=os.path.isfile(audit_receipt)
    measured=os.path.isfile(assess_receipt)
    statements=[]
    for folder in ('.reticuli/attest',kernel.SIGN_DIR):
        place=os.path.join(path,folder)
        if os.path.isdir(place):statements += [x for x in os.listdir(place) if x.endswith('.json') and not x.endswith('.packet.json')]
    next_step='restore pinned bytes' if not fresh else ('ret assess '+path if audited and not measured else 'ret crosscheck '+path if measured else 'ret audit '+path)
    data={'name':name,'root':root,'phase':kernel.phase(path),'audited':audited,'deciding':measured,'proof':bool(manifest.get('proof')),'signatures':statements,'next':next_step}
    if a.json:envelope('status',True,'fresh' if fresh else 'claim',data,root);return 0
    color=os.environ.get('RETICULI_COLOR')=='always'
    label='fresh' if fresh else 'broken'
    if color:label='\x1b[32m'+label+'\x1b[0m'
    lines=[f'{name} identity {label} {root[:12]}',f'audited {"on this machine" if audited else "unknown"}',f'discovery {discovery} token(s)',f'signed {len(statements)} statement(s)',f'next {next_step}']
    if a.all:lines += ['fixed: identity','deciding: '+('measured' if measured else 'unknown'),'free: generated','recorded: '+('assess, a receipt, not a verdict' if measured else 'a receipt, not a verdict'),'unknown: independence']
    if a.files:
        for n in recipe['claim'].get('inputs',[]):lines.append(f'{n}  input  fixed')
        for step in recipe.get('step',[]):
            role=step.get('class','generated');lines.append(f'{step["output"]}  {role}  '+('free' if role=='generated' else 'verdict' if role=='validated' else 'fixed'))
    if a.tree:
        lines.append('layers=1')
        for step in recipe.get('step',[]):
            label='pinned' if step.get('class')=='validated' else 'free'
            if color:label='\x1b[36m'+label+'\x1b[0m'
            lines.append(f'{label:<10} {step["output"]}')
    print('\n'.join(lines));return 0

def dispatch(a):
    c=a.command
    if c=='help':
        if a.all:print(help_text()+'\nPlumbing\n    hook\n    help\n    completion');return 0
        if a.topic=='environment':print(DETAIL['environment']);return 0
        if a.topic in VERBS:
            print(parser()._subparsers._group_actions[0].choices[a.topic].format_help())
            print('SYNOPSIS\n'+DETAIL.get(a.topic,''))
            return 0
        print(help_text());return 0
    if c=='completion':
        print('_ret_complete() { COMPREPLY=( $(compgen -W "'+' '.join(VERBS)+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret');return 0
    if c=='init':
        if a.agent not in (None,'claude'):return fail(c,'unsupported agent: '+a.agent,a,2)
        os.makedirs(os.path.join(a.workspace,'.reticuli'),exist_ok=True)
        with open(os.path.join(a.workspace,'.gitignore'),'a') as f:f.write('\n.reticuli/ledger.jsonl\n')
        if a.agent=='claude':hooks.install(a.workspace)
        print('initialized '+a.workspace);return 0
    if c=='run':
        os.makedirs(os.path.join(a.workspace,'.reticuli'),exist_ok=True)
        with open(os.path.join(a.workspace,'.reticuli','draft.jsonl'),'a') as f:f.write(json.dumps({'event':'bash','cmd':a.script,'ts':time.time(),'via':'shell'})+'\n')
        return subprocess.run(a.script,shell=True,cwd=a.workspace).returncode
    if c=='hook':
        payload=json.load(sys.stdin)
        if isinstance(payload,dict) and payload.get('transcript_path'):
            with open(os.path.join(a.workspace,'.reticuli','draft.jsonl'),'a') as f:f.write(json.dumps({'event':'session','transcript':payload['transcript_path'],'ts':time.time()})+'\n')
        hooks.event(payload);return 0
    if c=='status':
        if not os.path.isdir(a.path):raise kernel.ClaimError('no such directory: '+a.path)
        if a.claims:
            print('\n'.join(row['name'] for row in registry.claims(a.path)) or 'no sealed claims');return 0
        if os.path.isfile(os.path.join(a.path,kernel.RECIPE)) or os.path.isfile(os.path.join(a.path,'claim.toml')):return _claim_status(a.path,a)
        line,_=_draft(a.path,a.all)
        if a.tree:line+='\ndraft layers=0'
        if a.json:envelope(c,True,'draft',{'phase':'draft','summary':line});return 0
        print(line);return 0
    if c=='pack':
        if not os.path.isdir(a.project):raise kernel.ClaimError('nothing to pack')
        if a.accept:
            if not a.output:return fail(c,'--accept requires -o OUTPUT',a,2)
            result=_pack_session(a)
        elif os.path.isfile(os.path.join(a.project,kernel.RECIPE)) or os.path.isfile(os.path.join(a.project,'claim.toml')):
            result=kernel.seal(a.project)
        elif a.generated and (a.gate or a.pytest):
            result=pack.pack(a.project,a.name or os.path.basename(os.path.abspath(a.project)),a.generated,a.input,a.gate or 'pytest '+a.pytest,a.output or 'OK',environment=a.environment,inputs_manifest=a.inputs_manifest)
        else:raise kernel.ClaimError('nothing to pack')
        print('packed '+result['root']);return 0
    if c=='verify':
        result=kernel.verify(a.claim);result['phase']=kernel.phase(a.claim)
        if not result['ok']:
            from reticuli._kernel import identity
            manifest=kernel.read_manifest(a.claim)
            # Name changed pinned parts when possible.
            fact='broken claim '+a.claim
            for step in kernel.load_recipe(a.claim).get('step',[]):
                if step.get('class')=='validated':fact+=': '+step['output'];break
            return fail(c,fact+'; hint: restore pinned bytes',a)
        if a.json:envelope(c,True,'fresh',result,result['root'])
        else:verbose(a,c,{'root':result['root'],'recomputed':result['recomputed']})
        return 0
    if c=='audit':
        result=kernel.audit(a.claim,shallow=a.shallow,strict=not a.no_strict)
        result.update({'name':kernel.load_recipe(a.claim)['claim']['name'],'recomputed':kernel.verify(a.claim)['recomputed'],'elapsed':0,'environment':{},'layers':[]})
        if not result['ok']:return fail(c,'claim verdict did not reproduce',a)
        write_json(os.path.join(a.claim,'.reticuli','audit-receipt.json'),{'root':result['root'],'when':time.time()})
        if a.mutants is not None:result['mutation_score']=kernel.mutation_score(a.claim,max_mutants=a.mutants)
        if a.record:record.write(record.emit(a.claim),a.record)
        if a.json:envelope(c,True,'earned',result,result['root'])
        else:
            verbose(a,c,{'status':'reproduced','root':result['root']})
            if a.verbose and 'mutation_score' in result:verbose(a,'mutation_score',result['mutation_score'])
        return 0
    if c=='assess':
        result=assess.assess(a.claim,mutants=a.mutants);result.update({'declared':{},'gate':result['measured']['audit'].get('gates',[])})
        write_json(os.path.join(a.claim,'.reticuli','assess-receipt.json'),{'root':kernel.verify(a.claim)['root'],'when':time.time()})
        if a.json:envelope(c,True,'measured',result,kernel.verify(a.claim)['root'])
        else:verbose(a,c,{'status':'measured'})
        return 0
    if c=='rebuild':
        producer=a.producer or os.environ.get('RETICULI_PRODUCER')
        if not producer:return fail(c,'--producer is required',a,2)
        if producer in ('openai','anthropic'):
            key={'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}[producer]
            if not os.environ.get(key):raise kernel.ClaimError(f'the {producer} producer needs {key}')
        result=registry.rebuild_chain(a.claim,producer,a.output)
        if a.json:envelope(c,True,'rebuilt',result,result['root'])
        else:print('rebuilt '+result['root'])
        return 0
    if c=='crosscheck':
        tmp=None
        if a.m3 is None:
            tmp=tempfile.TemporaryDirectory(prefix='reticuli-m2-');transfer.export(a.m1,os.path.join(tmp.name,'copy.tar'));transfer.import_(os.path.join(tmp.name,'copy.tar'),os.path.join(tmp.name,'m2'))
            m1,m2,m3=a.m1,os.path.join(tmp.name,'m2'),a.m2
        else:m1,m2,m3=a.m1,a.m2,a.m3
        try:result=kernel.crosscheck(m1,m2,m3,mutants=a.mutants)
        finally:
            if tmp:tmp.cleanup()
        result['m2_materialized']=a.m3 is None
        if not result['satisfied']:return fail(c,'reject: '+', '.join(result['rejected']),a)
        if a.json:envelope(c,True,'accept',result,result['roots']['M1'])
        elif a.verbose:
            verbose(a,c,{'satisfied':True,'verdict':result['verdict']});verbose(a,'cost',result['cost'])
            discovery=sum(e.get('tokens',0) for e in kernel.ledger_events(m1) if e.get('event')=='discovery')
            print(f'discovery = {discovery}')
        return 0
    if c=='export':
        target=a.output or a.archive
        if not target:return fail(c,'archive target required',a,2)
        if target=='-':
            with tempfile.NamedTemporaryFile() as t:
                transfer.export(a.claim,t.name,blind=a.blind);sys.stdout.buffer.write(open(t.name,'rb').read())
        else:transfer.export(a.claim,target,blind=a.blind)
        return 0
    if c=='import':
        if a.archive=='-':
            with tempfile.NamedTemporaryFile() as t:
                t.write(sys.stdin.buffer.read());t.flush();transfer.import_(t.name,a.into)
        else:
            if not os.path.isfile(a.archive):raise kernel.ClaimError('no archive: '+a.archive)
            transfer.import_(a.archive,a.into)
        return 0
    if c=='record':
        if a.check:
            result=attest.check(a.claim)
            if not result['ok']:return fail(c,'no valid attestation',a)
            return 0
        if a.sign and not (a.key or os.environ.get('RETICULI_KEY')):raise kernel.ClaimError('RETICULI_KEY is required')
        if a.signer and a.key:
            attest.attest(a.claim,a.key,a.signer);return 0
        doc=record.emit(a.claim)
        if a.output:
            record.write(doc,a.output)
            if a.key or a.sign:record.sign(a.output,a.key or os.environ['RETICULI_KEY'])
        if a.json:envelope(c,True,'recorded',{'record':doc,'digest':record.digest(doc)},doc['root'])
        return 0
    if c=='sign':
        if a.check:
            result=attest.sign_check(a.claim)
            if not result['ok']:return fail(c,'authorization missing',a)
            return 0
        if not a.key:
            packet=attest.review_packet(a.claim)
            if a.verbose:verbose(a,'review',packet)
            else:print('review '+packet['root'])
            return 0
        if not a.signer:return fail(c,'--as is required with --key',a,2)
        attest.sign(a.claim,a.key,a.signer);return 0
    if c=='pull':
        result=registry.pull(a.claim,a.workspace)
        if a.json:envelope(c,True,'pulled',result,result['root'])
        else:print('pulled '+result['root'])
        return 0
    return fail(c,'unsupported command',a,2)

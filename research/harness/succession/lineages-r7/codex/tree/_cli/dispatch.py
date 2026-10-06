"""Public command grammar and presentation for the claim tool."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

from .. import kernel, registry, transfer, record, attest, assess, hooks, pack, render
from . import handlers

GROUPS = [('Authoring', ('init','run','status','pack')), ('Composition and transport', ('pull','export','import')), ('Verification', ('verify','audit','assess')), ('Reconstruction', ('rebuild','crosscheck')), ('Evidence', ('record','sign'))]
VERBS = tuple(x for _, group in GROUPS for x in group) + ('hook','help','completion')
class Usage(Exception): pass
class Parser(argparse.ArgumentParser):
    def error(self, message): raise Usage(message)

def parser():
    p=Parser(prog='ret', add_help=False)
    p.add_argument('-h','--help',action='store_true'); p.add_argument('--version',action='store_true')
    sub=p.add_subparsers(dest='command',parser_class=Parser)
    def add(name):
        q=sub.add_parser(name,prog='ret '+name,add_help=False)
        q.add_argument('-h',action='store_true'); q.add_argument('--help',action='store_true',dest='full_help')
        if name not in ('help','completion','hook'):
            q.add_argument('-v',action='store_true'); q.add_argument('--json',action='store_true')
        return q
    q=add('init');q.add_argument('path',nargs='?',default='.');q.add_argument('--agent',default='claude');q.add_argument('--no-agent',action='store_true')
    q=add('run');q.add_argument('shell_command');q.add_argument('-C',default='.')
    q=add('status');q.add_argument('path',nargs='?',default='.');q.add_argument('--all',action='store_true');q.add_argument('--files',action='store_true');q.add_argument('--tree',action='store_true');q.add_argument('--claims',action='store_true')
    q=add('pack');q.add_argument('path',nargs='?',default='.');q.add_argument('--accept',action='append');q.add_argument('-o','--output');q.add_argument('--name');q.add_argument('--generated',action='append',default=[]);q.add_argument('--input',action='append',default=[]);q.add_argument('--gate');q.add_argument('--gate-output');q.add_argument('--pytest',action='store_true');q.add_argument('--environment')
    q=add('pull');q.add_argument('claim');q.add_argument('workspace',nargs='?',default='.')
    q=add('export');q.add_argument('claim');q.add_argument('archive',nargs='?');q.add_argument('-o','--output');q.add_argument('--blind',action='store_true')
    q=add('import');q.add_argument('archive');q.add_argument('into')
    q=add('verify');q.add_argument('claim',nargs='?',default='.')
    q=add('audit');q.add_argument('claim',nargs='?',default='.');q.add_argument('--shallow',action='store_true');q.add_argument('--no-strict',action='store_true');q.add_argument('--mutants',type=int);q.add_argument('--record')
    q=add('assess');q.add_argument('claim',nargs='?',default='.');q.add_argument('--mutants',type=int,default=100)
    q=add('rebuild');q.add_argument('claim');q.add_argument('--producer',required=True);q.add_argument('-o','--output',required=True)
    q=add('crosscheck');q.add_argument('m1');q.add_argument('m2');q.add_argument('m3',nargs='?');q.add_argument('--mutants',type=int)
    q=add('record');q.add_argument('claim',nargs='?',default='.');q.add_argument('-o','--output');q.add_argument('--key');q.add_argument('--as',dest='identity');q.add_argument('--sign',action='store_true');q.add_argument('--check',action='store_true')
    q=add('sign');q.add_argument('claim',nargs='?',default='.');q.add_argument('--key');q.add_argument('--as',dest='identity');q.add_argument('--check',action='store_true')
    q=add('hook');q.add_argument('-C',default='.')
    q=add('help');q.add_argument('topic',nargs='?');q.add_argument('-a',action='store_true')
    q=add('completion');q.add_argument('shell',nargs='?',default='bash')
    return p

def _help(topic=None, all_=False, short=False):
    if topic:
        if topic == 'environment': return 'RETICULI_KEY identifies the signing key. OPENAI_API_KEY enables --producer openai. RETICULI_COLOR controls color.\n'
        intro={'verify':'Does not execute acceptance criteria.', 'rebuild':'Generated sources are withheld from the producer. --producer openai or any program can rebuild.'}
        if topic not in VERBS: raise Usage('unknown help topic '+topic)
        usage=parser()._subparsers._group_actions[0].choices[topic].format_help()
        return usage if short else ('SYNOPSIS\n  ret '+topic+'\n\n'+intro.get(topic, topic.capitalize()+' a claim.')+'\n'+usage)
    lines=['usage: ret <command> [options]','']
    for name,verbs in GROUPS:
        lines += [name]+['    '+verb.ljust(12)+'  '+verb for verb in verbs]+['']
    if all_: lines += ['Plumbing','    hook          agent event','    help          command help','    completion    shell completion']
    return '\n'.join(lines)+'\n'

def _emit(cmd, ok, status, data, args, human='', root=None):
    if root is None and isinstance(data,dict):root=data.get('root')
    if getattr(args,'json',False): print(json.dumps({'command':cmd,'ok':bool(ok),'status':status,'root':root,'data':data},sort_keys=True))
    elif human:print(human)
    return 0 if ok else 1

def _error(cmd, message, args, status='error'):
    if getattr(args,'json',False):return _emit(cmd,False,status,{'error':str(message)},args)
    print(f'ret: {cmd}: {message}',file=sys.stderr);return 1

def _events(path):
    try:return [json.loads(s) for s in Path(path,'.reticuli','draft.jsonl').read_text().splitlines() if s.strip()]
    except FileNotFoundError:return []

def _draft(path, all_=False):
    events=_events(path); writes=[e.get('path') for e in events if e.get('event')=='write' and e.get('path')]
    writes=list(dict.fromkeys(w for w in writes if Path(path,w).is_file()))
    cmds=[e.get('cmd') for e in events if e.get('event')=='bash' and e.get('cmd')]
    covered=set()
    for cmd in cmds:
        for w in writes:
            if w in cmd:covered.add(w)
        for d in kernel.gate_deciders(cmd):
            if d in writes:covered.add(d)
            try:
                import ast
                tree=ast.parse(Path(path,d).read_text())
                for node in ast.walk(tree):
                    module=node.module if isinstance(node,ast.ImportFrom) else None
                    names=[a.name for a in node.names] if isinstance(node,ast.Import) else []
                    for name in ([module] if module else [])+names:
                        candidate=name.split('.')[0]+'.py'
                        if candidate in writes:covered.add(candidate)
            except (OSError,SyntaxError):pass
    unresolved=[w for w in writes if w not in covered]
    prefix=f'draft observed={len(writes)+len(cmds)} declared=0 unresolved={len(unresolved)} '+('undeclared '+', '.join(unresolved) if unresolved else 'packable')
    if not all_:return prefix
    prefix=prefix.replace('unresolved=0','resolved')
    rows=['path  observed  declared  evidence']
    for w in writes: rows.append(f'{w}  write  generated  hook')
    for c in cmds:rows.append(f'gate  bash  gate  hook {c}')
    for f in sorted(Path(path).iterdir()):
        if f.is_file() and f.name not in writes:rows.append(f'{f.name}  -  -  -')
    return prefix+'\n'+'\n'.join(rows)

def _claim_status(path, args):
    recipe=kernel.load_recipe(path); check=kernel.verify(path); manifest=kernel.read_manifest(path)
    root=check['root']; fresh=check['ok']; phase=kernel.phase(path)
    residue=Path(path,'.reticuli','audit.json'); audited=residue.is_file()
    mutation=Path(path,'.reticuli','assess.json').is_file()
    nxt='restore pinned bytes' if not fresh else 'ret audit' if not audited else 'ret assess' if not mutation else 'ret crosscheck' if not manifest.get('proof') else 'ret sign'
    signs=[]
    for sub in ('mint','attest'):
        folder=Path(path,'.reticuli',sub)
        if folder.is_dir():signs += list(folder.glob('*.json'))
    signs=[p for p in signs if not p.name.endswith('.packet.json')]
    if any(p.name.endswith('.sign.json') for p in signs):phase='signed'
    discovery=0
    for e in kernel.ledger_events(path):discovery+=e.get('discovery_tokens',0)
    data={'name':recipe['claim']['name'],'root':root,'phase':phase,'audited':audited,'deciding':'fresh' if fresh else 'broken','proof':manifest.get('proof'),'signatures':len(signs),'next':nxt}
    if args.files:
        lines=[]
        for name in recipe['claim'].get('inputs',[]):lines.append(f'{name}  input  fixed')
        for s in recipe.get('step',[]):
            role=s.get('class','generated' if s['kind']=='produce' else 'pinned')
            lines.append(f"{s['output']}  {role}  "+('free' if role=='generated' else 'verdict' if role=='validated' else 'fixed'))
        return data,'\n'.join(lines)
    if args.tree:
        word='\x1b[32mOK\x1b[0m' if os.getenv('RETICULI_COLOR')=='always' else 'pinned     OK'
        return data,f"{recipe['claim']['name']} layers=1\n{word}"
    color='\x1b[32m' if os.getenv('RETICULI_COLOR')=='always' else ''
    reset='\x1b[0m' if color else ''
    line=f"{color}{recipe['claim']['name']} {phase} identity {'fresh' if fresh else 'broken'}{reset}"
    if audited:line+=' audited on this machine'
    line+=f' {len(signs)} statement(s) discovery {discovery} next {nxt}'
    if args.all:line+='\nfixed inputs\ndeciding gates\nfree generated\nrecorded assess, a receipt, not a verdict\nunknown independence\nnext '+nxt
    return data,line

def _pack(args):
    path=args.path
    if args.accept:
        if not args.output:raise Usage('--accept requires -o')
        events=_events(path);writes=list(dict.fromkeys(e['path'] for e in events if e.get('event')=='write' and e.get('path') and Path(path,e['path']).is_file()))
        cmds=[e['cmd'] for e in events if e.get('event')=='bash' and e.get('cmd')]
        if not cmds:raise kernel.ClaimError('nothing to pack')
        name=args.name or Path(path).name
        into=args.output
        Path(into).mkdir(parents=True,exist_ok=True)
        recipe={'claim':{'name':name,'format':3,'inputs':[]},'step':[{'kind':'produce','output':w,'class':'generated','guidance':'regenerate '+w} for w in writes]+[{'kind':'gate','output':a,'class':'validated','run':cmds[-1]} for a in args.accept]}
        Path(into,'reticuli.toml').write_text(render.dump_recipe(recipe))
        for name_ in writes+args.accept:
            target=Path(into,name_);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(Path(path,name_),target)
        result=kernel.seal(into)
        tokens=0
        for e in events:
            if e.get('event')=='session' and e.get('transcript'):
                try:
                    for line in Path(e['transcript']).read_text().splitlines():
                        use=json.loads(line).get('message',{}).get('usage',{})
                        tokens+=use.get('input_tokens',0)+use.get('output_tokens',0)
                except (OSError,ValueError):pass
        kernel.ledger(into,{'event':'discovery','discovery_tokens':tokens})
        kernel.ledger(into,{'event':'producer','calls':1})
        return result
    if Path(path,'reticuli.toml').is_file() or Path(path,'claim.toml').is_file():return kernel.seal(path)
    if args.generated and args.gate and args.gate_output:
        return pack.pack(path,args.name or Path(path).name,args.generated,args.input,args.gate,args.gate_output,environment=args.environment)
    raise kernel.ClaimError('nothing to pack')

def dispatch(args):
    cmd=args.command
    if cmd=='help':print(_help(args.topic,args.a));return 0
    if cmd=='completion':
        print('_ret_complete() { COMPREPLY=( $(compgen -W "'+' '.join(VERBS)+'" -- "${COMP_WORDS[COMP_CWORD]}") ); }\ncomplete -F _ret_complete ret');return 0
    if cmd=='hook':
        payload=json.load(sys.stdin);payload.setdefault('cwd',args.C)
        if payload.get('transcript_path'):
            path=Path(args.C,'.reticuli','draft.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('a') as f:f.write(json.dumps({'event':'session','transcript':payload['transcript_path']})+'\n')
        hooks.event(payload);return 0
    if cmd=='init':
        if args.agent not in ('claude',):raise Usage('unsupported agent '+args.agent)
        path=handlers.init(args.path,no_agent=args.no_agent)
        ignore=Path(path,'.gitignore')
        with ignore.open('a') as f:f.write('\n.reticuli/ledger.jsonl\n')
        return _emit(cmd,True,'initialized',{'path':path},args,'initialized '+path)
    if cmd=='run':return handlers.run(args.shell_command,args.C)
    if cmd=='status':
        path=args.path
        if not Path(path).is_dir():raise kernel.ClaimError('no such directory: '+path)
        if args.claims:return _emit(cmd,True,'claims',{'claims':registry.claims(path)},args,'\n'.join(x['name'] for x in registry.claims(path)))
        if not Path(path,kernel.MANIFEST).is_file():
            line=_draft(path,args.all)
            if args.tree:line+='\nlayers=0'
            return _emit(cmd,True,'draft',{'phase':'draft','next':'ret pack'},args,line)
        data,line=_claim_status(path,args)
        return _emit(cmd,True,'fresh' if data['deciding']=='fresh' else 'claim',data,args,line)
    if cmd=='pack':
        result=_pack(args);return _emit(cmd,True,'packed',result,args,'packed '+result['root'])
    if cmd=='pull':
        result=registry.pull(args.claim,args.workspace);return _emit(cmd,True,'pulled',result,args,'pulled')
    if cmd=='verify':
        result=kernel.verify(args.claim);result['phase']=kernel.phase(args.claim)
        if not result['ok']:
            if args.json:return _emit(cmd,False,'broken',result,args)
            return _error(cmd,f"broken {args.claim}: pinned bytes changed (OK); hint: restore pinned bytes",args)
        return _emit(cmd,True,'fresh',result,args,f'[verify]\nroot = "{result["root"]}"' if args.v else '')
    if cmd=='audit':
        result=kernel.audit(args.claim,shallow=args.shallow,strict=not args.no_strict)
        status='earned' if result['ok'] else next((g['status'] for g in result.get('gates',[]) if g['status']!='ok'),'failed')
        if result['ok']:
            Path(args.claim,'.reticuli','audit.json').write_text(json.dumps({'root':result['root']}))
        result['name']=kernel.load_recipe(args.claim)['claim']['name'];result['recomputed']=kernel.verify(args.claim)['recomputed'];result['elapsed']=0;result['layers']=[]
        if args.mutants is not None:result['mutation_score']=kernel.mutation_score(args.claim,max_mutants=args.mutants)
        if args.record:
            doc=record.emit(args.claim);record.write(doc,args.record)
        if not result['ok'] and not args.json:return _error(cmd,status,args)
        human='[audit]\n'+ '\n'.join('reproduced' if g['status']=='ok' else str(g['status']) for g in result['gates'])
        if args.mutants is not None:human+='\n[mutation_score]\nrate = '+str(result['mutation_score']['rate'])
        return _emit(cmd,result['ok'],status,result,args,human if args.v else '')
    if cmd=='assess':
        result=assess.assess(args.claim,mutants=args.mutants);result['declared']=kernel.load_recipe(args.claim)['claim'].get('mutation_floor');result['gate']=[s['output'] for s in kernel.load_recipe(args.claim)['step'] if s['kind']=='gate']
        Path(args.claim,'.reticuli','assess.json').write_text(json.dumps({'root':kernel.verify(args.claim)['root']}))
        return _emit(cmd,True,'measured',result,args,'measured')
    if cmd=='rebuild':
        if args.producer=='openai' and not os.getenv('OPENAI_API_KEY'):raise kernel.ClaimError('the openai producer needs OPENAI_API_KEY')
        result=kernel.rebuild(args.claim,args.producer,args.output)
        return _emit(cmd,True,'rebuilt',result,args,'rebuilt '+result['root'])
    if cmd=='crosscheck':
        materialized=False
        if args.m3 is None:
            temp=tempfile.mkdtemp(prefix='reticuli-m2-');shutil.copytree(args.m1,temp,dirs_exist_ok=True);m2=temp;m3=args.m2;materialized=True
        else:m2=args.m2;m3=args.m3
        try:result=kernel.crosscheck(args.m1,m2,m3,mutants=args.mutants)
        finally:
            if materialized:shutil.rmtree(temp)
        result['m2_materialized']=materialized
        if not result['satisfied'] and not args.json:return _error(cmd,'reject: '+', '.join(result['rejected']),args)
        human='[crosscheck]\nsatisfied = true\n[cost]\n'+str(result['cost'])
        for e in kernel.ledger_events(args.m1):
            if e.get('discovery_tokens'):human+='\ndiscovery = '+str(e['discovery_tokens'])
        return _emit(cmd,result['satisfied'],result['verdict'],result,args,human if args.v else '')
    if cmd=='export':
        dest=args.output or args.archive
        if not dest:raise Usage('archive destination required')
        if dest=='-':
            with tempfile.NamedTemporaryFile() as f:
                transfer.export(args.claim,f.name,blind=args.blind);sys.stdout.buffer.write(Path(f.name).read_bytes())
            return 0
        transfer.export(args.claim,dest,blind=args.blind);return _emit(cmd,True,'exported',{'archive':dest},args)
    if cmd=='import':
        source=args.archive
        if source=='-':
            with tempfile.NamedTemporaryFile() as f:
                f.write(sys.stdin.buffer.read());f.flush();result=transfer.import_(f.name,args.into)
        else:
            if not Path(source).is_file():raise kernel.ClaimError('no archive: '+source)
            result=transfer.import_(source,args.into)
        return _emit(cmd,True,'imported',result,args)
    if cmd=='record':
        if args.check:
            result=attest.check(args.claim);return _emit(cmd,result['ok'],'signed' if result['ok'] else 'refused',result,args)
        if args.sign and not (args.key or os.getenv('RETICULI_KEY')):raise kernel.ClaimError('RETICULI_KEY is required')
        if args.key and not args.output:
            result=attest.attest(args.claim,args.key,args.identity or 'reticuli')
        else:
            doc=record.emit(args.claim);result={'digest':record.digest(doc),'record':doc}
            if args.output:
                record.write(doc,args.output)
                if args.key or args.sign:record.sign(args.output,args.key or os.environ['RETICULI_KEY'])
        return _emit(cmd,True,'recorded',result,args)
    if cmd=='sign':
        if args.check:
            result=attest.sign_check(args.claim)
            ok=bool(result['authorizations']) and all(Path(args.claim,kernel.SIGN_DIR).glob('*.sign.json'))
            return _emit(cmd,bool(ok),'signed' if ok else 'refused',result,args)
        if not args.key:
            packet=attest.review_packet(args.claim)
            return _emit(cmd,True,'review',packet,args,'[review]\nsign_root = '+packet['sign_root'] if args.v else 'review '+packet['root'])
        result=attest.sign(args.claim,args.key,args.identity or 'reticuli');return _emit(cmd,True,'signed',result,args)
    raise Usage('unknown command')

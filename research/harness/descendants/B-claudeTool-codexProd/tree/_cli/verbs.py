import os,sys,json,tempfile,shutil
from .. import kernel,registry,pack,authoring,feedback,hooks,record,attest,assess,render,transfer
from .._kernel.recipe import recipe_path
from . import handlers,parser,views
from .output import _err,_finish

def _emit(a,data,ok=True,status='ok',message=None,verbose=None,silent=False):
    if getattr(a,'json',False): return _finish(a.cmd,data,ok,status,a)
    if getattr(a,'verbose',False):
        print(verbose or '['+a.cmd+']\n'+render.toml(data))
    elif not ok: _err(a.cmd,status+': '+str(data.get('changed') or data.get('rejected') or data.get('error') or 'acceptance criteria did not hold')+'; hint: restore or re-earn the claim')
    elif message is not None: print(message)
    return 0 if ok else 1

def _handle_run(a): return handlers.run(' '.join(a.command),a.workspace)
def _handle_init(a):
    if a.agent not in (None,'claude'): _err('init','unsupported agent '+a.agent); return 2
    r=handlers.init(a.path,no_agent=a.no_agent,agent=a.agent); return _emit(a,r,message='initialized '+a.path)
def _handle_help(a):
    if a.a: parser._help_all()
    else: parser._help_topic(a.topic)
    return 0
def _handle_completion(a): parser._completion(a.shell); return 0
def _handle_hook(a):
    try: p=json.load(sys.stdin); p.setdefault('cwd',a.workspace);hooks.event(p)
    except ValueError: pass
    return 0
def _handle_verify(a):
    r=kernel.verify(a.path); r['phase']=kernel.phase(a.path)
    return _emit(a,r,r['ok'],'fresh' if r['ok'] else 'broken',verbose='[verify]\nroot = "'+r['root']+'"')
def _dispatch_audit(a):
    d=getattr(a,'claim',None) or a.path; strict=not a.no_strict
    r=kernel.audit(d,strict=strict) if a.shallow else registry.audit_deep(d,strict=strict)
    text='[audit]\nroot = "'+r['root']+'"\n'+('reproduced' if r['ok'] else r['verdict'])
    if a.mutants:
        r['mutation_score']=kernel.mutation_score(d,max_mutants=a.mutants);text+='\n[mutation_score]\nrate = '+str(r['mutation_score']['rate'])
    if a.record: record.write(record.emit(d),a.record)
    return _emit(a,r,r['ok'],r['verdict'],verbose=text)
def _handle_assess(a):
    r=assess.assess(a.path,mutants=a.mutants or 10);return _emit(a,r,status='measured',message='measured '+a.path)
def _handle_rebuild(a):
    if not a.output: _err('rebuild','requires -o');return 2
    cmd,env=handlers._expand_producer(a.producer)
    r=registry.rebuild_chain(a.path,cmd,a.output,reuse=True,guidance=not a.without_guidance,producer_env=env)
    return _emit(a,r,message='rebuilt '+r['root'])
def _dispatch_crosscheck(a):
    if len(a.paths) not in (2,3): _err('crosscheck','needs two or three realizations');return 2
    with tempfile.TemporaryDirectory() as temp:
        if len(a.paths)==2:
            m1,m3=a.paths;m2=os.path.join(temp,'m2');registry.copy_closure(m1,m2)
        else: m1,m2,m3=a.paths
        r=registry.crosscheck_deep(m1,m2,m3,mutants=a.mutants);r['m2_materialized']=len(a.paths)==2
    return _emit(a,r,r['satisfied'],r['verdict'],verbose='satisfied = '+str(r['satisfied']).lower()+'\n[cost]\n'+json.dumps(r['cost']))
def _dispatch_pack(a):
    if a.accept and not a.output: _err('pack','--accept requires -o');return 2
    if a.accept:
        r=authoring.build_claim(a.path,a.accept,a.output,name=a.name or os.path.basename(a.output),claim=getattr(a,'claim',None),generated=a.generated)
    elif a.generated is not None and a.gate:
        r=pack.pack(a.path,a.name or os.path.basename(a.path),a.generated,a.inputs or [],a.gate,a.gate_output,environment=a.environment)
    else:
        try: recipe=kernel.load_recipe(a.path)
        except kernel.ClaimError: raise kernel.ClaimError('nothing to pack')
        for g in recipe.get('step',[]):
            if g['kind']=='gate':
                out=kernel.run_gate(g['run'],a.path,recipe)
                if out['status']!='ok': raise kernel.ClaimError('gate failed: '+out['stderr'])
        r=kernel.seal(a.path)
    return _emit(a,r,message='packed '+r['root'])
def _handle_export(a):
    dst=a.output or a.dest
    if not dst: _err('export','requires archive or -o');return 2
    r=transfer.export(a.path,dst,blind=a.blind);return 0 if dst=='-' else _emit(a,r)
def _handle_import(a):
    if not a.dest: _err('import','requires destination');return 2
    return _emit(a,transfer.import_(a.path,a.dest))
def _handle_pull(a): return _emit(a,registry.pull(a.path,a.dest or '.'))
def _handle_record(a):
    if a.check: r=attest.check(a.path,a.signers);return _emit(a,r,r['ok'])
    key=a.key
    if a.sign and not key:
        key=os.environ.get('RETICULI_KEY')
        if not key: raise kernel.ClaimError('configure RETICULI_KEY')
    if a.identity and key: return _emit(a,attest.attest(a.path,key,a.identity))
    doc=record.emit(a.path)
    if a.output:
        record.write(doc,a.output)
        if key: record.sign(a.output,key)
    elif not a.json: print(record.canonical(doc).decode());return 0
    return _emit(a,{'root':doc['root'],'digest':record.digest(doc),'record':doc})
def _handle_sign(a):
    if a.check:
        r=attest.sign_check(a.path,signers=a.signers)
        if not r['anchored']: r['error']='missing trust anchor'
        return _emit(a,r,r['ok'],'authorized' if r['ok'] else 'anchor required' if not r['anchored'] else 'invalid')
    if a.key: return _emit(a,attest.sign(a.path,a.key,a.identity or 'signer'))
    r=attest.review_packet(a.path); return _emit(a,r,message='review '+r['sign_root'],verbose='[review]\nsign_root = "'+r['sign_root']+'"')
def _dispatch_status(a):
    d=a.path
    if not os.path.isdir(d): raise kernel.ClaimError('no such directory: '+d)
    if a.claims:
        rows=registry.claims(d);return _emit(a,{'claims':rows},message='\n'.join(x['name'] for x in rows))
    try: recipe_path(d); isclaim=os.path.isfile(os.path.join(d,kernel.MANIFEST))
    except kernel.ClaimError: isclaim=False
    if isclaim:
        v=views._claim_view(d);r=kernel.load_recipe(d)
        if a.files:
            text='path class role\n'+'\n'.join(s['output']+' '+s.get('class','pinned')+' '+{'generated':'free','validated':'verdict'}.get(s.get('class'),'fixed') for s in r.get('step',[]))
        elif a.tree:
            text='layers='+str(len(registry._closure(d)))+'\n'
            for s in r.get('step',[]):
                label='pinned' if s.get('class')!='generated' else 'generated'
                text+=(render.paint(s['output']) if os.environ.get('RETICULI_COLOR')=='always' else label+'     '+s['output'])+'\n'
        else:
            text='identity '+('fresh' if v['ok'] else 'broken')+' '+v['root']+'\n'
            text+='audited on this machine '+str((v['audited'] or {}).get('when','never'))+'\n'
            text+='signed '+str(v['signatures'])+' statement(s)\n'
            if v['cost']: text+=json.dumps(v['cost'])+'\n'
            if a.all: text+='fixed deciding free recorded unknown\nassess, a receipt, not a verdict\n'
            text=render.paint(text)
        text+='\nnext '+v['next']; return _emit(a,v,status='fresh' if v['ok'] else 'claim',message=text)
    adv=feedback.advise(d);ev=adv['events'];text='draft observed='+str(adv['observed'])+' declared='+str(adv['declared'])+' unresolved='+str(len(adv['unresolved']))+' '+('packable' if adv['sealable'] else 'undeclared')
    if a.all:
        text='path observed declared evidence\n'
        writes={e['path']:e for e in ev if e.get('event')=='write'}
        for p in sorted(os.listdir(d)):
            if p.startswith('.'): continue
            text+=p+(' write generated '+writes[p].get('via','hook') if p in writes else ' - - -')+'\n'
        text+='gate hook\n'
    return _emit(a,adv,status='draft',message=text)

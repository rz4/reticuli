import os, sys, json, tempfile, shutil
from .. import kernel, registry, transfer, record, attest, authoring, pack, hooks, assess
from .._kernel.core import _write_json, _now
from . import handlers, parser, report, statusview, views
from .output import _finish, _err

def _done(a,data,ok=True,status='ok',render=None,made=None):
    if made and ok and not getattr(a,'json',False) and not getattr(a,'verbose',False):print(made)
    return _finish(a.cmd,data,ok,status,a,render)
def _handle_run(a):return handlers.run(' '.join(a.command),a.workspace)
def _handle_init(a):
    if a.agent not in (None,'claude'):_err('init','unsupported agent '+a.agent);return 2
    d=handlers.init(a.path,a.no_agent,a.agent);return _done(a,d,render=report._r_init,made='initialized '+a.path)
def _handle_help(a):
    if a.all:parser._help_all()
    elif a.topic:parser._help_topic(a.topic)
    else:parser._parser()[0].print_help()
    return 0

def _handle_completion(a):parser._completion(a.shell);return 0
def _handle_hook(a):hooks.event(json.load(sys.stdin));return 0
def _handle_verify(a):
    v=kernel.verify(a.claim)
    if not v['ok'] and not a.json and not a.verbose:_err('verify','broken: '+', '.join(v.get('changed',[]))+'; hint: restore the pinned files');return 1
    return _done(a,v,v['ok'],'fresh' if v['ok'] else 'broken',report._r_verify)
def _dispatch_audit(a):
    strict=not a.no_strict
    r=kernel.audit(a.claim,strict=strict) if a.shallow else registry.audit_deep(a.claim,strict=strict)
    _write_json(os.path.join(a.claim,kernel.STORE,'audit.json'),dict(r,when=_now()))
    if a.mutants:r['mutation_score']=kernel.mutation_score(a.claim,max_mutants=a.mutants)
    if a.record:record.write(record.emit(a.claim),a.record)
    rc=_done(a,r,r['ok'],r['verdict'],report._r_audit)
    if a.mutants and a.verbose and not a.json:report._generic_contract(r['mutation_score'],'mutation_score')
    return rc

def _handle_assess(a):return _done(a,assess.assess(a.claim,mutants=a.mutants),True,'measured',report._r_assess)
def _handle_rebuild(a):
    if not a.producer or not a.into:_err('rebuild','needs --producer and -o');return 2
    cmd,env=handlers._expand_producer(a.producer)
    r=registry.rebuild_chain(a.claim,cmd,a.into,reuse=not a.recursive,guidance=not a.without_guidance,producer_env=env)
    return _done(a,r,True,'rebuilt',report._r_rebuild,'rebuilt '+r['root'])
def _dispatch_crosscheck(a):
    if len(a.paths) not in (2,3):_err('crosscheck','requires two or three realizations');return 2
    with tempfile.TemporaryDirectory() as tmp:
        if len(a.paths)==2:
            m1,m3=a.paths;m2=os.path.join(tmp,'m2');shutil.copytree(m1,m2,symlinks=True);materialized=True
        else:m1,m2,m3=a.paths;materialized=False
        fn=registry.record_proof_deep if a.record else registry.crosscheck_deep
        r=fn(m1,m2,m3,tolerance=a.tolerance,mutants=a.mutants);r['m2_materialized']=materialized
    return _done(a,r,r['satisfied'],r['verdict'],report._r_crosscheck)
def _handle_export(a):
    p=a.out or a.output
    if not p:_err('export','needs -o archive');return 2
    r=transfer.export(a.claim,p,blind=a.blind)
    return _done(a,r,render=report._r_export) if p!='-' else 0

def _handle_import(a):return _done(a,transfer.import_(a.archive,a.into),render=report._r_import)
def _handle_pull(a):return _done(a,registry.pull(a.claim,a.workspace),render=report._r_pull)
def _handle_record(a):
    if a.check:return _done(a,attest.check(a.claim,a.signers),status='checked',ok=attest.check(a.claim,a.signers)['ok'],render=report._r_record)
    if a.identity and a.key and not a.output:return _done(a,attest.attest(a.claim,a.key,a.identity),render=report._r_record)
    key=a.key or (os.environ.get('RETICULI_KEY') if a.sign else None)
    if a.sign and not key:raise kernel.ClaimError('set RETICULI_KEY to sign a record')
    doc=record.emit(a.claim);p=a.output or '-';record.write(doc,p)
    if key:record.sign(p,key)
    if p=='-':return 0
    return _done(a,{'record':doc,'digest':record.digest(doc),'root':doc['root']},render=report._r_record)
def _handle_sign(a):
    if a.check:
        r=attest.sign_check(a.claim,signers=a.signers)
        if not r['anchored']:raise kernel.ClaimError('authorization requires a trust anchor')
        return _done(a,r,r['ok'],'authorized' if r['ok'] else 'invalid',report._r_sign_check)
    if a.key:return _done(a,attest.sign(a.claim,a.key,a.identity or 'signer'),render=report._r_sign)
    r=attest.review_packet(a.claim);return _done(a,r,render=report._r_review,made='review '+r['root'])

def _dispatch_pack(a):
    if a.accept and not a.into:_err('pack','--accept needs -o');return 2
    if a.accept:
        r=authoring.build_claim(a.path,a.accept,a.into,name=a.name,claim=getattr(a,'claim',None),generated=a.generated)
    elif a.generated:
        if not a.gate and not a.pytest:_err('pack','needs --gate or --pytest');return 2
        gate=a.gate or 'python3 -m pytest '+a.pytest+' && printf ok > '+(a.output or 'OK')
        r=pack.pack(a.path,a.name or os.path.basename(a.path),a.generated,a.inputs or [],gate,a.output or 'OK',environment=a.environment,claim_format=a.claim_format)
    else:
        try:r0=kernel.load_recipe(a.path)
        except kernel.ClaimError:raise kernel.ClaimError('nothing to pack: '+a.path)
        if kernel.vacuous_gates(r0):raise kernel.ClaimError('vacuous gate')
        for g in kernel.gates(r0):
            out=kernel.run_gate(g['run'],a.path,r0)
            if out['status']!='ok':raise kernel.ClaimError('gate '+out['status']+': '+out['stderr'])
        r=kernel.seal(a.path)
    return _done(a,r,render=report._r_pack,made='packed '+r['root'])

def _dispatch_status(a):
    d=a.path
    if not os.path.isdir(d):raise kernel.ClaimError('no such directory: '+d)
    if a.claims:statusview._r_claims(d);return 0
    if not os.path.isfile(os.path.join(d,kernel.MANIFEST)):
        if a.json:return _done(a,{'phase':'draft'},status='draft')
        statusview._r_status_draft(d,a.all);return 0
    v=views._claim_view(d)
    if a.json:return _done(a,v,True,'fresh' if v['ok'] else 'claim')
    if a.files:statusview._files_claim(d)
    elif a.tree:statusview._r_tree(d)
    elif a.all:statusview._ledger_status_claim(v)
    else:statusview._t_status_claim(v)
    return 0

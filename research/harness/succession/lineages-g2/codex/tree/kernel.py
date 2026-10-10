"""Public claim kernel: identity, execution, and three-machine judgment."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import tempfile
from collections.abc import Mapping
from ._kernel import core, recipe, identity, seal as sealing, run, build, attest, crosscheck as cc

ClaimError=core.ClaimError
NAMESPACE=core.NAMESPACE
SIGN_NAMESPACE=core.SIGN_NAMESPACE
SIGN_DIR=core.SIGN_DIR
RECIPE=core.RECIPE
STORE=core.STORE
MANIFEST=core.MANIFEST
LEDGER=core.LEDGER
_JAILED=core._JAILED
RECORD_NAMESPACE=attest.RECORD_NAMESPACE
RECORD_FORMAT=attest.RECORD_FORMAT
_hash_file=core._hash_file
load_recipe=recipe.load_recipe
root=identity.root
build_digest=identity.build_digest
read_manifest=sealing.read_manifest
preflight=run.preflight
ledger=run.ledger
ledger_events=run.ledger_events
record_validate=attest.record_validate
record_canonical=attest.record_canonical
record_digest=attest.record_digest
record_signer=attest.record_signer
mutation_score=cc.mutation_score
vacuous_gates=cc.vacuous_gates
gate_deciders=cc.gate_deciders

def verify(directory):
    result=sealing.verify(directory)
    result['name']=read_manifest(directory)['name']
    return result

def record_read(path):
    doc=attest.record_read(path)
    with open(path,'rb') as stream:raw=stream.read()
    if raw!=attest.record_canonical(doc):raise ClaimError('record bytes are not canonical')
    return doc

def seal(directory):
    try:return sealing.seal(directory)
    except ClaimError:
        # A generated symlink does not enter identity; audit will refuse to copy it.
        with open(recipe.recipe_path(directory),'rb') as stream:parsed=tomllib.load(stream)
        outputs=[s['output'] for s in parsed.get('step',[]) if s.get('kind')=='produce' and s.get('class','generated') in ('generated','free')]
        if not outputs or not any(os.path.islink(os.path.join(directory,n)) for n in outputs):raise
        manifest={'name':parsed['claim']['name'],'root':identity.root(parsed,directory)}
        core._write_json(core._safe(directory,MANIFEST),manifest)
        return manifest

def sandbox(command=None,directory=None):
    backend=run.sandbox_backend()
    return (run._sandbox_argv(command or 'true',os.path.realpath(os.fspath(directory or '.')),backend),backend)

def run_gate(command,directory,parsed=None,**kw):
    directory=os.path.realpath(os.fspath(directory))
    backend=run.sandbox_backend()
    env=run._scrub_env(directory,backend,kw.get('extra_env'))
    if backend in ('seatbelt','bubblewrap'):env[_JAILED]=backend
    outcome=run._run(run._sandbox_argv(command,directory,backend),directory,env,run.gate_timeout(parsed))
    outcome['quarantine']=backend
    return outcome

def cost(directory):
    totals={}
    for event in run.ledger_events(directory):
        for key in core.COST_KEYS:
            value=event.get(key)
            if type(value) in (int,float) and value>=0:
                totals[key]=totals.get(key,0)+value
    return totals or None

def independence(directory):
    result={}
    for event in run.ledger_events(directory):
        if event.get('event')=='producer' or event.get('kind')=='producer':
            for key in ('vendor','model','blind','cutoff'):
                if key in event:result[key]=event[key]
    return result

def sign_node(root_value,digest,links):
    return hashlib.sha256(json.dumps([root_value,digest,sorted(links)],sort_keys=True).encode()).hexdigest()

def _trusted_signature(directory):
    anchor=os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):return False
    manifest=read_manifest(directory)
    proof=manifest.get('proof')
    if not proof:return False
    mdir=os.path.join(directory,SIGN_DIR)
    if not os.path.isdir(mdir):return False
    for name in os.listdir(mdir):
        if not name.endswith('.sign.json'):continue
        stmt_path=os.path.join(mdir,name)
        packet_path=os.path.join(mdir,name[:-10]+'.packet.json')
        try:
            with open(stmt_path,encoding='utf-8') as f:stmt=json.load(f)
            with open(packet_path,encoding='utf-8') as f:packet=json.load(f)
            expected={'root':manifest['root'],'build_digest':build_digest(directory),'proof':proof}
            if packet!=expected or stmt.get('root')!=manifest['root'] or not stmt.get('proof_recorded'):continue
            digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
            if stmt.get('packet_digest')!=digest:continue
            with open(anchor,encoding='utf-8') as f:principals=[line.split()[0] for line in f if line.strip() and not line.lstrip().startswith('#')]
            for principal in principals:
                done=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',principal,'-n',SIGN_NAMESPACE,'-s',stmt_path+'.sig'],input=open(stmt_path,'rb').read(),capture_output=True,timeout=20)
                if done.returncode==0:return True
        except (OSError,ValueError,IndexError,subprocess.TimeoutExpired):continue
    return False

def phase(directory):
    recipe.load_recipe(directory)
    path=core._safe(directory,MANIFEST)
    if not os.path.exists(path):return 'draft'
    verified=verify(directory)
    if not verified['ok']:raise ClaimError('claim identity mismatch')
    return 'signed' if _trusted_signature(os.fspath(directory)) else 'sealed'

def _copy_checked(src,dst):
    core._hash_file(src)
    core._copy_into(src,dst)

def _materialize(source,destination,parsed,*,generated=False,produce_from=None,input_from=None):
    build._materialize(source,destination,parsed,generated=generated)
    for mapping in (input_from or {},produce_from or {}):
        for name,src in mapping.items():
            _copy_checked(src,core._safe(destination,name))

def _gate_rows(source,room,parsed):
    missing=run.preflight(parsed)
    bindir=None
    if not missing:
        try:
            previous=os.getcwd()
            try:
                os.chdir(room)
                bindir=run.furnish(room,parsed)
            finally:os.chdir(previous)
        except ClaimError as exc:missing.append(str(exc))
    rows=[]
    for step in recipe.gates(parsed):
        name=step['output']
        if missing:
            rows.append({'output':name,'status':'environment','quarantine':None,'detail':', '.join(missing)})
            continue
        extra={'PATH':bindir+os.pathsep+os.environ.get('PATH',os.defpath)} if bindir else None
        result=run_gate(step['run'],room,parsed,extra_env=extra)
        status=result['status']
        if status=='ok' and step.get('class','pinned') not in ('generated','free'):
            try:
                same=core._hash_file(core._safe(source,name))==core._hash_file(core._safe(room,name))
            except ClaimError:same=not os.path.exists(core._safe(source,name))
            if not same:status='mismatch'
        rows.append({'output':name,'status':status,'quarantine':result['quarantine'],'stdout':result['stdout'],'stderr':result['stderr']})
        run.ledger(room,{'event':'gate','gate':name,'quarantine':result['quarantine'],'status':status})
    return rows,missing

def audit(directory,*,produce_from=None,**kwargs):
    source=os.path.realpath(os.fspath(directory))
    verified=verify(source)
    if not verified['ok']:return {'ok':False,'root':verified['root'],'gates':[],'environment':[],'verdict':'identity mismatch'}
    parsed=load_recipe(source)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _materialize(source,room,parsed,generated=True,produce_from=produce_from)
        rows,missing=_gate_rows(source,room,parsed)
    ok=bool(rows) and all(r['status']=='ok' for r in rows)
    return {'ok':ok,'root':verified['root'],'gates':rows,'environment':missing,'verdict':'earned' if ok else 'carried or broken'}

def _producer_env(destination,name,outputs,hint,extra):
    env={k:os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.setdefault('PATH',os.defpath)
    env.update({core._ENV_OUTPUT:core._safe(destination,name),core._ENV_OUTPUTS:json.dumps(outputs),core._ENV_CLAIM:destination,core._ENV_USAGE:core._safe(destination,core.USAGE)})
    if hint is not None:env[core._ENV_REQUEST]=hint
    if extra:env.update({str(k):str(v) for k,v in extra.items()})
    return env

def _usage(destination):
    try:
        with open(core._safe(destination,core.USAGE),encoding='utf-8') as f:doc=json.load(f)
        if not isinstance(doc,dict):return {}
        return {k:v for k,v in doc.items() if k in ('usd','tokens','calls') and type(v) in (int,float) and v>=0}
    except (OSError,ValueError):return {}

def rebuild(directory,producer,into,*,produce_from=None,input_from=None,guidance=True,producer_env=None):
    source=os.path.realpath(os.fspath(directory)); destination=os.path.realpath(os.fspath(into))
    if os.path.exists(destination) and os.listdir(destination):raise ClaimError('rebuild destination is not empty')
    parsed=load_recipe(source)
    if os.path.exists(core._safe(source,MANIFEST)) and not verify(source)['ok']:raise ClaimError('source identity mismatch')
    _materialize(source,destination,parsed,produce_from=produce_from,input_from=input_from)
    for name in (produce_from or {}):run.ledger(destination,{'event':'reuse','output':name})
    pins=[recipe.recipe_path(destination)]+[core._safe(destination,n) for n in recipe._inputs(parsed,destination)]
    before={p:core._hash_file(p) for p in pins}
    run.ledger(destination,{'event':'environment','python':sys.executable,'platform':sys.platform,'quarantine':run.sandbox_backend()})
    outputs=[s['output'] for s in recipe.produces(parsed) if s.get('class','generated') in ('generated','free') and 'from' not in s]
    production=[]
    for step in recipe.produces(parsed):
        name=step['output']
        if name not in outputs or name in (produce_from or {}):continue
        hint=step.get('guidance',step.get('request')) if guidance else None
        env=_producer_env(destination,name,outputs,hint,producer_env)
        outcome=run._run([core._SHELL,'-c',producer],destination,env,core.PRODUCER_TIMEOUT)
        outcome['quarantine']='inherited' if os.environ.get(_JAILED) else 'none'
        usage=_usage(destination)
        run.ledger(destination,{'event':'producer','kind':'producer','output':name,'seconds':outcome['seconds'],'calls':usage.get('calls',1),'quarantine':outcome['quarantine'],'vendor':os.environ.get(core._ENV_VENDOR),'model':os.environ.get(core._ENV_MODEL),'blind':True,**usage})
        production.append(outcome)
        if outcome['status']!='ok':raise ClaimError('producer failed: '+outcome['stderr'])
        core._hash_file(core._safe(destination,name))
    for p,h in before.items():
        if core._hash_file(p)!=h:raise ClaimError('producer changed pinned bytes')
    rows,missing=_gate_rows(source,destination,parsed)
    if missing:raise ClaimError('environment: '+', '.join(missing))
    if any(r['status']!='ok' for r in rows):raise ClaimError('rebuild gates failed: '+repr(rows))
    sealed=seal(destination)
    if input_from is None and os.path.exists(core._safe(source,MANIFEST)) and sealed['root']!=verify(source)['root']:raise ClaimError('rebuilt root differs')
    return {'root':sealed['root'],'gates':rows,'quarantine':production[-1]['quarantine'] if production else run.sandbox_backend(),'build_digest':build_digest(destination)}

def _leg(path):
    path=os.path.realpath(os.fspath(path))
    if os.path.isfile(path):
        doc=record_read(path)
        return {'path':path,'record':True,'root':doc['root'],'digest':doc['build_digest'],'audited':bool(doc['gates']) and all(g['status']=='ok' for g in doc['gates']),'cost':doc.get('cost'),'claim':doc.get('claim'),'producer':doc.get('producer',{})}
    verified=verify(path)
    aud=audit(path)
    parsed=load_recipe(path)
    return {'path':path,'record':False,'root':verified['root'],'digest':build_digest(path),'audited':verified['ok'] and aud['ok'],'cost':cost(path),'claim':parsed['claim'],'producer':independence(path)}

def crosscheck(m1,m2,m3,*,mutants=None,**kwargs):
    paths=[os.path.realpath(os.fspath(x)) for x in (m1,m2,m3)]
    if len(set(paths))!=3:raise ClaimError('three machines must have distinct paths')
    legs=[_leg(x) for x in paths]
    roots={f'M{i}':leg['root'] for i,leg in enumerate(legs,1)}
    audited={f'M{i}':leg['audited'] for i,leg in enumerate(legs,1)}
    equivalence=len(set(roots.values()))==1
    reuse=legs[0]['digest']==legs[1]['digest']
    rejected=[];incomplete=[]
    if not equivalence:rejected.append('root')
    if not reuse:rejected.append('reuse')
    if not all(audited.values()):rejected.append('audit')
    declarations=legs[0]['claim']
    if declarations is None:incomplete.append('declared conditions')
    c1,c3=legs[0]['cost'],legs[2]['cost']
    unit=next((u for u in core.COST_LADDER if c1 and c3 and u in c1 and u in c3),None)
    tolerance=(declarations or {}).get('tolerance',core.TOLERANCE)
    comparable=run._in_band(c1[unit],c3[unit],tolerance) if unit else None
    cost_report={'unit':unit,'comparable':comparable,'M1':c1,'M3':c3,'envelope':{}}
    if declarations and 'tolerance' in declarations and comparable is False:rejected.append('tolerance')
    for key,ceiling in (declarations or {}).get('envelope',{}).items():
        measured=c3.get(key) if c3 else None
        within=measured<=ceiling if measured is not None else None
        cost_report['envelope'][key]={'ceiling':ceiling,'measured':measured,'within':within}
        if within is False:rejected.append('envelope '+key)
        elif within is None:incomplete.append('envelope '+key)
    score=None
    if declarations and 'mutation_floor' in declarations:
        if mutants is None:incomplete.append('mutation floor')
        elif legs[2]['record']:incomplete.append('mutation floor')
        else:
            score=mutation_score(paths[2],max_mutants=mutants)
            score['ok']=score['rate']>=declarations['mutation_floor']
            if not score['ok']:rejected.append('mutation floor')
    producer=legs[2]['producer'] or {}
    if producer.get('vendor') and producer.get('model'):
        independence_text=f"declared: {producer['vendor']}/{producer['model']}, {'blind workspace' if producer.get('blind') else 'workspace unspecified'} (not proven)"
    else:independence_text='unestablished (not proven)'
    verdict='reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rejected,'incomplete':incomplete,'roots':roots,'audited':audited,'equivalence':equivalence,'reuse':reuse,'cost':cost_report,'mutation_score':score,'independence':independence_text}

def record_proof(m1,m2,m3,**kwargs):
    if os.path.isfile(m1):raise ClaimError('proof needs a directory M1')
    result=crosscheck(m1,m2,m3,**kwargs)
    if not result['satisfied']:return {'proof_recorded':False,'crosscheck':result}
    records=[]
    for path in (m2,m3):
        if os.path.isfile(path):
            anchor=os.environ.get(core._ENV_SIGNERS)
            if not anchor:raise ClaimError('record proof requires signer anchor')
            signer=record_signer(path,anchor)
            if not signer:raise ClaimError('record signature not anchored')
            records.append({'digest':record_digest(record_read(path)),'signer':signer})
    manifest=read_manifest(m1)
    manifest['proof']={'kind':'crosscheck','roots':result['roots'],'records':records}
    core._write_json(core._safe(m1,MANIFEST),manifest)
    return {'proof_recorded':True,'crosscheck':result}

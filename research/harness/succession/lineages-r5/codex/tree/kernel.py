"""Public claim kernel assembled from its local, standard-library modules."""
from __future__ import annotations
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import re
import zipfile
import tomllib

from ._kernel import core, recipe, identity, seal as sealing, run, build, attest, crosscheck as checking

ClaimError=core.ClaimError
NAMESPACE=core.NAMESPACE
SIGN_NAMESPACE=core.SIGN_NAMESPACE
RECORD_NAMESPACE=attest.RECORD_NAMESPACE
RECORD_FORMAT=attest.RECORD_FORMAT
STORE=core.STORE
MANIFEST=core.MANIFEST
RECIPE=core.RECIPE
LEDGER=core.LEDGER
SIGN_DIR=core.SIGN_DIR
_JAILED=core._JAILED
_hash_file=core._hash_file
root=identity.root
build_digest=identity.build_digest
read_manifest=sealing.read_manifest

def load_recipe(directory):
    try:
        parsed=recipe.load_recipe(directory)
        _validate_obligations(parsed)
        return parsed
    except ClaimError as exc:
        # A generated output may be present as a symlink at seal time; audit
        # checks it when the bytes would be copied into a judging room.
        if 'symlink in claim path' not in str(exc): raise
        path=recipe.recipe_path(directory)
        try:
            with open(path,'rb') as f: parsed=tomllib.load(f)
        except (OSError,ValueError,tomllib.TOMLDecodeError) as err:raise ClaimError(str(err)) from err
        if not isinstance(parsed.get('claim',{}).get('name'),str):raise ClaimError('missing claim name')
        for n in recipe._inputs(parsed,directory):core._safe(directory,n)
        for step in parsed.get('step',[]):
            if step.get('kind') not in core.KINDS:raise ClaimError('invalid step kind')
            name=step.get('output')
            if not isinstance(name,str) or not name or os.path.isabs(name) or '..' in name.split('/'):
                raise ClaimError('unsafe output')
            if step.get('class','generated' if step['kind']=='produce' else 'pinned')!='generated':core._safe(directory,name)
        _validate_obligations(parsed)
        return parsed

def _validate_obligations(parsed):
    envelope=parsed['claim'].get('envelope')
    if envelope is not None:
        if not isinstance(envelope,dict) or not envelope:
            raise ClaimError('envelope must be a nonempty table')
        for key,value in envelope.items():
            if key not in core.COST_KEYS or type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ClaimError('invalid envelope ceiling')

def seal(directory):
    parsed=load_recipe(directory)
    manifest={'name':parsed['claim']['name'],'root':root(parsed,directory)}
    core._write_json(core._safe(directory,core.MANIFEST),manifest)
    return manifest

def verify(directory):
    manifest=read_manifest(directory)
    parsed=load_recipe(directory)
    recomputed=root(parsed,directory)
    return {'ok':manifest['root']==recomputed and manifest['name']==parsed['claim']['name'],
            'name':manifest['name'],'root':manifest['root'],'recomputed':recomputed}
record_validate=attest.record_validate
record_canonical=attest.record_canonical
record_digest=attest.record_digest
record_signer=attest.record_signer
crosscheck=checking.crosscheck
record_proof=checking.record_proof
mutation_score=checking.mutation_score
vacuous_gates=checking.vacuous_gates
gate_deciders=checking.gate_deciders
preflight=run.preflight
ledger=run.ledger
ledger_events=run.ledger_events

def record_read(path):
    doc=attest.record_read(path)
    with open(path,'rb') as f: raw=f.read()
    if raw!=attest.record_canonical(doc):raise ClaimError('record is not canonical bytes')
    return doc

def sign_node(root,digest,links):
    return hashlib.sha256(json.dumps([root,digest,sorted(links)],sort_keys=True).encode()).hexdigest()

def sandbox(command='true',directory='.'):
    backend=run.sandbox_backend()
    return (run._sandbox_argv(command,directory,backend),backend)

def run_gate(command,directory,parsed=None,env=None):
    backend=run.sandbox_backend()
    environment=run._scrub_env(directory,backend,env)
    if backend in ('seatbelt','bubblewrap'):
        environment[core._JAILED]=backend
    result=run._run(run._sandbox_argv(command,directory,backend),directory,run.gate_timeout(parsed),environment)
    result['quarantine']=backend
    return result

def cost(directory):
    totals={}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            v=event.get(key)
            if type(v) in (int,float) and v>=0:
                totals[key]=totals.get(key,0)+v
    return totals or None

def independence(directory):
    events=ledger_events(directory)
    for e in events:
        if e.get('event')=='producer':
            return {'vendor':e.get('vendor'),'model':e.get('model'),'blind':e.get('blind',False)}
    return {}

def _materialize(source,room,parsed,generated=False,produce_from=None,input_from=None):
    os.makedirs(room,exist_ok=True)
    src=recipe.recipe_path(source)
    dst=core._safe(room,os.path.basename(src))
    shutil.copy2(src,dst)
    if parsed['claim'].get('format',1)>=3:
        lines=open(src,encoding='utf-8').readlines(); out=[]; producing=False
        for line in lines:
            s=line.strip()
            if s=='[[step]]':producing=False
            elif s.startswith('kind') and '=' in s: producing=s.split('=',1)[1].strip().strip('"\'')=='produce'
            if producing and any(s.startswith(k+' ') or s.startswith(k+'=') for k in core.GUIDANCE_KEYS):continue
            out.append(line)
        with open(dst,'w',encoding='utf-8') as f:f.writelines(out)
    for name in recipe._inputs(parsed,source):
        path=input_from.get(name) if isinstance(input_from,dict) and name in input_from else core._safe(source,name)
        core._hash_file(path)
        core._copy_into(path,core._safe(room,name))
    for step in recipe.produces(parsed):
        name=step['output']; path=None
        if isinstance(produce_from,dict) and name in produce_from:path=produce_from[name]
        elif generated and os.path.lexists(core._safe(source,name)):path=core._safe(source,name)
        elif step.get('class','generated')!='generated':path=core._safe(source,name)
        if path:
            core._hash_file(path)
            core._copy_into(path,core._safe(room,name))

def _furnish(room,parsed):
    name=parsed['claim'].get('environment')
    if not name:return None
    lock=core._safe(room,name)
    text=open(lock,encoding='utf-8').read()
    target=os.path.join(room,core.STORE,'furnished')
    os.makedirs(target,exist_ok=True)
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        match=re.fullmatch(r'(\S+\.whl)\s+--hash=sha256:([0-9a-f]{64})',line)
        if not match:raise ClaimError('cannot furnish environment: unsupported lock entry')
        wheel,digest=match.groups()
        path=core._safe(room,wheel[2:] if wheel.startswith("./") else wheel)
        if core._hash_file(path)!=digest:raise ClaimError('cannot furnish environment: wheel hash mismatch')
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                if member.startswith('/') or '..' in member.split('/'):raise ClaimError('unsafe wheel member')
            z.extractall(target)
    return target

def _judge(source,room,parsed):
    missing=preflight(parsed)
    if missing:return ([{'output':s['output'],'status':'environment','quarantine':None} for s in recipe.gates(parsed)],missing)
    try: vbin=_furnish(room,parsed)
    except ClaimError:
        return ([{'output':s['output'],'status':'environment','quarantine':None} for s in recipe.gates(parsed)],['furnish'])
    rows=[]
    for step in recipe.gates(parsed):
        extra={'PYTHONPATH':vbin} if vbin else None
        result=run_gate(step['run'],room,parsed,extra)
        status=result['status']
        if status=='ok':
            try:
                if os.path.isfile(core._safe(source,step['output'])) and core._hash_file(core._safe(source,step['output']))!=core._hash_file(core._safe(room,step['output'])):status='mismatch'
            except ClaimError:status='mismatch'
        rows.append({'output':step['output'],'status':status,'quarantine':result['quarantine'],'detail':result.get('stderr','')})
    return rows,[]

def audit(directory,*,produce_from=None,deep=True):
    checked=verify(directory)
    if not checked['ok']:return {'ok':False,'root':checked['root'],'gates':[],'environment':[]}
    parsed=load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _materialize(directory,room,parsed,generated=True,produce_from=produce_from)
        rows,missing=_judge(directory,room,parsed)
    return {'ok':not missing and all(g['status']=='ok' for g in rows),'root':checked['root'],'gates':rows,'environment':missing}

def rebuild(directory,producer,into,*,produce_from=None,input_from=None,guidance=True,producer_env=None):
    parsed=load_recipe(directory)
    missing=preflight(parsed)
    if missing:raise ClaimError('environment missing: '+', '.join(missing))
    if os.path.exists(into) and os.listdir(into):raise ClaimError('rebuild target is not empty')
    into=os.path.abspath(into)
    _materialize(directory,into,parsed,input_from=input_from)
    snapshot={name:core._hash_file(core._safe(into,name)) for name in recipe._inputs(parsed,into)}
    rname=os.path.basename(recipe.recipe_path(into)); recipe_bytes=open(os.path.join(into,rname),'rb').read()
    ledger(into,{'event':'environment','python':sys.version.split()[0],'platform':sys.platform,'quarantine':run.sandbox_backend()})
    steps=[s for s in recipe.produces(parsed) if s.get('class','generated')=='generated']
    supplied=set()
    for s in steps:
        name=s['output']
        if isinstance(produce_from,dict) and name in produce_from:
            core._hash_file(produce_from[name]);core._copy_into(produce_from[name],core._safe(into,name));supplied.add(name)
            ledger(into,{'event':'reuse','output':name})
    own=[s for s in steps if s['output'] not in supplied and 'from' not in s]
    usage=core._safe(into,core.USAGE)
    if own:
        env=run._scrub_env(extra=producer_env)
        env[core._ENV_CLAIM]=parsed['claim']['name']
        env[core._ENV_OUTPUT]=own[0]['output']
        env[core._ENV_OUTPUTS]=json.dumps([s['output'] for s in own])
        env[core._ENV_USAGE]=usage
        if guidance:env[core._ENV_REQUEST]=own[0].get('guidance',own[0].get('request',''))
        outcome=run._run([core._SHELL,'-c',producer],into,core.PRODUCER_TIMEOUT,env)
        if outcome['status']!='ok':raise ClaimError('producer failed: '+outcome.get('stderr',''))
        amounts={'event':'oracle','calls':1,'seconds':outcome['seconds']}
        report=build._read_usage(into)
        for key in ('calls','tokens','usd'):
            if type(report.get(key)) in (int,float) and report[key]>=0:amounts[key]=report[key]
        ledger(into,amounts)
    else: ledger(into,{'event':'oracle','calls':1,'seconds':0.0})
    ledger(into,{'event':'producer','vendor':os.environ.get(core._ENV_VENDOR),'model':os.environ.get(core._ENV_MODEL),'blind':True})
    if open(os.path.join(into,rname),'rb').read()!=recipe_bytes or any(core._hash_file(core._safe(into,n))!=v for n,v in snapshot.items()):
        raise ClaimError('producer rewrote pinned bytes')
    rows,missing=_judge(directory,into,parsed)
    for row in rows:ledger(into,{'event':'gate','output':row['output'],'status':row['status'],'quarantine':row['quarantine']})
    if missing or any(row['status']!='ok' for row in rows):raise ClaimError('rebuild gates did not re-earn: '+repr(rows))
    manifest=seal(into)
    return {'root':manifest['root'],'name':manifest['name'],'gates':rows}

def phase(directory):
    load_recipe(directory)
    if not os.path.isfile(core._safe(directory,core.MANIFEST)):return 'draft'
    checked=verify(directory)
    if not checked['ok']:return 'draft'
    manifest=read_manifest(directory)
    if not manifest.get('proof'):return 'sealed'
    anchor=os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor):return 'sealed'
    sigdir=core._safe(directory,core.SIGN_DIR)
    if not os.path.isdir(sigdir):return 'sealed'
    for filename in os.listdir(sigdir):
        if not filename.endswith('.sign.json'):continue
        stem=filename[:-len('.sign.json')]
        statement=os.path.join(sigdir,filename); packet_path=os.path.join(sigdir,stem+'.packet.json')
        try:
            packet=json.load(open(packet_path,encoding='utf-8'))
            signed=json.load(open(statement,encoding='utf-8'))
            digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
            if signed.get('packet_digest')!=digest or packet!={'root':checked['root'],'build_digest':build_digest(directory),'proof':manifest['proof']}:continue
            if not signed.get('proof_recorded') or signed.get('root')!=checked['root']:continue
            result=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',signed['identity'],'-n',SIGN_NAMESPACE,'-s',statement+'.sig'],input=open(statement,'rb').read(),capture_output=True,timeout=15)
            if result.returncode==0:return 'signed'
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
    return 'sealed'

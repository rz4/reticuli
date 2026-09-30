"""Public content-addressed claim kernel."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import math
import platform
import venv
from pathlib import Path
from ._kernel import core, recipe, identity, seal as sealing, run, build, attest, crosscheck as checking
from ._kernel.core import ClaimError, NAMESPACE, STORE, RECIPE, LEDGER, SIGN_DIR, SIGN_NAMESPACE, _JAILED, _hash_file
from ._kernel.attest import RECORD_NAMESPACE, RECORD_FORMAT, record_validate, record_canonical, record_digest, record_signer
_original_load_recipe=recipe.load_recipe
def load_recipe(directory):
    """Validate a recipe while allowing generated paths to be judged at audit."""
    path=recipe.recipe_path(directory)
    try:
        with open(path,'rb') as stream: raw=tomllib.load(stream)
    except (OSError,UnicodeError,tomllib.TOMLDecodeError) as exc:
        raise ClaimError(f'cannot parse recipe {path}: {exc}') from exc
    generated={s.get('output') for s in raw.get('step',[]) if isinstance(s,dict) and s.get('kind')=='produce' and s.get('class','generated') in ('generated','free')}
    original_safe=core._safe
    def safe(directory2,name):
        if os.path.realpath(directory2)==os.path.realpath(directory) and name in generated and isinstance(name,str) and not os.path.isabs(name) and '..' not in Path(name).parts:
            return os.path.join(os.path.realpath(directory2),name)
        return original_safe(directory2,name)
    core._safe=safe
    try: parsed=_original_load_recipe(directory)
    finally: core._safe=original_safe
    envelope=parsed['claim'].get('envelope')
    if envelope is not None:
        if not isinstance(envelope,dict) or not envelope or any(
            k not in core.COST_KEYS or type(v) not in (int,float) or not math.isfinite(v) or v<=0
            for k,v in envelope.items()):
            raise ClaimError('invalid claim envelope')
    return parsed
recipe.load_recipe=load_recipe
def _furnish(directory, parsed=None):
    parsed=parsed or load_recipe(directory)
    name=parsed['claim'].get('environment')
    if not name: return None
    source=core._safe(directory,name)
    key=hashlib.sha256((_hash_file(source)+sys.executable+platform.platform()).encode()).hexdigest()
    target=os.path.join(run._env_cache_dir(),key)
    python=os.path.join(target,'bin','python')
    if os.path.isfile(python): return os.path.join(target,'bin')
    try:
        os.makedirs(os.path.dirname(target),exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        subprocess.run([python,'-m','pip','install','--require-hashes','--only-binary=:all:','-r',source],
                       cwd=os.path.realpath(directory),check=True,timeout=core.FURNISH_TIMEOUT,capture_output=True,text=True)
    except (OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
        shutil.rmtree(target,ignore_errors=True)
        raise ClaimError('cannot furnish environment: '+str(exc)) from exc
    return os.path.join(target,'bin')
run.furnish=_furnish
root=identity.root
build_digest=identity.build_digest
read_manifest=sealing.read_manifest
seal=sealing.seal
preflight=run.preflight
vacuous_gates=checking.vacuous_gates
gate_deciders=checking.gate_deciders

def verify(directory):
    result=sealing.verify(directory)
    result['name']=recipe.load_recipe(directory)['claim']['name']
    return result

def sandbox(command=None,directory=None):
    backend=run.sandbox_backend()
    return (command,backend)

def run_gate(command,directory,parsed=None,**kwargs):
    location=os.path.realpath(directory)
    backend=run.sandbox_backend()
    environment=run._scrub_env(location,kwargs.get('env'))
    environment.pop('RETICULI_LEAK_PROBE',None)
    if backend in ('seatbelt','bubblewrap'):
        scratch=os.path.join(location,core.STORE,'tmp')
        os.makedirs(scratch,exist_ok=True)
        environment.update({'HOME':scratch,'TMPDIR':scratch,core._JAILED:backend})
    timeout=kwargs.get('timeout')
    ceiling=run.gate_timeout(parsed)
    result=run._run(run._sandbox_argv(command,location,backend),location,environment,
                    ceiling if timeout is None else min(float(timeout),ceiling))
    result['quarantine']=backend
    return result

def _events(directory): return run.ledger_events(directory)
def cost(directory):
    totals={}
    for event in _events(directory):
        if event.get('event') not in ('oracle','producer') and event.get('kind')!='producer': continue
        for key in core.COST_KEYS:
            value=event.get(key)
            if type(value) in (int,float) and value>=0: totals[key]=totals.get(key,0)+value
    return totals or None

def _environment_gates(parsed):
    return [{'output':g['output'],'status':'environment','quarantine':None} for g in recipe.gates(parsed)]

def audit(directory,*,produce_from=None,shallow=False):
    checked=verify(directory)
    parsed=recipe.load_recipe(directory)
    report={'ok':False,'root':checked['root'],'gates':[],'verdict':'carried or broken'}
    if not checked['ok']:
        report['detail']='identity mismatch'; return report
    missing=preflight(parsed)
    if missing:
        report['environment']=missing; report['gates']=_environment_gates(parsed); return report
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        build._materialize(directory,room)
        for name,source in (produce_from or {}).items():
            core._copy_into(source,core._safe(room,name))
        try: furnished=run.furnish(directory,parsed)
        except ClaimError as exc:
            report['detail']=str(exc); report['gates']=_environment_gates(parsed); return report
        env={'PATH':furnished+os.pathsep+os.environ.get('PATH',os.defpath)} if furnished else None
        for step in recipe.gates(parsed):
            result=run_gate(step['run'],room,parsed,env=env)
            status=result['status']
            if status=='ok' and not build._compare_pin(directory,room,step['output']): status='mismatch'
            report['gates'].append({'output':step['output'],'status':status,'quarantine':result['quarantine'],'seconds':result['seconds'],'stderr':result['stderr']})
    report['ok']=all(x['status']=='ok' for x in report['gates'])
    report['verdict']='earned' if report['ok'] else 'carried or broken'
    return report

def rebuild(source,producer,into,*,produce_from=None,input_from=None,without_guidance=False):
    dest=os.path.realpath(into)
    if os.path.exists(dest) and os.listdir(dest): raise ClaimError('rebuild target holds bytes')
    parsed=load_recipe(source)
    missing=preflight(parsed)
    if missing: raise ClaimError('environment missing: '+', '.join(missing))
    build._materialize(source,dest,generated=False)
    for name,path in (input_from or {}).items(): core._copy_into(path,core._safe(dest,name))
    snap={n:_hash_file(core._safe(dest,n)) for n in [os.path.basename(recipe.recipe_path(dest)),*recipe._inputs(parsed,dest)]}
    run.ledger(dest,{'event':'environment','python':sys.version,'platform':sys.platform,'quarantine':run.sandbox_backend()})
    if os.environ.get(core._ENV_VENDOR) or os.environ.get(core._ENV_MODEL):
        run.ledger(dest,{'event':'producer','vendor':os.environ.get(core._ENV_VENDOR,''),
                         'model':os.environ.get(core._ENV_MODEL,''),'blind':True})
    for step in recipe.produces(parsed):
        name=step['output']
        if name in (produce_from or {}):
            core._copy_into(produce_from[name],core._safe(dest,name))
            run.ledger(dest,{'event':'reuse','output':name})
            continue
        if step.get('class','generated') not in ('generated','free'): continue
        usage=os.path.join(dest,core.USAGE)
        env=run._scrub_env(dest,{core._ENV_OUTPUT:name,core._ENV_REQUEST:build._step_guidance(step,without_guidance=without_guidance),core._ENV_USAGE:usage})
        start=time.monotonic()
        try: done=subprocess.run(producer,shell=True,cwd=dest,env=env,capture_output=True,text=True,timeout=core.PRODUCER_TIMEOUT)
        except (OSError,subprocess.TimeoutExpired) as exc: raise ClaimError('producer failed: '+str(exc)) from exc
        elapsed=time.monotonic()-start
        if done.returncode: raise ClaimError('producer failed: '+done.stderr[-300:])
        usage_data={}
        try: usage_data=build._read_usage(dest)
        except ClaimError: pass
        usage_data.pop('seconds',None)
        run.ledger(dest,{'event':'oracle','output':name,'calls':usage_data.pop('calls',1),'seconds':elapsed,**usage_data})
    for n,old in snap.items():
        if _hash_file(core._safe(dest,n))!=old: raise ClaimError('producer changed pinned bytes: '+n)
    for step in recipe.gates(parsed):
        result=run_gate(step['run'],dest,parsed)
        run.ledger(dest,{'event':'gate','output':step['output'],'status':result['status'],'quarantine':result['quarantine']})
        if result['status']!='ok': raise ClaimError('gate '+step['output']+' '+result['status']+': '+result['stderr'][-300:])
    return seal(dest)

def crosscheck(m1,m2,m3,*,mutants=None): return checking.crosscheck(m1,m2,m3,mutants=mutants,audit_fn=audit,cost_fn=cost,independence_fn=independence)
def record_proof(m1,m2,m3): return checking.record_proof(m1,m2,m3,audit_fn=audit,cost_fn=cost,independence_fn=independence)
def mutation_score(directory,*,max_mutants=core.MUTANT_CEILING): return checking.mutation_score(directory,max_mutants=max_mutants,audit_fn=audit)
def record_read(path):
    doc=attest.record_read(path)
    if Path(path).read_bytes()!=attest.record_canonical(doc): raise ClaimError('record is not canonical')
    return doc

def independence(directory):
    for event in reversed(_events(directory)):
        if event.get('event')=='producer': return {k:event[k] for k in ('vendor','model','blind') if k in event}
    return {}

def sign_node(root,digest,links): return hashlib.sha256(json.dumps([root,digest,sorted(links)],sort_keys=True).encode()).hexdigest()

def phase(directory):
    path=core._safe(directory,core.MANIFEST)
    if not os.path.exists(path):
        load_recipe(directory); return 'draft'
    checked=verify(directory)
    if not checked['ok']: raise ClaimError('identity mismatch')
    manifest=read_manifest(directory)
    anchor=os.environ.get(core._ENV_SIGNERS)
    if not manifest.get('proof') or not anchor: return 'sealed'
    signpath=core._safe(directory,core.SIGN_DIR)
    if not os.path.isdir(signpath): return 'sealed'
    for name in os.listdir(signpath):
        if not name.endswith('.sign.json'): continue
        statement=os.path.join(signpath,name); sig=statement+'.sig'; packet=statement[:-10]+'.packet.json'
        try:
            with open(statement) as f: stmt=json.load(f)
            with open(packet) as f: pkt=json.load(f)
            digest=hashlib.sha256(json.dumps(pkt,sort_keys=True).encode()).hexdigest()
            if stmt.get('packet_digest')!=digest or pkt.get('root')!=checked['root'] or pkt.get('build_digest')!=build_digest(directory) or pkt.get('proof')!=manifest['proof'] or not stmt.get('proof_recorded'): continue
            if build._ssh_verify(Path(statement).read_bytes(),sig,anchor,stmt['identity']): return 'signed'
        except (OSError,ValueError,KeyError): continue
    return 'sealed'

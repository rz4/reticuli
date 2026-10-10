"""Public claim kernel: identity, judging, rebuilding, and comparison."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import platform
import venv

from ._kernel import core, recipe, identity, seal as sealing, run, build, attest, crosscheck as comparing

ClaimError = core.ClaimError
NAMESPACE = core.NAMESPACE
SIGN_NAMESPACE = core.SIGN_NAMESPACE
RECORD_NAMESPACE = attest.RECORD_NAMESPACE
RECORD_FORMAT = attest.RECORD_FORMAT
STORE = core.STORE
MANIFEST = core.MANIFEST
RECIPE = core.RECIPE
LEDGER = core.LEDGER
SIGN_DIR = core.SIGN_DIR
_JAILED = core._JAILED
_hash_file = core._hash_file
_original_load_recipe = recipe.load_recipe
_original_safe = core._safe

def load_recipe(directory):
    """Generated paths may be named at seal time; audit checks their bytes."""
    try:
        return _original_load_recipe(directory)
    except ClaimError as exc:
        if 'symlink in claim path' not in str(exc): raise
        path = recipe.recipe_path(directory)
        with open(path,'rb') as f: raw = tomllib.load(f)
        allowed = {s.get('output') for s in raw.get('step',[]) if s.get('kind')=='produce' and s.get('class','generated')=='generated'}
        def relaxed(base,name):
            if name in allowed:
                return os.path.join(os.path.realpath(base),name)
            return _original_safe(base,name)
        core._safe = relaxed
        try:
            return _original_load_recipe(directory)
        finally:
            core._safe = _original_safe
recipe.load_recipe = load_recipe
root = identity.root
build_digest = identity.build_digest
def seal(directory):
    parsed=load_recipe(directory)
    manifest={'name':parsed['claim']['name'],'root':root(parsed,directory)}
    core._write_json(core._safe(directory,MANIFEST),manifest)
    return manifest

def verify(directory):
    manifest=sealing.read_manifest(directory)
    parsed=load_recipe(directory)
    recomputed=root(parsed,directory)
    return {'ok':recomputed==manifest['root'] and parsed['claim']['name']==manifest['name'],
            'name':manifest['name'],'root':manifest['root'],'recomputed':recomputed}
read_manifest = sealing.read_manifest
ledger = run.ledger
ledger_events = run.ledger_events
preflight = run.preflight
record_canonical = attest.record_canonical
record_digest = attest.record_digest
record_validate = attest.record_validate
record_signer = attest.record_signer


def record_read(path):
    doc = attest.record_read(path)
    with open(path,'rb') as f:
        raw = f.read()
    if raw != attest.record_canonical(doc):
        raise ClaimError('record file is not canonical')
    return doc


def sandbox(command='true', directory='.'):
    return run._sandbox_argv(command,os.path.abspath(directory)), run.sandbox_backend()


def run_gate(command, directory, parsed=None, *, env=None):
    return run.run_gate(command,directory,parsed,env=env)


def cost(directory):
    totals = {}
    for event in ledger_events(directory):
        for key in core.COST_KEYS:
            value = event.get(key)
            if type(value) in (int,float) and value >= 0:
                totals[key] = totals.get(key,0) + value
    return totals or None


def _furnish(room,parsed):
    named=parsed['claim'].get('environment')
    if not named: return None
    lock=core._safe(room,named)
    digest=core._hash_file(lock)
    cache_key=hashlib.sha256(f"{digest}:{sys.executable}:{platform.platform()}".encode()).hexdigest()
    target=os.path.join(run._env_cache_dir(),cache_key)
    python=os.path.join(target,'bin','python')
    if not os.path.isfile(python):
        os.makedirs(os.path.dirname(target),exist_ok=True)
        venv.EnvBuilder(with_pip=True).create(target)
        done=subprocess.run([python,'-m','pip','install','--require-hashes','--only-binary=:all:','-r',lock],cwd=room,capture_output=True,text=True,timeout=core.FURNISH_TIMEOUT)
        if done.returncode:
            shutil.rmtree(target,ignore_errors=True)
            raise ClaimError('cannot furnish environment: '+done.stderr.strip())
    return target

def _gate_judge(source,room,parsed):
    missing = preflight(parsed)
    furnished = None
    if not missing:
        try:
            furnished = _furnish(room,parsed)
        except ClaimError as exc:
            missing = [str(exc)]
    rows=[]
    for step in recipe.gates(parsed):
        name=step['output']
        if missing:
            rows.append({'output':name,'status':'environment','quarantine':None,'detail':missing})
            continue
        path=core._safe(room,name)
        if os.path.lexists(path): os.unlink(path)
        extra={}
        if furnished: extra['PATH']=os.path.join(furnished,'bin')+os.pathsep+os.environ.get('PATH',os.defpath)
        outcome=run_gate(step['run'],room,parsed,env=extra)
        status=outcome['status']
        if status=='ok' and os.path.exists(core._safe(source,name)) and core._hash_file(path)!=core._hash_file(core._safe(source,name)):
            status='mismatch'
        rows.append({'output':name,'status':status,'quarantine':outcome['quarantine'],'stdout':outcome['stdout'],'stderr':outcome['stderr']})
        ledger(room,{'event':'gate','gate':name,'quarantine':outcome['quarantine'],'seconds':outcome['seconds']})
    return rows,missing


def audit(directory, *, produce_from=None, shallow=False):
    checked=verify(directory)
    if not checked['ok']:
        return {'ok':False,'root':checked['root'],'gates':[],'verdict':'identity mismatch'}
    parsed=load_recipe(directory)
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        build._materialize(directory,room,parsed,generated=True)
        if produce_from:
            for name,path in produce_from.items():
                if name in recipe.generated_outputs(parsed):
                    core._copy_into(path,core._safe(room,name))
        rows,missing=_gate_judge(directory,room,parsed)
    ok=all(row['status']=='ok' for row in rows)
    return {'ok':ok,'root':checked['root'],'gates':rows,'environment':missing,'verdict':'earned' if ok else 'broken'}


def _source_ready(directory):
    try:
        return verify(directory)
    except ClaimError as exc:
        if 'cannot read manifest' in str(exc):
            parsed=load_recipe(directory)
            return {'ok':True,'root':None,'name':parsed['claim']['name']}
        raise


def _snapshot(room,parsed):
    names=set(recipe._inputs(parsed,room))
    if parsed['claim'].get('environment'): names.add(parsed['claim']['environment'])
    names.add(os.path.basename(recipe.recipe_path(room)))
    return {name:core._hash_file(core._safe(room,name)) for name in names}


def rebuild(directory,producer,into,*,produce_from=None,input_from=None,guidance=True,producer_env=None):
    checked=_source_ready(directory)
    if not checked['ok']: raise ClaimError('source identity mismatch')
    parsed=load_recipe(directory)
    if os.path.exists(into) and os.listdir(into): raise ClaimError('rebuild target is not empty')
    missing=preflight(parsed)
    if missing: raise ClaimError('environment missing: '+', '.join(missing))
    build._materialize(directory,into,parsed)
    into=os.path.abspath(into)
    if input_from:
        for name,path in input_from.items():
            if name in recipe._inputs(parsed,directory): core._copy_into(path,core._safe(into,name))
    if produce_from:
        for name,path in produce_from.items():
            if name in recipe.generated_outputs(parsed):
                core._copy_into(path,core._safe(into,name))
                ledger(into,{'event':'reuse','output':name})
    snapshot=_snapshot(into,parsed)
    ledger(into,{'event':'environment','python':sys.version.split()[0], 'platform':sys.platform,'quarantine':run.sandbox_backend()})
    produced=[]
    for step in recipe.produces(parsed):
        name=step['output']
        if step.get('class','generated')!='generated' or 'from' in step or produce_from and name in produce_from: continue
        producer_variables={core._ENV_USAGE:core._safe(into,core.USAGE)}
        if producer_env: producer_variables.update(producer_env)
        result=build._produce(producer,into,step,parsed,guidance=guidance,producer_env=producer_variables)
        produced.append(result)
        if result['status']!='ok': raise ClaimError('producer '+result['status']+': '+result['stderr'][-300:])
        usage_path=core._safe(into,core.USAGE)
        usage={}
        if os.path.isfile(usage_path):
            try:
                reported=json.load(open(usage_path,encoding='utf-8'))
                if isinstance(reported,dict):
                    usage={k:v for k,v in reported.items() if k in ('usd','tokens','calls') and type(v) in (int,float) and v>=0}
            except (OSError,ValueError): pass
        event={'event':'producer','calls':1,'seconds':result['seconds'],'quarantine':result['quarantine'], 'vendor':os.environ.get(core._ENV_VENDOR), 'model':os.environ.get(core._ENV_MODEL), 'blind':True}
        event.update(usage)
        ledger(into,event)
    if _snapshot(into,parsed)!=snapshot: raise ClaimError('producer changed pinned bytes')
    rows,missing=_gate_judge(directory,into,parsed)
    if missing: raise ClaimError('environment missing: '+', '.join(missing))
    if any(row['status']!='ok' for row in rows): raise ClaimError('gate did not reproduce: '+repr(rows))
    manifest=seal(into)
    return {'ok':True,'root':manifest['root'],'gates':rows,'quarantine':produced[-1]['quarantine'] if produced else run.sandbox_backend(),'verdict':'earned'}


def sign_node(root_value,digest,links):
    return hashlib.sha256(json.dumps({'root':root_value,'build_digest':digest,'links':sorted(links)},sort_keys=True).encode()).hexdigest()


def phase(directory):
    load_recipe(directory)
    manifest_path=core._safe(directory,MANIFEST)
    if not os.path.exists(manifest_path): return 'draft'
    checked=verify(directory)
    if not checked['ok']: return 'sealed'
    if not read_manifest(directory).get('proof'): return 'sealed'
    anchor=os.environ.get(core._ENV_SIGNERS)
    if not anchor or not os.path.isfile(anchor): return 'sealed'
    sign_dir=core._safe(directory,SIGN_DIR)
    if not os.path.isdir(sign_dir): return 'sealed'
    for filename in os.listdir(sign_dir):
        if not filename.endswith('.sign.json'): continue
        statement_path=os.path.join(sign_dir,filename)
        packet_path=statement_path[:-10]+'.packet.json'
        try:
            with open(statement_path) as f: statement=json.load(f)
            with open(packet_path) as f: packet=json.load(f)
            pdig=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
            if statement.get('packet_digest')!=pdig or statement.get('root')!=checked['root'] or not statement.get('proof_recorded'): continue
            if packet != {'root':checked['root'],'build_digest':build_digest(directory),'proof':read_manifest(directory).get('proof')}: continue
            principal=statement.get('identity')
            if not principal: continue
            with open(statement_path,'rb') as f: data=f.read()
            done=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',principal,'-n',SIGN_NAMESPACE,'-s',statement_path+'.sig'],input=data,capture_output=True)
            if done.returncode==0: return 'signed'
        except (OSError,ValueError,ClaimError): continue
    return 'sealed'


def gate_deciders(command):
    words=shlex.split(command)
    result=[]
    for i,word in enumerate(words):
        if word in ('&&','||',';','|'): continue
        if word in ('python','python3','python2','py','pytest','py.test'):
            if i+1<len(words):
                if words[i+1]=='-m' and i+2<len(words):
                    module=words[i+2]
                    if module=='pytest':
                        result.extend(w for w in words[i+3:] if not w.startswith('-') and w not in ('&&','||',';','|','printf','ok','>','OK'))
                    else: result.append(module)
                elif not words[i+1].startswith('-'): result.append(words[i+1])
        elif word.startswith('./'): result.append(word[2:])
    return list(dict.fromkeys(result))


def vacuous_gates(parsed):
    generated=set(recipe.generated_outputs(parsed))
    pinned=set(parsed.get('claim',{}).get('inputs',[]))
    bad=[]
    for step in recipe.gates(parsed):
        deciders=gate_deciders(step['run'])
        if deciders and all(d in generated and d not in pinned for d in deciders): bad.append(step['output'])
    return bad


def independence(directory):
    result={'vendor':None,'model':None,'blind':False}
    if os.path.isdir(directory):
        for event in ledger_events(directory):
            if event.get('event')=='producer':
                result.update({k:event.get(k) for k in ('vendor','model','blind') if k in event})
    return result

mutation_score=comparing.mutation_score
crosscheck=comparing.crosscheck
record_proof=comparing.record_proof

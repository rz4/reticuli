"""Claim identity, local verification, rebuilding, and comparison."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import venv
from pathlib import Path
from typing import Any
from ._kernel import core, recipe as lower_recipe, identity as lower_identity, seal as lower_seal, run as lower_run, build as lower_build, attest as lower_attest, crosscheck as mutations

ClaimError = core.ClaimError
STORE, LEDGER, RECIPE, SIGN_DIR = core.STORE, core.LEDGER, core.RECIPE, core.SIGN_DIR
NAMESPACE, SIGN_NAMESPACE, RECORD_NAMESPACE = core.NAMESPACE, core.SIGN_NAMESPACE, 'reticuli.record'
RECORD_FORMAT = 2
_JAILED = core._JAILED
COST_UNITS = ('usd','tokens','calls','seconds')


def _safe(root: str, name: str) -> str:
    if not isinstance(name,str) or not name or os.path.isabs(name) or '..' in Path(name).parts:
        raise ClaimError(f'unsafe claim path: {name!r}')
    base=os.path.realpath(root)
    at=base
    for part in Path(name).parts:
        if part in ('', '.') : continue
        at=os.path.join(at,part)
        if os.path.islink(at): raise ClaimError(f'symlink in claim path: {name!r}')
    if os.path.commonpath((base,os.path.realpath(at)))!=base or at==base:
        raise ClaimError(f'unsafe claim path: {name!r}')
    return at


def _hash_file(path: str) -> str:
    try:
        s=os.stat(path,follow_symlinks=False)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise ClaimError(f'not an ordinary single-link file: {path}')
        return core._hash_file(path)
    except OSError as e: raise ClaimError(f'cannot read declared file {path}: {e}') from e


def _recipe_path(d):
    return lower_recipe.recipe_path(d)


def _inputs(data):
    claim=data['claim']; out=list(claim.get('inputs',[]))
    if 'environment' in claim and claim['environment'] not in out: out.append(claim['environment'])
    if 'inputs_manifest' in claim:
        p=claim['inputs_manifest']
        if p not in out: out.append(p)
        with open(_safe(data.get('_directory','.'),p),encoding='utf8') as f:
            for line in f:
                line=line.strip()
                if line and not line.startswith('#'):
                    out.append(line.split('  ',1)[-1] if re.match(r'^[0-9a-f]{64}  ',line) else line)
    return out


def _number(v,positive=False):
    return type(v) in (int,float) and math.isfinite(v) and (v>0 if positive else v>=0)


def load_recipe(d):
    try:
        with open(_recipe_path(d),'rb') as source: data=tomllib.load(source)
    except (OSError,ValueError,tomllib.TOMLDecodeError) as e: raise ClaimError(f'cannot read recipe: {e}') from e
    if not isinstance(data.get('claim'),dict) or not isinstance(data['claim'].get('name'),str) or not data['claim']['name']: raise ClaimError('claim requires name')
    if not isinstance(data.get('step',[]),list): raise ClaimError('invalid steps')
    for step in data.get('step',[]):
        if not isinstance(step,dict) or step.get('kind') not in ('produce','gate'): raise ClaimError('unknown step kind')
        if step.get('class') != ('generated' if step['kind']=='produce' else 'validated'): raise ClaimError('invalid step class')
        if not isinstance(step.get('output'),str): raise ClaimError('step output required')
        if step['kind']=='gate' and (not isinstance(step.get('run'),str) or not step['run']): raise ClaimError('gate command required')
    claim=data['claim']
    fmt=claim.get('format',1)
    if type(fmt) is not int or fmt<1 or fmt>3: raise ClaimError(f'unsupported claim format {fmt!r}')
    if 'environment' in claim and (not isinstance(claim['environment'],str) or not claim['environment']): raise ClaimError('environment must be a path')
    if 'envelope' in claim:
        envelope=claim['envelope']
        if not isinstance(envelope,dict) or not envelope or any(k not in COST_UNITS or not _number(v,True) for k,v in envelope.items()): raise ClaimError('invalid envelope')
    if 'mutation_floor' in claim and (not _number(claim['mutation_floor']) or claim['mutation_floor']>1): raise ClaimError('invalid mutation floor')
    if 'tolerance' in claim and not _number(claim['tolerance'],True): raise ClaimError('invalid tolerance')
    for path in list(claim.get('inputs',[]))+([claim['environment']] if 'environment' in claim else []): _safe(d,path)
    for step in data.get('step',[]):
        if step['kind']=='gate': _safe(d,step['output'])
        if 'guidance' in step and not isinstance(step['guidance'],str): raise ClaimError('guidance must be text')
    try: json.dumps(data,sort_keys=True)
    except (TypeError,ValueError) as e: raise ClaimError(f'uncanonical recipe: {e}') from e
    return data


def _preimage(data):
    x=copy.deepcopy(data)
    if x['claim'].get('format',1)>=3:
        for step in x.get('step',[]):
            if step.get('kind')=='produce':
                step.pop('request',None); step.pop('guidance',None)
    return x


def root(data,d):
    parts={'digest':'sha256','recipe':json.dumps(_preimage(data),sort_keys=True)}
    for name in _inputs(data): parts['input:'+name]=_hash_file(_safe(d,name))
    for step in data.get('step',[]):
        if step.get('class') not in ('generated','free'):
            name=step['output']; parts['pinned:'+name]=_hash_file(_safe(d,name))
    return hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest()


def build_digest(d):
    data=load_recipe(d); own=[]
    for step in data.get('step',[]):
        if step['kind']=='produce' and step.get('class')=='generated' and 'from' not in step:
            p=_safe(d,step['output'])
            if os.path.lexists(p): own.append([step['output'],_hash_file(p)])
    return hashlib.sha256(json.dumps(sorted(own),sort_keys=True).encode()).hexdigest()


def read_manifest(d):
    m=lower_seal.read_manifest(d)
    if not isinstance(m.get('name'),str) or not isinstance(m.get('root'),str): raise ClaimError('invalid manifest name or root')
    return m


def seal(d):
    data=load_recipe(d)
    m={'name':data['claim']['name'],'root':root(data,d),'format':data['claim'].get('format',1)}
    core._write_json(_safe(d,core.MANIFEST),m)
    return m


def verify(d):
    m=read_manifest(d); data=load_recipe(d); got=root(data,d)
    return {'ok':got==m['root'],'root':m['root'],'recomputed':got,'name':m['name']}


def _backend():
    if os.environ.get(_JAILED): return 'inherited'
    if sys.platform=='darwin' and shutil.which('sandbox-exec'): return 'seatbelt'
    if shutil.which('bwrap'):
        try:
            probe=subprocess.run(['bwrap','--ro-bind','/','/','--unshare-net','true'],capture_output=True,timeout=3)
            if probe.returncode==0: return 'bubblewrap'
        except (OSError,subprocess.TimeoutExpired): pass
    return 'none'


def sandbox(command,d):
    backend=_backend(); argv=['/bin/sh','-c',command]
    if backend=='seatbelt':
        base=os.path.realpath(d)
        profile='(version 1)(allow default)(deny network*)(deny file-write*)(allow file-write* (subpath '+json.dumps(base)+') (subpath "/dev"))'
        argv=['sandbox-exec','-p',profile,*argv]
    elif backend=='bubblewrap':
        base=os.path.realpath(d)
        argv=['bwrap','--ro-bind','/','/','--dev-bind','/dev','/dev','--proc','/proc','--bind',base,base,'--unshare-net','--die-with-parent',*argv]
    return argv,backend


def run_gate(command,d,recipe=None,env_extra=None):
    if recipe is None: recipe=load_recipe(d)
    claim=recipe.get('claim',{})
    timeout=min(float(os.environ.get('RETICULI_GATE_TIMEOUT',60)),float(claim.get('gate_timeout',60)))
    argv,backend=sandbox(command,d)
    scratch=os.path.join(os.path.realpath(d),STORE,'scratch')
    os.makedirs(scratch,exist_ok=True)
    env={k:os.environ[k] for k in core._KEEP_ENV if k in os.environ}
    env.update({'TMPDIR':scratch,'HOME':scratch})
    if backend in ('seatbelt','bubblewrap'): env[_JAILED]=backend
    if env_extra: env.update(env_extra)
    try:
        proc=subprocess.Popen(argv,cwd=d,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try: stdout,stderr=proc.communicate(timeout=timeout); status='ok' if proc.returncode==0 else 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL); stdout,stderr=proc.communicate(); status='timeout'
        return {'status':status,'stdout':stdout,'stderr':stderr,'returncode':proc.returncode,'quarantine':backend}
    except OSError as e: return {'status':'failed','stdout':'','stderr':str(e),'returncode':None,'quarantine':backend}


def preflight(data):
    missing=[]
    for req in data.get('claim',{}).get('requires',[]):
        if req.startswith('python') and re.match(r'python(?:[<>=!~].*)?$',req):
            if not shutil.which('python3'): missing.append(req)
        elif not shutil.which(req): missing.append(req)
    return missing


def _furnish(d,data):
    lock=data['claim'].get('environment')
    if not lock: return None
    path=_safe(d,lock)
    try:
        lines=Path(path).read_text().splitlines()
        wheels=[]
        for line in lines:
            line=line.split('#',1)[0].strip()
            if not line: continue
            match=re.search(r'--hash=sha256:([0-9a-f]{64})',line)
            name=line.split()[0]
            if not match or not name.endswith('.whl'): return None
            wheel=_safe(d,name.removeprefix('./'))
            if _hash_file(wheel)!=match.group(1): return None
            wheels.append(wheel)
        if not wheels: return None
        cache=os.environ.get('RETICULI_ENV_CACHE',os.path.join(d,STORE,'env'))
        key=hashlib.sha256((_hash_file(path)+sys.executable+sys.platform).encode()).hexdigest()
        target=os.path.join(cache,key)
        py=os.path.join(target,'bin','python3')
        if not os.path.isfile(py):
            os.makedirs(cache,exist_ok=True)
            venv.EnvBuilder(with_pip=True).create(target)
            result=subprocess.run([py,'-m','pip','install','--no-index','--no-deps','--only-binary=:all:',*wheels],capture_output=True,text=True,timeout=60)
            if result.returncode: return None
        return os.path.join(target,'bin')
    except (OSError,ClaimError,subprocess.TimeoutExpired): return None


def _copy_file(src,dst):
    _hash_file(src)
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    shutil.copyfile(src,dst)


def _room(source,dest,data,produce_from=None,input_from=None,generated=True):
    produce_from=produce_from or {}; input_from=input_from or {}
    recipe_name=os.path.basename(_recipe_path(source))
    if data['claim'].get('format',1)>=3:
        Path(dest,recipe_name).write_text(''.join(line for line in Path(_recipe_path(source)).read_text().splitlines(True) if not re.match(r'\s*(?:guidance|request)\s*=', line)))
    else: _copy_file(_recipe_path(source),_safe(dest,recipe_name))
    for name in _inputs(data): _copy_file(input_from.get(name,_safe(source,name)),_safe(dest,name))
    if generated:
        for step in data.get('step',[]):
            if step.get('kind')=='produce':
                name=step['output']; _copy_file(produce_from.get(name,_safe(source,name)),_safe(dest,name))


def _toml_recipe(data):
    lines=['[claim]']
    for k,v in data['claim'].items(): lines.append(f'{k} = {json.dumps(v)}')
    for step in data.get('step',[]):
        lines.extend(['','[[step]]'])
        for k,v in step.items(): lines.append(f'{k} = {json.dumps(v)}')
    return '\n'.join(lines)+'\n'


def audit(d,produce_from=None):
    checked=verify(d)
    result={'ok':False,'gates':[],'seal':checked}
    if not checked['ok']: return result
    data=load_recipe(d)
    missing=preflight(data)
    if missing: result['environment']=missing
    with tempfile.TemporaryDirectory(prefix='reticuli-audit-') as room:
        _room(d,room,data,produce_from)
        envbin=_furnish(room,data) if data['claim'].get('environment') else None
        for step in data.get('step',[]):
            if step['kind']!='gate': continue
            name=step['output']
            if missing or (data['claim'].get('environment') and not envbin):
                gate={'output':name,'status':'environment','quarantine':None,'stdout':'','stderr':''}
                result['gates'].append(gate); continue
            extra={'PATH':envbin+os.pathsep+os.environ.get('PATH','')} if envbin else None
            out=run_gate(step['run'],room,data,extra)
            gate={'output':name,**out}
            if gate['status']=='ok':
                p=_safe(room,name)
                if not os.path.isfile(p): gate['status']='failed'
                elif _hash_file(p)!=_hash_file(_safe(d,name)): gate['status']='mismatch'
            result['gates'].append(gate)
    result['ok']=not missing and all(g['status']=='ok' for g in result['gates'])
    return result


def _ledger(d,event):
    path=_safe(d,LEDGER); os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'a') as f: f.write(json.dumps(event,sort_keys=True)+'\n')


def cost(d):
    path=_safe(d,LEDGER)
    if not os.path.isfile(path): return None
    totals={}
    try:
        for line in Path(path).read_text().splitlines():
            event=json.loads(line)
            for k in COST_UNITS:
                v=event.get(k)
                if _number(v): totals[k]=totals.get(k,0)+v
    except (OSError,ValueError,TypeError) as e: raise ClaimError(f'invalid ledger: {e}') from e
    return totals or None


def rebuild(source,producer,into,produce_from=None,input_from=None):
    data=load_recipe(source)
    if preflight(data): raise ClaimError('environment missing: '+', '.join(preflight(data)))
    if os.path.isdir(into) and os.listdir(into): raise ClaimError('rebuild target contains bytes')
    if os.path.exists(into) and not os.path.isdir(into): raise ClaimError('rebuild target is not a directory')
    os.makedirs(into,exist_ok=True)
    into=os.path.abspath(into)
    _room(source,into,data,produce_from,input_from,generated=False)
    recipe_name=os.path.basename(_recipe_path(source))
    pins={name:_hash_file(_safe(into,name)) for name in [recipe_name,*_inputs(data)]}
    for name,path in (produce_from or {}).items():
        _copy_file(path,_safe(into,name)); _ledger(into,{'event':'reuse','output':name})
    envbin=_furnish(into,data) if data['claim'].get('environment') else None
    if data['claim'].get('environment') and not envbin: raise ClaimError('environment cannot be furnished')
    _ledger(into,{'event':'environment','python':sys.version.split()[0],'platform':sys.platform,'quarantine':_backend()})
    _ledger(into,{'event':'producer','vendor':os.environ.get('RETICULI_VENDOR',''),
                  'model':os.environ.get('RETICULI_MODEL',''),'blind':True})
    outputs=[s['output'] for s in data.get('step',[]) if s['kind']=='produce' and s['output'] not in (produce_from or {})]
    usage=os.path.join(into,STORE,'usage.json'); os.makedirs(os.path.dirname(usage),exist_ok=True)
    env={**os.environ,'RETICULI_USAGE':usage,'RETICULI_OUTPUT':_safe(into,outputs[0]) if outputs else '', 'RETICULI_OUTPUTS':json.dumps(outputs)}
    if envbin: env['PATH']=envbin+os.pathsep+env.get('PATH','')
    guidance='\n'.join(str(s.get('guidance',s.get('request',''))) for s in data.get('step',[]) if s['kind']=='produce')
    env['RETICULI_REQUEST']=guidance
    start=time.monotonic()
    try: done=subprocess.run(producer,shell=True,cwd=into,env=env,capture_output=True,text=True,timeout=core.PRODUCER_TIMEOUT)
    except subprocess.TimeoutExpired as e: raise ClaimError('producer timeout') from e
    seconds=time.monotonic()-start
    if done.returncode: raise ClaimError(f'producer failed: {done.stderr[-300:]}')
    for name,digest in pins.items():
        if _hash_file(_safe(into,name))!=digest: raise ClaimError(f'producer changed pinned bytes: {name}')
    event={'event':'oracle','calls':1,'seconds':seconds}
    try:
        reported=json.loads(Path(usage).read_text())
        if isinstance(reported,dict):
            for k in ('calls','tokens','usd'):
                if _number(reported.get(k)): event[k]=reported[k]
    except (OSError,ValueError): pass
    _ledger(into,event)
    producer_record={'event':'producer','blind':True}
    for key in ('VENDOR','MODEL'):
        value=os.environ.get('RETICULI_'+key)
        if value: producer_record[key.lower()]=value
    if len(producer_record)>2: _ledger(into,producer_record)
    for step in data.get('step',[]):
        if step['kind']!='gate': continue
        extra={'PATH':envbin+os.pathsep+os.environ.get('PATH','')} if envbin else None
        outcome=run_gate(step['run'],into,data,extra)
        _ledger(into,{'event':'gate','gate':step['output'],'status':outcome['status'],'quarantine':outcome['quarantine']})
        if outcome['status']!='ok': raise ClaimError(f"gate {step['output']} {outcome['status']}: {outcome['stderr'][-200:]}")
    return seal(into)


def sign_node(root_value,digest,components):
    return hashlib.sha256(json.dumps([root_value,digest,sorted(components)],sort_keys=True).encode()).hexdigest()


def independence(d):
    path=_safe(d,LEDGER)
    if not os.path.isfile(path): return {}
    for line in Path(path).read_text().splitlines():
        event=json.loads(line)
        if event.get('event')=='producer': return {k:event[k] for k in ('vendor','model','blind') if k in event}
    return {}


def _machine(path):
    if os.path.isdir(path):
        check=verify(path); result=audit(path); data=load_recipe(path)
        return {'root':check['root'],'digest':build_digest(path),'audited':result['ok'],
                'cost':cost(path),'claim':{k:data['claim'][k] for k in ('tolerance','envelope','mutation_floor') if k in data['claim']},
                'producer':independence(path)}
    doc=record_read(path)
    return {'root':doc['root'],'digest':doc['build_digest'],
            'audited':all(g['status']=='ok' for g in doc['gates']),
            'cost':doc.get('cost'),'claim':doc.get('claim'),'producer':doc.get('producer',{})}


def _cost_comparison(left,right,tolerance=2.0):
    if left and right:
        for unit in COST_UNITS:
            if unit in left and unit in right:
                a,b=left[unit],right[unit]
                ratio=max(a,b)/min(a,b) if min(a,b)>0 else (1 if a==b else float('inf'))
                return {'comparable':ratio<=tolerance,'unit':unit,'ratio':ratio}
    return {'comparable':None,'unit':None,'ratio':None}


def crosscheck(m1,m2,m3,mutants=None):
    if len({os.path.realpath(p) for p in (m1,m2,m3)})!=3: raise ClaimError('machines must be distinct')
    a,b,c=map(_machine,(m1,m2,m3))
    roots={'M1':a['root'],'M2':b['root'],'M3':c['root']}
    equivalence=len(set(roots.values()))==1
    reuse=a['digest']==b['digest']
    audited={'M1':a['audited'],'M2':b['audited'],'M3':c['audited']}
    claim=a['claim']; comparison=_cost_comparison(a['cost'],c['cost'],(claim or {}).get('tolerance',2.0))
    cost_report={**comparison,'envelope':{}}
    rejected=[]; incomplete=[]
    if not equivalence: rejected.append('root')
    if not reuse: rejected.append('reuse')
    for key,passed in audited.items():
        if not passed: rejected.append('audit '+key)
    if claim is None: incomplete.append('claim obligations')
    else:
        if 'tolerance' in claim:
            if comparison['comparable'] is False: rejected.append('tolerance')
            elif comparison['comparable'] is None: incomplete.append('tolerance')
        for unit,ceiling in claim.get('envelope',{}).items():
            amount=(c['cost'] or {}).get(unit)
            within=None if amount is None else amount<=ceiling
            cost_report['envelope'][unit]={'within':within,'limit':ceiling,'measured':amount}
            if within is False: rejected.append('envelope '+unit)
            elif within is None: incomplete.append('envelope '+unit)
    score=None
    if claim and 'mutation_floor' in claim:
        if mutants is None: incomplete.append('mutation floor')
        else:
            score=mutation_score(m3,max_mutants=mutants)
            score['ok']=score['rate']>=claim['mutation_floor']
            if not score['ok']: rejected.append('mutation floor')
    verdict='reject' if rejected else 'incomplete' if incomplete else 'accept'
    producer=c['producer']
    if producer.get('vendor') and producer.get('model'):
        independence_text=f"declared: {producer['vendor']}/{producer['model']}, {'blind workspace' if producer.get('blind') else 'workspace'}, not proven"
    else: independence_text='unestablished from content'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rejected,'incomplete':incomplete,
            'equivalence':equivalence,'reuse':reuse,'roots':roots,'audited':audited,'cost':cost_report,
            'mutation_score':score,'independence':independence_text}


def record_proof(m1,m2,m3):
    if not os.path.isdir(m1): raise ClaimError('proof must land on a directory')
    result=crosscheck(m1,m2,m3)
    if not result['satisfied']: return {'proof_recorded':False,**result}
    records=[]
    for path in (m2,m3):
        if not os.path.isdir(path):
            doc=record_read(path)
            records.append({'digest':record_digest(doc),'signer':_verify_record_signature(path)})
    manifest=read_manifest(m1)
    manifest['proof']={'kind':'crosscheck','roots':result['roots'],'records':records}
    core._write_json(_safe(m1,core.MANIFEST),manifest)
    return {'proof_recorded':True,**result}


def record_validate(doc):
    if not isinstance(doc,dict): raise ClaimError('record must be an object')
    version=doc.get('record')
    if type(version)!=int or version not in (1,2): raise ClaimError('unknown record version')
    required={'record','name','root','build_digest','gates','environment','when'}
    allowed=required|{'cost','producer','tool'}|({'claim'} if version==2 else set())
    if version==2: required.add('claim')
    if not required<=doc.keys() or not doc.keys()<=allowed: raise ClaimError('record members invalid')
    if not isinstance(doc['name'],str) or not doc['name']: raise ClaimError('name invalid')
    for key in ('root','build_digest'):
        if not isinstance(doc[key],str) or not re.fullmatch('[0-9a-f]{64}',doc[key]): raise ClaimError(f'{key} invalid')
    if not isinstance(doc['when'],str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',doc['when']): raise ClaimError('when invalid')
    env=doc['environment']
    if not isinstance(env,dict) or env.keys()!={'platform','machine','runtime'} or any(not isinstance(v,str) or not v for v in env.values()): raise ClaimError('environment invalid')
    if not isinstance(doc['gates'],list): raise ClaimError('gates invalid')
    for gate in doc['gates']:
        if not isinstance(gate,dict) or gate.keys()!={'output','status','sandbox'}: raise ClaimError('gate invalid')
        if not isinstance(gate['output'],str) or not gate['output'] or gate['status'] not in ('ok','failed','timeout','environment','mismatch') or gate['sandbox'] not in ('none','seatbelt','bubblewrap','inherited'): raise ClaimError('gate invalid')
    if 'cost' in doc:
        value=doc['cost']
        if not isinstance(value,dict) or any(k not in COST_UNITS or not _number(v) for k,v in value.items()): raise ClaimError('cost invalid')
    if 'producer' in doc:
        value=doc['producer']
        if not isinstance(value,dict) or any(k not in ('vendor','model','cutoff','blind') for k in value): raise ClaimError('producer invalid')
        if any(not isinstance(v,str) or not v for k,v in value.items() if k!='blind') or ('blind' in value and type(value['blind'])!=bool): raise ClaimError('producer invalid')
    if 'tool' in doc and (not isinstance(doc['tool'],str) or not doc['tool']): raise ClaimError('tool invalid')
    if version==2:
        value=doc['claim']
        if not isinstance(value,dict) or any(k not in ('envelope','tolerance','mutation_floor') for k in value): raise ClaimError('claim invalid')
        if 'envelope' in value and (not isinstance(value['envelope'],dict) or not value['envelope'] or any(k not in COST_UNITS or not _number(v) for k,v in value['envelope'].items())): raise ClaimError('envelope invalid')
        for key in ('tolerance','mutation_floor'):
            if key in value and not _number(value[key]): raise ClaimError(f'{key} invalid')


def record_canonical(doc):
    record_validate(doc)
    return json.dumps(doc,sort_keys=True).encode()


def record_digest(doc): return hashlib.sha256(record_canonical(doc)).hexdigest()


def record_read(path):
    try: raw=Path(path).read_bytes(); doc=json.loads(raw)
    except (OSError,ValueError,UnicodeError) as e: raise ClaimError(f'cannot read record: {e}') from e
    if raw!=record_canonical(doc): raise ClaimError('record is not canonical')
    return doc


def record_signer(doc):
    record_validate(doc)
    return doc.get('producer')


def _verify_record_signature(path):
    anchor=os.environ.get('RETICULI_SIGNERS')
    if not anchor or not os.path.isfile(anchor): raise ClaimError('record has no trust anchor')
    for line in Path(anchor).read_text().splitlines():
        signer=line.split()[0]
        try:
            done=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',signer,'-n',RECORD_NAMESPACE,'-s',path+'.sig'],input=Path(path).read_bytes(),capture_output=True)
            if done.returncode==0: return signer
        except OSError: pass
    raise ClaimError('record signature untrusted')


def _signed(d,manifest):
    anchor=os.environ.get('RETICULI_SIGNERS')
    if not anchor or not os.path.isfile(anchor): return False
    folder=_safe(d,SIGN_DIR)
    if not os.path.isdir(folder): return False
    expected={'root':manifest['root'],'build_digest':build_digest(d),'proof':manifest['proof']}
    for filename in os.listdir(folder):
        if not filename.endswith('.sign.json'): continue
        statement_path=os.path.join(folder,filename)
        packet_path=statement_path[:-10]+'.packet.json'
        try:
            statement=json.loads(Path(statement_path).read_text())
            packet=json.loads(Path(packet_path).read_text())
            if packet!=expected: continue
            digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
            if statement.get('packet_digest')!=digest or statement.get('root')!=manifest['root'] or not statement.get('proof_recorded'): continue
            done=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',statement['identity'],'-n',SIGN_NAMESPACE,'-s',statement_path+'.sig'],input=Path(statement_path).read_bytes(),capture_output=True)
            if done.returncode==0: return True
        except (OSError,ValueError,KeyError,subprocess.SubprocessError): pass
    return False


def phase(d):
    load_recipe(d)
    if not os.path.exists(_safe(d,core.MANIFEST)): return 'draft'
    checked=verify(d)
    if not checked['ok']: return 'draft'
    manifest=read_manifest(d)
    if manifest.get('proof') and _signed(d,manifest): return 'signed'
    return 'sealed'


def gate_deciders(command):
    tokens=re.findall(r'[A-Za-z0-9_./-]+|&&|[;|&]',command)
    found=[]
    for i,token in enumerate(tokens):
        if token in ('python','python3','pytest','py.test'):
            if i+2<len(tokens) and tokens[i+1]=='-m' and tokens[i+2]=='pytest':
                for j in range(i+3,len(tokens)):
                    if tokens[j] in ('&&',';','|','&'): break
                    if not tokens[j].startswith('-'): found.append(tokens[j]); break
            elif i+1<len(tokens) and tokens[i+1].endswith('.py'): found.append(tokens[i+1])
        elif token.startswith('./'): found.append(token[2:])
    return found


def vacuous_gates(data):
    generated=set(lower_recipe.generated_outputs(data)); pinned=set(data['claim'].get('inputs',[]))
    return [gate['output'] for gate in lower_recipe.gates(data) if (deciders:=gate_deciders(gate['run'])) and all(name in generated and name not in pinned for name in deciders)]


def mutation_score(d,max_mutants=6):
    data=load_recipe(d)
    outputs=[s['output'] for s in lower_recipe.produces(data) if s['output'].endswith('.py')]
    survivors=[]; killed=0; count=0
    if outputs:
        name=outputs[0]; original=Path(_safe(d,name)).read_text()
        variants=[]
        for old,new in [(' > ',' < '),(' - ',' + '),(' + ',' - '),(' == ',' != '),('return ','return 0 # '),('if ','if False and ')]:
            if old in original: variants.append(original.replace(old,new,1))
        while variants and count<max_mutants:
            variant=variants[count%len(variants)]; count+=1
            with tempfile.TemporaryDirectory() as room:
                _room(d,room,data)
                Path(_safe(room,name)).write_text(variant)
                passed=all(run_gate(g['run'],room,data)['status']=='ok' for g in lower_recipe.gates(data))
                if passed: survivors.append(count)
                else: killed+=1
    result={'mutants':count,'killed':killed,'survivors':survivors,'rate':killed/count if count else 0.0}
    core._write_json(_safe(d,STORE+'/mutation_score.json'),result)
    return result

def sign_node(root,digest,links):
    return hashlib.sha256(json.dumps([root,digest,sorted(links)],sort_keys=True).encode()).hexdigest()


def gate_deciders(command):
    words=shlex.split(command)
    found=[]
    for i,word in enumerate(words):
        if word in ('python','python3','pytest','py.test') and i+1<len(words):
            nextword=words[i+1]
            if nextword=='-m' and i+2<len(words) and words[i+2]=='pytest':
                for x in words[i+3:]:
                    if not x.startswith('-') and x not in ('&&',';'): found.append(x); break
            elif not nextword.startswith('-'): found.append(nextword)
        if word.startswith('./'): found.append(word[2:])
    return list(dict.fromkeys(found))


def vacuous_gates(data):
    generated={s['output'] for s in data.get('step',[]) if s.get('kind')=='produce'}
    pinned=set(data.get('claim',{}).get('inputs',[]))
    return [s['output'] for s in data.get('step',[]) if s.get('kind')=='gate' and (dec:=gate_deciders(s['run'])) and all(x in generated and x not in pinned for x in dec)]


def mutation_score(d,max_mutants=12):
    data=load_recipe(d); candidates=[]
    for step in data.get('step',[]):
        if step['kind']=='produce' and step['output'].endswith('.py'):
            name=step['output']; source=Path(_safe(d,name)).read_text()
            candidates.extend((name,x) for x in mutations._mutants(source))
    candidates=mutations._mutant_order(candidates,root(data,d))[:max_mutants]
    survivors=[]
    for i,(name,body) in enumerate(candidates):
        with tempfile.TemporaryDirectory(prefix='reticuli-mut-') as tmp:
            changed=os.path.join(tmp,os.path.basename(name)); Path(changed).write_text(body)
            try: ok=audit(d,produce_from={name:changed})['ok']
            except ClaimError: ok=False
            if ok: survivors.append(i)
    n=len(candidates); rate=(n-len(survivors))/n if n else 0.0
    result={'mutants':n,'survivors':survivors,'rate':rate}
    core._write_json(_safe(d,core.MUTATION_RESIDUE),result)
    return result


def independence(d):
    path=_safe(d,LEDGER)
    if not os.path.isfile(path): return {}
    for line in reversed(Path(path).read_text().splitlines()):
        e=json.loads(line)
        if e.get('event')=='producer': return {k:e[k] for k in ('vendor','model','blind') if k in e}
    return {}


def _leg(path):
    if os.path.isdir(path):
        v=verify(path); a=audit(path)
        return {'root':v['root'],'digest':build_digest(path),'ok':v['ok'] and a['ok'],
                'cost':cost(path),'claim':load_recipe(path)['claim'],'record':False}
    doc=record_read(path)
    return {'root':doc['root'],'digest':doc['build_digest'],
            'ok':all(g['status']=='ok' for g in doc['gates']),
            'cost':doc.get('cost'),'claim':doc.get('claim'),'record':True}


def crosscheck(m1,m2,m3,mutants=None):
    if len({os.path.realpath(x) for x in (m1,m2,m3)})!=3: raise ClaimError('three distinct machines required')
    legs={name:_leg(path) for name,path in (('M1',m1),('M2',m2),('M3',m3))}
    roots={k:v['root'] for k,v in legs.items()}
    equivalent=len(set(roots.values()))==1
    reuse=legs['M1']['digest']==legs['M2']['digest']
    audited={k:v['ok'] for k,v in legs.items()}
    c1,c3=legs['M1']['cost'],legs['M3']['cost']
    unit=next((k for k in COST_UNITS if c1 and c3 and k in c1 and k in c3),None)
    tolerance=(legs['M1']['claim'] or {}).get('tolerance',2.0)
    if unit:
        x,y=c1[unit],c3[unit]
        comparable=(x==y==0 or x>0 and y>0 and 1/tolerance<=y/x<=tolerance)
    else: comparable=None
    cost_report={'comparable':comparable,'unit':unit,'envelope':{}}
    rejected=[]; incomplete=[]
    if not equivalent: rejected.append('root')
    if not reuse: rejected.append('reuse')
    if not all(audited.values()): rejected.append('audit')
    claim=legs['M1']['claim']
    if claim is None: incomplete.append('declared conditions')
    else:
        if 'tolerance' in claim and comparable is False: rejected.append('tolerance')
        for unit,ceiling in claim.get('envelope',{}).items():
            measured=c3.get(unit) if c3 else None
            within=(measured<=ceiling) if measured is not None else None
            cost_report['envelope'][unit]={'limit':ceiling,'measured':measured,'within':within}
            if within is False: rejected.append('envelope '+unit)
            if within is None: incomplete.append('envelope '+unit)
    score=None
    if claim and 'mutation_floor' in claim:
        if mutants is None: incomplete.append('mutation floor')
        elif os.path.isdir(m1):
            score=mutation_score(m1,max_mutants=mutants)
            score['ok']=score['rate']>=claim['mutation_floor']
            if not score['ok']: rejected.append('mutation floor')
        else: incomplete.append('mutation floor')
    ind=independence(m3) if os.path.isdir(m3) else (record_read(m3).get('producer') or {})
    if ind.get('vendor') and ind.get('model'):
        independence_text=f"declared: {ind['vendor']}/{ind['model']}, blind workspace ({'not proven' if ind.get('blind') else 'not proven'})"
    else: independence_text='unestablished (not proven)'
    verdict='reject' if rejected else 'incomplete' if incomplete else 'accept'
    return {'satisfied':verdict=='accept','verdict':verdict,'rejected':rejected,'incomplete':incomplete,
            'equivalence':equivalent,'reuse':reuse,'audited':audited,'roots':roots,
            'cost':cost_report,'mutation_score':score,'independence':independence_text}


def record_proof(m1,m2,m3,**kwargs):
    if not os.path.isdir(m1): raise ClaimError('proof target must be a claim directory')
    result=crosscheck(m1,m2,m3,**kwargs)
    if not result['satisfied']: return {'proof_recorded':False,'crosscheck':result}
    records=[]
    for p in (m2,m3):
        if not os.path.isdir(p):
            signer=record_signer(p,os.environ.get('RETICULI_SIGNERS'))
            if not signer: raise ClaimError('record signature is not anchored')
            records.append({'digest':record_digest(record_read(p)),'signer':signer})
    manifest=read_manifest(m1)
    manifest['proof']={'kind':'crosscheck','roots':result['roots'],'records':records}
    core._write_json(_safe(m1,core.MANIFEST),manifest)
    return {'proof_recorded':True,'crosscheck':result}


def _ssh_verify(data_path,sig_path,identity,namespace,anchor):
    try:
        with open(data_path,'rb') as f:
            done=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',identity,'-n',namespace,'-s',sig_path],stdin=f,capture_output=True,timeout=10)
        return done.returncode==0
    except (OSError,subprocess.TimeoutExpired): return False


def phase(d):
    load_recipe(d)
    try: v=verify(d)
    except ClaimError as e:
        if not os.path.isfile(_safe(d,core.MANIFEST)): return 'draft'
        raise
    if not v['ok']: return 'draft'
    manifest=read_manifest(d)
    anchor=os.environ.get('RETICULI_SIGNERS')
    if not anchor or not manifest.get('proof'): return 'sealed'
    folder=_safe(d,SIGN_DIR)
    if not os.path.isdir(folder): return 'sealed'
    for name in os.listdir(folder):
        if not name.endswith('.sign.json'): continue
        stmt=os.path.join(folder,name); packet=stmt[:-10]+'.packet.json'
        try:
            doc=json.loads(Path(stmt).read_text()); pack=json.loads(Path(packet).read_text())
            digest=hashlib.sha256(json.dumps(pack,sort_keys=True).encode()).hexdigest()
            if doc.get('packet_digest')!=digest or doc.get('root')!=v['root']: continue
            if pack!={'root':v['root'],'build_digest':build_digest(d),'proof':manifest['proof']}: continue
            if not doc.get('proof_recorded'): continue
            if _ssh_verify(stmt,stmt+'.sig',doc['identity'],SIGN_NAMESPACE,anchor): return 'signed'
        except (OSError,ValueError,KeyError,ClaimError): continue
    return 'sealed'


def record_validate(doc):
    if not isinstance(doc,dict): raise ClaimError('record must be an object')
    ver=doc.get('record')
    if type(ver) is not int or ver not in (1,2): raise ClaimError('unsupported record version')
    required={'record','name','root','build_digest','gates','environment','when'} | ({'claim'} if ver==2 else set())
    allowed=required|{'cost','producer','tool'}
    if not required<=doc.keys() or not doc.keys()<=allowed: raise ClaimError('invalid record members')
    if not isinstance(doc['name'],str) or not doc['name']: raise ClaimError('invalid name')
    for k in ('root','build_digest'):
        if not isinstance(doc[k],str) or not re.fullmatch('[0-9a-f]{64}',doc[k]): raise ClaimError('invalid '+k)
    if not isinstance(doc['when'],str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',doc['when']): raise ClaimError('invalid when')
    env=doc['environment']
    if not isinstance(env,dict) or set(env)!={'platform','machine','runtime'} or any(not isinstance(v,str) or not v for v in env.values()): raise ClaimError('invalid environment')
    if not isinstance(doc['gates'],list): raise ClaimError('invalid gates')
    for g in doc['gates']:
        if not isinstance(g,dict) or set(g)!={'output','status','sandbox'} or not isinstance(g['output'],str) or not g['output'] or g['status'] not in ('ok','failed','timeout','mismatch','environment') or g['sandbox'] not in ('none','seatbelt','bubblewrap','inherited'): raise ClaimError('invalid gate')
    if 'cost' in doc:
        c=doc['cost']
        if not isinstance(c,dict) or any(k not in COST_UNITS or not _number(v) for k,v in c.items()): raise ClaimError('invalid cost')
    if 'claim' in doc:
        c=doc['claim']
        if not isinstance(c,dict) or any(k not in ('tolerance','envelope','mutation_floor') for k in c): raise ClaimError('invalid claim obligations')
        if 'tolerance' in c and not _number(c['tolerance'],True): raise ClaimError('invalid tolerance')
        if 'mutation_floor' in c and (not _number(c['mutation_floor']) or c['mutation_floor']>1): raise ClaimError('invalid mutation floor')
        if 'envelope' in c and (not isinstance(c['envelope'],dict) or not c['envelope'] or any(k not in COST_UNITS or not _number(v,True) for k,v in c['envelope'].items())): raise ClaimError('invalid envelope')
    if 'producer' in doc:
        p=doc['producer']
        if not isinstance(p,dict) or any(k not in ('vendor','model','cutoff','blind') for k in p) or any(k!='blind' and (not isinstance(v,str) or not v) or k=='blind' and type(v) is not bool for k,v in p.items()): raise ClaimError('invalid producer')
    if 'tool' in doc and (not isinstance(doc['tool'],str) or not doc['tool']): raise ClaimError('invalid tool')


def record_canonical(doc): record_validate(doc); return json.dumps(doc,sort_keys=True).encode()
def record_digest(doc): return hashlib.sha256(record_canonical(doc)).hexdigest()
def record_read(path):
    try: raw=Path(path).read_bytes(); doc=json.loads(raw)
    except (OSError,UnicodeError,ValueError) as e: raise ClaimError(f'cannot read record: {e}') from e
    if raw!=record_canonical(doc): raise ClaimError('record is not canonical')
    return doc


def record_signer(path,anchor=None):
    if not anchor: return None
    record_read(path)
    try:
        for line in Path(anchor).read_text().splitlines():
            ident=line.split()[0]
            if _ssh_verify(path,path+'.sig',ident,RECORD_NAMESPACE,anchor): return ident
    except (OSError,IndexError): pass
    return None

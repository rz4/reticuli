import os,shutil,tempfile,json,time,subprocess,glob
from .core import *
from .core import _safe,_hash_file,_copy_into,_write_json,_judging_host,_now
from .recipe import load_recipe,recipe_path,_inputs,produces,gates,step_class,number
from .identity import _preimage_recipe,_claim_format,build_digest,root
from .seal import verify,seal,read_manifest
from .run import run_gate,preflight,furnish,ledger,_scrub_env,_run,sandbox_backend

def _step_guidance(s): return s.get('guidance',s.get('request'))
def _materialize(src,d,r=None,produce_from=None,input_from=None,generated=True):
    r=r or load_recipe(src); os.makedirs(d,exist_ok=True)
    rp=recipe_path(src); target=os.path.join(d,os.path.basename(rp))
    if _claim_format(r)>=3:
        with open(target,'w') as f: f.write(dump_toml(_preimage_recipe(r)))
    else: shutil.copy2(rp,target)
    for p in _inputs(r,src): _copy_into((input_from or {}).get(p,_safe(src,p)),d,p)
    for s in produces(r):
        p=s['output']; override=(produce_from or {}).get(p)
        if override or generated or step_class(s) not in ('generated','free'):
            source=override or _safe(src,p)
            if os.path.exists(source): _copy_into(source,d,p)
    occupied=set(_inputs(r,src)+[s['output'] for s in produces(r)])
    for member in r['claim'].get('assembles',[]):
        name,want=member.split('@'); m=os.path.join(src,STORE,'sealed',name)
        mr=load_recipe(m)
        if root(mr,m)!=want: raise ClaimError(f'assembly member {name} differs from declared root')
        for s in produces(mr):
            p=s['output']
            if p in occupied: raise ClaimError(f'assembly path collision: {p}')
            occupied.add(p); _copy_into(_safe(m,p),d,p)
        dest=os.path.join(d,STORE,'sealed',name)
        shutil.copytree(m,dest,dirs_exist_ok=True)
    return r

def _compare_pin(src,d,p):
    try: return _hash_file(_safe(src,p))==_hash_file(_safe(d,p))
    except ClaimError: return False

def audit(d,produce_from=None,strict=False,**kw):
    start=time.monotonic(); r=load_recipe(d); v=verify(d)
    result={**v,'elapsed':0,'environment':[],'gates':[],'layers':[],'verdict':'broken' if not v['ok'] else 'earned'}
    with tempfile.TemporaryDirectory(prefix='ret-audit-') as room:
        _materialize(d,room,r,produce_from)
        missing=preflight(r); env={}
        if not missing:
            try: env=furnish(r,room)
            except (ClaimError,subprocess.SubprocessError) as e: missing=[str(e)]
        result['environment']=missing
        for g in gates(r):
            if missing: row={'status':'environment','quarantine':None,'stdout':'','stderr':'; '.join(missing)}
            else:
                row=run_gate(g['run'],room,r,strict=strict,env=env)
                if row['status']=='ok' and not _compare_pin(d,room,g['output']): row['status']='mismatch'
            row['output']=g['output']; result['gates'].append(row)
        result['ok']=v['ok'] and all(g['status']=='ok' for g in result['gates'])
        if v['ok'] and not result['ok']: result['verdict']=next(g['status'] for g in result['gates'] if g['status']!='ok')
    result['elapsed']=time.monotonic()-start
    if result['ok']: _write_json(os.path.join(d,STORE,'audit.json'),{'root':v['root'],'when':_now(),'ok':True})
    return result

def _read_usage(p):
    try:
        v=json.load(open(p)); return {k:v[k] for k in ('usd','tokens','calls') if isinstance(v,dict) and number(v.get(k))}
    except (OSError,ValueError): return {}
def _produce(cmd,d,r,s,guidance=True,producer_env=None):
    outputs=[x['output'] for x in produces(r) if step_class(x) in ('generated','free') and 'from' not in x]
    usage=os.path.join(os.path.abspath(d),USAGE)
    if os.path.exists(usage): os.unlink(usage)
    e=_scrub_env(producer_env); e.update(RETICULI_OUTPUT=_safe(d,s['output']),RETICULI_OUTPUTS=json.dumps(outputs),RETICULI_USAGE=usage,RETICULI_CLAIM=os.path.abspath(d))
    if guidance and _step_guidance(s) is not None: e['RETICULI_REQUEST']=_step_guidance(s)
    else: e.pop('RETICULI_REQUEST',None)
    os.makedirs(os.path.dirname(e['RETICULI_OUTPUT']),exist_ok=True)
    a=_run(['/bin/sh','-c',cmd],d,e,PRODUCER_TIMEOUT)
    ledger(d,{'event':'oracle','calls':1,**_read_usage(usage),'seconds':a['elapsed']})
    if a['status']!='ok': raise ClaimError('producer '+a['status']+': '+a['stderr'])
    return a

def rebuild(d,producer,into,produce_from=None,input_from=None,guidance=True,producer_env=None,**kw):
    d=os.path.abspath(d); into=os.path.abspath(into); r=load_recipe(d)
    if os.path.exists(into) and os.listdir(into): raise ClaimError('rebuild target already holds bytes')
    missing=preflight(r)
    if missing: raise ClaimError('environment: '+', '.join(missing))
    _materialize(d,into,r,produce_from,input_from,False)
    watch=[os.path.basename(recipe_path(into))]+_inputs(r,into)+[s['output'] for s in produces(r) if step_class(s) not in ('generated','free')]
    hashes={p:_hash_file(_safe(into,p)) for p in watch}
    ledger(into,{'event':'environment',**_judging_host(),'quarantine':sandbox_backend()})
    ledger(into,{'event':'producer','blind':True,**{k:os.environ['RETICULI_'+k.upper()] for k in ('vendor','model') if 'RETICULI_'+k.upper() in os.environ}})
    for p in produce_from or {}: ledger(into,{'event':'reuse','output':p})
    for s in produces(r):
        if step_class(s) not in ('generated','free') or s['output'] in (produce_from or {}): continue
        if not os.path.isfile(_safe(into,s['output'])): _produce(producer,into,r,s,guidance,producer_env)
    for p,h in hashes.items():
        if _hash_file(_safe(into,p))!=h: raise ClaimError(f'producer rewrote pinned file {p}')
    env=furnish(r,into); quarantine=sandbox_backend()
    for g in gates(r):
        p=_safe(into,g['output'])
        if os.path.exists(p): os.unlink(p)
        row=run_gate(g['run'],into,r,env=env); quarantine=row['quarantine']; ledger(into,{'event':'gate','output':g['output'],**row})
        if row['status']!='ok': raise ClaimError(f'gate {g["output"]} {row["status"]}: {row["stderr"]}')
        if os.path.exists(_safe(d,g['output'])) and not _compare_pin(d,into,g['output']): raise ClaimError('pinned mismatch: '+g['output'])
    return {**seal(into),'ok':True,'quarantine':quarantine}

def _ssh_verify(path,namespace,identity=None,anchor=None):
    if not os.path.isfile(path+'.sig'): return False
    args=['ssh-keygen','-Y']
    if anchor and identity: args+=['verify','-f',anchor,'-I',identity]
    else: args+=['check-novalidate']
    args+=['-n',namespace,'-s',path+'.sig']
    try:
        with open(path,'rb') as f: return subprocess.run(args,stdin=f,capture_output=True).returncode==0
    except OSError: return False

def _authorized(d,anchor=None):
    anchor=anchor or os.environ.get('RETICULI_SIGNERS')
    if not anchor: return False
    m=read_manifest(d)
    for p in glob.glob(os.path.join(d,SIGN_DIR,'*.sign.json')):
        try:
            s=json.load(open(p)); pp=p.replace('.sign.json','.packet.json'); packet=json.load(open(pp))
            if digest(packet)!=s.get('packet_digest') or packet.get('root')!=m['root'] or packet.get('build_digest')!=build_digest(d): continue
            if not packet.get('proof') or packet['proof']!=m.get('proof'): continue
            if _ssh_verify(p,SIGN_NAMESPACE,s['identity'],anchor): return True
        except (OSError,ValueError,KeyError): pass
    return False
def phase(d):
    if not os.path.exists(os.path.join(d,MANIFEST)): load_recipe(d); return 'draft'
    v=verify(d)
    return 'signed' if v['ok'] and _authorized(d) else 'sealed'

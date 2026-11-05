import os, sys, shutil, tempfile, json, subprocess, time, glob
from .core import *
from .core import _safe, _hash_file, _copy_into, _write_json, _read_json, _judging_host, _now
from .recipe import load_recipe, recipe_path, produces, gates, _inputs, step_class
from .identity import root, build_digest, _preimage_recipe, _claim_format
from .seal import seal, verify, read_manifest
from .run import run_gate, preflight, furnish, ledger, _scrub_env, _run, sandbox_backend

def _step_guidance(s):return s.get('guidance',s.get('request',''))
def _read_usage(p):
    try:x=_read_json(p)
    except ClaimError:return {}
    if not isinstance(x,dict):return {}
    import math
    return {k:v for k,v in x.items() if k in ('usd','tokens','calls') and type(v) in (int,float) and math.isfinite(v) and v>=0}

def _materialize(src,d,r=None,generated=False,produce_from=None,input_from=None):
    r=r or load_recipe(src);os.makedirs(d,exist_ok=True)
    rp=recipe_path(src);rn=os.path.basename(rp)
    if _claim_format(r)>=3:
        with open(os.path.join(d,rn),'w',encoding='utf-8') as f:f.write(dump_recipe(_preimage_recipe(r)))
    else:_copy_into(rp,d,rn)
    for n in _inputs(r,src):_copy_into((input_from or {}).get(n,_safe(src,n)),d,n)
    for s in produces(r):
        n=s['output'];_safe(src,n);_safe(d,n)
        p=(produce_from or {}).get(n)
        if p or generated or step_class(s)!='generated':
            _copy_into(p or _safe(src,n),d,n)
    for g in gates(r):_safe(d,g['output'])
    for member in r.get('claim',{}).get('assembles',[]):
        name,want=member.split('@'); md=os.path.join(src,STORE,'sealed',name)
        if not verify(md)['ok'] or root(load_recipe(md),md)!=want:raise ClaimError('assembly member root drift: '+name)
        mr=load_recipe(md)
        for s in produces(mr):
            if os.path.exists(_safe(d,s['output'])):raise ClaimError('assembly path collision '+s['output'])
            _copy_into(_safe(md,s['output']),d,s['output'])
        shutil.copytree(md,os.path.join(d,STORE,'sealed',name),symlinks=True)
    return r

def _compare_pin(src,d,n):return _hash_file(_safe(src,n))==_hash_file(_safe(d,n))
def audit(d,produce_from=None,strict=False,**kwargs):
    start=time.monotonic();r=load_recipe(d);v=verify(d); rows=[];missing=preflight(r)
    result={**v,'elapsed':0,'environment':missing,'layers':[], 'gates':rows}
    if not v['ok']:result.update(verdict='broken');return result
    with tempfile.TemporaryDirectory(prefix='ret-audit-') as room:
        _materialize(d,room,r,True,produce_from)
        try:env=furnish(r,room) if not missing else None
        except ClaimError as e:missing=[str(e)];result['environment']=missing;env=None
        for g in gates(r):
            n=g['output']
            if missing:o={'status':'environment','quarantine':None,'stdout':'','stderr':', '.join(missing)}
            else:
                o=run_gate(g['run'],room,r,strict,env)
                if o['status']=='ok':
                    try:match=_compare_pin(d,room,n)
                    except ClaimError:match=False
                    if not match:o['status']='mismatch'
            rows.append(dict(o,output=n))
    ok=all(x['status']=='ok' for x in rows)
    result.update(ok=ok,verdict='earned' if ok else next((x['status'] for x in rows if x['status']!='ok'),'failed'),elapsed=time.monotonic()-start)
    return result

def _produce(cmd,d,s,outputs,guidance=True,producer_env=None):
    usage=os.path.join(os.path.abspath(d),USAGE);os.makedirs(os.path.dirname(usage),exist_ok=True)
    if os.path.exists(usage):os.unlink(usage)
    e=_scrub_env(producer_env)
    e.update(RETICULI_OUTPUT=os.path.abspath(_safe(d,s['output'])),RETICULI_OUTPUTS=json.dumps(outputs),RETICULI_USAGE=usage,RETICULI_CLAIM=os.path.abspath(d))
    if guidance and _step_guidance(s):e['RETICULI_REQUEST']=_step_guidance(s)
    out=_run(['/bin/sh','-c',cmd],d,e,PRODUCER_TIMEOUT)
    ledger(d,{'event':'oracle','calls':1,**_read_usage(usage),'seconds':out['seconds']})
    if out['status']!='ok':raise ClaimError('producer '+out['status']+': '+out['stderr'])
    return out

def rebuild(src,producer,into,produce_from=None,input_from=None,guidance=True,producer_env=None,**kwargs):
    src=os.path.abspath(src);into=os.path.abspath(into);r=load_recipe(src)
    if os.path.exists(into) and os.listdir(into):raise ClaimError('target already holds bytes: '+into)
    if preflight(r):raise ClaimError('environment: '+', '.join(preflight(r)))
    _materialize(src,into,r,False,produce_from,input_from)
    protected=[os.path.basename(recipe_path(into))]+_inputs(r,src)+[s['output'] for s in produces(r) if step_class(s)!='generated']
    before={n:_hash_file(_safe(into,n)) for n in protected}
    outs=[s['output'] for s in produces(r) if step_class(s)=='generated' and not s.get('from')]
    ledger(into,{'event':'producer','vendor':os.environ.get('RETICULI_VENDOR',''), 'model':os.environ.get('RETICULI_MODEL',''), 'blind':True})
    for s in produces(r):
        n=s['output']
        if (produce_from or {}).get(n):ledger(into,{'event':'reuse','output':n});continue
        if step_class(s)!='generated':continue
        if os.path.isfile(_safe(into,n)):continue
        _produce(producer,into,s,outs,guidance,producer_env)
    for n,h in before.items():
        if _hash_file(_safe(into,n))!=h:raise ClaimError('producer rewrote pinned bytes: '+n)
    env=furnish(r,into);b=sandbox_backend()
    ledger(into,{'event':'environment',**_judging_host(),'quarantine':b})
    for g in gates(r):
        n=g['output'];p=_safe(into,n)
        if os.path.exists(p):os.unlink(p)
        o=run_gate(g['run'],into,r,env=env);ledger(into,dict(o,event='gate',output=n))
        if o['status']!='ok':raise ClaimError('gate '+n+' '+o['status']+': '+o['stderr'])
        if os.path.isfile(_safe(src,n)) and not _compare_pin(src,into,n):raise ClaimError('gate mismatch: '+n)
    m=seal(into);return dict(m,ok=True,quarantine=b)

def _ssh_verify(path,namespace,anchor=None,identity=None):
    try:
        data=open(path,'rb').read();sig=path+'.sig'
        if anchor:
            ids=[identity] if identity else [l.split()[0] for l in open(anchor) if l.strip() and not l.startswith('#')]
            for ident in ids:
                p=subprocess.run(['ssh-keygen','-Y','verify','-f',anchor,'-I',ident,'-n',namespace,'-s',sig],input=data,capture_output=True)
                if p.returncode==0:return ident
            return None
        p=subprocess.run(['ssh-keygen','-Y','check-novalidate','-n',namespace,'-s',sig],input=data,capture_output=True)
        return 'intact' if p.returncode==0 else None
    except (OSError,ValueError):return None

def _authorized(d,anchor=None):
    anchor=anchor or os.environ.get('RETICULI_SIGNERS')
    if not anchor:return False
    m=read_manifest(d)
    for p in glob.glob(os.path.join(d,SIGN_DIR,'*.sign.json')):
        try:
            s=_read_json(p);pp=p[:-len('.sign.json')]+'.packet.json';packet=_read_json(pp)
            if not _ssh_verify(p,SIGN_NAMESPACE,anchor,s.get('identity')):continue
            if digest(packet)!=s.get('packet_digest') or packet.get('root')!=m['root'] or packet.get('build_digest')!=build_digest(d):continue
            if s.get('proof_recorded') and packet.get('proof') and packet.get('proof')==m.get('proof'):return True
        except ClaimError:continue
    return False

def phase(d):
    load_recipe(d)
    if not os.path.exists(os.path.join(d,MANIFEST)):return 'draft'
    v=verify(d)
    return 'signed' if v['ok'] and _authorized(d) else 'sealed'

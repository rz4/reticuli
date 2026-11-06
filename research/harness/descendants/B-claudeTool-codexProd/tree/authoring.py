import os,json,re,shlex,shutil,tempfile
from . import kernel,render
from ._kernel.core import _safe,_copy_into
TRACE='.reticuli/draft.jsonl'
def events(ws):
    try: return [json.loads(l) for l in open(os.path.join(ws,TRACE)) if l.strip()]
    except OSError: return []
def _exists(ws,p):
    try:
        path=_safe(ws,p)
        return os.path.isfile(path) and os.path.basename(path) in os.listdir(os.path.dirname(path))
    except kernel.ClaimError: return False
def propose(ws,outputs,name,claim=None,generated=None):
    ev=events(ws); writes={e['path'] for e in ev if e.get('event')=='write' and _exists(ws,e['path'])}; writes.update(generated or [])
    reads={e['path'] for e in ev if e.get('event')=='read'}
    for p in reads|writes: _safe(ws,p)
    reads={p for p in reads if _exists(ws,p)}
    commands=[e['cmd'] for e in ev if e.get('event')=='bash']; steps=[]; ins=reads|set(claim or [])
    for out in outputs:
        cmd=next((c for c in reversed(commands) if out in c),None)
        if cmd is None: raise kernel.ClaimError('no observed gate for '+out)
        try: tokens=shlex.split(cmd)
        except ValueError: tokens=[]
        ins.update(t for t in tokens if t not in writes and t not in outputs and _exists(ws,t))
        steps.append({'kind':'gate','output':out,'class':'validated','run':cmd})
    writes-=ins
    gen=[{'kind':'produce','output':p,'class':'generated','guidance':'regenerate '+p+' to pass the gate'} for p in sorted(writes)]
    return {'claim':{'name':name,'format':3,'inputs':sorted(ins)},'step':gen+steps}
def build_claim(ws,outputs,into,name='claim',claim=None,generated=None,**kw):
    r=propose(ws,outputs,name,claim,generated)
    if kernel.vacuous_gates(r): raise kernel.ClaimError('vacuous gate')
    with tempfile.TemporaryDirectory() as room:
        for p in r['claim']['inputs']+[s['output'] for s in r['step']]: _copy_into(_safe(ws,p),room,p)
        with open(os.path.join(room,kernel.RECIPE),'w') as f: f.write(render.dump_recipe(r))
        kernel.seal(room)
        if not kernel.audit(room)['ok']: raise kernel.ClaimError('cold verdict did not reproduce')
        if os.path.exists(into): shutil.rmtree(into)
        shutil.copytree(room,into)
    ev=events(ws); times=[e['ts'] for e in ev if 'ts' in e]; calls=sum(e.get('event')=='prompt' for e in ev)
    kernel.ledger(into,{'event':'oracle','calls':calls,'seconds':max(times)-min(times) if times else 0})
    tokens=0
    for p in set(e['transcript'] for e in ev if e.get('event')=='session' and e.get('transcript')):
        try:
            for line in open(p):
                obj=json.loads(line); u=obj.get('message',{}).get('usage',{}); tokens+=sum(u.get(k,0) for k in ('input_tokens','output_tokens'))
        except (OSError,ValueError): pass
    if tokens: kernel.ledger(into,{'event':'usage','scope':'discovery','tokens':tokens})
    return {**kernel.read_manifest(into),'ok':True}

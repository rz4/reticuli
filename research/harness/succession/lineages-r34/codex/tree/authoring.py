import os, json, re, shlex, tempfile, shutil, ast
from . import kernel, registry
from .render import dump_recipe
from ._kernel.core import _safe, _copy_into
TRACE='.reticuli/draft.jsonl'

def events(d):
    try:
        with open(os.path.join(d,TRACE)) as f:return [json.loads(l) for l in f if l.strip()]
    except OSError:return []

def _existing(d,n):
    p=_safe(d,n)
    if not os.path.isfile(p):return False
    cur=os.path.realpath(d)
    for part in n.split('/'):
        if part=='.':continue
        if part not in os.listdir(cur):return False
        cur=os.path.join(cur,part)
    return True

def _tokens(command):
    try:return shlex.split(command.replace('>',' > '))
    except ValueError:return []

def propose(ws,accept,name,claim=None,generated=None):
    ev=events(ws);writes=[];reads=[]
    for e in ev:
        if e.get('event') in ('write','read'):
            n=e['path'];_safe(ws,n)
            if _existing(ws,n):(writes if e['event']=='write' else reads).append(n)
    gen=list(dict.fromkeys(writes+list(generated or [])));pinned=list(claim or [])
    commands=[e['cmd'] for e in ev if e.get('event')=='bash']
    steps=[]
    for output in accept:
        cmd=next((c for c in reversed(commands) if output in _tokens(c) or output in c),None)
        if cmd is None:raise kernel.ClaimError('no observed gate for '+output)
        steps.append({'kind':'gate','output':output,'class':'validated','run':cmd})
        for t in _tokens(cmd):
            if t in ('>','&&','||') or t.startswith('-'):continue
            try:exists=_existing(ws,t)
            except kernel.ClaimError:continue
            if exists and t not in accept and t not in gen:pinned.append(t)
    pinned=list(dict.fromkeys(pinned+reads));gen=[n for n in gen if n not in pinned and n not in accept]
    produce=[{'kind':'produce','output':n,'class':'generated','guidance':'regenerate '+n+' to pass the gate'} for n in sorted(gen)]
    return {'claim':{'name':name,'format':3,'inputs':sorted(set(pinned))},'step':produce+steps}

def build_claim(ws,accept,into,name=None,claim=None,generated=None,**kwargs):
    r=propose(ws,accept,name or os.path.basename(into),claim,generated)
    if kernel.vacuous_gates(r):raise kernel.ClaimError('vacuous gate: claim its check')
    # Stage first: a failed cold earn must not leave a claim at the target.
    with tempfile.TemporaryDirectory() as tmp:
        for n in r['claim']['inputs']+[s['output'] for s in r['step']]:_copy_into(_safe(ws,n),tmp,n)
        with open(os.path.join(tmp,kernel.RECIPE),'w') as f:f.write(dump_recipe(r))
        m=kernel.seal(tmp)
        if not kernel.audit(tmp)['ok']:raise kernel.ClaimError('cold verdict does not reproduce')
        if os.path.exists(into):shutil.rmtree(into)
        shutil.copytree(tmp,into)
    es=events(ws);ts=[e['ts'] for e in es if type(e.get('ts')) in (float,int)]
    calls=sum(e.get('event')=='prompt' for e in es)
    kernel.ledger(into,{'event':'oracle','calls':calls,'seconds':max(ts)-min(ts) if ts else 0})
    for e in es:
        if e.get('event')=='session' and e.get('transcript'):
            tokens=0;usd=0
            try:
                for l in open(e['transcript']):
                    x=json.loads(l);u=x.get('message',{}).get('usage',{})
                    tokens+=sum(v for k,v in u.items() if k.endswith('tokens') and type(v) in (int,float))
                    usd+=x.get('costUSD',0)
            except (OSError,ValueError):continue
            if tokens:kernel.ledger(into,{'event':'producer','scope':'discovery','tokens':tokens,**({'usd':usd} if usd else {}),'testimony':True})
    return dict(m,ok=True)

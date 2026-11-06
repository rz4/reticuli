import os, shutil, tempfile
from . import kernel
from ._kernel.recipe import _inputs, step_class
from ._kernel.core import _safe, _copy_into, _write_json

def _links(d):return kernel.read_manifest(d).get('components',[])
def _index(d,ws=None):
    index={};seen=set();queue=[d]+([ws] if ws else [])
    # A claim in a workspace's drawer can see its siblings.
    if os.path.basename(os.path.dirname(d))=='sealed':queue.append(os.path.dirname(os.path.dirname(os.path.dirname(d))))
    while queue:
        p=queue.pop();rp=os.path.realpath(p)
        if rp in seen:continue
        seen.add(rp)
        if os.path.isfile(os.path.join(p,kernel.MANIFEST)):
            m=kernel.read_manifest(p);index[(m['name'],m['root'])]=p
        for sub in ('sealed','deps'):
            drawer=os.path.join(p,kernel.STORE,sub)
            if os.path.isdir(drawer):queue.extend(os.path.join(drawer,n) for n in os.listdir(drawer) if os.path.isdir(os.path.join(drawer,n)))
    return index

def _resolve(link,index):
    p=index.get((link['component'],link.get('root')))
    if p:return p
    if not link.get('root'):return next((p for (n,r),p in index.items() if n==link['component']),None)
    return None

def claims(ws):
    p=os.path.join(ws,kernel.STORE,'sealed');out=[]
    if not os.path.isdir(p):return out
    for n in sorted(os.listdir(p)):
        d=os.path.join(p,n)
        if not os.path.isfile(os.path.join(d,kernel.MANIFEST)):continue
        out.append(dict(kernel.read_manifest(d),phase=kernel.phase(d),path=d))
    return out

def detect_components(ws,inputs):
    out=[]
    for c in claims(ws):
        r=kernel.load_recipe(c['path'])
        for n in inputs:
            h=kernel._hash_file(_safe(ws,n))
            for s in r.get('step',[]):
                p=_safe(c['path'],s['output'])
                if os.path.isfile(p) and kernel._hash_file(p)==h:
                    out.append({'input':n,'component':c['name'],'root':c['root'],'output':s['output']})
    return out

def seal_with(d,components=None,proof=None):return kernel.seal(d,components=components,proof=proof)
def deps(ws):
    idx=_index(ws);out=[]
    for c in claims(ws):out.append(dict(c,depends_on=[dict(l,status='ok' if _resolve(l,idx) else 'unresolved') for l in _links(c['path'])]))
    return {'claims':out}

def _copy_claim(src,dst,blind=False):
    os.makedirs(dst,exist_ok=True);r=kernel.load_recipe(src)
    files=[os.path.basename(kernel.recipe_path(src))]+_inputs(r,src)+[s['output'] for s in r.get('step',[]) if not (blind and step_class(s)=='generated')]
    files += [kernel.MANIFEST]
    for residue in ('parts.json',):
        n=os.path.join(kernel.STORE,residue)
        if os.path.isfile(os.path.join(src,n)):files.append(n)
    for n in dict.fromkeys(files):
        p=_safe(src,n)
        if os.path.isfile(p):_copy_into(p,dst,n)
    for folder in ('attest','mint'):
        p=os.path.join(src,kernel.STORE,folder)
        if os.path.isdir(p):shutil.copytree(p,os.path.join(dst,kernel.STORE,folder),dirs_exist_ok=True)

def _closure(d,ws=None):
    idx=_index(d,ws);out=[];seen=set()
    def visit(p):
        for l in _links(p):
            key=(l['component'],l.get('root'))
            if key in seen:continue
            seen.add(key);cp=_resolve(l,idx)
            if cp is None:raise kernel.ClaimError('unresolved component '+l['component'])
            visit(cp);out.append(cp)
    visit(d);return out

def pull(src,ws):
    allclaims=_closure(src)+[src];drawer=os.path.join(ws,kernel.STORE,'sealed')
    for p in allclaims:
        m=kernel.read_manifest(p);dest=os.path.join(drawer,m['name'])
        if not os.path.exists(dest):_copy_claim(p,dest)
    for p in allclaims:
        dest=os.path.join(drawer,kernel.read_manifest(p)['name'])
        local=os.path.join(dest,kernel.STORE,'sealed');os.makedirs(local,exist_ok=True)
        for cp in allclaims:
            name=kernel.read_manifest(cp)['name'];target=os.path.join(drawer,name);link=os.path.join(local,name)
            if os.path.realpath(dest)!=os.path.realpath(target) and not os.path.lexists(link):os.symlink(os.path.relpath(target,local),link)
    materialized=[]
    for s in kernel.load_recipe(src).get('step',[]):
        n=s['output'];p=_safe(src,n)
        if os.path.isfile(p):_copy_into(p,ws,n);materialized.append(n)
    return dict(kernel.read_manifest(src),ok=True,materialized=materialized)

def audit_deep(d,ws=None,strict=False,**kwargs):
    top=kernel.audit(d,strict=strict);idx=_index(d,ws);rows=[];seen=set()
    def visit(p,overrides):
        groups={}
        for l in _links(p):groups.setdefault((l['component'],l.get('root')),[]).append(l)
        for key,links in groups.items():
            if key in seen:continue
            seen.add(key);cp=_resolve(links[0],idx)
            if cp is None:rows.append({'name':key[0],'root':key[1],'ok':False,'status':'unresolved'});continue
            supplied={};attribution=True; names=[]
            inputs=set(_inputs(kernel.load_recipe(p),p))
            for l in links:
                n=l.get('input');o=l.get('output',n)
                if not n:continue
                actual=overrides.get(n,_safe(p,n));names.append(n)
                if n in inputs:
                    try:attribution &= kernel._hash_file(actual)==kernel._hash_file(_safe(cp,o))
                    except kernel.ClaimError:attribution=False
                else:supplied[o]=actual
            a=kernel.audit(cp,produce_from=supplied,strict=strict)
            if not attribution:a.update(ok=False,verdict='attribution mismatch')
            rows.append(dict(a,name=key[0],status=a['verdict'],bytes_from=sorted(names)))
            visit(cp,supplied)
    visit(d,{})
    top.update(layers=rows,ok=top['ok'] and all(x['ok'] for x in rows))
    if not top['ok'] and top['verdict']=='earned':top['verdict']='failed'
    return top

def rebuild_chain(src,producer,into,ws=None,reuse=False,**kwargs):
    idx=_index(src,ws);done={};rebuilt=[]
    with tempfile.TemporaryDirectory(prefix='chain-') as tmp:
        def build(p,target):
            pf={};inf={}
            for l in _links(p):
                key=(l['component'],l.get('root'));cp=_resolve(l,idx)
                if cp is None:raise kernel.ClaimError('unresolved component '+l['component'])
                if key not in done:
                    dest=cp if reuse else os.path.join(tmp,l['component'])
                    if not reuse:build(cp,dest)
                    done[key]=dest;rebuilt.append({'component':key[0],'root':kernel.read_manifest(dest)['root']})
                n=l.get('input');o=l.get('output',n)
                if n:
                    mapping=inf if n in _inputs(kernel.load_recipe(p),p) else pf
                    mapping[n]=_safe(done[key],o)
            r=kernel.rebuild(p,producer,target,produce_from=pf,input_from=inf,**kwargs)
            kernel.seal(target,components=_links(p));return r
        result=build(src,into)
        drawer=os.path.join(into,kernel.STORE,'sealed')
        for key,p in done.items():_copy_claim(p,os.path.join(drawer,key[0]))
    return dict(result,rebuilt_components=rebuilt)

def crosscheck_deep(m1,m2,m3,**kwargs):
    r=kernel.crosscheck(m1,m2,m3,**kwargs)
    for tag,p in zip(('M1','M2','M3'),(m1,m2,m3)):
        if os.path.isdir(p):
            a=audit_deep(p);r['audited'][tag]=a['ok']
            if not a['ok']:r['rejected'].append('composed audit '+tag)
    if r['rejected']:r.update(satisfied=False,verdict='reject')
    return r

def record_proof_deep(m1,m2,m3,**kwargs):
    r=crosscheck_deep(m1,m2,m3,**kwargs);r['proof_recorded']=False
    if r['satisfied']:return kernel.record_proof(m1,m2,m3,**kwargs)
    return r

def sign_root(d,ws=None):
    idx=_index(d,ws);memo={};active=set()
    def fold(p):
        key=os.path.realpath(p)
        if key in active:raise kernel.ClaimError('component cycle')
        if key in memo:return memo[key]
        active.add(key);nodes=[]
        for l in _links(p):
            cp=_resolve(l,idx)
            if cp is None:raise kernel.ClaimError('unresolved component '+l['component'])
            nodes.append(fold(cp))
        v=kernel.verify(p)
        if not v['ok']:raise kernel.ClaimError('broken component')
        value=kernel.sign_node(v['root'],kernel.build_digest(p),sorted(set(nodes)));memo[key]=value;active.remove(key);return value
    return fold(d)

def structure(d,ws=None):return dict(kernel.verify(d),components=_links(d),phase=kernel.phase(d))

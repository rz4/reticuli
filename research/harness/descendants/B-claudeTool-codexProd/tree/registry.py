import os,shutil,tempfile
from . import kernel
from ._kernel.recipe import produces,_inputs,recipe_path
from ._kernel.core import _copy_into,_safe,_write_json

def _index(d,ws=None):
    index={}; seen=set(); queue=[d]+([ws] if ws else [])
    # Enclosing workspaces often own the sibling drawer.
    parent=os.path.dirname(os.path.abspath(d))
    if os.path.basename(parent)=='sealed': queue.append(os.path.dirname(os.path.dirname(parent)))
    while queue:
        base=queue.pop(); real=os.path.realpath(base)
        if real in seen: continue
        seen.add(real)
        try:
            m=kernel.read_manifest(base); index[m['root']]=base
        except kernel.ClaimError: pass
        for drawer in ('sealed','deps'):
            store=os.path.join(base,kernel.STORE,drawer)
            if os.path.isdir(store):
                queue.extend(os.path.join(store,n) for n in os.listdir(store) if os.path.isdir(os.path.join(store,n)))
    return index

def claims(ws):
    store=os.path.join(ws,kernel.STORE,'sealed'); out=[]
    if os.path.isdir(store):
        for n in sorted(os.listdir(store)):
            d=os.path.join(store,n)
            try: out.append({**kernel.read_manifest(d),'path':d,'phase':kernel.phase(d)})
            except kernel.ClaimError: pass
    return out

def detect_components(ws,inputs):
    out=[]
    for c in claims(ws):
        r=kernel.load_recipe(c['path'])
        for s in r.get('step',[]):
            p=os.path.join(c['path'],s['output'])
            if not os.path.isfile(p): continue
            h=kernel._hash_file(p)
            for inp in inputs:
                if kernel._hash_file(_safe(ws,inp))==h: out.append({'input':inp,'component':c['name'],'root':c['root'],'output':s['output']})
    return out

def seal_with(d,components=None,proof=None): return kernel.seal(d,components=components,proof=proof)
def deps(ws):
    idx=_index(ws); out=[]
    for c in claims(ws): out.append({**c,'depends_on':[{**l,'status':'ok' if l['root'] in idx else 'unresolved'} for l in c.get('components',[])]})
    return {'claims':out}
def _closure(d,ws=None):
    idx=_index(d,ws); out={}; active=set()
    def visit(p):
        m=kernel.read_manifest(p)
        if m['root'] in active: raise kernel.ClaimError('component cycle')
        if m['root'] in out: return
        active.add(m['root'])
        for link in m.get('components',[]):
            q=idx.get(link['root'])
            if not q: raise kernel.ClaimError('missing component '+link['component'])
            visit(q)
        active.remove(m['root']); out[m['root']]=p
    visit(d); return out

def _copy_claim(src,dst,blind=False):
    os.makedirs(dst,exist_ok=True); r=kernel.load_recipe(src)
    paths=[os.path.basename(recipe_path(src)),kernel.MANIFEST]+_inputs(r,src)
    paths += [s['output'] for s in r.get('step',[]) if not blind or s.get('class')!='generated']
    for p in dict.fromkeys(paths):
        if os.path.isfile(_safe(src,p)): _copy_into(_safe(src,p),dst,p)
    for folder in ('attest','mint'):
        source=os.path.join(src,kernel.STORE,folder)
        if os.path.isdir(source): shutil.copytree(source,os.path.join(dst,kernel.STORE,folder),dirs_exist_ok=True)

def copy_closure(src,dst,ws=None,blind=False,dependency_blind=False):
    closure=_closure(src,ws); _copy_claim(src,dst,blind)
    top=kernel.read_manifest(src)['root']
    for root,p in closure.items():
        if root==top: continue
        name=kernel.read_manifest(p)['name']; _copy_claim(p,os.path.join(dst,kernel.STORE,'deps',name),dependency_blind or blind)

def pull(src,ws):
    m=kernel.read_manifest(src); dst=os.path.join(ws,kernel.STORE,'sealed',m['name'])
    if not os.path.exists(dst): copy_closure(src,dst)
    r=kernel.load_recipe(src); materialized=[]
    for s in r.get('step',[]):
        p=s['output']
        if os.path.isfile(_safe(src,p)): _copy_into(_safe(src,p),ws,p); materialized.append(p)
    return {'ok':True,'root':m['root'],'materialized':materialized,'name':m['name']}

def audit_deep(d,ws=None,strict=False,**kw):
    idx=_index(d,ws); seen=set(); layers=[]
    def walk(p,overrides=None,top=False):
        m=kernel.read_manifest(p)
        if not top and m['root'] in seen: return
        seen.add(m['root']); result=kernel.audit(p,produce_from=overrides,strict=strict)
        grouped={}
        for l in m.get('components',[]): grouped.setdefault(l['root'],[]).append(l)
        for rt,links in grouped.items():
            if rt in seen: continue
            q=idx.get(rt)
            if not q:
                seen.add(rt); layers.append({'name':links[0]['component'],'root':rt,'ok':False,'status':'unresolved'}); continue
            pr=kernel.load_recipe(p); ins=set(_inputs(pr,p)); sub={}; bad=False
            for l in links:
                if not l.get('input'): continue
                inp=l['input']; source=(overrides or {}).get(inp,_safe(p,inp)); target=l.get('output',inp)
                if inp in ins:
                    try: bad |= kernel._hash_file(source)!=kernel._hash_file(_safe(q,target))
                    except kernel.ClaimError: bad=True
                else: sub[target]=source
            cr=walk(q,sub)
            if cr is not None:
                cr['bytes_from']=sorted(sub)
                if bad: cr.update(ok=False,status='attribution mismatch')
        if not top: result['status']=result['verdict']; layers.append(result)
        return result
    result=walk(d,top=True); result['layers']=layers; result['ok'] &= all(x['ok'] for x in layers)
    if not result['ok'] and result['verdict']=='earned': result['verdict']='failed'
    return result

def sign_root(d,ws=None):
    idx=_index(d,ws); memo={}
    def fold(p):
        m=kernel.read_manifest(p)
        if m['root'] in memo: return memo[m['root']]
        links=[]
        for rt in dict.fromkeys(l['root'] for l in m.get('components',[])):
            if rt not in idx: raise kernel.ClaimError('missing component')
            links.append(fold(idx[rt]))
        value=kernel.sign_node(kernel.verify(p)['root'],kernel.build_digest(p),links); memo[m['root']]=value; return value
    return fold(d)
def rebuild_chain(d,producer,into,ws=None,reuse=False,**kw):
    idx=_index(d,ws); rebuilt=[]; mapped={}
    with tempfile.TemporaryDirectory() as temp:
        def build(p,where):
            m=kernel.read_manifest(p); r=kernel.load_recipe(p); supply={}; inputs={}
            for l in m.get('components',[]):
                rt=l['root']
                if rt not in mapped:
                    if rt not in idx: raise kernel.ClaimError('missing component '+l['component'])
                    q=idx[rt]
                    if not reuse:
                        dest=os.path.join(temp,str(len(mapped))); mapped[rt]=dest; build(q,dest); q=dest
                    mapped[rt]=q; rebuilt.append({'component':l['component'],'root':rt})
                if l.get('input'):
                    target=inputs if l['input'] in _inputs(r,p) else supply
                    target[l['input']]=_safe(mapped[rt],l.get('output',l['input']))
            result=kernel.rebuild(p,producer,where,produce_from=supply,input_from=inputs,**kw)
            if m.get('components'): seal_with(where,components=m['components'])
            return result
        result=build(d,into)
        for rt,p in _closure(d,ws).items():
            if rt==kernel.read_manifest(d)['root']: continue
            q=mapped.get(rt,p); name=kernel.read_manifest(q)['name']
            _copy_claim(q,os.path.join(into,kernel.STORE,'deps',name))
    result['rebuilt_components']=rebuilt; return result

def crosscheck_deep(m1,m2,m3,**kw):
    r=kernel.crosscheck(m1,m2,m3,**kw)
    for key,p in zip(('M1','M2','M3'),(m1,m2,m3)):
        if os.path.isdir(p): r['audited'][key]=audit_deep(p)['ok']
    if not all(r['audited'].values()): r.update(satisfied=False,verdict='reject'); r['rejected'].append('composed audit')
    return r
def record_proof_deep(m1,m2,m3,**kw):
    r=crosscheck_deep(m1,m2,m3,**kw); r['proof_recorded']=r['satisfied']
    if r['satisfied']: seal_with(m1,proof=r)
    return r
def structure(d,ws=None): return {'root':kernel.verify(d)['root'],'layers':list(_closure(d,ws))}

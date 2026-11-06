import os,json
from .core import ClaimError, MANIFEST, _write_json
from .recipe import load_recipe,produces
from .identity import root,_parts

def read_manifest(d):
    try:
        with open(os.path.join(d,MANIFEST)) as f: m=json.load(f)
        if not isinstance(m,dict) or not isinstance(m.get('name'),str) or not isinstance(m.get('root'),str): raise ClaimError('invalid manifest')
        return m
    except (OSError,ValueError,TypeError) as e: raise ClaimError(f'invalid manifest: {e}') from e
def seal(d,**kw):
    r=load_recipe(d)
    for inp,outs in r['claim'].get('constrains',{}).items():
        for out in outs:
            s=next((s for s in produces(r) if s['output']==out),None)
            if not s: raise ClaimError(f'constrains phantom target {out}')
            if s.get('from'): raise ClaimError(f'{inp} constrains {out}; belongs in {s["from"]}')
    m=read_manifest(d) if os.path.isfile(os.path.join(d,MANIFEST)) else {}
    m.update(name=r['claim']['name'],root=root(r,d),parts=_parts(r,d)); m.update({k:v for k,v in kw.items() if v is not None})
    _write_json(os.path.join(d,MANIFEST),m); return m
def _changed_parts(old,new): return sorted(k.split(':',1)[-1] for k in set(old)|set(new) if old.get(k)!=new.get(k))
def verify(d):
    r=load_recipe(d); m=read_manifest(d); p=_parts(r,d); now=root(r,d)
    return {'name':m['name'],'root':m['root'],'recomputed':now,'ok':now==m['root'],'phase':'sealed','changed':_changed_parts(m.get('parts',{}),p)}

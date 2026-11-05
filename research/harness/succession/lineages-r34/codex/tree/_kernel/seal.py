import os
from .core import ClaimError, MANIFEST, STORE, _read_json, _write_json
from .recipe import load_recipe, produces
from .identity import root, _parts

def read_manifest(d):
    m=_read_json(os.path.join(d,MANIFEST))
    if not isinstance(m,dict) or not isinstance(m.get('name'),str) or not isinstance(m.get('root'),str):raise ClaimError('malformed manifest')
    return m

def seal(d,proof=None,components=None):
    r=load_recipe(d); c=r.get('claim',r.get('record',{}))
    targets={s['output']:s for s in produces(r)}
    for p,outs in c.get('constrains',{}).items():
        for o in outs:
            if o not in targets:raise ClaimError('constrains phantom target '+o)
            if targets[o].get('from'):raise ClaimError(p+' belongs in '+targets[o]['from'])
    m=read_manifest(d) if os.path.exists(os.path.join(d,MANIFEST)) else {}
    m.update(name=c['name'],root=root(r,d))
    if proof is not None:m['proof']=proof
    if components is not None:m['components']=components
    _write_json(os.path.join(d,MANIFEST),m)
    _write_json(os.path.join(d,STORE,'parts.json'),_parts(r,d))
    return m

def _changed_parts(old,new):return [k.split(':',1)[-1] for k in set(old)|set(new) if old.get(k)!=new.get(k)]
def verify(d):
    r=load_recipe(d); m=read_manifest(d); parts=_parts(r,d); actual=root(r,d)
    old=_read_json(os.path.join(d,STORE,'parts.json')) if os.path.isfile(os.path.join(d,STORE,'parts.json')) else {}
    return {'name':m['name'],'root':m['root'],'recomputed':actual,'ok':actual==m['root'],'phase':'sealed','changed':_changed_parts(old,parts)}

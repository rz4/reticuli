import os, copy
from .core import digest, canonical, ClaimError, _safe, _hash_file
from .recipe import load_recipe, _steps, _inputs, produces, step_class

def _claim_format(r):return r.get('claim',r.get('record',{})).get('format',1)
def _preimage_recipe(r):
    r=copy.deepcopy(r); fmt=_claim_format(r)
    if fmt>=3:
        for s in _steps(r):
            s.pop('guidance',None);s.pop('request',None)
    if fmt in (4,5) and 'step' in r:r['step']=sorted(r['step'],key=canonical)
    return r

def _parts(r,d):
    try:p={'digest':'sha256','recipe':canonical(_preimage_recipe(r)).decode()}
    except (TypeError,ValueError) as e:raise ClaimError('recipe has no canonical JSON form: '+str(e))
    for n in _inputs(r,d):p['input:'+n]=_hash_file(_safe(d,n))
    for s in _steps(r):
        if step_class(s)!='generated':p['pinned:'+s['output']]=_hash_file(_safe(d,s['output']))
    return p

def root(r,d):return digest(_parts(r,d))
def build_digest(d):
    r=load_recipe(d); own=[]
    for s in produces(r):
        if 'from' in s or step_class(s)!='generated':continue
        p=_safe(d,s['output'])
        if os.path.exists(p):
            row=[s['output'],_hash_file(p)]
            if _claim_format(r)>=6:row.append('x' if os.stat(p).st_mode & 0o100 else '-')
            own.append(row)
    return digest(sorted(own))
def sign_node(root,digest_,links):return digest([root,digest_,sorted(links)])

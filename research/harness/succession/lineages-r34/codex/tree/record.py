import platform, sys
from . import kernel, registry
from ._kernel.core import _now
from .attest import _sign
canonical=kernel.record_canonical
digest=kernel.record_digest
validate=kernel.record_validate
read=kernel.record_read
signer=kernel.record_signer

def emit(d):
    v=kernel.verify(d)
    if not v['ok']:raise kernel.ClaimError('identity is broken')
    a=registry.audit_deep(d);c=kernel.load_recipe(d)['claim']
    doc={'record':2,'name':v['name'],'root':v['root'],'build_digest':kernel.build_digest(d),'claim':{k:c[k] for k in ('tolerance','envelope','mutation_floor') if k in c},'gates':[{'output':g['output'],'status':g['status'],'sandbox':g['quarantine'] or 'none'} for g in a['gates']], 'environment':{'platform':sys.platform,'machine':platform.machine(),'runtime':platform.python_implementation()+' '+platform.python_version()},'when':_now()}
    costs={k:v for k,v in (kernel.cost(d) or {}).items() if k in ('usd','tokens','calls','seconds')}
    if costs:doc['cost']=costs
    p=kernel.independence(d)
    if p and (p.get('vendor') or p.get('model')):doc['producer']=p
    validate(doc);return doc

def write(doc,path):
    b=canonical(doc)
    if path=='-':sys.stdout.buffer.write(b)
    else:
        with open(path,'wb') as f:f.write(b)
def sign(path,key):read(path);_sign(path,key,kernel.RECORD_NAMESPACE)

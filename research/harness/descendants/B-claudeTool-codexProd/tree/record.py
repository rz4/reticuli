import os,platform,sys
from . import kernel
from ._kernel.core import _now,COST_KEYS
from .attest import _sign
canonical=kernel.record_canonical
digest=kernel.record_digest
validate=kernel.record_validate
read=kernel.record_read
signer=kernel.record_signer
def emit(d):
    v=kernel.verify(d)
    if not v['ok']: raise kernel.ClaimError('broken claim')
    a=kernel.audit(d); c=kernel.load_recipe(d)['claim']
    doc={'record':2,'claim':{k:c[k] for k in ('tolerance','envelope','mutation_floor') if k in c},'name':v['name'],'root':v['root'],'build_digest':kernel.build_digest(d),'gates':[{'output':g['output'],'status':g['status'],'sandbox':g['quarantine'] or 'none'} for g in a['gates']],'environment':{'platform':sys.platform,'machine':platform.machine(),'runtime':platform.python_implementation()+' '+platform.python_version()},'when':_now()}
    costs=kernel.cost(d)
    if costs:
        costs={k:x for k,x in costs.items() if k in COST_KEYS}
        if costs: doc['cost']=costs
    ind=kernel.independence(d)
    if ind: doc['producer']=ind
    return doc
def write(doc,path):
    with open(path,'wb') as f: f.write(canonical(doc))
def sign(path,key): read(path); _sign(path,key,kernel.RECORD_NAMESPACE)

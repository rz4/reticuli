"""Public portable record emission and signing."""
import os
import subprocess
from . import kernel
from ._kernel import core
from ._util import stamp


def validate(doc):
    return kernel.record_validate(doc)

def canonical(doc):
    return kernel.record_canonical(doc)

def digest(doc):
    return kernel.record_digest(doc)

def read(path):
    return kernel.record_read(path)

def write(doc,path):
    data=canonical(doc)
    with open(path,'wb') as f:
        f.write(data)
    return path

def sign(path,key):
    read(path)
    sig=os.fspath(path)+'.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    done=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',kernel.RECORD_NAMESPACE,path],capture_output=True,text=True)
    if done.returncode:
        raise kernel.ClaimError('cannot sign record: '+done.stderr)
    return sig

def signer(path,anchor):
    try:
        return kernel.record_signer(path,anchor)
    except kernel.ClaimError:
        return None

def emit(directory):
    checked=kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('cannot record an identity mismatch')
    parsed=kernel.load_recipe(directory)
    audit=kernel.audit(directory)
    gates=[]
    for row in audit['gates']:
        status=row['status']
        if status not in ('ok','failed','timeout','mismatch','environment'):
            status='ok' if status=='reproduced' else 'failed'
        gates.append({'output':row['output'],'status':status,'sandbox':row.get('quarantine') or audit.get('quarantine') or 'none'})
    claim={k:parsed['claim'][k] for k in ('tolerance','mutation_floor','envelope') if k in parsed['claim']}
    doc={'record':2,'claim':claim,'name':parsed['claim']['name'],'root':checked['root'],
         'build_digest':kernel.build_digest(directory),'gates':gates,
         'environment':core._judging_host(),'when':stamp()}
    cost=kernel.cost(directory)
    if cost:
        doc['cost']=cost
    for event in kernel.ledger_events(directory):
        if event.get('event')=='producer':
            producer={k:event[k] for k in ('vendor','model','blind','cutoff') if k in event}
            if producer:
                doc['producer']=producer
    validate(doc)
    return doc

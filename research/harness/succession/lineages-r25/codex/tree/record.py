"""Author and sign portable result records using the kernel's schema."""
import os
import platform
import subprocess
from . import kernel
from ._kernel import attest as schema, core

validate=schema.record_validate
canonical=schema.record_canonical
digest=schema.record_digest
read=schema.record_read

def emit(directory):
    if not kernel.verify(directory)['ok']: raise kernel.ClaimError('cannot record changed claim')
    parsed=kernel.load_recipe(directory)
    audit=kernel.audit(directory)
    doc={'record':2,'name':parsed['claim']['name'],'root':kernel.verify(directory)['root'],
         'build_digest':kernel.build_digest(directory),
         'claim':{k:parsed['claim'][k] for k in ('tolerance','envelope','mutation_floor') if k in parsed['claim']},
         'gates':[{'output':r['output'],'status':r['status'],'sandbox':r.get('quarantine') or 'none'} for r in audit['gates']],
         'environment':core._judging_host(),'when':core._now()}
    cost=kernel.cost(directory)
    if cost: doc['cost']=cost
    for event in kernel.ledger_events(directory):
        if event.get('event')=='producer':
            producer={k:event[k] for k in ('vendor','model','blind','cutoff') if k in event}
            if producer: doc['producer']=producer
    validate(doc)
    return doc

def write(doc,path):
    data=canonical(doc)
    with open(path,'wb') as f: f.write(data)
    return path

def sign(path,key):
    read(path)
    sig=os.fspath(path)+'.sig'
    if os.path.exists(sig): os.unlink(sig)
    subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',kernel.RECORD_NAMESPACE,path],capture_output=True,check=True)
    return sig

def signer(path,signers):
    try: doc=read(path)
    except kernel.ClaimError: return None
    with open(signers,encoding='utf-8') as f:
        principals=[line.split()[0] for line in f if line.split()]
    for principal in principals:
        done=subprocess.run(['ssh-keygen','-Y','verify','-f',signers,'-I',principal,'-n',kernel.RECORD_NAMESPACE,'-s',os.fspath(path)+'.sig'],input=canonical(doc),capture_output=True)
        if done.returncode==0:return principal
    return None

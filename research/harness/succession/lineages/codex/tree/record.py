"""Portable canonical records for an earned claim audit."""
from __future__ import annotations
import datetime
import os
import platform
import subprocess
import sys
from pathlib import Path
from . import kernel

canonical=kernel.record_canonical
digest=kernel.record_digest
validate=kernel.record_validate
read=kernel.record_read
def signer(path, anchor=None):
    try: return kernel.record_signer(path, anchor)
    except kernel.ClaimError: return None

def emit(d):
    verified=kernel.verify(d)
    if not verified['ok']: raise kernel.ClaimError('cannot record a drifted claim')
    data=kernel.load_recipe(d); audit=kernel.audit(d)
    doc={'record':2,'name':data['claim']['name'],'root':verified['root'],
         'build_digest':kernel.build_digest(d),
         'claim':{k:data['claim'][k] for k in ('tolerance','envelope','mutation_floor') if k in data['claim']},
         'gates':[{'output':g['output'],'status':g['status'],'sandbox':g.get('quarantine') or 'none'} for g in audit['gates']],
         'environment':{'platform':sys.platform,'machine':platform.machine() or 'unknown',
                        'runtime':platform.python_implementation()+' '+platform.python_version()},
         'when':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    cost=kernel.cost(d)
    if cost: doc['cost']=cost
    producer=kernel.independence(d)
    producer={k:v for k,v in producer.items() if v!=''}
    if producer: doc['producer']=producer
    validate(doc)
    return doc

def write(doc,path):
    Path(path).write_bytes(canonical(doc))
    return path

def sign(path,key):
    read(path)
    sig=path+'.sig'
    if os.path.exists(sig): os.unlink(sig)
    done=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',kernel.RECORD_NAMESPACE,path],capture_output=True)
    if done.returncode: raise kernel.ClaimError('record signing failed')
    return sig

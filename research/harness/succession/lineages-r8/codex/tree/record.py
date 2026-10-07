"""Canonical, signed statements of locally re-earned claim results."""
import os
import subprocess
from . import kernel
from ._util import stamp

validate = kernel.record_validate
canonical = kernel.record_canonical
digest = kernel.record_digest
read = kernel.record_read
def signer(path, anchor):
    try:
        document = read(path)
    except kernel.ClaimError:
        return None
    if open(path, 'rb').read() != canonical(document):
        return None
    return kernel.record_signer(path, anchor)

def emit(directory):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity does not hold')
    claim = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    from ._kernel.core import _judging_host
    result = {'record': 2, 'name': checked['name'], 'root': checked['root'],
              'build_digest': kernel.build_digest(directory),
              'claim': {k:v for k,v in claim['claim'].items() if k in ('tolerance','envelope','mutation_floor')},
              'gates': [{'output': g['output'], 'status': g['status'],
                         'sandbox': g.get('quarantine') or 'none'} for g in audit['gates']],
              'environment': _judging_host(), 'when': stamp()}
    cost = kernel.cost(directory)
    if cost: result['cost'] = cost
    for event in reversed(kernel.ledger_events(directory)):
        if event.get('event') == 'producer':
            producer = {k:event[k] for k in ('vendor','model','blind','cutoff') if k in event}
            if producer: result['producer'] = producer
            break
    validate(result)
    return result

def write(document, path):
    data = canonical(document)
    with open(path, 'wb') as f: f.write(data)
    return path

def sign(path, key):
    read(path)
    signature = os.fspath(path)+'.sig'
    if os.path.exists(signature): os.unlink(signature)
    done = subprocess.run(['ssh-keygen','-Y','sign','-f',os.fspath(key),'-n',kernel.RECORD_NAMESPACE,os.fspath(path)], capture_output=True, text=True)
    if done.returncode: raise kernel.ClaimError(done.stderr.strip())
    return signature

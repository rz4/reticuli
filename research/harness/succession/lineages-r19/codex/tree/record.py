"""Portable result records, using the kernel's closed record vocabulary."""
import os
import platform
import subprocess
from . import kernel, _util

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read
def signer(path, anchor):
    try:
        doc = read(path)
        with open(path, 'rb') as f: raw = f.read()
        if raw != canonical(doc): return None
        return kernel.record_signer(path, anchor)
    except kernel.ClaimError:
        return None

def emit(directory):
    try:
        verified = kernel.verify(directory)
    except kernel.ClaimError:
        raise
    if not verified['ok']: raise kernel.ClaimError('identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    claim = {key: parsed['claim'][key] for key in ('tolerance', 'envelope', 'mutation_floor') if key in parsed['claim']}
    doc = {'record': 2, 'name': verified['name'], 'root': verified['root'],
           'build_digest': kernel.build_digest(directory), 'claim': claim,
           'gates': [{'output': g['output'], 'status': g['status'], 'sandbox': g.get('quarantine') or 'none'} for g in audit['gates']],
           'environment': {'platform': platform.system().lower(), 'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': _util.stamp()}
    cost = kernel.cost(directory)
    if cost: doc['cost'] = cost
    for event in reversed(kernel.ledger_events(directory)):
        if event.get('event') == 'producer':
            producer = {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event}
            if producer: doc['producer'] = producer
            break
    validate(doc)
    return doc

def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as f: f.write(data)
    return path

def sign(path, key):
    if os.path.exists(path + '.sig'): os.unlink(path + '.sig')
    result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', kernel.RECORD_NAMESPACE, path], capture_output=True)
    if result.returncode: raise kernel.ClaimError('record signing failed: ' + result.stderr.decode(errors='replace'))
    return path + '.sig'

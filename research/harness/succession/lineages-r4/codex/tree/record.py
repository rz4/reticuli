"""Portable records of a claim's earned results."""
import os
import platform
import subprocess

from . import kernel
from ._util import stamp

def validate(doc):
    return kernel.record_validate(doc)

def canonical(doc):
    return kernel.record_canonical(doc)

def digest(doc):
    return kernel.record_digest(doc)

def read(path):
    return kernel.record_read(path)

def emit(directory):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity does not hold')
    parsed = kernel.load_recipe(directory)
    audited = kernel.audit(directory)
    doc = {'record': 2, 'name': parsed['claim']['name'], 'root': verified['root'],
           'build_digest': kernel.build_digest(directory),
           'claim': {k: parsed['claim'][k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in parsed['claim']},
           'gates': [{'output': g['output'], 'status': g['status'], 'sandbox': g.get('quarantine', 'none')}
                     for g in audited['gates']],
           'environment': {'platform': platform.system().lower(), 'machine': platform.machine(),
                           'runtime': platform.python_version()}, 'when': stamp()}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    for event in reversed(kernel.ledger_events(directory)):
        if event.get('event') == 'producer':
            doc['producer'] = {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event}
            break
    validate(doc)
    return doc

def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as f:
        f.write(data)
    return path

def sign(path, key):
    read(path)
    try:
        os.remove(os.fspath(path) + '.sig')
    except FileNotFoundError:
        pass
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', kernel.RECORD_NAMESPACE, path], capture_output=True)
    if done.returncode:
        raise kernel.ClaimError(done.stderr.decode(errors='replace'))
    return os.fspath(path) + '.sig'

def signer(path, signers):
    try:
        return kernel.record_signer(path, signers)
    except kernel.ClaimError:
        return None

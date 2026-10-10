"""Portable, canonical observations about a sealed claim."""
import datetime
import json
import os
import platform
import subprocess

from . import kernel

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read

def emit(directory):
    checked = kernel.verify(directory)
    if not checked['ok']: raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    doc = {'record': 2, 'name': checked['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory),
           'claim': {k: parsed['claim'][k] for k in ('tolerance','envelope','mutation_floor') if k in parsed['claim']},
           'gates': [{'output': g['output'], 'status': g['status'],
                      'sandbox': g.get('quarantine') or 'none'} for g in audit['gates']],
           'environment': {'platform': platform.system().lower(),
                           'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    cost = kernel.cost(directory)
    if cost: doc['cost'] = cost
    producer = kernel.independence(directory)
    if producer: doc['producer'] = producer
    validate(doc)
    return doc

def write(doc, path):
    with open(path, 'wb') as stream: stream.write(canonical(doc))
    return path

def sign(path, key):
    doc = read(path)
    data = canonical(doc)
    if open(path,'rb').read() != data: raise kernel.ClaimError('record bytes are not canonical')
    done = subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',kernel.RECORD_NAMESPACE],
                          input=data, capture_output=True)
    if done.returncode: raise kernel.ClaimError('cannot sign record')
    with open(os.fspath(path)+'.sig','wb') as stream: stream.write(done.stdout)
    return os.fspath(path)+'.sig'

def signer(path, signers):
    try:
        doc = read(path)
        data = canonical(doc)
        if open(path,'rb').read() != data: return None
        with open(signers,encoding='utf-8') as stream:
            identities = [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith('#')]
        for ident in identities:
            done = subprocess.run(['ssh-keygen','-Y','verify','-f',signers,'-I',ident,
                                   '-n',kernel.RECORD_NAMESPACE,'-s',os.fspath(path)+'.sig'],
                                  input=data,capture_output=True,timeout=15)
            if done.returncode == 0: return ident
    except (OSError, ValueError, kernel.ClaimError, subprocess.TimeoutExpired): pass
    return None

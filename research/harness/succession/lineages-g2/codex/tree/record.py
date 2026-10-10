"""Author and sign portable claim records."""
import os
import subprocess
from . import kernel
from ._kernel import core

validate = kernel.record_validate
canonical = kernel.record_canonical
digest = kernel.record_digest
read = kernel.record_read
def signer(path, anchor):
    try:
        doc = kernel.record_read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, anchor)
    except (OSError, kernel.ClaimError):
        return None

def emit(directory):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    gates = [{'output': row['output'], 'status': row['status'],
              'sandbox': row.get('quarantine') or 'none'} for row in audit['gates']]
    doc = {'record': 2, 'claim': {k: parsed['claim'][k] for k in
           ('tolerance', 'envelope', 'mutation_floor') if k in parsed['claim']},
           'name': parsed['claim']['name'], 'root': verified['root'],
           'build_digest': kernel.build_digest(directory), 'gates': gates,
           'environment': core._judging_host(), 'when': core._now()}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    producer = kernel.independence(directory)
    if producer:
        doc['producer'] = {k: v for k, v in producer.items() if v is not None}
        if not doc['producer']:
            del doc['producer']
    validate(doc)
    return doc

def write(doc, path):
    data = canonical(doc)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path

def sign(path, key):
    read(path)
    signature = os.fspath(path) + '.sig'
    if os.path.exists(signature):
        os.unlink(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key),
                           '-n', kernel.RECORD_NAMESPACE, os.fspath(path)],
                          capture_output=True)
    if done.returncode:
        raise kernel.ClaimError(done.stderr.decode(errors='replace'))
    return signature

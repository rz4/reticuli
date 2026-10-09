"""Portable, signed records of one locally earned claim result."""
import os
import subprocess

from . import kernel
from ._util import write_json, stamp

validate = kernel.record_validate
canonical = kernel.record_canonical
digest = kernel.record_digest
read = kernel.record_read


def emit(path):
    checked = kernel.verify(path)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    doc = kernel.load_recipe(path)
    audit = kernel.audit(path)
    import platform
    result = {'record': 2, 'name': doc['claim']['name'], 'root': checked['root'],
              'build_digest': kernel.build_digest(path),
              'claim': {k: doc['claim'][k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in doc['claim']},
              'gates': [{'output': g['output'], 'status': g['status'],
                         'sandbox': g.get('quarantine') or 'none'} for g in audit['gates']],
              'environment': {'platform': platform.system().lower(), 'machine': platform.machine(),
                              'runtime': platform.python_implementation() + ' ' + platform.python_version()},
              'when': stamp()}
    cost = kernel.cost(path)
    if cost:
        result['cost'] = cost
    producer = kernel.independence(path)
    if producer:
        result['producer'] = producer
    validate(result)
    return result


def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path


def sign(path, key):
    doc = read(path)
    if open(path, 'rb').read() != canonical(doc):
        raise kernel.ClaimError('record is not canonical')
    signature = os.fspath(path) + '.sig'
    if os.path.exists(signature):
        os.remove(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key), '-n', kernel.RECORD_NAMESPACE, os.fspath(path)], capture_output=True)
    if done.returncode:
        raise kernel.ClaimError('record signing failed: ' + done.stderr.decode(errors='replace'))
    return signature


def signer(path, anchor):
    try:
        doc = read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, anchor)
    except kernel.ClaimError:
        return None

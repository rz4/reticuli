"""Portable signed records of a claim's locally earned result."""
import json
import os
import platform
import subprocess

from . import kernel
from ._util import stamp

NAMESPACE = 'reticuli.record'
canonical = kernel.record_canonical if hasattr(kernel, 'record_canonical') else None
# The kernel's record codec owns the vocabulary.
from ._kernel.attest import record_canonical as canonical, record_digest as digest, record_validate as validate
from ._kernel.attest import record_signer as _record_signer
read = kernel.record_read


def signer(path, signers):
    try:
        doc = read(path)
        if open(path, 'rb').read() != canonical(doc):
            return None
        return _record_signer(path, signers)
    except (OSError, kernel.ClaimError):
        return None


def emit(directory):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('cannot record a drifted claim')
    recipe = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    doc = {'record': 2, 'name': recipe['claim']['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory),
           'claim': {k: recipe['claim'][k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in recipe['claim']},
           'gates': [{'output': row['output'], 'status': row['status'],
                      'sandbox': row.get('quarantine') or 'none'} for row in audit['gates']],
           'environment': {'platform': platform.system().lower(), 'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': stamp()}
    measured = kernel.cost(directory)
    if measured:
        doc['cost'] = measured
    producer = {}
    for event in kernel.ledger_events(directory):
        if event.get('event') == 'producer':
            producer = {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event and event[k] is not None}
    if producer:
        doc['producer'] = producer
    validate(doc)
    return doc


def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as target:
        target.write(data)
    return path


def sign(path, key):
    doc = read(path)
    if open(path, 'rb').read() != canonical(doc):
        raise kernel.ClaimError('record bytes are not canonical')
    signature = os.fspath(path) + '.sig'
    if os.path.exists(signature):
        os.remove(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key), '-n', NAMESPACE, os.fspath(path)],
                          capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('record signing failed: ' + done.stderr)
    return signature

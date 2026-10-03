"""Produce the portable record described by spec/record.md."""
from __future__ import annotations

import os
import platform
import subprocess

from . import kernel
from ._util import stamp

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
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
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    gates = [{'output': row['output'], 'status': row['status'],
              'sandbox': row.get('quarantine') or 'none'} for row in audit['gates']]
    doc = {'record': 2, 'name': parsed['claim']['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory), 'gates': gates,
           'claim': {key: parsed['claim'][key] for key in ('tolerance', 'envelope', 'mutation_floor')
                     if key in parsed['claim']},
           'environment': {'platform': platform.system().lower(),
                           'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': stamp()}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    for event in kernel.ledger_events(directory):
        if event.get('event') == 'producer':
            producer = {key: event[key] for key in ('vendor', 'model', 'blind', 'cutoff')
                        if key in event and event[key] is not None}
            if producer:
                doc['producer'] = producer
    validate(doc)
    return doc

def write(doc, path):
    with open(path, 'wb') as stream:
        stream.write(canonical(doc))
    return path

def sign(path, key):
    read(path)
    signature = os.fspath(path) + '.sig'
    if os.path.exists(signature):
        os.unlink(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', kernel.RECORD_NAMESPACE,
                           os.fspath(path)], capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('record signing failed: ' + done.stderr)
    return signature

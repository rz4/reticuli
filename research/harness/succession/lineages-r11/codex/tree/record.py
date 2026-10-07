"""Produce and sign portable records of freshly earned claim results."""
import os
import subprocess

from . import kernel
from ._kernel import core

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate
read = kernel.record_read
def signer(path, anchor):
    try:
        doc = read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, anchor)
    except (OSError, kernel.ClaimError):
        return None

def emit(directory):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('record requires a sealed, matching claim')
    parsed = kernel.load_recipe(directory)
    audited = kernel.audit(directory)
    gates = []
    for row in audited['gates']:
        status = row['status']
        if status == 'reproduced':
            status = 'ok'
        gates.append({'output': row['output'], 'status': status,
                      'sandbox': row.get('quarantine') or 'none'})
    doc = {'record': 2, 'name': parsed['claim']['name'], 'root': verified['root'],
           'build_digest': kernel.build_digest(directory), 'gates': gates,
           'claim': {key: parsed['claim'][key] for key in
                     ('tolerance', 'envelope', 'mutation_floor') if key in parsed['claim']},
           'environment': core._judging_host(), 'when': core._now()}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    for event in reversed(kernel.ledger_events(directory)):
        if event.get('event') == 'producer' and any(k in event for k in ('vendor', 'model', 'blind', 'cutoff')):
            doc['producer'] = {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event}
            break
        if event.get('event') == 'producer_identity':
            doc['producer'] = {k: event[k] for k in ('vendor', 'model', 'blind', 'cutoff') if k in event and event[k] is not None}
            break
    validate(doc)
    return doc

def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path

def sign(path, key):
    doc = read(path)
    with open(path, 'rb') as stream:
        if stream.read() != canonical(doc):
            raise kernel.ClaimError('record bytes are not canonical')
    sig = os.fspath(path) + '.sig'
    if os.path.exists(sig):
        os.remove(sig)
    subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key), '-n',
                    kernel.RECORD_NAMESPACE, os.fspath(path)], check=True,
                   capture_output=True)
    return sig

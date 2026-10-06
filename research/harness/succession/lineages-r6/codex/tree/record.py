"""Portable canonical records of an audited claim build."""
from __future__ import annotations

import os
import subprocess
from . import kernel
from ._kernel import core

canonical = kernel.record_canonical
digest = kernel.record_digest
validate = kernel.record_validate

def emit(directory):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    claim = {key: parsed['claim'][key] for key in ('tolerance', 'envelope', 'mutation_floor')
             if key in parsed['claim']}
    gates = [{'output': row['output'], 'status': row['status'],
              'sandbox': row.get('quarantine') or 'none'} for row in audit['gates']]
    doc = {'record': 2, 'name': checked['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory), 'claim': claim,
           'gates': gates, 'environment': core._judging_host(), 'when': core._now()}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    producer = kernel.independence(directory)
    if producer:
        doc['producer'] = producer
    validate(doc)
    return doc

def write(doc, path):
    data = canonical(doc)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)

def read(path):
    return kernel.record_read(path)

def sign(path, key):
    doc = read(path)
    if open(path, 'rb').read() != canonical(doc):
        raise kernel.ClaimError('record bytes are not canonical')
    signature = os.fspath(path) + '.sig'
    if os.path.exists(signature):
        os.unlink(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key), '-n',
                           kernel.RECORD_NAMESPACE, os.fspath(path)], capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('cannot sign record: ' + done.stderr)
    return signature

def signer(path, signers):
    try:
        doc = read(path)
        if open(path, 'rb').read() != canonical(doc):
            return None
        return kernel.record_signer(path, signers)
    except kernel.ClaimError:
        return None

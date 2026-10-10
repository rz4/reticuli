"""Canonical, signed reports of one claim's current execution."""
import datetime
import json
import os
import platform
import subprocess
import sys

from . import kernel

NAMESPACE = kernel.RECORD_NAMESPACE

def validate(doc):
    return kernel.record_validate(doc)

def canonical(doc):
    return kernel.record_canonical(doc)

def digest(doc):
    return kernel.record_digest(doc)

def read(path):
    return kernel.record_read(path)

def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path

def emit(directory):
    try:
        checked = kernel.verify(directory)
    except kernel.ClaimError as exc:
        raise kernel.ClaimError(f'cannot emit record: {exc}') from exc
    if not checked['ok']:
        raise kernel.ClaimError('cannot emit record for drifted claim')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    obligations = {key: parsed['claim'][key] for key in ('tolerance', 'envelope', 'mutation_floor')
                   if key in parsed['claim']}
    doc = {'record': 2, 'name': parsed['claim']['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory), 'claim': obligations,
           'gates': [{'output': row['output'], 'status': row['status'],
                      'sandbox': row.get('quarantine') or 'none'} for row in audit['gates']],
           'environment': {'platform': platform.system().lower(),
                           'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    for event in reversed(kernel.ledger_events(directory)):
        if event.get('event') == 'producer':
            producer = event.get('producer')
            if not isinstance(producer, dict):
                producer = {key: event[key] for key in ('vendor', 'model', 'blind', 'cutoff') if key in event}
            if producer:
                doc['producer'] = producer
            break
    validate(doc)
    return doc

def sign(path, key):
    doc = read(path)
    if open(path, 'rb').read() != canonical(doc):
        raise kernel.ClaimError('record bytes are not canonical')
    if os.path.exists(path + '.sig'):
        os.unlink(path + '.sig')
    result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', NAMESPACE, path],
                            capture_output=True, text=True)
    if result.returncode:
        raise kernel.ClaimError('record signing failed: ' + result.stderr)
    return path + '.sig'

def signer(path, signers):
    try:
        doc = read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
    except (OSError, kernel.ClaimError):
        return None
    return kernel.record_signer(path, signers)

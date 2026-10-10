"""Portable canonical statements of one machine's earned claim results."""
import datetime
import hashlib
import json
import os
import platform
import subprocess
import sys

from . import kernel


def emit(directory):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('cannot record a drifted claim')
    recipe = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    claim = recipe['claim']
    doc = {'record': 2, 'name': claim['name'], 'root': verified['root'],
           'build_digest': kernel.build_digest(directory),
           'claim': {k: claim[k] for k in ('tolerance', 'envelope', 'mutation_floor') if k in claim},
           'gates': [{'output': gate['output'],
                      'status': 'ok' if gate['status'] in ('ok', 'reproduced') else gate['status'],
                      'sandbox': gate.get('quarantine') or 'none'} for gate in audit['gates']],
           'environment': {'platform': sys.platform, 'machine': platform.machine(),
                           'runtime': f'{platform.python_implementation()} {platform.python_version()}'},
           'when': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    # Only production events are metered. Gate timings belong to the audit,
    # never in this signed document.
    cost = {}
    producer = None
    for event in kernel.ledger_events(directory):
        if event.get('event') == 'oracle' or event.get('kind') == 'producer':
            for unit in ('usd', 'tokens', 'calls', 'seconds'):
                if type(event.get(unit)) in (int, float) and event[unit] >= 0:
                    cost[unit] = cost.get(unit, 0) + event[unit]
        if event.get('event') == 'producer':
            producer = {key: event[key] for key in ('vendor', 'model', 'blind', 'cutoff') if key in event}
    if cost:
        doc['cost'] = cost
    if producer:
        doc['producer'] = producer
    validate(doc)
    return doc


def validate(doc):
    return kernel.record_validate(doc)


def canonical(doc):
    return kernel.record_canonical(doc)


def digest(doc):
    return hashlib.sha256(canonical(doc)).hexdigest()


def write(doc, path):
    data = canonical(doc)
    with open(path, 'wb') as stream:
        stream.write(data)
    return path


def read(path):
    return kernel.record_read(path)


def sign(path, key):
    read(path)
    sig = os.fspath(path) + '.sig'
    if os.path.exists(sig):
        os.remove(sig)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n',
                           kernel.RECORD_NAMESPACE, path], capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('record signing failed: ' + done.stderr)
    return sig


def signer(path, anchor):
    try:
        doc = read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, anchor)
    except (OSError, kernel.ClaimError):
        return None

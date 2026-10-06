"""Emit and sign the canonical public results record."""
import datetime
import os
import platform
import subprocess

from . import kernel


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
    with open(path, 'wb') as f:
        f.write(data)


def emit(directory):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    audit = kernel.audit(directory)
    claim = {key: parsed['claim'][key] for key in ('tolerance', 'envelope', 'mutation_floor')
             if key in parsed['claim']}
    gates = [{'output': row['output'], 'status': row['status'],
              'sandbox': row.get('sandbox', row.get('quarantine', 'none'))}
             for row in audit.get('gates', [])]
    doc = {'record': 2, 'claim': claim, 'name': checked['name'], 'root': checked['root'],
           'build_digest': kernel.build_digest(directory), 'gates': gates,
           'environment': {'platform': platform.system().lower(), 'machine': platform.machine(),
                           'runtime': platform.python_implementation() + ' ' + platform.python_version()},
           'when': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    cost = kernel.cost(directory)
    if cost:
        doc['cost'] = cost
    producer = kernel.independence(directory)
    if producer and any(v is not None for v in producer.values()):
        doc['producer'] = {k: v for k, v in producer.items() if v is not None}
    validate(doc)
    return doc


def sign(path, key):
    doc = read(path)
    if open(path, 'rb').read() != canonical(doc):
        raise kernel.ClaimError('record is not canonical')
    sig = path + '.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    try:
        subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', kernel.RECORD_NAMESPACE, path],
                       check=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise kernel.ClaimError('record signing failed') from exc
    return sig


def signer(path, signers):
    try:
        doc = read(path)
        with open(path, 'rb') as stream:
            if stream.read() != canonical(doc):
                return None
        return kernel.record_signer(path, signers)
    except (OSError, kernel.ClaimError):
        return None

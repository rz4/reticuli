"""SSH attestations of builds and reviewer authorization of chains."""
import hashlib
import json
import os
import subprocess

from . import kernel, registry
from ._util import write_json, stamp

ATTEST = '.reticuli/attest'

def _sign(path, key, namespace):
    try:
        os.unlink(path + '.sig')
    except FileNotFoundError:
        pass
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                          capture_output=True)
    if done.returncode:
        raise kernel.ClaimError(done.stderr.decode(errors='replace'))
    return path + '.sig'

def _verify(path, signers, namespace, principal=None):
    sig = path + '.sig'
    if not os.path.isfile(sig):
        return None
    if signers:
        found = subprocess.run(['ssh-keygen', '-Y', 'find-principals', '-f', signers, '-s', sig],
                               capture_output=True, text=True)
        candidates = found.stdout.splitlines()
    else:
        return None
    with open(path, 'rb') as f:
        data = f.read()
    for candidate in candidates:
        if principal and candidate != principal:
            continue
        result = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', candidate,
                                 '-n', namespace, '-s', sig], input=data, capture_output=True)
        if result.returncode == 0:
            return candidate
    return None

def _public_key_matches(path, sig, namespace):
    try:
        data = open(path, 'rb').read()
        done = subprocess.run(['ssh-keygen', '-Y', 'check-novalidate', '-n', namespace,
                               '-s', sig], input=data, capture_output=True)
        return done.returncode == 0
    except OSError:
        return False

def attest(directory, key, principal):
    verified = kernel.verify(directory)
    if not verified['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('cannot attest an unearned claim')
    folder = os.path.join(directory, ATTEST)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, 'build.json')
    doc = {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
           'principal': principal, 'when': stamp()}
    write_json(path, doc)
    sig = _sign(path, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(path, directory), 'signature': os.path.relpath(sig, directory)}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(folder, filename)
            try:
                doc = json.load(open(path, encoding='utf-8'))
                drifted = doc['build_digest'] != kernel.build_digest(directory) or doc['root'] != kernel.verify(directory)['root']
                valid = (_verify(path, signers, kernel.NAMESPACE, doc.get('principal')) is not None
                         if signers else _public_key_matches(path, path + '.sig', kernel.NAMESPACE))
                rows.append({'verdict': 'signed' if valid and not drifted else 'refused',
                             'drifted': drifted, 'signer': doc.get('principal') if valid else None})
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'drifted': False})
    return {'ok': bool(rows) and all(r['verdict'] == 'signed' for r in rows), 'attestations': rows}

def review_packet(directory, *, ws=None):
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    return {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws),
            'audit': registry.audit_deep(directory, ws),
            'proof': kernel.read_manifest(directory).get('proof')}

def sign(directory, key, principal, *, ws=None):
    packet = review_packet(directory, ws=ws)
    if not packet['audit']['ok']:
        raise kernel.ClaimError('cannot authorize an unearned claim')
    folder = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(folder, exist_ok=True)
    packet_path = os.path.join(folder, 'review.packet.json')
    packet_bytes = json.dumps(packet, sort_keys=True).encode()
    with open(packet_path, 'wb') as f:
        f.write(packet_bytes)
    path = os.path.join(folder, 'review.sign.json')
    statement = {'ceremony': 'RETICULI_CLAIM_BASIN_V1', 'principal': principal,
                 'root': packet['root'], 'sign_root': packet['sign_root'],
                 'build_digest': packet['build_digest'],
                 'packet_digest': hashlib.sha256(packet_bytes).hexdigest(),
                 'proof_recorded': packet['proof'] is not None}
    write_json(path, statement)
    signature = _sign(path, key, kernel.SIGN_NAMESPACE)
    return {**statement, 'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(signature, directory),
            'packet': os.path.relpath(packet_path, directory)}

def sign_check(directory, *, ws=None, signers=None):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(folder):
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.sign.json'):
                continue
            path = os.path.join(folder, filename)
            try:
                doc = json.load(open(path, encoding='utf-8'))
                packet_path = os.path.join(folder, filename[:-10] + '.packet.json')
                raw = open(packet_path, 'rb').read()
                payload = json.loads(raw)
                packet_holds = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() == doc['packet_digest']
                current = review_packet(directory, ws=ws)
                packet_holds = packet_holds and payload == current
                valid = _verify(path, signers, kernel.SIGN_NAMESPACE, doc.get('principal')) is not None if signers else False
                rows.append({'verdict': 'authorized' if valid and packet_holds else 'refused',
                             'packet_holds': packet_holds, 'proof_recorded': doc.get('proof_recorded', False)})
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False})
    return {'ok': bool(rows) and all(r['verdict'] == 'authorized' for r in rows), 'authorizations': rows}

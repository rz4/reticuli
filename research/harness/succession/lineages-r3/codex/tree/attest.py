"""Signed build statements and accountable chain authorization."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

from . import kernel, registry
from ._util import stamp, write_json

ATTEST = '.reticuli/attest'

def _canonical(value):
    return json.dumps(value, sort_keys=True).encode()

def _sign(path, key, namespace):
    signature = path + '.sig'
    if os.path.exists(signature):
        os.unlink(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                          capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('ssh signature failed: ' + done.stderr)

def _principals(anchor):
    if not anchor:
        return []
    try:
        with open(anchor, encoding='utf-8') as stream:
            return [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith('#')]
    except OSError:
        return []

def _verify(path, anchor, namespace):
    try:
        data = open(path, 'rb').read()
    except OSError:
        return None
    for principal in _principals(anchor):
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor, '-I', principal,
                               '-n', namespace, '-s', path + '.sig'],
                              input=data, capture_output=True)
        if done.returncode == 0:
            return principal
    return None

def _earned(directory):
    if not kernel.verify(directory)['ok'] or not registry.audit_deep(directory)['ok']:
        raise kernel.ClaimError('claim verdicts did not reproduce')

def attest(directory, key, signer):
    _earned(directory)
    statement = {'root': kernel.verify(directory)['root'],
                 'build_digest': kernel.build_digest(directory),
                 'signer': signer, 'when': stamp()}
    path = os.path.join(directory, ATTEST, 'build.json')
    write_json(path, statement)
    _sign(path, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory), **statement}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json'):
                continue
            path = os.path.join(folder, name)
            try:
                statement = json.load(open(path, encoding='utf-8'))
                drifted = (statement.get('root') != kernel.verify(directory)['root']
                           or statement.get('build_digest') != kernel.build_digest(directory))
                signed = os.path.isfile(path + '.sig')
                if signers:
                    signed = bool(_verify(path, signers, kernel.NAMESPACE))
                rows.append({'verdict': 'signed' if signed and not drifted else 'refused',
                             'drifted': drifted, 'signed': signed})
            except (OSError, ValueError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'drifted': True, 'signed': False})
    return {'ok': bool(rows) and all(x['verdict'] == 'signed' for x in rows), 'attestations': rows}

def review_packet(directory, *, ws=None):
    manifest = kernel.read_manifest(directory)
    audit = registry.audit_deep(directory)
    return {'root': kernel.verify(directory)['root'],
            'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws),
            'audit': audit, 'proof': manifest.get('proof')}

def sign(directory, key, signer, *, ws=None):
    _earned(directory)
    packet = review_packet(directory, ws=ws)
    path = os.path.join(directory, kernel.SIGN_DIR, 'authorization.sign.json')
    packet_path = path[:-len('.sign.json')] + '.packet.json'
    # The kernel's phase reader binds the same minimal packet.
    phase_packet = {'root': packet['root'], 'build_digest': packet['build_digest'],
                    'proof': packet['proof']}
    write_json(packet_path, phase_packet)
    statement = {'ceremony': 'RETICULI_CLAIM_BASIN_V1', 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'signer': signer,
                 'proof_recorded': bool(packet['proof']),
                 'packet_digest': hashlib.sha256(_canonical(phase_packet)).hexdigest(),
                 'when': stamp()}
    write_json(path, statement)
    _sign(path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': statement['ceremony'], 'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory),
            'packet': os.path.relpath(packet_path, directory)}

def sign_check(directory, *, ws=None, signers=None):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.sign.json'):
                continue
            path = os.path.join(folder, name)
            packet_path = path[:-len('.sign.json')] + '.packet.json'
            try:
                statement = json.load(open(path, encoding='utf-8'))
                packet = json.load(open(packet_path, encoding='utf-8'))
                manifest = kernel.read_manifest(directory)
                expected = {'root': kernel.verify(directory)['root'],
                            'build_digest': kernel.build_digest(directory),
                            'proof': manifest.get('proof')}
                holds = (packet == expected and
                         hashlib.sha256(_canonical(packet)).hexdigest() == statement.get('packet_digest') and
                         statement.get('sign_root') == registry.sign_root(directory, ws))
                trusted = bool(_verify(path, signers, kernel.SIGN_NAMESPACE)) if signers else os.path.isfile(path + '.sig')
                rows.append({'verdict': 'authorized' if holds and trusted else 'refused',
                             'packet_holds': holds, 'proof_recorded': statement.get('proof_recorded', False)})
            except (OSError, ValueError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False})
    return {'ok': bool(rows) and all(x['verdict'] == 'authorized' for x in rows),
            'authorizations': rows}

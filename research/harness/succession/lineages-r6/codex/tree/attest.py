"""SSH attestations of builds and keyholder authorization ceremonies."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from . import kernel, registry
from ._util import write_json, read_json

ATTEST = '.reticuli/attest'

def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()

def _key_id(key):
    return hashlib.sha256(open(key + '.pub', 'rb').read()).hexdigest()[:16]

def _sign(path, key, namespace):
    sig = path + '.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                          capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('cannot sign: ' + done.stderr)

def _verify(path, namespace, signers=None, pubkey=None):
    try:
        if signers is None:
            if not pubkey:
                return None
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
                f.write('self ' + pubkey.strip() + '\n')
                signers = f.name
            principals = ['self']
        else:
            with open(signers) as f:
                principals = [line.split()[0] for line in f if line.strip() and not line.lstrip().startswith('#')]
        for principal in principals:
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', principal,
                                   '-n', namespace, '-s', path + '.sig'],
                                  input=open(path, 'rb').read(), capture_output=True)
            if done.returncode == 0:
                return principal
    except (OSError, ValueError):
        return None
    finally:
        if pubkey and signers and principals == ['self']:
            os.unlink(signers)
    return None

def _earned(directory):
    checked = kernel.verify(directory)
    if not checked['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('claim verdict does not reproduce')
    return checked

def attest(directory, key, identity):
    checked = _earned(directory)
    name = _key_id(key)
    statement = os.path.join(ATTEST, name + '.json')
    absolute = os.path.join(directory, statement)
    doc = {'root': checked['root'], 'build_digest': kernel.build_digest(directory),
           'identity': identity, 'public_key': open(key + '.pub').read().strip()}
    write_json(absolute, doc)
    _sign(absolute, key, kernel.NAMESPACE)
    return {'statement': statement, 'signature': statement + '.sig', **doc}

def check(directory, signers=None):
    base = os.path.join(directory, ATTEST)
    rows = []
    try:
        checked = kernel.verify(directory)
        digest = kernel.build_digest(directory)
    except kernel.ClaimError:
        checked, digest = {'ok': False, 'root': None}, None
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.endswith('.json'):
                continue
            path = os.path.join(base, name)
            try:
                doc = read_json(path)
                signer = _verify(path, kernel.NAMESPACE, signers, doc.get('public_key'))
                drifted = doc.get('build_digest') != digest
                good = bool(checked['ok'] and doc.get('root') == checked['root'] and
                            not drifted and signer)
                rows.append({'verdict': 'signed' if good else 'refused', 'ok': good,
                             'drifted': drifted, 'signer': signer})
            except (OSError, ValueError):
                rows.append({'verdict': 'refused', 'ok': False, 'drifted': False})
    return {'ok': bool(rows and all(r['ok'] for r in rows)), 'attestations': rows}

def review_packet(directory, *, ws=None):
    checked = kernel.verify(directory)
    audit = registry.audit_deep(directory, ws)
    return {'root': checked['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws), 'audit': audit,
            'proof': kernel.read_manifest(directory).get('proof')}

def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    if not packet['audit']['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('claim verdict does not reproduce')
    name = _key_id(key)
    packet_rel = os.path.join(kernel.SIGN_DIR, name + '.packet.json')
    statement_rel = os.path.join(kernel.SIGN_DIR, name + '.sign.json')
    packet_path = os.path.join(directory, packet_rel)
    statement_path = os.path.join(directory, statement_rel)
    write_json(packet_path, packet)
    doc = {'ceremony': 'RETICULI_CLAIM_BASIN_V1', 'identity': identity,
           'root': packet['root'], 'sign_root': packet['sign_root'],
           'build_digest': packet['build_digest'],
           'packet_digest': hashlib.sha256(_bytes(packet)).hexdigest(),
           'proof_recorded': packet['proof'] is not None,
           'public_key': open(key + '.pub').read().strip()}
    write_json(statement_path, doc)
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {**doc, 'packet': packet_rel, 'statement': statement_rel,
            'signature': statement_rel + '.sig'}

def sign_check(directory, *, ws=None, signers=None):
    base = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.endswith('.sign.json'):
                continue
            statement = os.path.join(base, name)
            packet_path = os.path.join(base, name[:-10] + '.packet.json')
            try:
                doc = read_json(statement)
                packet = read_json(packet_path)
                packet_holds = hashlib.sha256(_bytes(packet)).hexdigest() == doc.get('packet_digest')
                signer = _verify(statement, kernel.SIGN_NAMESPACE, signers, doc.get('public_key'))
                checked = kernel.verify(directory)
                holds = bool(packet_holds and signer and checked['ok'] and
                             doc.get('root') == checked['root'] and
                             packet.get('root') == checked['root'] and
                             packet.get('build_digest') == kernel.build_digest(directory) and
                             packet.get('sign_root') == registry.sign_root(directory, ws) and
                             packet.get('proof') == kernel.read_manifest(directory).get('proof'))
                rows.append({'verdict': 'authorized' if holds else 'refused', 'ok': holds,
                             'packet_holds': packet_holds, 'proof_recorded': doc.get('proof_recorded'),
                             'signer': signer})
            except (OSError, ValueError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'ok': False, 'packet_holds': False})
    return {'ok': bool(rows and all(r['ok'] for r in rows)), 'authorizations': rows}

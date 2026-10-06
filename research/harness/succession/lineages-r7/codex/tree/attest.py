"""SSH attestations and review authorizations for concrete claim builds."""
import hashlib
import json
import os
import subprocess

from . import kernel, registry
from ._util import write_json

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'


def _sign(path, key, namespace):
    signature = path + '.sig'
    if os.path.exists(signature):
        os.remove(signature)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                          capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('ssh signing failed: ' + done.stderr)
    return signature


def _verify(path, identity, signers, namespace):
    try:
        data = open(path, 'rb').read()
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', identity,
                               '-n', namespace, '-s', path + '.sig'], input=data,
                              capture_output=True, timeout=15)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _ready(directory):
    verified = kernel.verify(directory)
    if not verified['ok'] or not registry.audit_deep(directory)['ok']:
        raise kernel.ClaimError('claim verdicts do not reproduce')
    return verified


def attest(directory, key, identity):
    verified = _ready(directory)
    path = os.path.join(directory, ATTEST, identity.replace('/', '_') + '.json')
    statement = {'identity': identity, 'root': verified['root'],
                 'build_digest': kernel.build_digest(directory)}
    write_json(path, statement)
    _sign(path, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory), **statement}


def check(directory, signers=None):
    base = os.path.join(directory, ATTEST)
    rows = []
    if not os.path.isdir(base):
        return {'ok': False, 'attestations': rows}
    try:
        verified = kernel.verify(directory)
        digest = kernel.build_digest(directory)
    except kernel.ClaimError:
        return {'ok': False, 'attestations': rows}
    for filename in sorted(os.listdir(base)):
        if not filename.endswith('.json'):
            continue
        path = os.path.join(base, filename)
        try:
            raw = open(path, 'rb').read()
            doc = json.loads(raw)
            canonical = (json.dumps(doc, sort_keys=True) + '\n').encode()
            intact = raw == canonical and doc['root'] == verified['root'] and verified['ok']
            drifted = doc['build_digest'] != digest
            if signers:
                signed = _verify(path, doc['identity'], signers, kernel.NAMESPACE)
            else:
                signed = os.path.isfile(path + '.sig')
            ok = intact and not drifted and signed
            rows.append({'verdict': 'signed' if ok else 'refused', 'ok': ok,
                         'drifted': drifted, 'identity': doc['identity']})
        except (OSError, ValueError, KeyError):
            rows.append({'verdict': 'refused', 'ok': False, 'drifted': False})
    return {'ok': bool(rows) and all(x['ok'] for x in rows), 'attestations': rows}


def review_packet(directory, *, ws=None):
    verified = _ready(directory)
    manifest = kernel.read_manifest(directory)
    return {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws),
            'audit': registry.audit_deep(directory, ws=ws),
            'proof': manifest.get('proof')}


def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    # The kernel phase reader requires this exact three-member packet.
    phase_packet = {'root': packet['root'], 'build_digest': packet['build_digest'],
                    'proof': packet['proof']}
    base = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(base, exist_ok=True)
    stem = identity.replace('/', '_')
    packet_path = os.path.join(base, stem + '.packet.json')
    statement_path = os.path.join(base, stem + '.sign.json')
    write_json(packet_path, phase_packet)
    digest = hashlib.sha256(json.dumps(phase_packet, sort_keys=True).encode()).hexdigest()
    statement = {'ceremony': CEREMONY, 'identity': identity, 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'packet_digest': digest,
                 'proof_recorded': packet['proof'] is not None}
    write_json(statement_path, statement)
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'statement': os.path.relpath(statement_path, directory),
            'packet': os.path.relpath(packet_path, directory),
            'signature': os.path.relpath(statement_path + '.sig', directory)}


def sign_check(directory, *, ws=None, signers=None):
    base = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if not os.path.isdir(base):
        return {'ok': False, 'authorizations': rows}
    for filename in sorted(os.listdir(base)):
        if not filename.endswith('.sign.json'):
            continue
        path = os.path.join(base, filename)
        packet_path = path.replace('.sign.json', '.packet.json')
        try:
            raw = open(path, 'rb').read()
            statement = json.loads(raw)
            packet = json.load(open(packet_path))
            canonical = (json.dumps(statement, sort_keys=True) + '\n').encode()
            packet_digest = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()
            packet_holds = packet_digest == statement['packet_digest']
            manifest = kernel.read_manifest(directory)
            current = {'root': kernel.verify(directory)['root'],
                       'build_digest': kernel.build_digest(directory),
                       'proof': manifest.get('proof')}
            packet_holds &= packet == current
            chain_holds = statement['sign_root'] == registry.sign_root(directory, ws)
            anchored = _verify(path, statement['identity'], signers, kernel.SIGN_NAMESPACE) if signers else False
            ok = raw == canonical and packet_holds and chain_holds and anchored
            rows.append({'verdict': 'authorized' if ok else 'refused', 'ok': ok,
                         'packet_holds': packet_holds, 'proof_recorded': statement.get('proof_recorded', False)})
        except (OSError, ValueError, KeyError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'ok': False, 'packet_holds': False,
                         'proof_recorded': False})
    return {'ok': bool(rows) and all(r['ok'] for r in rows), 'authorizations': rows}

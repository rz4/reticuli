"""SSH signed build attestations and review ceremonies."""
import hashlib
import json
import os
import subprocess

from . import kernel, registry
from ._util import stamp

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'

def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()

def _sign(data, key, namespace, path):
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace],
                          input=data, capture_output=True)
    if done.returncode: raise kernel.ClaimError('ssh signing failed: ' + done.stderr.decode(errors='replace')[-300:])
    with open(path, 'wb') as stream: stream.write(done.stdout)

def _verify(data, path, signers, ident, namespace):
    if not os.path.isfile(path) or not signers: return False
    try:
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', ident,
                               '-n', namespace, '-s', path], input=data,
                              capture_output=True, timeout=15)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired): return False

def _safe_build(directory):
    if not kernel.verify(directory)['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('claim verdict does not reproduce')

def attest(directory, key, identity):
    _safe_build(directory)
    folder = os.path.join(directory, ATTEST)
    os.makedirs(folder, exist_ok=True)
    statement = {'root': kernel.read_manifest(directory)['root'],
                 'build_digest': kernel.build_digest(directory), 'identity': identity,
                 'when': stamp()}
    rel = ATTEST + '/build.json'
    with open(os.path.join(directory, rel), 'wb') as stream: stream.write(_bytes(statement))
    _sign(_bytes(statement), key, kernel.NAMESPACE, os.path.join(directory, rel + '.sig'))
    return {'statement': rel, 'signature': rel + '.sig', **statement}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json'): continue
            path = os.path.join(folder, name)
            try:
                data = open(path, 'rb').read()
                statement = json.loads(data)
                canonical = data == _bytes(statement)
                drift = statement.get('build_digest') != kernel.build_digest(directory)
                root = statement.get('root') == kernel.verify(directory)['root']
                signature = _verify(data, path + '.sig', signers, statement.get('identity',''), kernel.NAMESPACE) if signers else os.path.isfile(path+'.sig')
                ok = canonical and not drift and root and signature
                rows.append({'verdict': 'signed' if ok else 'refused', 'drifted': drift, 'ok': ok})
            except (OSError, ValueError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'drifted': False, 'ok': False})
    return {'ok': bool(rows) and all(r['ok'] for r in rows), 'attestations': rows}

def review_packet(directory, ws=None):
    manifest = kernel.read_manifest(directory)
    return {'root': manifest['root'], 'build_digest': kernel.build_digest(directory),
            'proof': manifest.get('proof'), 'audit': registry.audit_deep(directory, ws),
            'sign_root': registry.sign_root(directory, ws)}

def sign(directory, key, identity, ws=None):
    review = review_packet(directory, ws)
    if not review['audit']['ok']:
        raise kernel.ClaimError('composed verdict does not reproduce')
    packet = {'root': review['root'], 'build_digest': review['build_digest'],
              'proof': review['proof']}
    folder = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(folder, exist_ok=True)
    packet_rel = kernel.SIGN_DIR + '/claim.packet.json'
    statement_rel = kernel.SIGN_DIR + '/claim.sign.json'
    with open(os.path.join(directory, packet_rel), 'wb') as stream: stream.write(_bytes(packet))
    statement = {'ceremony': CEREMONY, 'root': packet['root'],
                 'sign_root': review['sign_root'], 'build_digest': packet['build_digest'],
                 'proof_recorded': packet['proof'] is not None, 'identity': identity,
                 'packet_digest': hashlib.sha256(_bytes(packet)).hexdigest()}
    with open(os.path.join(directory, statement_rel), 'wb') as stream: stream.write(_bytes(statement))
    _sign(_bytes(statement), key, kernel.SIGN_NAMESPACE, os.path.join(directory, statement_rel+'.sig'))
    return {**statement, 'statement': statement_rel, 'signature': statement_rel+'.sig', 'packet': packet_rel}

def sign_check(directory, ws=None, signers=None):
    path = os.path.join(directory, kernel.SIGN_DIR, 'claim.sign.json')
    if not os.path.isfile(path): return {'ok': False, 'authorizations': []}
    try:
        data = open(path, 'rb').read()
        statement = json.loads(data)
        packet_path = os.path.join(directory, kernel.SIGN_DIR, 'claim.packet.json')
        packet = open(packet_path, 'rb').read()
        packet_holds = hashlib.sha256(packet).hexdigest() == statement.get('packet_digest')
        current = review_packet(directory, ws)
        chain_holds = statement.get('sign_root') == current['sign_root'] and statement.get('root') == current['root']
        sig = _verify(data, path+'.sig', signers, statement.get('identity',''), kernel.SIGN_NAMESPACE)
        ok = packet_holds and chain_holds and sig and data == _bytes(statement)
        row = {'verdict': 'authorized' if ok else 'refused', 'packet_holds': packet_holds,
               'proof_recorded': statement.get('proof_recorded', False), 'ok': ok}
    except (OSError, ValueError, kernel.ClaimError):
        row = {'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False, 'ok': False}
    return {'ok': row['ok'], 'authorizations': [row]}

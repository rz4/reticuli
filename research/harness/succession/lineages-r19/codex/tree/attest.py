"""Signed build attestations and chain authorization."""
import hashlib
import json
import os
import subprocess
from . import kernel, registry, _util

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'

def _canonical(obj): return json.dumps(obj, sort_keys=True).encode()
def _sign(path, key, namespace):
    if os.path.exists(path + '.sig'): os.unlink(path + '.sig')
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path], capture_output=True)
    if done.returncode: raise kernel.ClaimError(done.stderr.decode(errors='replace'))

def _verify(path, identity, signers, namespace):
    if not signers: return os.path.isfile(path + '.sig')
    try:
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', identity, '-n', namespace, '-s', path + '.sig'], input=open(path, 'rb').read(), capture_output=True)
        return done.returncode == 0
    except OSError: return False

def _earned(directory):
    if not kernel.verify(directory)['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('claim verdict did not reproduce')

def attest(directory, key, identity):
    _earned(directory)
    v = kernel.verify(directory)
    statement = {'root': v['root'], 'build_digest': kernel.build_digest(directory), 'identity': identity}
    rel = ATTEST + '/build.json'; path = os.path.join(directory, rel)
    _util.write_json(path, statement); _sign(path, key, kernel.NAMESPACE)
    return {'statement': rel, 'signature': rel + '.sig', **statement}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST); rows = []
    if not os.path.isdir(folder): return {'ok': False, 'attestations': []}
    for name in sorted(os.listdir(folder)):
        if not name.endswith('.json'): continue
        path = os.path.join(folder, name)
        try:
            raw = open(path, 'rb').read(); statement = json.loads(raw)
            drifted = statement.get('root') != kernel.verify(directory)['root'] or statement.get('build_digest') != kernel.build_digest(directory)
            valid = raw == _canonical(statement) and _verify(path, statement['identity'], signers, kernel.NAMESPACE)
            rows.append({'verdict': 'signed' if valid and not drifted else 'refused', 'drifted': drifted, 'ok': valid and not drifted})
        except (OSError, ValueError, KeyError, kernel.ClaimError): rows.append({'verdict': 'refused', 'drifted': False, 'ok': False})
    return {'ok': bool(rows) and all(r['ok'] for r in rows), 'attestations': rows}

def review_packet(directory, *, ws=None):
    v = kernel.verify(directory)
    return {'root': v['root'], 'build_digest': kernel.build_digest(directory), 'proof': kernel.read_manifest(directory).get('proof'),
            'audit': kernel.audit(directory), 'deep_audit': registry.audit_deep(directory, ws), 'sign_root': registry.sign_root(directory, ws)}

def sign(directory, key, identity, *, ws=None):
    _earned(directory)
    if registry._links(directory) and not registry.audit_deep(directory, ws)['ok']:
        raise kernel.ClaimError('composed verdict did not reproduce')
    packet = review_packet(directory, ws=ws)
    rel_packet = kernel.SIGN_DIR + '/authorization.packet.json'
    rel_statement = kernel.SIGN_DIR + '/authorization.sign.json'
    packet_path = os.path.join(directory, rel_packet); statement_path = os.path.join(directory, rel_statement)
    _util.write_json(packet_path, {k: packet[k] for k in ('root', 'build_digest', 'proof')})
    statement = {'ceremony': CEREMONY, 'identity': identity, 'root': packet['root'], 'sign_root': packet['sign_root'],
                 'packet_digest': hashlib.sha256(open(packet_path, 'rb').read()).hexdigest(), 'proof_recorded': bool(packet['proof'])}
    _util.write_json(statement_path, statement); _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'signature': rel_statement + '.sig', 'statement': rel_statement,
            'packet': rel_packet, 'sign_root': packet['sign_root']}

def sign_check(directory, *, ws=None, signers=None):
    rel_statement = kernel.SIGN_DIR + '/authorization.sign.json'; path = os.path.join(directory, rel_statement)
    packet_path = os.path.join(directory, kernel.SIGN_DIR, 'authorization.packet.json')
    if not os.path.isfile(path): return {'ok': False, 'authorizations': []}
    try:
        raw = open(path, 'rb').read(); st = json.loads(raw)
        packet_bytes = open(packet_path, 'rb').read(); packet = json.loads(packet_bytes)
        packet_holds = hashlib.sha256(packet_bytes).hexdigest() == st['packet_digest']
        fresh = st['root'] == kernel.verify(directory)['root'] and st['sign_root'] == registry.sign_root(directory, ws)
        signature = raw == _canonical(st) and _verify(path, st['identity'], signers, kernel.SIGN_NAMESPACE)
        ok = packet_holds and fresh and signature
        row = {'verdict': 'authorized' if ok else 'refused', 'packet_holds': packet_holds,
               'proof_recorded': bool(st.get('proof_recorded')), 'ok': ok}
    except (OSError, ValueError, KeyError, kernel.ClaimError): row = {'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False, 'ok': False}
    return {'ok': row['ok'], 'authorizations': [row]}

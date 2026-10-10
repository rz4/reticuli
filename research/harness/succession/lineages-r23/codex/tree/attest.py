"""SSH attestations of builds and accountable chain authorization."""
import hashlib
import json
import os
import subprocess
import tempfile

from . import kernel, registry
from ._util import write_json

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'


def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()


def _sign(path, key, namespace):
    sig = path + '.sig'
    if os.path.exists(sig):
        os.remove(sig)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                          capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('SSH signing failed: ' + done.stderr)


def _verify(path, sig, principal, anchor, namespace):
    try:
        with open(path, 'rb') as stream:
            data = stream.read()
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor, '-I', principal,
                               '-n', namespace, '-s', sig], input=data, capture_output=True)
        return done.returncode == 0
    except OSError:
        return False


def _key_anchor(statement):
    key = statement.get('key')
    if not isinstance(key, str):
        return None
    temp = tempfile.NamedTemporaryFile('w', delete=False)
    try:
        temp.write(statement['identity'] + ' ' + key + '\n')
        temp.close()
        return temp.name
    except Exception:
        os.unlink(temp.name)
        raise


def _earned(directory, *, deep=False, ws=None):
    if not kernel.verify(directory)['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    audit = registry.audit_deep(directory, ws) if deep else kernel.audit(directory)
    if not audit['ok']:
        raise kernel.ClaimError('composed verdict did not re-earn' if deep else 'verdict did not re-earn')
    return audit


def attest(directory, key, identity):
    _earned(directory)
    base = os.path.join(directory, ATTEST)
    os.makedirs(base, exist_ok=True)
    pub = open(key + '.pub', encoding='utf-8').read().split()[:2]
    statement = {'identity': identity, 'root': kernel.verify(directory)['root'],
                 'build_digest': kernel.build_digest(directory), 'key': ' '.join(pub)}
    path = os.path.join(base, 'build.json')
    write_json(path, statement)
    _sign(path, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory)}


def check(directory, signers=None):
    base = os.path.join(directory, ATTEST)
    rows = []
    if not os.path.isdir(base):
        return {'ok': False, 'attestations': []}
    for name in sorted(os.listdir(base)):
        if not name.endswith('.json'):
            continue
        path = os.path.join(base, name)
        try:
            statement = json.load(open(path, encoding='utf-8'))
            anchor = signers or _key_anchor(statement)
            signed = _verify(path, path + '.sig', statement['identity'], anchor, kernel.NAMESPACE)
            drifted = statement['build_digest'] != kernel.build_digest(directory)
            root_ok = kernel.verify(directory)['ok'] and statement['root'] == kernel.verify(directory)['root']
            rows.append({'verdict': 'signed' if signed and not drifted and root_ok else 'refused',
                         'drifted': drifted, 'identity': statement['identity']})
        except (OSError, ValueError, KeyError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'drifted': False})
        finally:
            if not signers and 'anchor' in locals() and anchor:
                os.unlink(anchor)
                anchor = None
    return {'ok': bool(rows) and all(x['verdict'] == 'signed' for x in rows),
            'attestations': rows}


def review_packet(directory, *, ws=None):
    audit = _earned(directory, deep=True, ws=ws)
    manifest = kernel.read_manifest(directory)
    return {'root': manifest['root'], 'sign_root': registry.sign_root(directory, ws),
            'build_digest': kernel.build_digest(directory), 'audit': audit,
            'proof': manifest.get('proof')}


def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    base = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(base, exist_ok=True)
    packet_path = os.path.join(base, 'claim.packet.json')
    # Keep the kernel phase verifier's compact packet schema.
    compact = {'root': packet['root'], 'build_digest': packet['build_digest'],
               'proof': packet['proof']}
    write_json(packet_path, compact)
    statement = {'ceremony': CEREMONY, 'identity': identity, 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'build_digest': packet['build_digest'],
                 'packet_digest': hashlib.sha256(_bytes(compact)).hexdigest(),
                 'proof_recorded': bool(packet['proof'])}
    path = os.path.join(base, 'claim.sign.json')
    write_json(path, statement)
    _sign(path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'signature': os.path.relpath(path + '.sig', directory),
            'statement': os.path.relpath(path, directory),
            'packet': os.path.relpath(packet_path, directory),
            'sign_root': packet['sign_root']}


def sign_check(directory, *, ws=None, signers=None):
    base = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if not os.path.isdir(base):
        return {'ok': False, 'authorizations': rows}
    for name in sorted(os.listdir(base)):
        if not name.endswith('.sign.json'):
            continue
        path = os.path.join(base, name)
        packet_path = path[:-10] + '.packet.json'
        try:
            statement = json.load(open(path, encoding='utf-8'))
            packet = json.load(open(packet_path, encoding='utf-8'))
            holds = statement['packet_digest'] == hashlib.sha256(_bytes(packet)).hexdigest()
            holds &= packet == {'root': kernel.verify(directory)['root'],
                                'build_digest': kernel.build_digest(directory),
                                'proof': kernel.read_manifest(directory).get('proof')}
            chain = statement['sign_root'] == registry.sign_root(directory, ws)
            anchor = signers or os.environ.get('RETICULI_SIGNERS')
            signed = bool(anchor) and _verify(path, path + '.sig', statement['identity'], anchor,
                                              kernel.SIGN_NAMESPACE)
            ok = holds and chain and signed
            rows.append({'verdict': 'authorized' if ok else 'refused',
                         'packet_holds': bool(holds), 'proof_recorded': statement['proof_recorded']})
        except (OSError, ValueError, KeyError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False})
    return {'ok': bool(rows) and all(x['verdict'] == 'authorized' for x in rows),
            'authorizations': rows}

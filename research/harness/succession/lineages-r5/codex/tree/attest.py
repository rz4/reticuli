"""Signed build attestations and reviewed chain authorizations."""
import hashlib
import json
import os
import subprocess

from . import kernel
from ._util import write_json

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'


def _signed(path, key, namespace):
    sig = path + '.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    try:
        subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                       check=True, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        raise kernel.ClaimError(f'cannot sign statement: {exc}') from exc


def _identities(anchor):
    try:
        with open(anchor, encoding='utf-8') as f:
            return [line.split()[0] for line in f if line.strip() and not line.lstrip().startswith('#')]
    except OSError:
        return []


def _verify(path, anchor, namespace, identity=None):
    identities = [identity] if identity else _identities(anchor)
    for candidate in identities:
        try:
            with open(path, 'rb') as f:
                data = f.read()
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor, '-I', candidate,
                                   '-n', namespace, '-s', path + '.sig'],
                                  input=data, capture_output=True, timeout=20)
            if done.returncode == 0:
                return candidate
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _audit(directory):
    from . import registry
    checked = kernel.verify(directory)
    if not checked['ok'] or not registry.audit_deep(directory)['ok']:
        raise kernel.ClaimError('claim verdicts do not reproduce')
    return checked


def attest(directory, key, identity):
    checked = _audit(directory)
    data = {'root': checked['root'], 'build_digest': kernel.build_digest(directory), 'identity': identity}
    path = os.path.join(directory, ATTEST, 'build.json')
    write_json(path, data)
    _signed(path, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory), 'root': checked['root']}


def check(directory, signers=None):
    base = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(base):
        for filename in sorted(os.listdir(base)):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(base, filename)
            try:
                data = json.load(open(path, encoding='utf-8'))
                drifted = data.get('root') != kernel.verify(directory)['root'] or data.get('build_digest') != kernel.build_digest(directory)
                signed = bool(signers and _verify(path, signers, kernel.NAMESPACE, data.get('identity')))
                if not signers:
                    signed = os.path.isfile(path + '.sig')
                rows.append({'verdict': 'signed' if signed and not drifted else 'refused',
                             'drifted': drifted, 'ok': signed and not drifted})
            except (OSError, ValueError, kernel.ClaimError):
                rows.append({'verdict': 'refused', 'drifted': True, 'ok': False})
    return {'ok': bool(rows) and all(x['ok'] for x in rows), 'attestations': rows}


def review_packet(directory, ws=None):
    from . import registry
    checked = _audit(directory)
    manifest = kernel.read_manifest(directory)
    return {'root': checked['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws), 'audit': registry.audit_deep(directory),
            'proof': manifest.get('proof')}


def sign(directory, key, identity, ws=None):
    packet = review_packet(directory, ws)
    # The kernel's phase reader accepts this exact packet shape.
    proof = kernel.read_manifest(directory).get('proof')
    phase_packet = {'root': packet['root'], 'build_digest': packet['build_digest'], 'proof': proof}
    base = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(base, exist_ok=True)
    packet_path = os.path.join(base, 'review.packet.json')
    write_json(packet_path, phase_packet)
    raw = json.dumps(phase_packet, sort_keys=True).encode()
    statement = {'ceremony': CEREMONY, 'root': packet['root'], 'build_digest': packet['build_digest'],
                 'sign_root': packet['sign_root'], 'packet_digest': hashlib.sha256(raw).hexdigest(),
                 'proof_recorded': bool(proof), 'identity': identity}
    path = os.path.join(base, 'review.sign.json')
    write_json(path, statement)
    _signed(path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'statement': os.path.relpath(path, directory),
            'signature': os.path.relpath(path + '.sig', directory),
            'packet': os.path.relpath(packet_path, directory)}


def sign_check(directory, ws=None, signers=None):
    from . import registry
    base = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if not os.path.isdir(base):
        return {'ok': False, 'authorizations': []}
    for filename in sorted(os.listdir(base)):
        if not filename.endswith('.sign.json'):
            continue
        path = os.path.join(base, filename)
        packet_path = os.path.join(base, filename[:-len('.sign.json')] + '.packet.json')
        try:
            statement = json.load(open(path, encoding='utf-8'))
            packet = json.load(open(packet_path, encoding='utf-8'))
            expected_packet = {'root': kernel.verify(directory)['root'],
                               'build_digest': kernel.build_digest(directory),
                               'proof': kernel.read_manifest(directory).get('proof')}
            raw = json.dumps(packet, sort_keys=True).encode()
            holds = packet == expected_packet and statement.get('packet_digest') == hashlib.sha256(raw).hexdigest()
            chain = registry.sign_root(directory, ws) == statement.get('sign_root')
            anchored = _verify(path, signers, kernel.SIGN_NAMESPACE, statement.get('identity')) if signers else None
            ok = bool(holds and chain and anchored)
            rows.append({'verdict': 'authorized' if ok else 'refused', 'packet_holds': holds,
                         'proof_recorded': bool(statement.get('proof_recorded')), 'ok': ok})
        except (OSError, ValueError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False, 'ok': False})
    return {'ok': bool(rows) and all(r['ok'] for r in rows), 'authorizations': rows}

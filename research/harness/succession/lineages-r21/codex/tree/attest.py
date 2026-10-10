"""Signed build attestations and chain authorization."""
import hashlib
import json
import os
import subprocess
import tempfile

from . import kernel, registry
from ._util import stamp, write_json

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'

def _canonical(value):
    return json.dumps(value, sort_keys=True).encode()

def _pubkey(key):
    try:
        with open(key + '.pub', encoding='utf-8') as stream:
            return ' '.join(stream.read().split()[:2])
    except OSError as exc:
        raise kernel.ClaimError(f'cannot read signing key: {exc}') from exc

def _sign(path, key, namespace):
    try:
        if os.path.exists(path + '.sig'):
            os.unlink(path + '.sig')
        result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                                capture_output=True, text=True)
        if result.returncode:
            raise kernel.ClaimError('ssh signing failed: ' + result.stderr)
    except OSError as exc:
        raise kernel.ClaimError(f'ssh signing failed: {exc}') from exc

def _verify(path, identity, namespace, signers=None, public_key=None):
    if not os.path.isfile(path + '.sig'):
        return False
    temporary = None
    try:
        if not signers:
            if not public_key:
                return False
            with tempfile.NamedTemporaryFile('w', delete=False) as stream:
                stream.write(identity + ' ' + public_key + '\n')
                temporary = stream.name
            signers = temporary
        with open(path, 'rb') as stream:
            data = stream.read()
        result = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers, '-I', identity,
                                 '-n', namespace, '-s', path + '.sig'], input=data,
                                capture_output=True)
        return result.returncode == 0
    except (OSError, ValueError):
        return False
    finally:
        if temporary:
            os.unlink(temporary)

def _earned(directory, composed=False):
    checked = kernel.verify(directory)
    if not checked['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('claim verdict does not reproduce')
    if composed and registry._manifest(directory).get('components') and not registry.audit_deep(directory)['ok']:
        raise kernel.ClaimError('composed verdict does not reproduce')
    return checked

def attest(directory, key, identity):
    checked = _earned(directory)
    statement = {'ceremony': 'RETICULI_BUILD_ATTEST_V1', 'identity': identity,
                 'public_key': _pubkey(key), 'root': checked['root'],
                 'build_digest': kernel.build_digest(directory), 'when': stamp()}
    rel = os.path.join(ATTEST, identity.replace('/', '_') + '.json')
    path = os.path.join(directory, rel)
    write_json(path, statement)
    _sign(path, key, kernel.NAMESPACE)
    return {'statement': rel, 'signature': rel + '.sig', 'root': checked['root']}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(folder, filename)
            row = {'statement': os.path.relpath(path, directory), 'verdict': 'invalid', 'drifted': False}
            try:
                with open(path, encoding='utf-8') as stream:
                    statement = json.load(stream)
                row['drifted'] = statement.get('build_digest') != kernel.build_digest(directory)
                root_ok = statement.get('root') == kernel.verify(directory)['root']
                signed = _verify(path, statement['identity'], kernel.NAMESPACE, signers, statement.get('public_key'))
                if root_ok and not row['drifted'] and signed:
                    row['verdict'] = 'signed'
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                pass
            rows.append(row)
    return {'ok': bool(rows) and all(row['verdict'] == 'signed' for row in rows), 'attestations': rows}

def review_packet(directory, *, ws=None):
    checked = _earned(directory, composed=True)
    manifest = kernel.read_manifest(directory)
    return {'root': checked['root'], 'sign_root': registry.sign_root(directory, ws),
            'build_digest': kernel.build_digest(directory),
            'audit': registry.audit_deep(directory, ws), 'proof': manifest.get('proof')}

def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    relbase = os.path.join(kernel.SIGN_DIR, identity.replace('/', '_'))
    packet_rel = relbase + '.packet.json'
    statement_rel = relbase + '.sign.json'
    packet_path = os.path.join(directory, packet_rel)
    statement_path = os.path.join(directory, statement_rel)
    write_json(packet_path, packet)
    statement = {'ceremony': CEREMONY, 'identity': identity,
                 'public_key': _pubkey(key), 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'build_digest': packet['build_digest'],
                 'packet_digest': hashlib.sha256(_canonical(packet)).hexdigest(),
                 'proof_recorded': bool(packet['proof']), 'when': stamp()}
    write_json(statement_path, statement)
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'statement': statement_rel,
            'signature': statement_rel + '.sig', 'packet': packet_rel,
            'sign_root': packet['sign_root']}

def sign_check(directory, *, ws=None, signers=None):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(folder):
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith('.sign.json'):
                continue
            path = os.path.join(folder, filename)
            packet_path = path[:-len('.sign.json')] + '.packet.json'
            row = {'verdict': 'invalid', 'packet_holds': False, 'proof_recorded': False}
            try:
                with open(path, encoding='utf-8') as stream:
                    statement = json.load(stream)
                with open(packet_path, encoding='utf-8') as stream:
                    packet = json.load(stream)
                row['proof_recorded'] = bool(statement.get('proof_recorded'))
                row['packet_holds'] = hashlib.sha256(_canonical(packet)).hexdigest() == statement['packet_digest']
                manifest = kernel.read_manifest(directory)
                valid = (row['packet_holds'] and statement['root'] == manifest['root']
                         and statement['sign_root'] == registry.sign_root(directory, ws)
                         and statement['build_digest'] == kernel.build_digest(directory)
                         and packet.get('proof') == manifest.get('proof'))
                if valid and _verify(path, statement['identity'], kernel.SIGN_NAMESPACE,
                                     signers, statement.get('public_key')):
                    row['verdict'] = 'authorized'
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                pass
            rows.append(row)
    return {'ok': bool(rows) and all(row['verdict'] == 'authorized' for row in rows),
            'authorizations': rows}

"""Signed build attestations and chain authorization ceremonies."""
import hashlib
import json
import os
import subprocess
import tempfile

from . import kernel, registry
from ._kernel import core

ATTEST = '.reticuli/attest'

def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()

def _sign(path, key, namespace):
    signature = path + '.sig'
    if os.path.exists(signature):
        os.remove(signature)
    result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path],
                            capture_output=True)
    if result.returncode:
        raise kernel.ClaimError('ssh signing failed: ' + result.stderr.decode('utf-8', 'replace'))
    return signature

def _verify(path, principal, signers, namespace):
    try:
        with open(path, 'rb') as stream:
            data = stream.read()
        result = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', signers,
                                 '-I', principal, '-n', namespace, '-s', path + '.sig'],
                                input=data, capture_output=True, timeout=15)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False

def _local_anchor(pub, principal):
    with open(pub, encoding='utf-8') as stream:
        keytype, blob = stream.read().split()[:2]
    temporary = tempfile.NamedTemporaryFile('w', delete=False)
    try:
        temporary.write(f'{principal} {keytype} {blob}\n')
        temporary.close()
        return temporary.name
    except Exception:
        temporary.close()
        os.remove(temporary.name)
        raise

def attest(directory, key, identity):
    verified = kernel.verify(directory)
    audited = registry.audit_deep(directory)
    if not verified['ok'] or not audited['ok']:
        raise kernel.ClaimError('attestation requires freshly earned verdicts')
    path = os.path.join(directory, ATTEST)
    os.makedirs(path, exist_ok=True)
    statement = os.path.join(path, 'build.json')
    value = {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
             'identity': identity}
    with open(statement, 'wb') as stream:
        stream.write(_bytes(value))
    with open(key + '.pub', 'rb') as source, open(statement + '.pub', 'wb') as target:
        target.write(source.read())
    _sign(statement, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(statement, directory),
            'signature': os.path.relpath(statement + '.sig', directory), **value}

def check(directory, signers=None):
    statement = os.path.join(directory, ATTEST, 'build.json')
    if not os.path.isfile(statement):
        return {'ok': False, 'attestations': []}
    anchor = signers
    temporary = None
    try:
        with open(statement, 'rb') as stream:
            raw = stream.read()
        value = json.loads(raw)
        if anchor is None:
            temporary = _local_anchor(statement + '.pub', value['identity'])
            anchor = temporary
        intact = raw == _bytes(value) and _verify(statement, value['identity'], anchor, kernel.NAMESPACE)
        drifted = (not kernel.verify(directory)['ok'] or
                   value['build_digest'] != kernel.build_digest(directory) or
                   value['root'] != kernel.verify(directory)['root'])
        signed = intact and not drifted
        return {'ok': signed, 'attestations': [{'verdict': 'signed' if signed else 'refused',
                                               'drifted': drifted, 'identity': value['identity']}]}
    except (OSError, ValueError, KeyError, kernel.ClaimError):
        return {'ok': False, 'attestations': [{'verdict': 'refused', 'drifted': True}]}
    finally:
        if temporary:
            os.remove(temporary)

def review_packet(directory, *, ws=None):
    verified = kernel.verify(directory)
    audited = registry.audit_deep(directory, ws)
    return {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws), 'audit': audited,
            'proof': kernel.read_manifest(directory).get('proof')}

def sign(directory, key, identity, *, ws=None):
    packet = review_packet(directory, ws=ws)
    if not kernel.verify(directory)['ok'] or not packet['audit']['ok']:
        raise kernel.ClaimError('signing requires freshly earned verdicts')
    folder = os.path.join(directory, kernel.SIGN_DIR)
    os.makedirs(folder, exist_ok=True)
    manifest = kernel.read_manifest(directory)
    stored_packet = {'root': packet['root'], 'build_digest': packet['build_digest'],
                     'proof': manifest.get('proof')}
    packet_path = os.path.join(folder, 'chain.packet.json')
    core._write_json(packet_path, stored_packet)
    packet_digest = hashlib.sha256(_bytes(stored_packet)).hexdigest()
    statement = {'ceremony': 'RETICULI_CLAIM_BASIN_V1', 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'build_digest': packet['build_digest'],
                 'packet_digest': packet_digest, 'proof_recorded': bool(manifest.get('proof')),
                 'identity': identity}
    statement_path = os.path.join(folder, 'chain.sign.json')
    with open(statement_path, 'wb') as stream:
        stream.write(_bytes(statement))
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return dict(statement, statement=os.path.relpath(statement_path, directory),
                signature=os.path.relpath(statement_path + '.sig', directory),
                packet=os.path.relpath(packet_path, directory))

def sign_check(directory, *, ws=None, signers=None):
    statement_path = os.path.join(directory, kernel.SIGN_DIR, 'chain.sign.json')
    packet_path = os.path.join(directory, kernel.SIGN_DIR, 'chain.packet.json')
    if not os.path.isfile(statement_path):
        return {'ok': False, 'authorizations': []}
    try:
        with open(statement_path, 'rb') as stream:
            raw = stream.read()
        statement = json.loads(raw)
        with open(packet_path, 'rb') as stream:
            packet_raw = stream.read()
        packet = json.loads(packet_raw)
        manifest = kernel.read_manifest(directory)
        expected = {'root': manifest['root'], 'build_digest': kernel.build_digest(directory),
                    'proof': manifest.get('proof')}
        packet_holds = (packet_raw == _bytes(packet) or packet_raw == _bytes(packet) + b'\n') and packet == expected and statement['packet_digest'] == hashlib.sha256(_bytes(packet)).hexdigest()
        chain_holds = statement['sign_root'] == registry.sign_root(directory, ws)
        signed = bool(signers) and raw == _bytes(statement) and _verify(statement_path, statement['identity'], signers, kernel.SIGN_NAMESPACE)
        ok = bool(packet_holds and chain_holds and signed)
        return {'ok': ok, 'authorizations': [{'verdict': 'authorized' if ok else 'refused',
                                              'packet_holds': bool(packet_holds),
                                              'proof_recorded': statement.get('proof_recorded', False)}]}
    except (OSError, ValueError, KeyError, kernel.ClaimError):
        return {'ok': False, 'authorizations': [{'verdict': 'refused',
                                                'packet_holds': False, 'proof_recorded': False}]}

"""SSH signed build attestations and chain authorizations."""
import hashlib
import json
import os
import re
import subprocess
from . import kernel, registry
from ._kernel import core

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'

def _bytes(value):
    return json.dumps(value, sort_keys=True).encode()

def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as stream:
        stream.write(data)

def _sign(path, key, namespace):
    sig = path + '.sig'
    if os.path.exists(sig):
        os.unlink(sig)
    done = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', os.fspath(key),
                           '-n', namespace, path], capture_output=True)
    if done.returncode:
        raise kernel.ClaimError(done.stderr.decode(errors='replace'))
    return sig

def _verify(path, anchor, namespace, principal=None):
    if not os.path.isfile(path + '.sig') or not anchor or not os.path.isfile(anchor):
        return None
    with open(path, 'rb') as stream:
        data = stream.read()
    try:
        with open(anchor, encoding='utf-8') as stream:
            principals = [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith('#')]
    except (OSError, IndexError):
        return None
    for candidate in principals:
        if principal is not None and candidate != principal:
            continue
        try:
            done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor,
                                   '-I', candidate, '-n', namespace, '-s', path + '.sig'],
                                  input=data, capture_output=True, timeout=20)
            if done.returncode == 0:
                return candidate
        except (OSError, subprocess.TimeoutExpired):
            pass
    return None

def _stem(principal):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', principal)

def attest(directory, key, principal):
    verified = kernel.verify(directory)
    audit = kernel.audit(directory)
    if not verified['ok'] or not audit['ok']:
        raise kernel.ClaimError('attestation requires an earned verdict')
    statement = {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
                 'name': verified['name'], 'principal': principal}
    relative = ATTEST + '/' + _stem(principal) + '.json'
    target = core._safe(directory, relative)
    _write(target, _bytes(statement))
    _sign(target, key, kernel.NAMESPACE)
    return {'statement': relative, 'signature': relative + '.sig', **statement}

def check(directory, signers=None):
    folder = os.path.join(directory, ATTEST)
    rows = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith('.json'):
            continue
        path = os.path.join(folder, name)
        try:
            with open(path, 'rb') as stream:
                raw = stream.read()
            statement = json.loads(raw)
            exact = raw == _bytes(statement)
            drifted = (statement.get('root') != kernel.verify(directory)['root'] or
                       statement.get('build_digest') != kernel.build_digest(directory))
            anchored = _verify(path, signers, kernel.NAMESPACE, statement.get('principal')) if signers else None
            valid = exact and not drifted and os.path.isfile(path + '.sig') and (anchored is not None if signers else True)
            rows.append({'verdict': 'signed' if valid else 'refused', 'drifted': drifted,
                         'principal': statement.get('principal'), 'signature_holds': valid})
        except (OSError, ValueError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'drifted': False, 'signature_holds': False})
    return {'ok': bool(rows) and all(r['verdict'] == 'signed' for r in rows), 'attestations': rows}

def review_packet(directory, *, ws=None):
    verified = kernel.verify(directory)
    audit = registry.audit_deep(directory, ws)
    manifest = kernel.read_manifest(directory)
    return {'root': verified['root'], 'build_digest': kernel.build_digest(directory),
            'sign_root': registry.sign_root(directory, ws), 'audit': audit,
            'proof': manifest.get('proof')}

def sign(directory, key, principal, *, ws=None):
    packet = review_packet(directory, ws=ws)
    if not packet['audit']['ok'] or not kernel.verify(directory)['ok']:
        raise kernel.ClaimError('composed verdict did not re-earn')
    proof = packet['proof']
    # The kernel's signed-phase reader expects this stable review summary.
    stored = {'root': packet['root'], 'build_digest': packet['build_digest'], 'proof': proof}
    base = kernel.SIGN_DIR + '/' + _stem(principal)
    packet_rel = base + '.packet.json'
    statement_rel = base + '.sign.json'
    packet_path = core._safe(directory, packet_rel)
    statement_path = core._safe(directory, statement_rel)
    _write(packet_path, _bytes(stored))
    statement = {'ceremony': CEREMONY, 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'principal': principal,
                 'packet_digest': hashlib.sha256(_bytes(stored)).hexdigest(),
                 'proof_recorded': bool(proof)}
    _write(statement_path, _bytes(statement))
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return {'ceremony': CEREMONY, 'statement': statement_rel,
            'signature': statement_rel + '.sig', 'packet': packet_rel,
            'sign_root': packet['sign_root']}

def sign_check(directory, *, ws=None, signers=None):
    folder = os.path.join(directory, kernel.SIGN_DIR)
    rows = []
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith('.sign.json'):
            continue
        path = os.path.join(folder, name)
        packet_path = path[:-10] + '.packet.json'
        try:
            with open(path, 'rb') as stream:
                raw = stream.read()
            stmt = json.loads(raw)
            with open(packet_path, 'rb') as stream:
                packet_raw = stream.read()
            packet = json.loads(packet_raw)
            current = kernel.read_manifest(directory)
            expected = {'root': current['root'], 'build_digest': kernel.build_digest(directory),
                        'proof': current.get('proof')}
            packet_holds = packet_raw == _bytes(packet) and packet == expected and stmt.get('packet_digest') == hashlib.sha256(packet_raw).hexdigest()
            chain_holds = stmt.get('sign_root') == registry.sign_root(directory, ws)
            anchored = _verify(path, signers, kernel.SIGN_NAMESPACE, stmt.get('principal')) if signers else None
            ok = raw == _bytes(stmt) and packet_holds and chain_holds and bool(anchored)
            rows.append({'verdict': 'authorized' if ok else 'refused',
                         'packet_holds': packet_holds, 'proof_recorded': bool(stmt.get('proof_recorded')),
                         'principal': stmt.get('principal')})
        except (OSError, ValueError, kernel.ClaimError):
            rows.append({'verdict': 'refused', 'packet_holds': False, 'proof_recorded': False})
    return {'ok': bool(rows) and all(row['verdict'] == 'authorized' for row in rows),
            'authorizations': rows}

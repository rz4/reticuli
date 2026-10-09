"""SSH signed attestations and review authorizations."""
import hashlib
import json
import os
import subprocess

from . import kernel, registry
from ._util import stamp, write_json

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'


def _sign(path, key, namespace):
    signature = path + '.sig'
    if os.path.exists(signature):
        os.remove(signature)
    result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', key, '-n', namespace, path], capture_output=True)
    if result.returncode:
        raise kernel.ClaimError('signing failed: ' + result.stderr.decode(errors='replace'))


def _principals(anchor):
    with open(anchor, encoding='utf-8') as stream:
        return [line.split()[0] for line in stream if line.strip() and not line.lstrip().startswith('#')]


def _verify(path, namespace, anchor):
    data = open(path, 'rb').read()
    for principal in _principals(anchor):
        done = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', anchor, '-I', principal,
                               '-n', namespace, '-s', path + '.sig'], input=data, capture_output=True)
        if done.returncode == 0:
            return principal
    return None


def attest(path, key, identity):
    if not kernel.verify(path)['ok'] or not kernel.audit(path)['ok']:
        raise kernel.ClaimError('claim verdict not earned')
    root = kernel.verify(path)['root']
    statement = {'identity': identity, 'root': root, 'build_digest': kernel.build_digest(path),
                 'when': stamp()}
    dest = os.path.join(path, ATTEST, 'build.json')
    write_json(dest, statement)
    _sign(dest, key, kernel.NAMESPACE)
    return {'statement': os.path.relpath(dest,path), 'signature': os.path.relpath(dest + '.sig',path)}


def check(path, signers=None):
    folder = os.path.join(path, ATTEST)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json'):
                continue
            file = os.path.join(folder, name)
            try:
                doc = json.load(open(file, encoding='utf-8'))
                holds = kernel.verify(path)['ok'] and doc['root'] == kernel.verify(path)['root'] and doc['build_digest'] == kernel.build_digest(path)
                if signers:
                    signed = _verify(file, kernel.NAMESPACE, signers) == doc['identity']
                else:
                    signed = os.path.isfile(file + '.sig')
                rows.append({'verdict': 'signed' if holds and signed else 'refused',
                             'drifted': not holds, 'identity': doc['identity']})
            except (OSError, ValueError, KeyError, kernel.ClaimError):
                rows.append({'verdict':'refused', 'drifted':False})
    return {'ok': bool(rows) and all(x['verdict']=='signed' for x in rows), 'attestations':rows}


def review_packet(path, *, ws=None):
    checked = kernel.verify(path)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    audit = registry.audit_deep(path, ws)
    return {'root': checked['root'], 'build_digest': kernel.build_digest(path),
            'sign_root': registry.sign_root(path, ws), 'audit': audit,
            'proof': kernel.read_manifest(path).get('proof')}


def sign(path, key, identity, *, ws=None):
    packet = review_packet(path, ws=ws)
    if not packet['audit']['ok']:
        raise kernel.ClaimError('claim verdict not earned')
    proof = packet['proof']
    statement = {'ceremony': CEREMONY, 'identity': identity, 'root': packet['root'],
                 'sign_root': packet['sign_root'], 'build_digest': packet['build_digest'],
                 'packet_digest': hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest(),
                 'proof_recorded': bool(proof), 'when': stamp()}
    folder = os.path.join(path, kernel.SIGN_DIR)
    packet_path = os.path.join(folder, 'review.packet.json')
    statement_path = os.path.join(folder, 'review.sign.json')
    write_json(packet_path, packet)
    write_json(statement_path, statement)
    _sign(statement_path, key, kernel.SIGN_NAMESPACE)
    return dict(statement, statement=os.path.relpath(statement_path,path),
                packet=os.path.relpath(packet_path,path), signature=os.path.relpath(statement_path+'.sig',path))


def sign_check(path, *, ws=None, signers=None):
    folder = os.path.join(path, kernel.SIGN_DIR)
    rows = []
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.sign.json'):
                continue
            file = os.path.join(folder,name)
            try:
                doc = json.load(open(file,encoding='utf-8'))
                packet_file = file[:-10] + '.packet.json'
                packet = json.load(open(packet_file,encoding='utf-8'))
                holds = (doc['packet_digest'] == hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
                         and packet['root'] == kernel.verify(path)['root']
                         and packet['build_digest'] == kernel.build_digest(path)
                         and packet['sign_root'] == registry.sign_root(path,ws)
                         and packet['proof'] == kernel.read_manifest(path).get('proof'))
                signed = _verify(file,kernel.SIGN_NAMESPACE,signers) == doc['identity'] if signers else os.path.isfile(file+'.sig')
                rows.append({'verdict':'authorized' if holds and signed else 'refused',
                             'packet_holds':holds, 'proof_recorded':doc.get('proof_recorded',False)})
            except (OSError,ValueError,KeyError,kernel.ClaimError):
                rows.append({'verdict':'refused','packet_holds':False,'proof_recorded':False})
    return {'ok':bool(rows) and all(x['verdict']=='authorized' for x in rows), 'authorizations':rows}

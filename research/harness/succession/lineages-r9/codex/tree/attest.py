"""SSH attestations and accountable claim authorization."""
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
        os.unlink(signature)
    done = subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',namespace,path], capture_output=True, text=True)
    if done.returncode:
        raise kernel.ClaimError('cannot sign: '+done.stderr)
    return signature

def _verify(path, signature, namespace, identity=None, signers=None):
    try:
        with open(path, 'rb') as f:
            data = f.read()
        if signers:
            argv = ['ssh-keygen','-Y','verify','-f',signers,'-I',identity,'-n',namespace,'-s',signature]
        else:
            argv = ['ssh-keygen','-Y','check-novalidate','-n',namespace,'-s',signature]
        done = subprocess.run(argv, input=data, capture_output=True)
        return done.returncode == 0
    except (OSError, TypeError):
        return False

def _build(directory):
    parsed = kernel.load_recipe(directory)
    outputs = {}
    for step in parsed.get('step', []):
        if step['kind'] == 'produce':
            path = os.path.join(directory, step['output'])
            if os.path.isfile(path):
                outputs[step['output']] = kernel._hash_file(path)
    return outputs

def attest(directory, key, identity):
    checked = kernel.verify(directory)
    if not checked['ok'] or not kernel.audit(directory)['ok']:
        raise kernel.ClaimError('cannot attest an unearned claim')
    payload = {'identity':identity,'root':checked['root'], 'build_digest':kernel.build_digest(directory), 'outputs':_build(directory)}
    path = os.path.join(directory, ATTEST, identity.replace('/','_')+'.json')
    write_json(path, payload)
    sig = _sign(path, key, kernel.NAMESPACE)
    return {'statement':os.path.relpath(path,directory),'signature':os.path.relpath(sig,directory)}

def check(directory, signers=None):
    base = os.path.join(directory, ATTEST)
    rows=[]
    if not os.path.isdir(base):
        return {'ok':False,'attestations':[]}
    for filename in sorted(os.listdir(base)):
        if not filename.endswith('.json'):
            continue
        path=os.path.join(base,filename)
        try:
            with open(path, encoding='utf-8') as f:
                doc=json.load(f)
            holds = _verify(path,path+'.sig',kernel.NAMESPACE,doc.get('identity'),signers)
            drifted = doc.get('root') != kernel.verify(directory)['root'] or doc.get('build_digest') != kernel.build_digest(directory) or doc.get('outputs') != _build(directory)
            rows.append({'identity':doc.get('identity'),'verdict':'signed' if holds and not drifted else 'refused','drifted':drifted})
        except (OSError, ValueError, kernel.ClaimError):
            rows.append({'verdict':'refused','drifted':False})
    return {'ok':bool(rows) and all(x['verdict']=='signed' for x in rows),'attestations':rows}

def review_packet(directory, *, ws=None):
    checked=kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    audit=kernel.audit(directory)
    return {'root':checked['root'],'build_digest':kernel.build_digest(directory),
            'sign_root':registry.sign_root(directory,ws), 'audit':audit,
            'proof':kernel.read_manifest(directory).get('proof')}

def sign(directory, key, identity, *, ws=None):
    packet=review_packet(directory,ws=ws)
    if not packet['audit']['ok']:
        raise kernel.ClaimError('cannot authorize unearned verdict')
    manifest=kernel.read_manifest(directory)
    proof=manifest.get('proof')
    # Kernel phase consumes this compact packet when a proof is recorded.
    stored = {'root':packet['root'],'build_digest':packet['build_digest'],'proof':proof} if proof else packet
    base=os.path.join(directory,kernel.SIGN_DIR)
    os.makedirs(base,exist_ok=True)
    stem=identity.replace('/','_')
    packet_path=os.path.join(base,stem+'.packet.json')
    statement_path=os.path.join(base,stem+'.sign.json')
    write_json(packet_path,stored)
    statement={'ceremony':CEREMONY,'identity':identity,'root':packet['root'],
               'sign_root':packet['sign_root'], 'packet_digest':hashlib.sha256(json.dumps(stored,sort_keys=True).encode()).hexdigest(),
               'proof_recorded':bool(proof)}
    write_json(statement_path,statement)
    sig=_sign(statement_path,key,kernel.SIGN_NAMESPACE)
    return {'ceremony':CEREMONY,'packet':os.path.relpath(packet_path,directory),
            'statement':os.path.relpath(statement_path,directory),'signature':os.path.relpath(sig,directory)}

def sign_check(directory, *, ws=None, signers=None):
    base=os.path.join(directory,kernel.SIGN_DIR)
    rows=[]
    if not os.path.isdir(base):
        return {'ok':False,'authorizations':[]}
    try:
        current=review_packet(directory,ws=ws)
    except kernel.ClaimError:
        current=None
    for filename in sorted(os.listdir(base)):
        if not filename.endswith('.sign.json'):
            continue
        path=os.path.join(base,filename)
        packet_path=os.path.join(base,filename[:-len('.sign.json')]+'.packet.json')
        try:
            with open(path,encoding='utf-8') as f: statement=json.load(f)
            with open(packet_path,encoding='utf-8') as f: packet=json.load(f)
            digest=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
            expected={'root':current['root'],'build_digest':current['build_digest'],'proof':current['proof']} if current and current['proof'] else current
            packet_holds=packet==expected and digest==statement.get('packet_digest')
            holds=packet_holds and statement.get('sign_root')==current['sign_root'] and _verify(path,path+'.sig',kernel.SIGN_NAMESPACE,statement.get('identity'),signers)
            rows.append({'verdict':'authorized' if holds else 'refused','packet_holds':packet_holds,'proof_recorded':statement.get('proof_recorded',False)})
        except (OSError,ValueError,TypeError,KeyError):
            rows.append({'verdict':'refused','packet_holds':False,'proof_recorded':False})
    return {'ok':bool(rows) and all(r['verdict']=='authorized' for r in rows),'authorizations':rows}

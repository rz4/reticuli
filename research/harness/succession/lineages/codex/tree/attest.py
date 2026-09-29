"""SSH signatures over earned builds and review packets."""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from pathlib import Path
from . import kernel, registry
from ._util import safe_path

ATTEST = '.reticuli/attest'
CEREMONY = 'RETICULI_CLAIM_BASIN_V1'

def _bytes(value):
    return json.dumps(value,sort_keys=True).encode()

def _write(path,value):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    Path(path).write_bytes(_bytes(value))

def _sign(path,key,namespace):
    sig=path+'.sig'
    if os.path.exists(sig): os.unlink(sig)
    done=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',namespace,path],capture_output=True)
    if done.returncode: raise kernel.ClaimError('ssh signing failed')

def _verify(path,identity,namespace,signers):
    if not signers: return os.path.isfile(path+'.sig')
    return kernel._ssh_verify(path,path+'.sig',identity,namespace,signers)

def _earned(d):
    if not kernel.verify(d)['ok'] or not kernel.audit(d)['ok']:
        raise kernel.ClaimError('claim verdict does not reproduce')

def _build(d):
    data=kernel.load_recipe(d)
    return {s['output']:kernel._hash_file(safe_path(d,s['output'])) for s in data.get('step',[]) if s['kind']=='produce' and os.path.isfile(safe_path(d,s['output']))}

def attest(d,key,identity):
    _earned(d)
    body={'identity':identity,'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d),'outputs':_build(d)}
    name=hashlib.sha256(identity.encode()).hexdigest()[:16]
    rel=f'{ATTEST}/{name}.json'; path=safe_path(d,rel)
    _write(path,body); _sign(path,key,kernel.NAMESPACE)
    return {'statement':rel,'signature':rel+'.sig','root':body['root']}

def check(d,signers=None):
    folder=safe_path(d,ATTEST); rows=[]
    if not os.path.isdir(folder): return {'ok':False,'attestations':[]}
    for file in sorted(Path(folder).glob('*.json')):
        try:
            doc=json.loads(file.read_bytes())
            drifted=doc.get('root')!=kernel.verify(d)['root'] or doc.get('build_digest')!=kernel.build_digest(d) or doc.get('outputs')!=_build(d)
            signed=_verify(str(file),doc['identity'],kernel.NAMESPACE,signers)
            rows.append({'identity':doc['identity'],'drifted':drifted,'verdict':'signed' if signed and not drifted else 'refused'})
        except (OSError,ValueError,KeyError,kernel.ClaimError):
            rows.append({'drifted':True,'verdict':'refused'})
    return {'ok':bool(rows) and all(r['verdict']=='signed' for r in rows),'attestations':rows}

def review_packet(d,ws=None):
    _earned(d)
    manifest=kernel.read_manifest(d)
    return {'root':manifest['root'],'build_digest':kernel.build_digest(d),
            'sign_root':registry.sign_root(d,ws),'audit':kernel.audit(d),
            'proof':manifest.get('proof')}

def sign(d,key,identity,ws=None):
    packet=review_packet(d,ws)
    # The kernel's phase reader expects this three-member packet.
    phase_packet={'root':packet['root'],'build_digest':packet['build_digest'],'proof':packet['proof']}
    rel=kernel.SIGN_DIR+'/'+hashlib.sha256(identity.encode()).hexdigest()[:16]
    packet_rel=rel+'.packet.json'; stmt_rel=rel+'.sign.json'
    _write(safe_path(d,packet_rel),phase_packet)
    stmt={'ceremony':CEREMONY,'identity':identity,'root':packet['root'],
          'sign_root':packet['sign_root'],'packet_digest':hashlib.sha256(_bytes(phase_packet)).hexdigest(),
          'proof_recorded':bool(packet['proof'])}
    _write(safe_path(d,stmt_rel),stmt); _sign(safe_path(d,stmt_rel),key,kernel.SIGN_NAMESPACE)
    return {'ceremony':CEREMONY,'statement':stmt_rel,'signature':stmt_rel+'.sig','packet':packet_rel}

def sign_check(d,ws=None,signers=None):
    folder=safe_path(d,kernel.SIGN_DIR); rows=[]
    if not os.path.isdir(folder): return {'ok':False,'authorizations':[]}
    for file in sorted(Path(folder).glob('*.sign.json')):
        try:
            doc=json.loads(file.read_bytes()); packet_path=str(file).removesuffix('.sign.json')+'.packet.json'
            packet=Path(packet_path).read_bytes()
            expected={'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d),
                      'proof':kernel.read_manifest(d).get('proof')}
            holds=packet==_bytes(expected) and doc['packet_digest']==hashlib.sha256(packet).hexdigest()
            holds=holds and doc.get('sign_root')==registry.sign_root(d,ws)
            signed=_verify(str(file),doc['identity'],kernel.SIGN_NAMESPACE,signers)
            row={'identity':doc['identity'],'packet_holds':holds,'proof_recorded':doc.get('proof_recorded',False),
                 'verdict':'authorized' if holds and signed else 'refused'}
        except (OSError,ValueError,KeyError,kernel.ClaimError):
            row={'packet_holds':False,'proof_recorded':False,'verdict':'refused'}
        rows.append(row)
    return {'ok':bool(rows) and all(r['verdict']=='authorized' for r in rows),'authorizations':rows}

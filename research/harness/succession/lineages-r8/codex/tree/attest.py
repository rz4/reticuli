"""SSH attestations of builds and keyholder authorizations of claim chains."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from . import kernel, registry
from ._util import write_json, stamp

ATTEST='.reticuli/attest'

def _canonical(value):
    return json.dumps(value,sort_keys=True).encode()

def _sign(path,key,namespace):
    signature=path+'.sig'
    if os.path.exists(signature): os.unlink(signature)
    done=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',namespace,path],capture_output=True,text=True)
    if done.returncode: raise kernel.ClaimError(done.stderr.strip())
    return signature

def _verify(path,identity,signature,signers,namespace):
    try:
        done=subprocess.run(['ssh-keygen','-Y','verify','-f',signers,'-I',identity,'-n',namespace,'-s',signature],
                            input=Path(path).read_bytes(),capture_output=True,timeout=10)
        return done.returncode==0
    except (OSError,subprocess.TimeoutExpired): return False

def _public(key):
    try: return Path(key+'.pub').read_text().split()[:2]
    except OSError as e: raise kernel.ClaimError(str(e)) from e

def _anchor(statement,signers):
    if signers: return signers,None
    fd,path=tempfile.mkstemp(prefix='reticuli-signers-')
    os.close(fd)
    pub=statement.get('public_key')
    if not pub:
        os.unlink(path)
        return None,None
    Path(path).write_text(f"{statement['identity']} {pub}\n")
    return path,path

def _audit(directory):
    if not kernel.verify(directory)['ok'] or not registry.audit_deep(directory)['ok']:
        raise kernel.ClaimError('claim verdicts do not reproduce')

def attest(directory,key,identity):
    _audit(directory)
    root=kernel.verify(directory)['root']
    public=' '.join(_public(key))
    statement={'root':root,'build_digest':kernel.build_digest(directory),'identity':identity,
               'public_key':public,'when':stamp()}
    relative=f'{ATTEST}/{identity.replace("/","_")}.json'
    path=os.path.join(directory,relative)
    write_json(path,statement)
    signature=_sign(path,key,kernel.NAMESPACE)
    return {'statement':relative,'signature':os.path.relpath(signature,directory),'root':root}

def check(directory,signers=None):
    base=os.path.join(directory,ATTEST)
    rows=[]
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.endswith('.json'): continue
            path=os.path.join(base,name)
            try:
                statement=json.loads(Path(path).read_text())
                anchor,temp=_anchor(statement,signers)
                try: signed=bool(anchor and _verify(path,statement['identity'],path+'.sig',anchor,kernel.NAMESPACE))
                finally:
                    if temp: os.unlink(temp)
                drifted=statement.get('build_digest')!=kernel.build_digest(directory)
                root_holds=statement.get('root')==kernel.verify(directory)['root'] and kernel.verify(directory)['ok']
                ok=signed and not drifted and root_holds
                rows.append({'verdict':'signed' if ok else 'refused','ok':ok,'drifted':drifted,'identity':statement.get('identity')})
            except (OSError,ValueError,KeyError,kernel.ClaimError):
                rows.append({'verdict':'refused','ok':False,'drifted':False})
    return {'ok':bool(rows) and all(row['ok'] for row in rows),'attestations':rows}

def review_packet(directory,*,ws=None):
    _audit(directory)
    manifest=kernel.read_manifest(directory)
    return {'root':manifest['root'],'build_digest':kernel.build_digest(directory),
            'sign_root':registry.sign_root(directory,ws),
            'audit':registry.audit_deep(directory),'proof':manifest.get('proof')}

def sign(directory,key,identity,*,ws=None):
    packet=review_packet(directory,ws=ws)
    base=os.path.join(directory,kernel.SIGN_DIR)
    os.makedirs(base,exist_ok=True)
    stem=identity.replace('/','_')
    packet_path=os.path.join(base,stem+'.packet.json')
    statement_path=os.path.join(base,stem+'.sign.json')
    write_json(packet_path,packet)
    manifest=kernel.read_manifest(directory)
    statement={'ceremony':'RETICULI_CLAIM_BASIN_V1','identity':identity,
               'public_key':' '.join(_public(key)),
               'packet_digest':hashlib.sha256(_canonical(packet)).hexdigest(),
               'proof_recorded':bool(manifest.get('proof')),
               'sign_root':packet['sign_root'],'when':stamp()}
    write_json(statement_path,statement)
    signature=_sign(statement_path,key,kernel.SIGN_NAMESPACE)
    return {**statement,'packet':os.path.relpath(packet_path,directory),
            'statement':os.path.relpath(statement_path,directory),
            'signature':os.path.relpath(signature,directory)}

def sign_check(directory,*,ws=None,signers=None):
    base=os.path.join(directory,kernel.SIGN_DIR)
    rows=[]
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if not name.endswith('.sign.json'): continue
            path=os.path.join(base,name)
            packet_path=path[:-10]+'.packet.json'
            try:
                statement=json.loads(Path(path).read_text())
                packet=json.loads(Path(packet_path).read_text())
                digest=hashlib.sha256(_canonical(packet)).hexdigest()
                packet_holds=digest==statement.get('packet_digest')
                if packet_holds:
                    current=review_packet(directory,ws=ws)
                    packet_holds=(all(packet.get(k)==current[k] for k in ('root','build_digest','sign_root','proof'))
                                  and packet.get('audit',{}).get('ok') is True)
                anchor,temp=_anchor(statement,signers)
                try: signed=bool(anchor and _verify(path,statement['identity'],path+'.sig',anchor,kernel.SIGN_NAMESPACE))
                finally:
                    if temp: os.unlink(temp)
                ok=signed and packet_holds
                rows.append({'verdict':'authorized' if ok else 'refused','packet_holds':packet_holds,
                             'proof_recorded':bool(statement.get('proof_recorded')),'ok':ok})
            except (OSError,ValueError,KeyError,kernel.ClaimError):
                rows.append({'verdict':'refused','packet_holds':False,'proof_recorded':False,'ok':False})
    return {'ok':bool(rows) and all(row['ok'] for row in rows),'authorizations':rows}

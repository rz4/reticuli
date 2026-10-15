"""SSH attestations of builds and authorization of reviewed claim chains."""
import hashlib
import json
import os
import subprocess
from . import kernel, registry
from ._util import write_json

ATTEST='.reticuli/attest'
CEREMONY='RETICULI_CLAIM_BASIN_V1'

def _bytes(doc): return json.dumps(doc,sort_keys=True).encode()
def _sign(data,key,namespace,path):
    subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',namespace],input=data,stdout=open(path,'wb'),stderr=subprocess.PIPE,check=True)
def _verify(data,sig,namespace,signers,identity):
    if not signers: return os.path.isfile(sig)
    try:
        return subprocess.run(['ssh-keygen','-Y','verify','-f',signers,'-I',identity,'-n',namespace,'-s',sig],input=data,capture_output=True).returncode==0
    except OSError: return False

def _prepare(directory,deep=False,ws=None):
    if not kernel.verify(directory)['ok']: raise kernel.ClaimError('changed claim')
    audited=registry.audit_deep(directory,ws) if deep else kernel.audit(directory)
    if not audited['ok']: raise kernel.ClaimError('composed verdict did not reproduce' if deep else 'verdict did not reproduce')
    return audited

def attest(directory,key,identity):
    _prepare(directory)
    doc={'root':kernel.read_manifest(directory)['root'],'build_digest':kernel.build_digest(directory),'identity':identity}
    folder=os.path.join(directory,ATTEST); os.makedirs(folder,exist_ok=True)
    statement=os.path.join(folder,'build.json'); signature=statement+'.sig'
    data=_bytes(doc); open(statement,'wb').write(data); _sign(data,key,kernel.NAMESPACE,signature)
    return {'statement':os.path.relpath(statement,directory),'signature':os.path.relpath(signature,directory)}

def check(directory,signers=None):
    folder=os.path.join(directory,ATTEST); rows=[]
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.json'): continue
            path=os.path.join(folder,name); sig=path+'.sig'
            try:
                data=open(path,'rb').read(); doc=json.loads(data)
                drifted=(doc.get('root')!=kernel.read_manifest(directory)['root'] or doc.get('build_digest')!=kernel.build_digest(directory))
                holds=data==_bytes(doc) and _verify(data,sig,kernel.NAMESPACE,signers,doc['identity'])
                rows.append({'verdict':'signed' if holds and not drifted else 'refused','drifted':drifted})
            except (OSError,ValueError,KeyError,kernel.ClaimError): rows.append({'verdict':'refused','drifted':True})
    return {'ok':bool(rows) and all(r['verdict']=='signed' for r in rows),'attestations':rows}

def review_packet(directory,*,ws=None):
    audit=_prepare(directory,deep=bool(kernel.read_manifest(directory).get('components')),ws=ws)
    m=kernel.read_manifest(directory)
    return {'root':m['root'],'build_digest':kernel.build_digest(directory),'proof':m.get('proof'),'sign_root':registry.sign_root(directory,ws),'audit':audit}

def sign(directory,key,identity,*,ws=None):
    packet=review_packet(directory,ws=ws)
    # Kernel.phase's verifier consumes the three immutable reviewed fields.
    stored={'root':packet['root'],'build_digest':packet['build_digest'],'proof':packet['proof']}
    folder=os.path.join(directory,kernel.SIGN_DIR); os.makedirs(folder,exist_ok=True)
    stem=os.path.join(folder,'authorization')
    packet_path=stem+'.packet.json'; statement=stem+'.sign.json'; signature=statement+'.sig'
    write_json(packet_path,stored)
    doc={'ceremony':CEREMONY,'root':packet['root'],'sign_root':packet['sign_root'],'identity':identity,'packet_digest':hashlib.sha256(_bytes(stored)).hexdigest(),'proof_recorded':bool(packet['proof'])}
    data=_bytes(doc); open(statement,'wb').write(data); _sign(data,key,kernel.SIGN_NAMESPACE,signature)
    return {'ceremony':CEREMONY,'sign_root':packet['sign_root'],'packet':os.path.relpath(packet_path,directory),'statement':os.path.relpath(statement,directory),'signature':os.path.relpath(signature,directory)}

def sign_check(directory,*,ws=None,signers=None):
    folder=os.path.join(directory,kernel.SIGN_DIR); rows=[]
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.sign.json'): continue
            statement=os.path.join(folder,name); stem=statement[:-10]
            try:
                data=open(statement,'rb').read(); doc=json.loads(data)
                packet=json.load(open(stem+'.packet.json'))
                expected={'root':kernel.read_manifest(directory)['root'],'build_digest':kernel.build_digest(directory),'proof':kernel.read_manifest(directory).get('proof')}
                packet_holds=packet==expected and hashlib.sha256(_bytes(packet)).hexdigest()==doc['packet_digest']
                holds=(data==_bytes(doc) and packet_holds and doc['sign_root']==registry.sign_root(directory,ws) and _verify(data,statement+'.sig',kernel.SIGN_NAMESPACE,signers,doc['identity']))
                rows.append({'verdict':'authorized' if holds else 'refused','packet_holds':packet_holds,'proof_recorded':doc.get('proof_recorded',False)})
            except (OSError,ValueError,KeyError,kernel.ClaimError): rows.append({'verdict':'refused','packet_holds':False,'proof_recorded':False})
    return {'ok':bool(rows) and all(r['verdict']=='authorized' for r in rows),'authorizations':rows}

import os, re, glob, json, subprocess
from . import kernel, registry
from ._kernel.core import _write_json, _read_json, digest
from ._kernel.build import _ssh_verify
ATTEST='.reticuli/attest'

def _sign(path,key,namespace):
    if os.path.exists(path+'.sig'):os.remove(path+'.sig')
    p=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',namespace,path],capture_output=True,text=True)
    if p.returncode:raise kernel.ClaimError('sign: '+p.stderr)
def _id(s):return re.sub(r'[^a-zA-Z0-9_-]','-',s)
def attest(d,key,identity):
    if not registry.audit_deep(d)['ok']:raise kernel.ClaimError('composed audit refused attestation')
    name=os.path.join(ATTEST,_id(identity)+'.attest.json')
    _write_json(os.path.join(d,name),{'identity':identity,'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d)})
    _sign(os.path.join(d,name),key,kernel.NAMESPACE)
    return {'statement':name,'signature':name+'.sig'}
def check(d,signers=None):
    rows=[]
    for p in sorted(glob.glob(os.path.join(d,ATTEST,'*.attest.json'))):
        try:
            doc=_read_json(p);drift=doc['root']!=kernel.verify(d)['root'] or doc['build_digest']!=kernel.build_digest(d)
            sig=_ssh_verify(p,kernel.NAMESPACE,signers,doc.get('identity'))
            ok=bool(sig) and not drift;rows.append({'ok':ok,'drifted':drift,'verdict':'signed' if ok and signers else 'intact' if ok else 'invalid'})
        except kernel.ClaimError:rows.append({'ok':False,'drifted':False,'verdict':'invalid'})
    return {'ok':bool(rows) and all(r['ok'] for r in rows),'attestations':rows}
def review_packet(d,ws=None):
    a=registry.audit_deep(d,ws)
    return {'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d),'sign_root':registry.sign_root(d,ws),'audit':a,'proof':kernel.read_manifest(d).get('proof')}
def sign(d,key,identity,ws=None):
    pkt=review_packet(d,ws)
    if not pkt['audit']['ok']:raise kernel.ClaimError('composed audit failed; cannot sign')
    base=os.path.join(kernel.SIGN_DIR,_id(identity));pp=base+'.packet.json';sp=base+'.sign.json'
    _write_json(os.path.join(d,pp),pkt)
    doc={'identity':identity,'root':pkt['root'],'packet_digest':digest(pkt),'proof_recorded':bool(pkt['proof']),'ceremony':'RETICULI_CLAIM_BASIN_V1'}
    _write_json(os.path.join(d,sp),doc);_sign(os.path.join(d,sp),key,kernel.SIGN_NAMESPACE)
    return dict(doc,sign_root=pkt['sign_root'],packet=pp,statement=sp,signature=sp+'.sig')
def sign_check(d,ws=None,signers=None):
    anchor=signers or os.environ.get('RETICULI_SIGNERS');rows=[]
    for p in sorted(glob.glob(os.path.join(d,kernel.SIGN_DIR,'*.sign.json'))):
        try:
            doc=_read_json(p);pkt=_read_json(p[:-len('.sign.json')]+'.packet.json')
            holds=digest(pkt)==doc.get('packet_digest')
            live=pkt.get('root')==kernel.verify(d)['root'] and pkt.get('build_digest')==kernel.build_digest(d)
            if 'sign_root' in pkt:live &= pkt['sign_root']==registry.sign_root(d,ws)
            sig=_ssh_verify(p,kernel.SIGN_NAMESPACE,anchor,doc.get('identity'))
            ok=bool(sig) and holds and live
            rows.append({'ok':ok and bool(anchor),'packet_holds':holds,'proof_recorded':bool(doc.get('proof_recorded')),'verdict':'authorized' if ok and anchor else 'intact' if ok else 'invalid'})
        except kernel.ClaimError:rows.append({'ok':False,'packet_holds':False,'proof_recorded':False,'verdict':'invalid'})
    return {'ok':bool(rows) and all(x['ok'] for x in rows),'anchored':bool(anchor),'authorizations':rows}

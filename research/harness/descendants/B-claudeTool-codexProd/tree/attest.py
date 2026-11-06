import os,json,re,glob,subprocess
from . import kernel,registry
from ._kernel.core import digest,_write_json
from ._kernel.build import _ssh_verify
ATTEST='.reticuli/attest'
def _sign(path,key,ns):
    if os.path.exists(path+'.sig'): os.unlink(path+'.sig')
    p=subprocess.run(['ssh-keygen','-Y','sign','-f',key,'-n',ns,path],capture_output=True,text=True)
    if p.returncode: raise kernel.ClaimError(p.stderr)
def _stem(identity): return re.sub(r'[^a-zA-Z0-9_-]','-',identity)
def attest(d,key,identity):
    if not kernel.audit(d)['ok']: raise kernel.ClaimError('verdict not earned')
    p=os.path.join(ATTEST,_stem(identity)+'.json'); doc={'identity':identity,'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d)}
    _write_json(os.path.join(d,p),doc); _sign(os.path.join(d,p),key,kernel.NAMESPACE)
    return {'ok':True,'statement':p,'signature':p+'.sig'}
def check(d,signers=None):
    rows=[]
    for p in glob.glob(os.path.join(d,ATTEST,'*.json')):
        try:
            doc=json.load(open(p)); drift=doc['root']!=kernel.verify(d)['root'] or doc['build_digest']!=kernel.build_digest(d)
            ok=_ssh_verify(p,kernel.NAMESPACE,doc['identity'],signers) and not drift
            rows.append({'verdict':'signed' if ok and signers else 'intact' if ok else 'invalid','drifted':drift,'ok':ok})
        except (ValueError,OSError,KeyError): rows.append({'ok':False,'verdict':'invalid','drifted':True})
    return {'ok':bool(rows) and all(r['ok'] for r in rows),'attestations':rows}
def review_packet(d,ws=None):
    return {'root':kernel.verify(d)['root'],'build_digest':kernel.build_digest(d),'sign_root':registry.sign_root(d,ws),'proof':kernel.read_manifest(d).get('proof'),'audit':registry.audit_deep(d,ws)}
def sign(d,key,identity,ws=None):
    packet=review_packet(d,ws)
    if not packet['audit']['ok']: raise kernel.ClaimError('composed verdict not earned')
    stem=os.path.join(kernel.SIGN_DIR,_stem(identity)); pp=stem+'.packet.json'; sp=stem+'.sign.json'
    _write_json(os.path.join(d,pp),packet)
    statement={'identity':identity,'root':packet['root'],'sign_root':packet['sign_root'],'packet_digest':digest(packet),'proof_recorded':bool(packet['proof'])}
    _write_json(os.path.join(d,sp),statement); _sign(os.path.join(d,sp),key,kernel.SIGN_NAMESPACE)
    return {'ok':True,'ceremony':'RETICULI_CLAIM_BASIN_V1','statement':sp,'signature':sp+'.sig','packet':pp,'sign_root':packet['sign_root']}
def sign_check(d,ws=None,signers=None):
    signers=signers or os.environ.get('RETICULI_SIGNERS'); rows=[]
    for p in glob.glob(os.path.join(d,kernel.SIGN_DIR,'*.sign.json')):
        try:
            s=json.load(open(p)); pk=json.load(open(p.replace('.sign.json','.packet.json')))
            holds=digest(pk)==s['packet_digest'] and pk['root']==kernel.verify(d)['root'] and pk['build_digest']==kernel.build_digest(d) and pk.get('sign_root')==registry.sign_root(d,ws)
            intact=_ssh_verify(p,kernel.SIGN_NAMESPACE,s['identity'],signers)
            ok=bool(signers and intact and holds)
            rows.append({'ok':ok,'packet_holds':holds,'proof_recorded':s.get('proof_recorded',False),'verdict':'authorized' if ok else 'intact' if intact and holds else 'invalid'})
        except (OSError,ValueError,KeyError): rows.append({'ok':False,'packet_holds':False,'proof_recorded':False,'verdict':'invalid'})
    return {'ok':bool(rows) and all(x['ok'] for x in rows),'anchored':bool(signers),'authorizations':rows}

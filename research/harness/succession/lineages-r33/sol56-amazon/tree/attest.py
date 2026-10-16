"""Build attestations and accountable chain authorization."""
from __future__ import annotations
import hashlib, json, os, subprocess
from . import kernel

ATTEST=".reticuli/attest"
CEREMONY="RETICULI_CLAIM_BASIN_V1"
def _canonical(x): return json.dumps(x,sort_keys=True).encode("utf-8")
def _digest(x): return hashlib.sha256(_canonical(x)).hexdigest()
def _write(path,data):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,"wb") as f:f.write(data)
def _ssh_sign(data,key,namespace,out):
    tmp=out+".data"; _write(tmp,data)
    try:
        p=subprocess.run(["ssh-keygen","-Y","sign","-f",key,"-n",namespace,tmp],capture_output=True)
        if p.returncode:raise kernel.ClaimError("ssh signing failed")
        os.replace(tmp+".sig",out)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def _identities(anchor):
    try:return [x for line in open(anchor,encoding="utf-8") if line.strip() and not line.lstrip().startswith("#") for x in line.split()[0].split(",")]
    except OSError:return []
def _verify(data,sig,anchor,namespace,identity=None):
    if not anchor or not os.path.isfile(sig):return None
    for who in ([identity] if identity else _identities(anchor)):
        if who and subprocess.run(["ssh-keygen","-Y","verify","-f",anchor,"-I",who,"-n",namespace,"-s",sig],input=data,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:return who
    return None

def attest(d,key,identity):
    v=kernel.verify(d)
    if not v["ok"]:raise kernel.ClaimError("claim identity does not hold")
    if not kernel.audit(d).get("ok"):raise kernel.ClaimError("verdicts do not reproduce")
    st={"attestation":1,"identity":identity,"root":v["root"],"build_digest":kernel.build_digest(d),"audit":"earned"}
    base=os.path.join(d,ATTEST,_digest(st)[:20]); statement=base+".json"; signature=statement+".sig"
    _write(statement,_canonical(st));_ssh_sign(_canonical(st),key,kernel.NAMESPACE,signature)
    return {"statement":os.path.relpath(statement,d),"signature":os.path.relpath(signature,d),**st}
def check(d,signers=None):
    rows=[]; directory=os.path.join(d,ATTEST)
    if not os.path.isdir(directory):return {"ok":False,"attestations":[]}
    try:current=kernel.build_digest(d);root=kernel.verify(d)["root"]
    except kernel.ClaimError:return {"ok":False,"attestations":[]}
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".json"):continue
        p=os.path.join(directory,fn);row={"statement":os.path.relpath(p,d)}
        try:
            raw=open(p,"rb").read();st=json.loads(raw);drift=st.get("build_digest")!=current
            who=_verify(raw,p+".sig",signers,kernel.NAMESPACE,st.get("identity")) if signers else None
            ok=raw==_canonical(st) and os.path.isfile(p+".sig") and st.get("root")==root and not drift and (who is not None if signers else True)
            row={**row,**st,"drifted":drift,"verdict":"signed" if ok else "refused","signer":who,"ok":ok}
        except (OSError,ValueError,TypeError):row.update({"ok":False,"drifted":False,"verdict":"refused"})
        rows.append(row)
    return {"ok":bool(rows) and all(x["ok"] for x in rows),"attestations":rows}
def review_packet(d,ws=None):
    from . import registry
    a=registry.audit_deep(d,ws);v=kernel.verify(d);man=kernel.read_manifest(d)
    return {"ceremony":CEREMONY,"root":v["root"],"build_digest":kernel.build_digest(d),"sign_root":registry.sign_root(d,ws),"audit":a,"proof":man.get("proof")}
def sign(d,key,identity,ws=None):
    from . import registry
    if not kernel.audit(d).get("ok"):raise kernel.ClaimError("claim verdicts do not reproduce")
    if kernel.read_manifest(d).get("components") and not registry.audit_deep(d,ws).get("ok"):raise kernel.ClaimError("composed verdict does not reproduce")
    packet=review_packet(d,ws);pd=_digest(packet);directory=os.path.join(d,kernel.SIGN_DIR)
    # One current ceremony per claim. Stable names ensure a later proof-bearing
    # ceremony supersedes, rather than coexisting with, the earlier review.
    pp=os.path.join(directory,"authorization.packet.json");sp=os.path.join(directory,"authorization.sign.json");sig=sp+".sig"
    st={"ceremony":CEREMONY,"identity":identity,"root":packet["root"],"build_digest":packet["build_digest"],"sign_root":packet["sign_root"],"packet_digest":pd,"proof_recorded":packet.get("proof") is not None}
    _write(pp,_canonical(packet));_write(sp,_canonical(st));_ssh_sign(_canonical(st),key,kernel.SIGN_NAMESPACE,sig)
    return {**st,"packet":os.path.relpath(pp,d),"statement":os.path.relpath(sp,d),"signature":os.path.relpath(sig,d)}
def sign_check(d,ws=None,signers=None):
    from . import registry
    rows=[];directory=os.path.join(d,kernel.SIGN_DIR)
    if not os.path.isdir(directory):return {"ok":False,"authorizations":[]}
    try:chain=registry.sign_root(d,ws);root=kernel.verify(d)["root"]
    except kernel.ClaimError:return {"ok":False,"authorizations":[]}
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".sign.json"):continue
        p=os.path.join(directory,fn)
        try:
            raw=open(p,"rb").read();st=json.loads(raw);holds=False
            for qn in os.listdir(directory):
                if not qn.endswith(".packet.json"):continue
                qb=open(os.path.join(directory,qn),"rb").read()
                try:packet=json.loads(qb)
                except ValueError:continue
                if qb==_canonical(packet) and _digest(packet)==st.get("packet_digest") and packet.get("root")==root and packet.get("sign_root")==chain and packet.get("build_digest")==kernel.build_digest(d):holds=True;break
            who=_verify(raw,p+".sig",signers,kernel.SIGN_NAMESPACE,st.get("identity")) if signers else (st.get("identity") if os.path.isfile(p+".sig") else None)
            ok=raw==_canonical(st) and holds and st.get("root")==root and st.get("sign_root")==chain and who is not None
            row={**st,"packet_holds":holds,"verdict":"authorized" if ok else "refused","signer":who,"ok":ok}
        except (OSError,ValueError,TypeError,kernel.ClaimError):row={"ok":False,"packet_holds":False,"verdict":"refused"}
        rows.append(row)
    return {"ok":bool(rows) and all(x["ok"] for x in rows),"authorizations":rows}

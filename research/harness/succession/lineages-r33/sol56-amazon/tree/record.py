"""Author portable canonical records of freshly earned claim results."""
from __future__ import annotations
import os, platform, subprocess
from . import kernel


def validate(doc): return kernel.record_validate(doc)
def canonical(doc): return kernel.record_canonical(doc)
def digest(doc): return kernel.record_digest(doc)
def read(path): return kernel.record_read(path)
def signer(path,anchor):
    try:return kernel.record_signer(path,anchor)
    except kernel.ClaimError:return None


def _producer(d):
    try: events=kernel.ledger_events(d)
    except (AttributeError,kernel.ClaimError):return None
    for e in reversed(events):
        if e.get("event")=="producer":
            return {k:e[k] for k in ("vendor","model","blind","cutoff") if k in e}
    return None


def emit(d,tool=None):
    try:v=kernel.verify(d)
    except kernel.ClaimError:raise kernel.ClaimError("a record requires a sealed claim") from None
    if not v.get("ok"):raise kernel.ClaimError("claim identity does not hold")
    a=kernel.audit(d); recipe=kernel.load_recipe(d); claim=recipe["claim"]
    status_map={"reproduced":"ok","ok":"ok","mismatch":"mismatch","timeout":"timeout","environment":"environment","failed":"failed"}
    gates=[]
    for row in a.get("gates",[]):
        gates.append({"output":row.get("output"),"status":status_map.get(row.get("status"),"failed"),"sandbox":row.get("quarantine","none")})
    obligations={k:claim[k] for k in ("tolerance","envelope","mutation_floor") if k in claim}
    doc={"record":2,"claim":obligations,"name":claim["name"],"root":v["root"],"build_digest":kernel.build_digest(d),"gates":gates,
         "environment":{"platform":platform.system().lower() or os.sys.platform,"machine":platform.machine(),"runtime":f"{platform.python_implementation()} {platform.python_version()}"},
         "when":__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    c=kernel.cost(d)
    if c:doc["cost"]=c
    p=_producer(d)
    if p:doc["producer"]=p
    if tool is not None:doc["tool"]=str(tool)
    validate(doc);return doc


def write(doc,path):
    data=canonical(doc); os.makedirs(os.path.dirname(os.path.abspath(path)),exist_ok=True)
    with open(path,"wb") as f:f.write(data)
    return path


def sign(path,key):
    # Validate and require exact canonical source bytes before signing.
    read(path)
    out=path+".sig"
    if os.path.exists(out):os.unlink(out)
    p=subprocess.run(["ssh-keygen","-Y","sign","-f",key,"-n",kernel.RECORD_NAMESPACE,path],capture_output=True,check=False)
    if p.returncode:raise kernel.ClaimError("record signing failed")
    made=path+".sig"
    if made!=out:os.replace(made,out)
    return out

"""Content-addressed claim registry and composed-claim operations."""
from __future__ import annotations
import hashlib, json, os, shutil, tempfile
from . import kernel

SEALED = os.path.join(kernel.STORE, "sealed")
DEPS = os.path.join(kernel.STORE, "deps")

# Resealing changes identity bytes, not provenance.  The minimal kernel is
# allowed to rewrite its private manifest, so the exchange facade preserves
# the two exchange-owned attachments around that operation.
_kernel_seal = kernel.seal
def _provenance_seal(d, *args, **kwargs):
    old={}
    try: old=kernel.read_manifest(d)
    except kernel.ClaimError: pass
    man=_kernel_seal(d,*args,**kwargs)
    extras={k:old[k] for k in ("components","proof") if k in old}
    if extras:
        man.update(extras)
        with open(os.path.join(d,kernel.MANIFEST),"w",encoding="utf-8") as f:
            json.dump(man,f,sort_keys=True);f.write("\n")
    return man
kernel.seal=_provenance_seal


def _links(d):
    try:
        value = kernel.read_manifest(d).get("components", [])
        return [dict(x) for x in value if isinstance(x, dict)] if isinstance(value, list) else []
    except kernel.ClaimError:
        return []


def seal_with(d, components=None, proof=None):
    old = {}
    try: old = kernel.read_manifest(d)
    except kernel.ClaimError: pass
    man = kernel.seal(d)
    if components is None and "components" in old: components = old["components"]
    if proof is None and "proof" in old: proof = old["proof"]
    if components is not None: man["components"] = [dict(x) for x in components]
    if proof is not None: man["proof"] = proof
    os.makedirs(os.path.dirname(os.path.join(d, kernel.MANIFEST)), exist_ok=True)
    with open(os.path.join(d, kernel.MANIFEST), "w", encoding="utf-8") as f:
        json.dump(man, f, sort_keys=True); f.write("\n")
    return man


def _direct_dirs(base):
    if not os.path.isdir(base): return []
    return [os.path.join(base,n) for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base,n))]

def _search_bases(top, ws=None):
    vals=[]
    for root in (top, ws):
        if root:
            root=os.path.abspath(root); vals += [os.path.join(root,SEALED),os.path.join(root,DEPS)]
    p=os.path.abspath(top)
    while True:
        vals += [os.path.join(p,SEALED),os.path.join(p,DEPS)]
        q=os.path.dirname(p)
        if q==p:break
        p=q
    return list(dict.fromkeys(vals))
def _index(top, ws=None):
    idx={}
    for base in _search_bases(top,ws):
        for p in _direct_dirs(base):
            try: idx.setdefault(kernel.read_manifest(p)["root"],p)
            except (kernel.ClaimError,OSError):pass
    try:idx.setdefault(kernel.read_manifest(top)["root"],os.path.abspath(top))
    except kernel.ClaimError:pass
    return idx
def _resolve(link, top, ws=None, idx=None):
    idx=idx if idx is not None else _index(top,ws);r=link.get("root")
    if isinstance(r,str) and r in idx:return idx[r]
    for base in _search_bases(top,ws):
        p=os.path.join(base,str(link.get("component")))
        if os.path.isdir(p):
            try:
                if not r or kernel.read_manifest(p)["root"]==r:return p
            except kernel.ClaimError:pass
    return None

def claims(ws):
    out=[]
    for p in _direct_dirs(os.path.join(ws,SEALED)):
        try:
            m=kernel.read_manifest(p)
            try:ph=kernel.phase(p)
            except kernel.ClaimError:ph="sealed"
            out.append({"name":m["name"],"root":m["root"],"path":p,"phase":ph})
        except kernel.ClaimError:pass
    return out
def detect_components(ws, inputs):
    result=[]
    for inp in inputs:
        ip=os.path.join(ws,inp)
        if not os.path.isfile(ip):continue
        ih=hashlib.sha256(open(ip,"rb").read()).hexdigest()
        for c in claims(ws):
            try:
                for s in kernel.load_recipe(c["path"]).get("step",[]):
                    out=s.get("output");op=os.path.join(c["path"],str(out))
                    if out and os.path.isfile(op) and hashlib.sha256(open(op,"rb").read()).hexdigest()==ih:result.append({"input":inp,"component":c["name"],"root":c["root"],"output":out})
            except (kernel.ClaimError,OSError):pass
    return list({json.dumps(x,sort_keys=True):x for x in result}.values())
def deps(ws):
    idx=_index(ws,ws);rows=[]
    for c in claims(ws):
        edges=[]
        for l in _links(c["path"]):
            p=_resolve(l,c["path"],ws,idx);status="missing"
            if p:
                try:status="ok" if kernel.verify(p)["root"]==l.get("root") else "mismatch"
                except kernel.ClaimError:status="mismatch"
            edges.append({**l,"status":status})
        rows.append({**c,"depends_on":edges})
    return {"claims":rows}
def structure(d,ws=None):
    m=kernel.read_manifest(d)
    try:ph=kernel.phase(d)
    except kernel.ClaimError:ph="sealed"
    return {"name":m["name"],"root":m["root"],"phase":ph,"components":_links(d)}

def _copy_claim(src,dst,blind=False,include_store=True):
    from ._kernel import recipe as rp
    parsed=kernel.load_recipe(src);os.makedirs(dst,exist_ok=True);rpath=rp.recipe_path(src);shutil.copyfile(rpath,os.path.join(dst,os.path.basename(rpath)))
    names=list(rp._inputs(parsed,src))
    for s in parsed.get("step",[]):
        if not (blind and s.get("kind")=="produce" and s.get("class","generated") in ("generated","free")):names.append(s.get("output"))
    for n in names:
        if n and os.path.isfile(os.path.join(src,n)):
            b=os.path.join(dst,n);os.makedirs(os.path.dirname(b),exist_ok=True);shutil.copyfile(os.path.join(src,n),b)
    if include_store and os.path.isfile(os.path.join(src,kernel.MANIFEST)):
        q=os.path.join(dst,kernel.MANIFEST);os.makedirs(os.path.dirname(q),exist_ok=True);shutil.copyfile(os.path.join(src,kernel.MANIFEST),q)
def _closure(d,ws=None):
    idx=_index(d,ws);result=[];seen=set()
    def walk(cur):
        for l in _links(cur):
            key=l.get("root") or l.get("component")
            if key in seen:continue
            seen.add(key);p=_resolve(l,d,ws,idx)
            if p:result.append((l,p));walk(p)
    walk(d);return result
def pull(claim,ws):
    claim=os.path.abspath(claim);ws=os.path.abspath(ws);store_mode=os.path.isdir(os.path.join(ws,kernel.STORE));target=os.path.join(ws,SEALED,kernel.read_manifest(claim)["name"]) if store_mode else ws
    if os.path.exists(target) and os.listdir(target) and os.path.realpath(target)!=os.path.realpath(ws):shutil.rmtree(target)
    _copy_claim(claim,target,False,True);base=os.path.join(target,SEALED);os.makedirs(base,exist_ok=True)
    for l,p in _closure(claim,ws):
        q=os.path.join(base,kernel.read_manifest(p)["name"])
        if not os.path.exists(q):_copy_claim(p,q,False,True)
    return {"materialized":True,"path":target,"root":kernel.read_manifest(claim)["root"]}

def audit_deep(d,ws=None):
    d=os.path.abspath(d);top=kernel.audit(d);idx=_index(d,ws);layers=[];seen=set()
    def walk(cur,inherited):
        for l in _links(cur):
            key=l.get("root") or l.get("component");out=l.get("output");inp=l.get("input");source_name=inp or out;shipped=inherited.get(out) or (os.path.join(cur,source_name) if source_name else None)
            if key in seen:continue
            seen.add(key);p=_resolve(l,d,ws,idx)
            if not p:layers.append({"name":l.get("component"),"root":l.get("root"),"ok":False,"status":"unresolved","bytes_from":[source_name] if source_name else []});continue
            expected=os.path.join(p,str(out));mismatch=bool(shipped and os.path.isfile(shipped) and os.path.isfile(expected) and hashlib.sha256(open(shipped,"rb").read()).digest()!=hashlib.sha256(open(expected,"rb").read()).digest())
            amap={}
            try:
                from ._kernel import recipe as rp
                if out in set(rp.generated_outputs(kernel.load_recipe(p))) and shipped and os.path.isfile(shipped):amap[out]=shipped
            except kernel.ClaimError:pass
            a=kernel.audit(p,produce_from=amap) if amap else kernel.audit(p);ok=bool(a.get("ok")) and not mismatch
            row={**a,"name":kernel.read_manifest(p)["name"],"root":l.get("root"),"ok":ok,"bytes_from":[source_name] if source_name else []}
            if mismatch:row["status"]="attribution mismatch"
            layers.append(row);child=dict(inherited)
            if out and shipped:child[out]=shipped
            walk(p,child)
    walk(d,{});return {**top,"ok":bool(top.get("ok")) and all(x.get("ok") for x in layers),"layers":layers}
def rebuild_chain(d,producer,into,ws=None,reuse=False,**opts):
    d=os.path.abspath(d);into=os.path.abspath(into);rebuilt=[];closure=_closure(d,ws)
    for l,p in reversed(closure):
        td=tempfile.mkdtemp(prefix="reticuli-component-");target=os.path.join(td,"build")
        try:
            r={"root":kernel.verify(p)["root"]} if reuse else kernel.rebuild(p,producer,target,**opts)
            if not r.get("ok",True):raise kernel.ClaimError("component rebuild failed")
            rebuilt.append({"component":l.get("component"),"root":r.get("root")})
        finally:shutil.rmtree(td,ignore_errors=True)
    # from outputs are already present in d and kernel rebuild copies them.
    r=kernel.rebuild(d,producer,into,**opts)
    if not r.get("ok",True):raise kernel.ClaimError(str(r.get("verdict","rebuild failed")))
    seal_with(into,components=_links(d));base=os.path.join(into,SEALED);os.makedirs(base,exist_ok=True)
    for l,p in closure:
        q=os.path.join(base,kernel.read_manifest(p)["name"])
        if not os.path.exists(q):_copy_claim(p,q,False,True)
    r["rebuilt_components"]=rebuilt;return r
def sign_root(d,ws=None,_seen=None):
    d=os.path.abspath(d);idx=_index(d,ws);seen=_seen if _seen is not None else set();m=kernel.read_manifest(d)
    if m["root"] in seen:return ""
    seen.add(m["root"]);children=[]
    for l in _links(d):
        p=_resolve(l,d,ws,idx)
        if not p:raise kernel.ClaimError("missing declared component: "+str(l.get("component")))
        children.append(sign_root(p,ws,seen))
    return kernel.sign_node(m["root"],kernel.build_digest(d),children)
def crosscheck_deep(m1,m2,m3,**opts):
    r=kernel.crosscheck(m1,m2,m3,**opts);deep={"M1":audit_deep(m1).get("ok"),"M2":audit_deep(m2).get("ok"),"M3":audit_deep(m3).get("ok")};r["deep_audited"]=deep
    if not all(deep.values()):r["satisfied"]=False;r["verdict"]="reject"
    return r
def record_proof_deep(m1,m2,m3,**opts):
    r=crosscheck_deep(m1,m2,m3,**opts)
    return kernel.record_proof(m1,m2,m3,**opts) if r["satisfied"] else r

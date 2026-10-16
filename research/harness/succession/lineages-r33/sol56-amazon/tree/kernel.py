"""Public Reticuli kernel (standard library only)."""
from __future__ import annotations
import hashlib, json, math, os, shutil, stat, subprocess, sys, tempfile, time
from collections.abc import Mapping
from typing import Any
from ._kernel import core, recipe as _recipe, identity as _identity, seal as _seal
from ._kernel import run as _run, build as _build, attest as _record
from ._kernel import crosscheck as _mutation

ClaimError=core.ClaimError
NAMESPACE=core.NAMESPACE; STORE=core.STORE; MANIFEST=core.MANIFEST
RECIPE=core.RECIPE; LEDGER=core.LEDGER; SIGN_DIR=core.SIGN_DIR
SIGN_NAMESPACE=core.SIGN_NAMESPACE; _JAILED=core._JAILED
RECORD_NAMESPACE=_record.RECORD_NAMESPACE; RECORD_FORMAT=_record.RECORD_FORMAT

# Output paths need syntactic confinement at parse time. Existing generated
# symlinks are refused at the bytes boundary (audit/copy), not while sealing.
def _recipe_path_check(d,value,what):
    if not isinstance(value,str) or not value or os.path.isabs(value) or "\0" in value:
        raise ClaimError(f"{what} must be a non-empty relative path")
    parts=value.replace("\\","/").split("/")
    if ".." in parts: raise ClaimError(f"invalid {what}: path escapes claim")
    return value
_recipe._validate_path=_recipe_path_check

load_recipe=_recipe.load_recipe; root=_identity.root; build_digest=_identity.build_digest
seal=_seal.seal; verify=_seal.verify; read_manifest=_seal.read_manifest
ledger=_run.ledger; ledger_events=_run.ledger_events; cost=_run.cost
preflight=_run.preflight
record_validate=_record.record_validate; record_canonical=_record.record_canonical
record_digest=_record.record_digest; record_read=_record.record_read
record_signer=_record.record_signer

def _hash_file(path):
    try:
        s=os.lstat(path)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise ClaimError("not an unaliased regular file")
        return core._hash_file(path)
    except ClaimError: raise
    except (OSError,TypeError,ValueError) as e: raise ClaimError(f"cannot hash file: {e}") from None

# A real jail tells the wrapped process which backend placed it there.
_old_argv=_run._sandbox_argv
def _sandbox_argv(command,d,scratch,backend=None):
    b=backend or _run.sandbox_backend(); a=_old_argv(command,d,scratch,b)
    if b=="bubblewrap":
        for i in range(len(a)-2):
            if a[i]=="--setenv" and a[i+1]==_JAILED: a[i+2]=b
    return a
_run._sandbox_argv=_sandbox_argv

def sandbox(command=None,d=None):
    b=_run.sandbox_backend()
    return ([],b) if command is None or d is None else (_sandbox_argv(command,os.path.abspath(os.fspath(d)),os.path.abspath(os.fspath(d)),b),b)
def run_gate(command,d,recipe=None,env=None): return _run.run_gate(command,d,recipe,env)

def sign_node(r,digest,links):
    return hashlib.sha256(json.dumps({"root":r,"build_digest":digest,"links":sorted(set(links))},sort_keys=True).encode()).hexdigest()

def gate_deciders(command):
    import shlex
    if isinstance(command,Mapping): command=command.get("run","")
    try: words=shlex.split(str(command))
    except ValueError: words=str(command).split()
    result=[]; boundaries={"&&","||",";","|","&","\n"}
    for i,w in enumerate(words):
        if os.path.basename(w) in _mutation._INTERPRETERS:
            j=i+1
            while j<len(words) and words[j].startswith("-"):
                if words[j] in _mutation._SKIP_VALUE: j+=2
                else: j+=1
            if j<len(words) and words[j] not in boundaries:
                x=words[j]; result.append(x[2:] if x.startswith("./") else x)
        elif (i==0 or words[i-1] in boundaries) and w.startswith("./"):
            result.append(w[2:])
    return list(dict.fromkeys(result))
def vacuous_gates(recipe):
    inputs=set(_recipe._inputs(dict(recipe))); generated=set(_recipe.generated_outputs(dict(recipe))); out=[]
    for s in _recipe.gates(dict(recipe)):
        ds=[x for x in gate_deciders(s.get("run","")) if x in inputs or x in generated]
        if ds and all(x in generated for x in ds): out.append(s["output"])
    return out

def _copy(src,dst,name,required=True):
    p=core._safe(src,name)
    if not os.path.lexists(p):
        if required: raise ClaimError(f"declared file absent: {name}")
        return False
    q=os.lstat(p)
    if not stat.S_ISREG(q.st_mode) or q.st_nlink!=1: raise ClaimError(f"declared file is aliased: {name}")
    core._copy_into(p,core._safe(dst,name)); return True
def _mapped(value,name):
    if isinstance(value,Mapping) and name in value: return os.path.abspath(os.fspath(value[name]))
    return None

def _materialize(source,target,generated=False,input_from=None):
    parsed=load_recipe(source)
    if os.path.exists(target):
        if not os.path.isdir(target) or os.listdir(target): raise ClaimError("build target is not empty")
    else: os.makedirs(target)
    if parsed["claim"].get("format",1)>=3:
        with open(core._safe(target,RECIPE),"w",encoding="utf8") as f: f.write(_build._toml_recipe(_identity._preimage_recipe(parsed)))
    else:
        p=_recipe.recipe_path(source); core._copy_into(p,core._safe(target,os.path.basename(p)))
    for name in _recipe._inputs(parsed,source):
        p=_mapped(input_from,name)
        if p:
            st=os.lstat(p)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1: raise ClaimError("bad threaded input")
            core._copy_into(p,core._safe(target,name))
        else:
            base=os.path.abspath(os.fspath(input_from)) if input_from is not None and not isinstance(input_from,Mapping) else source
            _copy(base,target,name)
    for s in _recipe.produces(parsed):
        if generated or "from" in s: _copy(source,target,s["output"],not generated)
    return parsed

def _produce(command,room,step,outputs,guidance,extra,claimroot):
    target=core._safe(room,step["output"]); os.makedirs(os.path.dirname(target) or room,exist_ok=True)
    up=core._safe(room,core.USAGE)
    if os.path.lexists(up): os.unlink(up)
    env=_run._scrub_env(); env.update({core._ENV_OUTPUT:target,core._ENV_OUTPUTS:json.dumps(outputs,sort_keys=True),core._ENV_USAGE:up})
    if claimroot: env[core._ENV_CLAIM]=claimroot
    hint=_build._step_guidance(step,guidance)
    if hint is not None: env[core._ENV_REQUEST]=hint
    if extra:
        for k,v in extra.items():
            if isinstance(k,str) and v is not None: env[k]=str(v)
    began=time.monotonic()
    try:
        p=subprocess.run(["/bin/sh","-c",command],cwd=room,env=env,capture_output=True,text=True,timeout=core.PRODUCER_TIMEOUT)
        r={"status":"ok" if p.returncode==0 else "failed","returncode":p.returncode,"stdout":p.stdout,"stderr":p.stderr,"seconds":time.monotonic()-began,"output":step["output"]}
    except subprocess.TimeoutExpired as e:
        r={"status":"timeout","returncode":None,"stdout":e.stdout or "","stderr":e.stderr or "","seconds":time.monotonic()-began,"output":step["output"]}
    try: r["usage"]=_build._read_usage(up)
    except ClaimError: r["usage"]={}
    return r

def _gates(source,room,parsed,pins=True):
    missing=preflight(parsed); rows=[]
    for s in _recipe.gates(dict(parsed)):
        name=s["output"]; actual=core._safe(room,name)
        if os.path.lexists(actual):
            if os.path.isdir(actual) and not os.path.islink(actual): shutil.rmtree(actual)
            else: os.unlink(actual)
        if missing:
            rows.append({"output":name,"status":"environment","quarantine":None,"missing":missing}); continue
        x=run_gate(s["run"],room,parsed); status=x.get("status","failed")
        if status=="ok" and pins and os.path.lexists(core._safe(source,name)):
            status="ok" if _build._compare_pin(core._safe(source,name),actual) else "mismatch"
        row={"output":name,"status":status,"quarantine":x.get("quarantine")}
        for k in ("returncode","stdout","stderr","seconds","missing"):
            if k in x: row[k]=x[k]
        rows.append(row)
    return rows

def audit(d,produce_from=None,**opts):
    source=os.path.abspath(os.fspath(d)); v=verify(source)
    if not v["ok"]: return {"ok":False,"verdict":"identity mismatch","root":v["root"],"recomputed":v["recomputed"],"gates":[]}
    parent=tempfile.mkdtemp(prefix="reticuli-audit-"); room=os.path.join(parent,"room")
    try:
        parsed=_materialize(source,room,True)
        if isinstance(produce_from,Mapping):
            for n,p in produce_from.items():
                if n in _recipe.generated_outputs(parsed): core._copy_into(p,core._safe(room,n))
        rows=_gates(source,room,parsed); ok=all(x["status"]=="ok" for x in rows)
        r={"ok":ok,"verdict":"earned" if ok else "broken","root":v["root"],"gates":rows}
        miss=preflight(parsed)
        if miss:r["environment"]=miss
        return r
    finally: shutil.rmtree(parent,ignore_errors=True)

def rebuild(d,producer,into,produce_from=None,input_from=None,guidance=True,producer_env=None):
    source=os.path.abspath(os.fspath(d)); target=os.path.abspath(os.fspath(into)); ps=load_recipe(source)
    miss=preflight(ps)
    if miss: raise ClaimError("environment missing: "+", ".join(miss))
    mp=core._safe(source,MANIFEST); sealedroot=None
    if os.path.isfile(mp):
        v=verify(source)
        if not v["ok"]: raise ClaimError("source identity does not hold")
        sealedroot=v["root"]
    parsed=_materialize(source,target,False,input_from); own=_recipe.generated_outputs(parsed)
    watch=[os.path.basename(_recipe.recipe_path(target))]+_recipe._inputs(parsed,target)
    snap={n:_identity._hash_declared(target,n) for n in watch}; production=[]
    for s in _recipe.produces(parsed):
        if "from" in s: continue
        n=s["output"]; supplied=_mapped(produce_from,n)
        if supplied is None and produce_from is not None and not isinstance(produce_from,Mapping):
            q=core._safe(produce_from,n); supplied=q if os.path.isfile(q) else None
        if supplied:
            core._copy_into(supplied,core._safe(target,n)); ledger(target,{"event":"reuse","output":n})
        else:
            item=_produce(producer,target,s,own,guidance,producer_env,sealedroot); production.append(item)
            if item["status"]!="ok": raise ClaimError("producer "+item["status"])
        if s.get("class","generated") not in ("generated","free") and not _build._compare_pin(core._safe(source,n),core._safe(target,n)):
            raise ClaimError("pinned output mismatch")
    for n,h in snap.items():
        if _identity._hash_declared(target,n)!=h: raise ClaimError("producer changed pinned bytes: "+n)
    rows=_gates(source,target,parsed,os.path.isfile(mp))
    if any(x["status"]!="ok" for x in rows): raise ClaimError("gates failed")
    man=seal(target)
    if sealedroot and input_from is None and man["root"]!=sealedroot: raise ClaimError("root mismatch")
    q=rows[-1]["quarantine"] if rows else _run.sandbox_backend(); elapsed=sum(float(x.get("seconds",0)) for x in production)
    event={"event":"oracle","kind":"rebuild","calls":len(production),"seconds":elapsed,"quarantine":q}
    for x in production:
        for k,v in x.get("usage",{}).items(): event[k]=event.get(k,0)+v
    ledger(target,event)
    for x in rows: ledger(target,{"event":"gate","gate":x["output"],"status":x["status"],"quarantine":x["quarantine"]})
    ledger(target,{"event":"environment","python":sys.version.split()[0],"platform":sys.platform,"quarantine":q})
    vendor=os.environ.get(core._ENV_VENDOR); model=os.environ.get(core._ENV_MODEL)
    if vendor or model: ledger(target,{"event":"producer","vendor":vendor,"model":model,"blind":True})
    return {"ok":True,"root":man["root"],"build_digest":build_digest(target),"verdict":"earned","production":production,"gates":rows,"quarantine":q}

def _producer_info(d):
    for e in reversed(ledger_events(d)):
        if e.get("event")=="producer": return {k:e[k] for k in ("vendor","model","blind","cutoff") if e.get(k) is not None}
    return None
def independence(value,rebuild_value=None):
    if rebuild_value is not None or isinstance(value,Mapping): return _run.independence(value,rebuild_value)
    return _producer_info(os.path.abspath(os.fspath(value))) or {}

def _leg(value):
    p=os.path.abspath(os.fspath(value))
    if os.path.isfile(p):
        x=record_read(p); return {"kind":"record","path":p,"root":x["root"],"digest":x["build_digest"],"audit":all(g["status"]=="ok" for g in x["gates"]),"cost":x.get("cost"),"claim":x.get("claim"),"version":x["record"],"producer":x.get("producer")}
    v=verify(p); a=audit(p) if v["ok"] else {"ok":False}
    return {"kind":"directory","path":p,"root":v["root"],"digest":build_digest(p),"audit":bool(a.get("ok")),"cost":cost(p),"claim":load_recipe(p)["claim"],"version":None,"producer":_producer_info(p)}

def crosscheck(m1,m2,m3,tolerance=None,mutants=None,**opts):
    raw=[os.path.abspath(os.fspath(x)) for x in (m1,m2,m3)]; dirs=[os.path.realpath(x) for x in raw if os.path.isdir(x)]
    if len(dirs)!=len(set(dirs)): raise ClaimError("machines must be distinct")
    L=[_leg(x) for x in raw]; roots={f"M{i+1}":x["root"] for i,x in enumerate(L)}; audited={f"M{i+1}":x["audit"] for i,x in enumerate(L)}
    eq=len(set(roots.values()))==1; reuse=L[0]["digest"]==L[1]["digest"]; declared=L[0]["claim"]
    unknown=L[0]["kind"]=="record" and L[0]["version"]==1
    tol=tolerance if tolerance is not None else (declared.get("tolerance",core.TOLERANCE) if isinstance(declared,Mapping) else core.TOLERANCE)
    c1,c3=L[0]["cost"],L[2]["cost"]; unit=ratio=comp=None
    if isinstance(c1,Mapping) and isinstance(c3,Mapping):
        for u in core.COST_LADDER:
            if u in c1 and u in c3:
                unit=u; a,b=float(c1[u]),float(c3[u]); ratio=1.0 if a==b==0 else math.inf if min(a,b)==0 else max(a,b)/min(a,b); comp=ratio<=tol; break
    rejected=[]; incomplete=[]
    if not eq: rejected.append("one root")
    if not reuse: rejected.append("byte reuse")
    for k,v in audited.items():
        if not v: rejected.append("audit "+k)
    if unknown: incomplete.append("declared conditions")
    if isinstance(declared,Mapping) and "tolerance" in declared and comp is False: rejected.append("cost tolerance")
    er={}; envelope=declared.get("envelope") if isinstance(declared,Mapping) else None
    if isinstance(envelope,Mapping):
        for u,ceil in envelope.items():
            measured=c3.get(u) if isinstance(c3,Mapping) else None; within=None if measured is None else measured<=ceil
            er[u]={"ceiling":ceil,"measured":measured,"within":within}
            if within is False: rejected.append("envelope "+u)
            elif within is None: incomplete.append("envelope "+u)
    ms=None; floor=declared.get("mutation_floor") if isinstance(declared,Mapping) else None
    if floor is not None:
        if mutants is None or L[2]["kind"]!="directory": incomplete.append("mutation score")
        else:
            ms=mutation_score(L[2]["path"],max_mutants=mutants); ms["floor"]=floor; ms["ok"]=ms["rate"]>=floor
            if not ms["ok"]: rejected.append("mutation score")
    verdict="reject" if rejected else "incomplete" if incomplete else "accept"; prod=L[2]["producer"]
    if prod:
        who="/".join(str(prod[k]) for k in ("vendor","model") if prod.get(k)); indep=f"declared: {who or 'producer'}, "+("blind workspace" if prod.get("blind") else "visibility unspecified")+"; not proven"
    else: indep="unestablished: producer independence not proven"
    return {"satisfied":verdict=="accept","verdict":verdict,"rejected":rejected,"incomplete":incomplete,"roots":roots,"equivalence":eq,"reuse":reuse,"audited":audited,"cost":{"M1":c1,"M3":c3,"unit":unit,"ratio":ratio,"comparable":comp,"envelope":er},"mutation_score":ms,"independence":indep}

def record_proof(m1,m2,m3,**opts):
    first=os.path.abspath(os.fspath(m1))
    if not os.path.isdir(first): raise ClaimError("M1 must be directory")
    trail=[]; anchor=os.environ.get(core._ENV_SIGNERS)
    for x in (m2,m3):
        p=os.path.abspath(os.fspath(x))
        if os.path.isfile(p):
            if not anchor: raise ClaimError("record requires anchor")
            signer=record_signer(p,anchor)
            if not signer: raise ClaimError("record unanchored")
            doc=record_read(p); trail.append({"digest":record_digest(doc),"signer":signer})
    r=crosscheck(m1,m2,m3,**opts)
    if not r["satisfied"]: return {**r,"proof_recorded":False}
    man=read_manifest(first); proof={"kind":"crosscheck","roots":r["roots"],"when":core._now(),"records":trail}; man["proof"]=proof; core._write_json(core._safe(first,MANIFEST),man)
    return {**r,"proof_recorded":True,"proof":proof}

def mutation_score(d,max_mutants=100,**opts):
    claim=os.path.abspath(os.fspath(d)); parsed=load_recipe(claim); choices=[]
    for n in _recipe.generated_outputs(parsed):
        p=core._safe(claim,n)
        if not os.path.isfile(p): continue
        try:
            with open(p,encoding="utf8") as f: text=f.read()
        except UnicodeError: continue
        choices.extend((n,x) for x in _mutation._mutants(text,n))
    seed=verify(claim)["root"] if os.path.isfile(core._safe(claim,MANIFEST)) else root(parsed,claim); selected=_mutation._draw_order(seed,choices)[:max_mutants]
    killed=0; survivors=[]
    for n,x in selected:
        fd,p=tempfile.mkstemp(); os.close(fd)
        try:
            with open(p,"w",encoding="utf8") as f:f.write(x["text"])
            if audit(claim,produce_from={n:p})["ok"]: survivors.append(x["label"])
            else:killed+=1
        finally: os.unlink(p)
    total=len(selected); r={"mutants":total,"killed":killed,"rate":killed/total if total else 0.0,"survivors":survivors}; os.makedirs(core._safe(claim,STORE),exist_ok=True); core._write_json(core._safe(claim,core.MUTATION_RESIDUE),r); return r

def _signed(d,man):
    anchor=os.environ.get(core._ENV_SIGNERS)
    if not anchor or not man.get("proof"): return False
    sd=core._safe(d,SIGN_DIR)
    if not os.path.isdir(sd): return False
    for fn in os.listdir(sd):
        if not fn.endswith(".sign.json"):continue
        sp=os.path.join(sd,fn); sig=sp+".sig"
        try:
            raw=open(sp,"rb").read(); st=json.loads(raw); ident=st.get("identity")
            if not os.path.isfile(sig) or not isinstance(ident,str) or not _build._ssh_verify(raw,sig,anchor,namespace=SIGN_NAMESPACE,identity_name=ident):continue
            if st.get("root")!=man["root"] or not st.get("proof_recorded"):continue
            for pf in (x for x in os.listdir(sd) if x.endswith(".packet.json")):
                packet=json.loads(open(os.path.join(sd,pf),"rb").read()); pd=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
                if pd==st.get("packet_digest") and packet.get("root")==man["root"] and packet.get("build_digest")==build_digest(d) and packet.get("proof")==man.get("proof"): return True
        except (OSError,ValueError,TypeError,ClaimError):pass
    return False
def phase(d):
    claim=os.path.abspath(os.fspath(d)); load_recipe(claim); p=core._safe(claim,MANIFEST)
    if not os.path.exists(p):return "draft"
    v=verify(claim)
    if not v["ok"]:raise ClaimError("identity does not hold")
    man=read_manifest(claim); return "signed" if _signed(claim,man) else "sealed"

__all__=[x for x in globals() if not x.startswith("_")]+["_JAILED","_hash_file"]

"""Execute, list, or strip runnable Reticuli claims (standard library only)."""
from __future__ import annotations
import argparse, hashlib, json, ntpath, os, shlex, shutil, stat
import subprocess, sys, tempfile, tomllib
from typing import Any
from . import kernel

PACKAGE="package.toml"; STATE_DIR=".launcher"; STATE_FILE="state.json"
NOT_RUNNABLE=3; CONSENT_REQUIRED=4; TRUST_REFUSED=5; DRIFT=6; NO_PRODUCER=7

def _say(s): print("reticuli launcher: "+s,file=sys.stderr)

def _relative(name,label):
    if not isinstance(name,str) or not name or "\0" in name: raise ValueError(label+" must be a non-empty relative path")
    drive,_=ntpath.splitdrive(name)
    if drive or os.path.isabs(name) or ntpath.isabs(name): raise ValueError(label+" must be relative to the claim")
    bits=name.replace("\\","/").split("/")
    if ".." in bits: raise ValueError(label+" escapes the claim root")
    if all(x in ("",".") for x in bits): raise ValueError(label+" does not name a file")
    return name

def _path(root,name,label):
    name=_relative(name,label); local=name.replace("\\",os.sep).replace("/",os.sep)
    path=os.path.abspath(os.path.join(root,local))
    try: inside=os.path.commonpath((root,path))==root
    except ValueError: inside=False
    if not inside or path==root: raise ValueError(label+" escapes the claim root")
    here=root
    for bit in local.split(os.sep):
        if bit in ("","."): continue
        here=os.path.join(here,bit)
        if os.path.lexists(here) and os.path.islink(here): raise ValueError(label+" contains a symlink")
    return path

def _generated(recipe):
    out=[]
    for s in recipe.get("step",[]):
        if isinstance(s,dict) and s.get("kind")=="produce" and s.get("class","generated") in ("generated","free") and "from" not in s:
            n=_relative(s.get("output"),"generated output")
            if n not in out: out.append(n)
    return out

def _inputs(root,recipe):
    c=recipe.get("claim",{}); names=list(c.get("inputs",[])) if isinstance(c,dict) else []
    if isinstance(c,dict):
        m=c.get("inputs_manifest")
        if isinstance(m,str):
            names.append(m)
            with open(_path(root,m,"inputs_manifest"),encoding="utf8") as f:
                for raw in f:
                    x=raw.strip()
                    if not x or x.startswith("#"): continue
                    p=x.split(None,1)
                    if len(p)==2 and len(p[0])==64 and all(z in "0123456789abcdef" for z in p[0]): x=p[1].strip()
                    names.append(x)
        e=c.get("environment")
        if isinstance(e,str): names.append(e)
    return {str(x).replace("\\","/") for x in names}

def _load(value):
    root=os.path.realpath(os.path.abspath(os.fspath(value)))
    if not os.path.isdir(root): raise ValueError("claim path is not a directory")
    try: recipe=kernel.load_recipe(root)
    except kernel.ClaimError as e: raise ValueError(str(e)) from None
    generated=_generated(recipe)
    for n in generated: _path(root,n,"generated output")
    return root,recipe,generated

def _package(root,recipe,generated):
    if PACKAGE not in _inputs(root,recipe):
        if PACKAGE in {x.replace("\\","/") for x in generated}: raise ValueError("package.toml must be a pinned input, not a generated output")
        raise ValueError("package.toml is missing from the claim's pinned inputs")
    p=_path(root,PACKAGE,PACKAGE)
    if not os.path.isfile(p): raise ValueError("pinned package.toml is absent")
    try:
        with open(p,"rb") as f: doc=tomllib.load(f)
    except (OSError,tomllib.TOMLDecodeError) as e: raise ValueError("cannot read package.toml: "+str(e)) from None
    t=doc.get("package"); entry=t.get("entrypoint") if isinstance(t,dict) else None
    if not isinstance(entry,str) or not entry: raise ValueError("package.toml requires [package] entrypoint")
    return _path(root,entry,"package entrypoint")

def _digest(path):
    s=os.lstat(path)
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise OSError("implementation file is not an unaliased regular file")
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""): h.update(b)
    return h.hexdigest()

def _digests(root,names):
    out={}
    for n in names:
        p=_path(root,n,"generated output")
        if not os.path.exists(p): raise OSError("generated output is absent: "+n)
        out[n]=_digest(p)
    return out

def _whole(root,names):
    try: return all(os.path.isfile(_path(root,n,"generated output")) and not os.path.islink(_path(root,n,"generated output")) for n in names)
    except (OSError,ValueError): return False

def _state_path(root): return os.path.join(root,STATE_DIR,STATE_FILE)
def _read_state(root):
    try:
        with open(_state_path(root),encoding="utf8") as f: x=json.load(f)
        return x if isinstance(x,dict) else {}
    except (OSError,ValueError,TypeError): return {}
def _write_state(root,value):
    d=os.path.join(root,STATE_DIR)
    if os.path.lexists(d) and not os.path.isdir(d): raise OSError(".launcher is not a directory")
    os.makedirs(d,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=".state-",dir=d)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f: json.dump(value,f,sort_keys=True); f.write("\n")
        os.replace(tmp,_state_path(root)); tmp=""
    finally:
        if tmp:
            try: os.unlink(tmp)
            except OSError: pass

def _identity(root):
    v=kernel.verify(root)
    if not v.get("ok"): raise kernel.ClaimError("sealed claim identity does not hold")
    return str(v.get("root",""))
def _audit(root):
    try: return kernel.audit(root).get("ok") is True
    except kernel.ClaimError: return False

def _rebuild(root,names,producer):
    parent=tempfile.mkdtemp(prefix="reticuli-launch-"); room=os.path.join(parent,"claim")
    try:
        result=kernel.rebuild(root,producer,room)
        if not result.get("ok"): _say("producer rebuild failed: "+str(result.get("verdict","failed"))); return False
        pairs=[]
        for n in names:
            src=_path(room,n,"rebuilt output"); dst=_path(root,n,"generated output"); _digest(src)
            if os.path.lexists(dst):
                s=os.lstat(dst)
                if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise OSError("unsafe existing generated output: "+n)
            pairs.append((src,dst))
        for src,dst in pairs:
            os.makedirs(os.path.dirname(dst),exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=".launcher-output-",dir=os.path.dirname(dst)); os.close(fd)
            try: shutil.copyfile(src,tmp); os.replace(tmp,dst)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        return True
    except (kernel.ClaimError,OSError,ValueError) as e: _say("producer rebuild failed: "+str(e)); return False
    finally: shutil.rmtree(parent,ignore_errors=True)

def _sandbox(command,root):
    value=kernel.sandbox(command,root)
    if isinstance(value,tuple) and len(value)==2:
        argv,backend=list(value[0]),str(value[1])
    elif isinstance(value,dict): argv,backend=["/bin/sh","-c",command],str(value.get("backend","none"))
    else: argv,backend=["/bin/sh","-c",command],"none"
    if backend!="none": return argv,backend
    # The launcher's availability contract is deliberately the acceptance
    # probe's modest one.  A kernel may reject bwrap for gates because its
    # stronger writable-room probe fails; execution must still use a bwrap
    # which can isolate the network and bind this claim writable.
    bwrap=shutil.which("bwrap")
    if bwrap and sys.platform.startswith("linux"):
        try:
            probe=subprocess.run([bwrap,"--ro-bind","/","/","--unshare-net","true"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8,check=False)
        except (OSError,subprocess.SubprocessError): probe=None
        if probe is not None and probe.returncode==0:
            return [bwrap,"--die-with-parent","--unshare-net","--ro-bind","/","/","--bind",root,root,"--chdir",root,"--setenv",kernel._JAILED,"bubblewrap","--","/bin/sh","-c",command],"bubblewrap"
    seat=shutil.which("sandbox-exec")
    if seat and sys.platform=="darwin":
        profile='(version 1) (allow default) (deny network*)'
        return [seat,"-p",profile,"/bin/sh","-c",command],"seatbelt"
    return argv,"none"

def _execute(root,entry,args,phase,no_sandbox):
    argv=[sys.executable,os.path.relpath(entry,root)]+list(args); command=shlex.join(argv)
    execution,backend=(argv,"off") if no_sandbox else _sandbox(command,root)
    parent=os.path.join(root,STATE_DIR)
    if os.path.lexists(parent) and not os.path.isdir(parent): _say("not runnable: .launcher is not a directory"); return NOT_RUNNABLE
    os.makedirs(parent,exist_ok=True); runtime=tempfile.mkdtemp(prefix="runtime-",dir=parent)
    env={"PATH":os.environ.get("PATH",os.defpath),"LANG":os.environ.get("LANG","C.UTF-8"),"HOME":runtime,"TMPDIR":runtime}
    for k in ("LC_ALL","TZ"):
        if k in os.environ: env[k]=os.environ[k]
    if backend not in ("none","off"): env[kernel._JAILED]=os.environ.get(kernel._JAILED,backend)
    _say(f'phase = "{phase}"'); _say(f'quarantine = "{backend}"')
    try: return int(subprocess.run(execution,cwd=root,env=env,check=False).returncode)
    except OSError as e: _say("cannot execute entrypoint: "+str(e)); return NOT_RUNNABLE
    finally:
        shutil.rmtree(runtime,ignore_errors=True)
        try:
            if not os.listdir(parent): os.rmdir(parent)
        except OSError: pass

def run(claim,args=None,*,accept_generated=False,signed_only=False,no_sandbox=False):
    try:
        root,recipe,generated=_load(claim); entry=_package(root,recipe,generated); phase=kernel.phase(root); identity=_identity(root)
    except (ValueError,OSError,kernel.ClaimError) as e: _say("not runnable: "+str(e)); return NOT_RUNNABLE
    if signed_only and phase!="signed": _say("trust refused: claim is not signed to the configured trust anchor"); return TRUST_REFUSED
    state=_read_state(root); accepted=state.get("accepted")
    if isinstance(accepted,dict) and state.get("root")==identity:
        try: current=_digests(root,generated)
        except (OSError,ValueError): current={}
        if current!=accepted: _say("drifted accepted build; nothing was executed (use strip to recover)"); return DRIFT
    if not _whole(root,generated):
        producer=os.environ.get("RETICULI_PRODUCER")
        if not producer: _say("claim is latent; RETICULI_PRODUCER is not configured"); return NO_PRODUCER
        if not _rebuild(root,generated,producer): return DRIFT
        try: _write_state(root,{"root":identity,"fresh":True})
        except OSError as e: _say("cannot record generated-byte consent state: "+str(e)); return NOT_RUNNABLE
        state=_read_state(root)
    fresh=state.get("root")==identity and state.get("fresh") is True
    if fresh and not accept_generated: _say("newly generated bytes require consent; pass --accept-generated"); return CONSENT_REQUIRED
    if not _audit(root): _say("build audit failed; nothing was executed or modified (use strip to recover)"); return DRIFT
    if fresh and accept_generated:
        try: _write_state(root,{"root":identity,"accepted":_digests(root,generated)})
        except (OSError,ValueError) as e: _say("cannot record accepted byte digests: "+str(e)); return NOT_RUNNABLE
    try:
        if not os.path.isfile(entry) or os.path.islink(entry): raise ValueError("package entrypoint is absent or aliased")
        _digest(entry)
    except (OSError,ValueError) as e: _say("not runnable: "+str(e)); return NOT_RUNNABLE
    return _execute(root,entry,args or [],phase,no_sandbox)

def invoke(*args,**kwargs): return run(*args,**kwargs)

def strip(claim):
    try:
        root,_,generated=_load(claim); paths=[]
        for n in generated:
            p=_path(root,n,"generated output")
            if os.path.lexists(p):
                s=os.lstat(p)
                if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise ValueError("generated output is not an unaliased file: "+n)
                paths.append(p)
        d=os.path.join(root,STATE_DIR)
        if os.path.lexists(d) and not os.path.isdir(d): raise ValueError(".launcher is not a directory")
        for p in paths: os.unlink(p)
        if os.path.isdir(d): shutil.rmtree(d)
        _say("generated implementation stripped; claim is latent"); return 0
    except (ValueError,OSError,kernel.ClaimError) as e: _say("not runnable: "+str(e)); return NOT_RUNNABLE

def ls(claims):
    rc=0
    for claim in claims:
        try:
            root,recipe,generated=_load(claim); m=kernel.read_manifest(root); phase=kernel.phase(root); presence="materialized" if _whole(root,generated) else "latent"; name=recipe.get("claim",{}).get("name",m.get("name","?")); print(f"{name}\t{str(m['root'])[:12]}\t{phase}\t{presence}")
        except (ValueError,OSError,kernel.ClaimError) as e: _say(f"cannot list {claim}: {e}"); rc=NOT_RUNNABLE
    return rc

def _parser():
    p=argparse.ArgumentParser(prog="python3 -m reticuli.launcher",description="Run or return a claim's generated implementation to latency.",epilog="run flags: --accept-generated --signed-only --no-sandbox")
    s=p.add_subparsers(dest="verb",required=True); r=s.add_parser("run"); r.add_argument("claim"); r.add_argument("--accept-generated",action="store_true"); r.add_argument("--signed-only",action="store_true"); r.add_argument("--no-sandbox",action="store_true"); r.add_argument("entry_args",nargs="*"); q=s.add_parser("strip"); q.add_argument("claim"); q=s.add_parser("ls"); q.add_argument("claims",nargs="+"); return p

def main(argv=None):
    o=_parser().parse_args(argv)
    if o.verb=="run": return run(o.claim,list(o.entry_args),accept_generated=o.accept_generated,signed_only=o.signed_only,no_sandbox=o.no_sandbox)
    if o.verb=="strip": return strip(o.claim)
    return ls(o.claims)
if __name__=="__main__": raise SystemExit(main())

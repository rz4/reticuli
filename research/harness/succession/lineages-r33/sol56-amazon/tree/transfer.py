"""Deterministic, verify-on-import claim transport."""
from __future__ import annotations
import io, os, shutil, tarfile
from . import kernel
from ._kernel import recipe as _recipe


def _file_names(d, blind=False):
    parsed=kernel.load_recipe(d); rp=_recipe.recipe_path(d)
    names=[os.path.basename(rp)] + list(_recipe._inputs(parsed,d))
    for s in parsed.get("step",[]):
        generated=s.get("kind")=="produce" and s.get("class","generated") in ("generated","free")
        if not (blind and generated): names.append(s.get("output"))
    names.append(kernel.MANIFEST)
    # Attestations are portable residue. Nothing else in the local store is.
    ad=os.path.join(d,".reticuli","attest")
    if os.path.isdir(ad):
        for base,dirs,files in os.walk(ad):
            dirs.sort(); files.sort()
            for fn in files: names.append(os.path.relpath(os.path.join(base,fn),d))
    return [n for n in names if n and os.path.isfile(os.path.join(d,n))]


def _component_index(d):
    idx={}
    for rel in (os.path.join(".reticuli","sealed"),os.path.join(".reticuli","deps")):
        base=os.path.join(d,rel)
        if not os.path.isdir(base): continue
        for n in sorted(os.listdir(base)):
            p=os.path.join(base,n)
            try: idx[kernel.read_manifest(p)["root"]]=p
            except (kernel.ClaimError,OSError): pass
    return idx


def _closure(d):
    idx=_component_index(d); out=[]; seen=set()
    def walk(cur):
        try: links=kernel.read_manifest(cur).get("components",[])
        except kernel.ClaimError: links=[]
        for l in links if isinstance(links,list) else []:
            r=l.get("root") if isinstance(l,dict) else None
            if r in seen: continue
            seen.add(r); p=idx.get(r)
            if p: out.append(p); walk(p)
    walk(d); return out


def export(d, path, blind=False):
    d=os.path.abspath(d)
    if not kernel.verify(d)["ok"]: raise kernel.ClaimError("claim identity does not hold")
    entries=[]
    for n in _file_names(d,blind): entries.append((n,os.path.join(d,n)))
    for comp in _closure(d):
        name=kernel.read_manifest(comp)["name"]
        for n in _file_names(comp,True):
            # Attestation residue on dependencies is harmless and portable too.
            entries.append((os.path.join(".reticuli","deps",name,n),os.path.join(comp,n)))
    # One deterministic entry per archive name.
    byname={n.replace(os.sep,"/"):p for n,p in entries}
    with tarfile.open(path,"w",format=tarfile.USTAR_FORMAT) as t:
        for name in sorted(byname):
            data=open(byname[name],"rb").read()
            info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o644
            info.mtime=0; info.uid=info.gid=0; info.uname=info.gname=""
            t.addfile(info,io.BytesIO(data))
    return {"path":os.path.abspath(path),"root":kernel.verify(d)["root"]}


def import_(path, into):
    into=os.path.abspath(into)
    if os.path.exists(into):
        if not os.path.isdir(into) or os.listdir(into): raise kernel.ClaimError("import target is not empty")
    else: os.makedirs(into)
    try:
        with tarfile.open(path,"r") as t:
            for member in t.getmembers():
                name=member.name
                if not member.isfile() or os.path.isabs(name) or ".." in name.replace("\\","/").split("/"):
                    raise kernel.ClaimError("unsafe archive member")
                target=os.path.abspath(os.path.join(into,name))
                if os.path.commonpath((into,target))!=into: raise kernel.ClaimError("archive escapes target")
                os.makedirs(os.path.dirname(target),exist_ok=True)
                src=t.extractfile(member)
                with open(target,"wb") as f: shutil.copyfileobj(src,f)
        result=kernel.verify(into)
        if not result["ok"]: raise kernel.ClaimError("imported identity does not hold")
        return result
    except Exception:
        # Preserve ClaimError while ensuring a partial import isn't mistaken for a claim.
        raise

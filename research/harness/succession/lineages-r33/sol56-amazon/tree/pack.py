"""Compose an ordinary project directory into a content-addressed claim."""
from __future__ import annotations
import glob, hashlib, os, shutil
from . import kernel, registry
from .render import dump_recipe


def _expand(root, declarations):
    root=os.path.abspath(os.fspath(root)); result=[]; seen=set()
    for declaration in declarations or []:
        if not isinstance(declaration,str) or not declaration: raise kernel.ClaimError("file declaration must be a non-empty string")
        pattern=os.path.join(root,declaration); magic=glob.has_magic(declaration)
        matches=sorted(glob.glob(pattern,recursive=True)) if magic else ([pattern] if os.path.isfile(pattern) else [])
        if not magic and not matches: raise kernel.ClaimError("declared file absent: "+declaration)
        for path in matches:
            if not os.path.isfile(path): continue
            relative=os.path.relpath(path,root).replace(os.sep,"/")
            if relative.startswith("../") or relative=="..": raise kernel.ClaimError("pattern escapes project")
            if relative not in seen: seen.add(relative); result.append(relative)
    return result


def _write_recipe(root,recipe):
    path=os.path.join(root,kernel.RECIPE); legacy=os.path.join(root,"claim.toml")
    if os.path.abspath(legacy)!=os.path.abspath(path) and os.path.isfile(legacy): os.unlink(legacy)
    with open(path,"w",encoding="utf-8",newline="\n") as stream: stream.write(dump_recipe(recipe))


def _manifest(root,name,inputs):
    path=os.path.join(root,name)
    with open(path,"w",encoding="utf-8",newline="\n") as stream:
        for item in inputs:
            with open(os.path.join(root,item),"rb") as source: digest=hashlib.sha256(source.read()).hexdigest()
            stream.write(f"{digest}  {item}\n")


def _component_steps(outputs,component):
    supplied=set((component or {}).get("outputs",[])); source_name=(component or {}).get("name"); steps=[]
    for output in outputs:
        step={"kind":"produce","output":output,"class":"generated"}
        if output in supplied:
            if not isinstance(source_name,str) or not source_name: raise kernel.ClaimError("component requires a name")
            step["from"]=source_name
        else: step["guidance"]=f"regenerate {output} to pass the gate"
        steps.append(step)
    return steps


def _same(a,b):
    with open(a,"rb") as x, open(b,"rb") as y: return hashlib.sha256(x.read()).digest()==hashlib.sha256(y.read()).digest()


def _carry_component(root,component):
    if component is None:return []
    if not isinstance(component,dict):raise kernel.ClaimError("component must be a mapping")
    name,source,outputs=component.get("name"),component.get("claim"),component.get("outputs",[])
    if not isinstance(name,str) or not name or source is None or not isinstance(outputs,list):raise kernel.ClaimError("malformed component declaration")
    source=os.path.abspath(os.fspath(source));man=kernel.read_manifest(source)
    for output in outputs:
        here,there=os.path.join(root,output),os.path.join(source,output)
        if not os.path.isfile(here) or not os.path.isfile(there):raise kernel.ClaimError("component output absent: "+str(output))
        if not _same(here,there):raise kernel.ClaimError("component output differs: "+str(output))
    target=os.path.join(root,kernel.STORE,"sealed",name)
    if os.path.lexists(target):
        if os.path.islink(target) or os.path.isfile(target):os.unlink(target)
        else:shutil.rmtree(target)
    os.makedirs(os.path.dirname(target),exist_ok=True)
    try:os.symlink(source,target,target_is_directory=True)
    except (OSError,NotImplementedError):shutil.copytree(source,target,ignore=shutil.ignore_patterns("sealed","deps"))
    return [{"input":output,"component":name,"root":man["root"],"output":output} for output in outputs]


def pack(root,name,generated,inputs,gate,gate_output,envelope=None,claim_format=3,
         component=None,mutation_floor=None,requires=None,by=None,
         inputs_manifest=None,environment=None):
    """Write, warm-certify, and seal a project's self-claim."""
    root=os.path.abspath(os.fspath(root))
    if not isinstance(name,str) or not name:raise kernel.ClaimError("claim name must be a string")
    outputs=_expand(root,generated);pinned=_expand(root,inputs)
    try:version=int(claim_format)
    except (TypeError,ValueError):raise kernel.ClaimError("claim_format must be an integer") from None
    if version<1:raise kernel.ClaimError("claim_format must be positive")
    claim={"name":name}
    if version!=1:claim["format"]=version
    if inputs_manifest is not None:
        if version<2:raise kernel.ClaimError("inputs_manifest requires claim format 2")
        if not isinstance(inputs_manifest,str) or not inputs_manifest:raise kernel.ClaimError("inputs_manifest must name a file")
        _manifest(root,inputs_manifest,pinned);claim["inputs_manifest"]=inputs_manifest
    else:claim["inputs"]=pinned
    if envelope is not None:claim["envelope"]=envelope
    if mutation_floor is not None:claim["mutation_floor"]=float(mutation_floor)
    if requires is not None:claim["requires"]=list(requires)
    if environment is not None:
        if not os.path.isfile(os.path.join(root,environment)):raise kernel.ClaimError("environment file absent: "+str(environment))
        claim["environment"]=environment
    steps=_component_steps(outputs,component)
    if version==1:
        for step in steps:
            if "guidance" in step:step["request"]=step.pop("guidance")
    steps.append({"kind":"gate","output":gate_output,"class":"validated","run":gate})
    recipe={"claim":claim,"step":steps}
    # Decide vacuity against the expanded author declarations (manifest or not).
    deciders=[x for x in kernel.gate_deciders(gate) if x in set(outputs)|set(pinned)]
    if deciders and all(x in outputs for x in deciders):raise kernel.ClaimError("vacuous gate: every decider is generated")
    _write_recipe(root,recipe)
    result=kernel.run_gate(gate,root,recipe)
    if result.get("status")!="ok":raise kernel.ClaimError("gate failed: "+str(result.get("status")))
    if not os.path.isfile(os.path.join(root,gate_output)):raise kernel.ClaimError("gate produced no verdict: "+str(gate_output))
    links=_carry_component(root,component);man=registry.seal_with(root,components=links if component else None)
    if by is not None:kernel.ledger(root,{"event":"producer","model":str(by)})
    return {"ok":True,"root":man["root"],"name":name,"build_digest":kernel.build_digest(root),"gate":result}

__all__=["pack"]

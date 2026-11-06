import os,glob,shutil
from . import kernel,render,registry
from ._kernel.core import _safe

def _expand(d,patterns):
    out=[]
    for pattern in patterns or []:
        _safe(d,pattern)
        out.extend(os.path.relpath(p,d) for p in glob.glob(os.path.join(d,pattern),recursive=True) if os.path.isfile(p))
    return sorted(set(out))
def pack(root,name,generated,inputs,gate,gate_output,component=None,envelope=None,claim_format=3,mutation_floor=None,requires=None,by=None,inputs_manifest=None,environment=None,carried=None,**kw):
    gen=_expand(root,generated); ins=_expand(root,inputs); carry=_expand(root,carried)
    c={'name':name,'inputs':ins}
    if claim_format!=1: c['format']=claim_format
    for k,v in [('envelope',envelope),('mutation_floor',mutation_floor),('requires',requires),('environment',environment)]:
        if v is not None: c[k]=v
    if environment and not os.path.isfile(_safe(root,environment)): raise kernel.ClaimError('missing environment file')
    if inputs_manifest:
        with open(_safe(root,inputs_manifest),'w') as f:
            for p in ins: f.write(kernel._hash_file(_safe(root,p))+'  '+p+'\n')
        c['inputs_manifest']=inputs_manifest; c['inputs']=[]
    steps=[]; components=[]
    for p in gen:
        s={'kind':'produce','output':p,'class':'generated','request' if claim_format==1 else 'guidance':'regenerate '+p+' to pass the gate'}
        if component and p in component['outputs']:
            s['from']=component['name']; components.append({'input':p,'output':p,'component':component['name'],'root':kernel.read_manifest(component['claim'])['root']})
        steps.append(s)
    steps.extend({'kind':'produce','output':p,'class':'carried'} for p in carry)
    steps.append({'kind':'gate','output':gate_output,'class':'validated','run':gate})
    r={'claim':c,'step':steps}
    if kernel.vacuous_gates(r): raise kernel.ClaimError('vacuous gate')
    with open(os.path.join(root,kernel.RECIPE),'w') as f: f.write(render.dump_recipe(r))
    if component:
        dst=os.path.join(root,kernel.STORE,'sealed',component['name'])
        if not os.path.exists(dst): registry.copy_closure(component['claim'],dst)
    result=kernel.run_gate(gate,root,r)
    if result['status']!='ok': raise kernel.ClaimError('gate failed: '+result['stderr']+result['stdout'])
    m=registry.seal_with(root,components=components or None)
    if by: kernel.ledger(root,{'event':'producer','model':by})
    return {**m,'ok':True,'generated':len(gen),'inputs':len(ins),'component':component['name'] if component else None}

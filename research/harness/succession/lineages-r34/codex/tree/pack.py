import os, glob
from . import kernel, registry
from .render import dump_recipe
from ._kernel.core import _safe

def _expand(d,patterns):
    out=[]
    for p in patterns or []:
        _safe(d,p)
        if glob.has_magic(p):matches=glob.glob(os.path.join(d,p),recursive=True)
        else:
            matches=[os.path.join(d,p)]
            if not os.path.isfile(matches[0]):raise kernel.ClaimError('missing file '+p)
        out.extend(os.path.relpath(x,d) for x in matches if os.path.isfile(x))
    return sorted(set(out))

def pack(root,name,generated,inputs,gate,gate_output,component=None,envelope=None,claim_format=3,mutation_floor=None,requires=None,by=None,inputs_manifest=None,environment=None,carried=None,**kwargs):
    gen=_expand(root,generated);ins=_expand(root,inputs);carry=_expand(root,carried)
    c={'name':name,'inputs':ins}
    if claim_format!=1:c['format']=claim_format
    for k,v in [('envelope',envelope),('mutation_floor',mutation_floor),('requires',requires),('environment',environment)]:
        if v is not None:c[k]=v
    if environment and not os.path.isfile(_safe(root,environment)):raise kernel.ClaimError('missing environment '+environment)
    if inputs_manifest:
        p=_safe(root,inputs_manifest)
        with open(p,'w') as f:
            for n in ins:f.write(kernel._hash_file(_safe(root,n))+'  '+n+'\n')
        c['inputs_manifest']=inputs_manifest;c.pop('inputs',None)
    steps=[];links=[]
    for n in gen:
        s={'kind':'produce','output':n,'class':'generated',('request' if claim_format<3 else 'guidance'):'regenerate '+n+' to pass the gate'}
        if component and n in component['outputs']:
            s['from']=component['name'];links.append({'input':n,'output':n,'component':component['name'],'root':kernel.read_manifest(component['claim'])['root']})
        steps.append(s)
    for n in carry:steps.append({'kind':'produce','output':n,'class':'carried'})
    steps.append({'kind':'gate','output':gate_output,'class':'validated','run':gate})
    r={'claim':c,'step':steps}
    if kernel.vacuous_gates(r):raise kernel.ClaimError('vacuous gate: '+gate_output)
    with open(os.path.join(root,kernel.RECIPE),'w',encoding='utf-8') as f:f.write(dump_recipe(r))
    if component:
        dest=os.path.join(root,kernel.STORE,'sealed',component['name'])
        registry._copy_claim(component['claim'],dest)
    outcome=kernel.run_gate(gate,root,r)
    if outcome['status']!='ok':raise kernel.ClaimError('gate '+outcome['status']+': '+outcome['stderr'])
    m=registry.seal_with(root,components=links if component else None)
    if by:kernel.ledger(root,{'event':'producer','model':by})
    return dict(m,ok=True,generated=len(gen),inputs=len(ins),component=component['name'] if component else None)

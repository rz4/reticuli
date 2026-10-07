"""Content-addressed component links and composed claim operations."""
import os
import shutil
import tempfile
from . import kernel
from ._util import safe_path, copy_into, write_json, declared_inputs

SEALED = '.reticuli/sealed'
DEPS = '.reticuli/deps'

def _store(ws):
    return os.path.join(ws, SEALED)

def _component(directory, name, ws=None):
    for base in (os.path.join(directory, SEALED), os.path.join(directory, DEPS),
                 _store(ws) if ws else ''):
        path = os.path.join(base, name) if base else ''
        if path and os.path.isdir(path): return path
    return None

def seal_with(directory, *, components=None, proof=None):
    old = None
    try: old = kernel.read_manifest(directory)
    except kernel.ClaimError: pass
    result = kernel.seal(directory)
    if components is not None: result['components'] = components
    elif old and old.get('components'): result['components'] = old['components']
    if proof is not None: result['proof'] = proof
    elif old and old.get('proof'): result['proof'] = old['proof']
    write_json(os.path.join(directory, kernel.MANIFEST), result)
    return result

def claims(ws):
    base = _store(ws)
    if not os.path.isdir(base): return []
    rows = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            try:
                m = kernel.read_manifest(path)
                rows.append({'name': m['name'], 'root': m['root'], 'phase': kernel.phase(path), 'path': path})
            except kernel.ClaimError: pass
    return rows

def detect_components(ws, inputs):
    found=[]
    for name in inputs:
        digest=kernel._hash_file(safe_path(ws,name))
        for row in claims(ws):
            path=row['path']
            recipe=kernel.load_recipe(path)
            for step in recipe.get('step',[]):
                out=step['output']
                p=safe_path(path,out)
                if os.path.isfile(p) and kernel._hash_file(p)==digest:
                    found.append({'input':name,'component':row['name'],'root':row['root'],'output':out})
    return found

def deps(ws):
    rows=[]
    for row in claims(ws):
        path=row['path']; links=kernel.read_manifest(path).get('components',[])
        edges=[]
        for link in links:
            component=_component(path,link['component'],ws)
            ok=component is not None and kernel.verify(component)['ok'] and kernel.read_manifest(component)['root']==link['root']
            edges.append({**link,'status':'ok' if ok else 'unresolved'})
        rows.append({**row,'depends_on':edges})
    return {'claims':rows}

def sign_root(directory, ws=None, _seen=None):
    seen=set() if _seen is None else _seen
    path=os.path.realpath(directory)
    if path in seen: raise kernel.ClaimError('component cycle')
    seen.add(path)
    checked=kernel.verify(directory)
    if not checked['ok']: raise kernel.ClaimError('component identity mismatch')
    nodes=[]
    names=set()
    for link in kernel.read_manifest(directory).get('components',[]):
        name=link['component']
        if name in names: continue
        names.add(name)
        part=_component(directory,name,ws)
        if not part: raise kernel.ClaimError(f'missing component {name}')
        if kernel.read_manifest(part)['root'] != link['root']: raise kernel.ClaimError('component root mismatch')
        nodes.append(sign_root(part,ws,seen.copy()))
    return kernel.sign_node(checked['root'],kernel.build_digest(directory),nodes)

def pull(directory, ws):
    manifest=kernel.read_manifest(directory)
    dst=os.path.join(_store(ws),manifest['name'])
    os.makedirs(os.path.dirname(dst),exist_ok=True)
    if os.path.exists(dst): shutil.rmtree(dst)
    shutil.copytree(directory,dst)
    claim=kernel.load_recipe(directory)
    names=declared_inputs(directory)+[s['output'] for s in claim.get('step',[])]
    for name in names:
        src=safe_path(directory,name)
        if os.path.isfile(src): copy_into(src,safe_path(ws,name))
    return {'materialized':True,'name':manifest['name'],'root':manifest['root']}

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    manifest=kernel.read_manifest(directory)
    links=manifest.get('components',[])
    built=[]; folders={}; copied={}
    with tempfile.TemporaryDirectory(prefix='reticuli-chain-') as temp:
        for link in links:
            name=link['component']
            if name not in folders:
                src=_component(directory,name,ws)
                if not src: raise kernel.ClaimError(f'missing component {name}')
                if reuse:
                    target=src
                else:
                    target=os.path.join(temp,name)
                    # A component with no generated output still earns its gates.
                    kernel.rebuild(src,producer,target)
                folders[name]=target
                built.append({'component':name,'root':kernel.read_manifest(target)['root']})
            claim=kernel.load_recipe(directory)
            from_outputs={s['output'] for s in claim.get('step',[]) if s.get('from')==name}
            if link.get('input') in from_outputs:
                copied[link['input']]=safe_path(folders[name],link['output'])
        result=kernel.rebuild(directory,producer,into,produce_from=copied or None)
        # Provenance is residue, and is attached after the kernel's fresh build.
        if links: seal_with(into,components=links)
        for name,target in folders.items():
            dst=os.path.join(into,SEALED,name)
            os.makedirs(os.path.dirname(dst),exist_ok=True)
            if os.path.exists(dst): shutil.rmtree(dst)
            shutil.copytree(target,dst)
        result['rebuilt_components']=built
        return result

def audit_deep(directory):
    own=kernel.audit(directory)
    layers=[]
    seen=set()
    def walk(parent, shipped, links):
        groups={}
        for link in links: groups.setdefault(link['component'],[]).append(link)
        for name,refs in groups.items():
            if name in seen: continue
            seen.add(name)
            component=_component(parent,name)
            if component is None:
                layers.append({'name':name,'root':refs[0].get('root'),'ok':False,'status':'unresolved','bytes_from':[x['input'] for x in refs]})
                continue
            with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
                shutil.copytree(component,room,dirs_exist_ok=True)
                for link in refs:
                    source=shipped.get(link['input'],safe_path(parent,link['input']))
                    copy_into(source,safe_path(room,link['output']))
                audit=kernel.audit(room)
                layers.append({'name':name,'root':kernel.read_manifest(component)['root'],
                               'ok':audit['ok'],'status':'earned' if audit['ok'] else 'broken',
                               'bytes_from':[x['input'] for x in refs]})
                child_shipped={}
                for child in kernel.read_manifest(component).get('components',[]):
                    child_shipped[child['input']]=safe_path(room,child['input'])
                walk(component,child_shipped,kernel.read_manifest(component).get('components',[]))
    walk(directory,{},kernel.read_manifest(directory).get('components',[]))
    return {'ok':own['ok'] and all(row['ok'] for row in layers),'root':own.get('root'),'layers':layers,'gates':own.get('gates',[])}

def crosscheck_deep(m1,m2,m3,**kwargs):
    result=kernel.crosscheck(m1,m2,m3,**kwargs)
    deep={f'M{i}':audit_deep(path) for i,path in enumerate((m1,m2,m3),1)}
    if not all(row['ok'] for row in deep.values()):
        result['satisfied']=False; result['verdict']='reject'; result['deep']=deep
    return result

def structure(directory):
    return {'name':kernel.read_manifest(directory)['name'],'phase':kernel.phase(directory),
            'components':kernel.read_manifest(directory).get('components',[])}

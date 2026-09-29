"""Stored claims, content links, and composed audits and rebuilds."""
from __future__ import annotations
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from . import kernel
from ._util import copy_into, safe_path, write_json

kernel.MANIFEST = kernel.core.MANIFEST

SEALED = '.reticuli/sealed'
DEPS = '.reticuli/deps'

def _store(ws):
    path = safe_path(ws, SEALED)
    return {p.name: str(p) for p in Path(path).iterdir() if p.is_dir()} if os.path.isdir(path) else {}

def _components(d):
    return kernel.read_manifest(d).get('components', [])

def _resolve(d, name, ws=None):
    candidates = [os.path.join(d, DEPS, name), os.path.join(d, SEALED, name)]
    if ws: candidates.append(os.path.join(ws, SEALED, name))
    for path in candidates:
        if os.path.isdir(path): return path
    return None

def detect_components(ws, inputs):
    links = []
    for name in inputs:
        source = safe_path(ws, name)
        if not os.path.isfile(source): continue
        digest = kernel._hash_file(source)
        for component, directory in sorted(_store(ws).items()):
            data = kernel.load_recipe(directory)
            for step in data.get('step', []):
                output = step['output']
                path = safe_path(directory, output)
                if os.path.isfile(path) and kernel._hash_file(path) == digest:
                    links.append({'input': name, 'component': component,
                                  'root': kernel.verify(directory)['root'], 'output': output})
    return links

def seal_with(d, components=None, proof=None):
    manifest = kernel.seal(d)
    if components is not None: manifest['components'] = components
    if proof is not None: manifest['proof'] = proof
    write_json(safe_path(d, kernel.core.MANIFEST), manifest)
    return manifest

def claims(ws):
    rows = []
    for name, path in sorted(_store(ws).items()):
        verified = kernel.verify(path)
        rows.append({'name': name, 'root': verified['root'], 'ok': verified['ok'],
                     'phase': kernel.phase(path), 'path': path})
    return rows

def deps(ws):
    rows=[]
    stored=_store(ws)
    for name,path in sorted(stored.items()):
        edges=[]
        for link in _components(path):
            dep=stored.get(link['component'])
            status='missing'
            if dep:
                status='ok' if kernel.verify(dep)['root']==link['root'] else 'mismatch'
            edges.append({**link,'status':status})
        rows.append({'name':name,'phase':kernel.phase(path),'depends_on':edges})
    return {'claims':rows}

def sign_root(d, ws=None, _seen=None):
    seen=set() if _seen is None else _seen
    real=os.path.realpath(d)
    if real in seen: raise kernel.ClaimError('component cycle')
    seen.add(real)
    children=[]
    for link in _components(d):
        dep=_resolve(d,link['component'],ws)
        if dep is None: raise kernel.ClaimError(f"missing component: {link['component']}")
        if kernel.verify(dep)['root']!=link['root']: raise kernel.ClaimError('component root mismatch')
        children.append(sign_root(dep,ws,seen))
    seen.remove(real)
    return kernel.sign_node(kernel.verify(d)['root'],kernel.build_digest(d),children)

def _claim_files(d, blind=False):
    data=kernel.load_recipe(d)
    names={os.path.basename(kernel._recipe_path(d)),*kernel._inputs(data)}
    for step in data.get('step',[]):
        if not blind or step['kind']!='produce': names.add(step['output'])
    return names

def pull(d, ws):
    os.makedirs(ws,exist_ok=True)
    for name in _claim_files(d):
        copy_into(safe_path(d,name),safe_path(ws,name))
    return {'materialized':True,'root':kernel.verify(d)['root']}

def rebuild_chain(d, producer, into, ws=None, reuse=False):
    components=_components(d)
    rebuilt=[]; produce_from={}; input_from={}
    with tempfile.TemporaryDirectory(prefix='reticuli-chain-') as tmp:
        for link in components:
            source=_resolve(d,link['component'],ws)
            if source is None: raise kernel.ClaimError(f"missing component: {link['component']}")
            if kernel.verify(source)['root']!=link['root']: raise kernel.ClaimError('component root mismatch')
            rebuilt.append({'component':link['component'],'root':link['root']})
            if reuse and link['input'] in {s['output'] for s in kernel.load_recipe(d).get('step',[]) if s['kind']=='produce'}:
                produce_from[link['input']]=safe_path(source,link['output'])
            elif link['input'] in kernel._inputs(kernel.load_recipe(d)):
                input_from[link['input']]=safe_path(source,link['output'])
        missing=[s['output'] for s in kernel.load_recipe(d).get('step',[]) if s['kind']=='produce' and s['output'] not in produce_from]
        command=producer
        if len(missing)>1:
            command='; '.join('RETICULI_OUTPUT="$PWD/"'+shlex.quote(name)+' sh -c '+shlex.quote(producer) for name in missing)
        result=kernel.rebuild(d,command,into,produce_from=produce_from,input_from=input_from)
    if components:
        manifest=kernel.read_manifest(into); manifest['components']=components
        write_json(safe_path(into,kernel.core.MANIFEST),manifest)
        for link in components:
            source=_resolve(d,link['component'],ws)
            target=safe_path(into,os.path.join(SEALED,link['component']))
            shutil.copytree(source,target,dirs_exist_ok=True)
    return {**result,'rebuilt_components':rebuilt}

def audit_deep(d, ws=None):
    own=kernel.audit(d)
    layers=[]
    for link in _components(d):
        source=_resolve(d,link['component'],ws)
        if not source:
            layers.append({'name':link['component'],'root':link['root'],'ok':False,'status':'unresolved','bytes_from':[link['input']]})
            continue
        with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
            for name in _claim_files(source,blind=True):
                copy_into(safe_path(source,name),safe_path(room,name))
            copy_into(safe_path(source,kernel.core.MANIFEST),safe_path(room,kernel.core.MANIFEST))
            copy_into(safe_path(d,link['input']),safe_path(room,link['output']))
            audited=kernel.audit(room)
            layers.append({'name':link['component'],'root':link['root'],'ok':audited['ok'],
                           'status':'ok' if audited['ok'] else 'failed','bytes_from':[link['input']]})
    return {'ok':own['ok'] and all(x['ok'] for x in layers),'layers':layers,'audit':own}

def crosscheck_deep(m1,m2,m3):
    base=kernel.crosscheck(m1,m2,m3)
    audits={k:audit_deep(v) for k,v in [('M1',m1),('M2',m2),('M3',m3)]}
    base['deep']=audits
    if not all(a['ok'] for a in audits.values()):
        base['satisfied']=False; base['verdict']='reject'; base['rejected'].append('deep audit')
    return base

def structure(d,ws=None):
    return {'name':kernel.load_recipe(d)['claim']['name'],'root':kernel.verify(d)['root'],
            'phase':kernel.phase(d),'components':_components(d)}

def record_proof_deep(m1,m2,m3):
    result=crosscheck_deep(m1,m2,m3)
    return kernel.record_proof(m1,m2,m3) if result['satisfied'] else {'proof_recorded':False,'crosscheck':result}

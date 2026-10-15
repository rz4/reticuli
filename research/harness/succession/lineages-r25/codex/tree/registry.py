"""Content addressed component registry and recursive claim operations."""
import os
import shutil
import tempfile
from . import kernel
from ._kernel import recipe as recipes
from ._util import copy_into, safe_path, write_json

# The supplied kernel's audit room includes local generated outputs; component
# supplied produce outputs are copied through the same explicit override seam.
_kernel_audit = kernel.audit
def _composed_kernel_audit(directory, *, produce_from=None, shallow=False):
    parsed=kernel.load_recipe(directory)
    mapping={step['output']:safe_path(directory,step['output'])
             for step in parsed.get('step',[]) if step.get('from')
             and os.path.isfile(os.path.join(directory,step['output']))}
    mapping.update(produce_from or {})
    return _kernel_audit(directory,produce_from=mapping or None,shallow=shallow)
kernel.audit = _composed_kernel_audit

_kernel_seal = kernel.seal
def _preserving_seal(directory):
    try: previous=kernel.read_manifest(directory)
    except kernel.ClaimError: previous={}
    result=_kernel_seal(directory)
    for key in ('components','proof'):
        if key in previous: result[key]=previous[key]
    if result != kernel.read_manifest(directory):
        write_json(os.path.join(directory,kernel.MANIFEST),result)
    return result
kernel.seal = _preserving_seal


def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')

def _entries(ws):
    folder = _store(ws)
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, n) for n in sorted(os.listdir(folder)) if os.path.isdir(os.path.join(folder,n))]

def _workspace(directory):
    p = os.path.abspath(directory)
    marker = os.sep + '.reticuli' + os.sep + 'sealed' + os.sep
    if marker in p:
        return p.split(marker)[0]
    return p

def _resolve(root, directory, ws=None):
    candidates = []
    for base in (directory, ws, _workspace(directory)):
        if base and os.path.isdir(base):
            candidates.extend(_entries(base))
            dep = os.path.join(base, '.reticuli', 'deps')
            if os.path.isdir(dep):
                candidates.extend(os.path.join(dep,n) for n in sorted(os.listdir(dep)))
    seen = set()
    for path in candidates:
        real = os.path.realpath(path)
        if real in seen: continue
        seen.add(real)
        try:
            if kernel.read_manifest(path)['root'] == root:
                return path
        except (kernel.ClaimError, OSError):
            pass
    raise kernel.ClaimError('missing declared component: '+str(root))

def _links(directory):
    return kernel.read_manifest(directory).get('components', [])

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
    rows=[]
    for path in _entries(ws):
        try:
            m=kernel.read_manifest(path)
            rows.append(dict(name=m['name'], root=m['root'], path=path, phase=kernel.phase(path)))
        except kernel.ClaimError: pass
    return rows

def detect_components(ws, inputs):
    links=[]
    for name in inputs:
        source=safe_path(ws,name)
        digest=kernel._hash_file(source)
        for component in _entries(ws):
            try:
                parsed=kernel.load_recipe(component)
                for step in parsed.get('step',[]):
                    out=step['output']
                    path=safe_path(component,out)
                    if os.path.isfile(path) and kernel._hash_file(path)==digest:
                        links.append({'input':name,'component':kernel.read_manifest(component)['name'], 'root':kernel.read_manifest(component)['root'],'output':out})
            except kernel.ClaimError: pass
    return links

def deps(ws):
    nodes=[]
    for row in claims(ws):
        edges=[]
        for link in _links(row['path']):
            try:
                target=_resolve(link['root'],row['path'],ws)
                ok=kernel.verify(target)['ok']
                if os.path.isfile(os.path.join(row['path'],link['input'])) and os.path.isfile(os.path.join(target,link['output'])):
                    ok=ok and kernel._hash_file(os.path.join(row['path'],link['input']))==kernel._hash_file(os.path.join(target,link['output']))
                edges.append(dict(link,status='ok' if ok else 'mismatch'))
            except kernel.ClaimError:
                edges.append(dict(link,status='unresolved'))
        nodes.append(dict(row,depends_on=edges))
    return {'claims':nodes}

def sign_root(directory, ws=None, _seen=None):
    seen=_seen if _seen is not None else set()
    root=kernel.verify(directory)['root']
    if root in seen: raise kernel.ClaimError('component cycle')
    seen.add(root)
    children=[]
    for link in _links(directory):
        child=_resolve(link['root'],directory,ws)
        children.append(sign_root(child,ws,seen))
    seen.remove(root)
    return kernel.sign_node(root,kernel.build_digest(directory),children)

def _closure(directory, ws=None):
    result={}; visiting=set()
    def visit(path):
        root=kernel.read_manifest(path)['root']
        if root in result: return
        if root in visiting: raise kernel.ClaimError('component cycle')
        visiting.add(root)
        for link in _links(path): visit(_resolve(link['root'],path,ws))
        visiting.remove(root)
        result[root]=path
    visit(directory)
    return result

def _copy_claim(source,target, *, generated=True):
    from ._kernel import build
    parsed=kernel.load_recipe(source)
    build._materialize(source,target,parsed,generated=generated)
    for step in parsed.get('step',[]):
        if step.get('class','generated' if step['kind']=='produce' else 'pinned')!='generated':
            name=step['output']; src=safe_path(source,name)
            if os.path.isfile(src): copy_into(src,safe_path(target,name))
        elif generated and 'from' in step:
            name=step['output']; src=safe_path(source,name)
            if os.path.isfile(src): copy_into(src,safe_path(target,name))
    copy_into(os.path.join(source,kernel.MANIFEST),os.path.join(target,kernel.MANIFEST))

def _stage_closure(source,target,ws=None):
    closure=_closure(source,ws)
    own=kernel.read_manifest(source)['root']
    for root,path in closure.items():
        if root==own: continue
        name=kernel.read_manifest(path)['name']
        dest=os.path.join(target,'.reticuli','sealed',name)
        if not os.path.exists(dest): _copy_claim(path,dest)
    return closure

def pull(source,ws):
    dest=os.path.join(_store(ws),kernel.read_manifest(source)['name'])
    if os.path.exists(dest): shutil.rmtree(dest)
    _copy_claim(source,dest)
    _stage_closure(source,ws,_workspace(source))
    for name in recipes._inputs(kernel.load_recipe(source),source):
        copy_into(safe_path(source,name),safe_path(ws,name))
    for step in kernel.load_recipe(source).get('step',[]):
        src=safe_path(source,step['output'])
        if os.path.isfile(src): copy_into(src,safe_path(ws,step['output']))
    return {'materialized':True,'root':kernel.read_manifest(source)['root'],'path':dest}

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    links=_links(directory)
    closure=_closure(directory,ws)
    rebuilt=[]; produce_from={}
    for root,path in closure.items():
        if path==directory: continue
        rebuilt.append({'component':kernel.read_manifest(path)['name'],'root':root})
    if reuse:
        for link in links:
            for step in kernel.load_recipe(directory).get('step',[]):
                if step.get('from')==link['component'] and step['output']==link['input']:
                    produce_from[step['output']]=safe_path(_resolve(link['root'],directory,ws),link['output'])
    else:
        # A from output is outside the local producer list; materialize it for gates.
        for link in links:
            if any(s.get('from')==link['component'] and s['output']==link['input'] for s in kernel.load_recipe(directory).get('step',[])):
                produce_from[link['input']]=safe_path(directory,link['input'])
    result=kernel.rebuild(directory,producer,into,produce_from=produce_from or None)
    if links:
        manifest=kernel.read_manifest(into); manifest['components']=links
        write_json(os.path.join(into,kernel.MANIFEST),manifest)
        _stage_closure(directory,into,ws)
    result['rebuilt_components']=rebuilt
    return result

def _audit_local(path, shipped):
    parsed=kernel.load_recipe(path)
    mapping={s['output']:safe_path(shipped,s['output']) for s in parsed.get('step',[])
             if s.get('from') and os.path.isfile(os.path.join(shipped,s['output']))}
    return kernel.audit(path,produce_from=mapping or None)

def audit_deep(directory, ws=None):
    own=_audit_local(directory,directory)
    layers=[]; visited=set()
    # Component checks run with the dependent's shipped source bytes, including
    # transitive outputs. A flat shared store resolves every ancestor by root.
    def visit(path, parent):
        for link in _links(path):
            root=link['root']
            if root in visited: continue
            visited.add(root)
            try:
                comp=_resolve(root,directory,ws)
            except kernel.ClaimError:
                layers.append({'name':link['component'],'root':root,'ok':False,'status':'unresolved','bytes_from':[]})
                continue
            links_for_root=[x for x in _links(path) if x['root']==root]
            mapping={}
            bad=False
            for edge in links_for_root:
                src=safe_path(directory,edge['input']) if os.path.isfile(os.path.join(directory,edge['input'])) else safe_path(parent,edge['input'])
                output=edge['output']
                parsed=kernel.load_recipe(comp)
                produced=any(s['output']==output and s['kind']=='produce' for s in parsed.get('step',[]))
                if produced:
                    mapping[output]=src
                else:
                    try: bad |= kernel._hash_file(src)!=kernel._hash_file(safe_path(comp,output))
                    except kernel.ClaimError: bad=True
            if bad:
                layers.append({'name':link['component'],'root':root,'ok':False,'status':'attribution mismatch','bytes_from':sorted(mapping)})
            else:
                judged=kernel.audit(comp,produce_from=mapping or None)
                layers.append({'name':link['component'],'root':root,'ok':judged['ok'],'status':'ok' if judged['ok'] else 'failed','bytes_from':sorted(mapping)})
            visit(comp,parent)
    visit(directory,directory)
    return {'ok':own['ok'] and all(x['ok'] for x in layers),'root':own['root'],'layers':layers,'audit':own}

def crosscheck_deep(m1,m2,m3):
    out=kernel.crosscheck(m1,m2,m3)
    deep={k:audit_deep(p)['ok'] for k,p in zip(('M1','M2','M3'),(m1,m2,m3))}
    out['deep']=deep
    if not all(deep.values()): out['satisfied']=False; out['verdict']='reject'
    return out

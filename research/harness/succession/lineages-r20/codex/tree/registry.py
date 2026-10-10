"""Content addressed component registry and composed verdicts."""
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, safe_path, write_json
from ._kernel import recipe as kr

def _store(directory):
    return os.path.join(directory, '.reticuli', 'sealed')

def _candidates(directory, ws=None):
    roots = [directory]
    if ws: roots.append(ws)
    parent = os.path.abspath(directory)
    for _ in range(4):
        parent = os.path.dirname(parent)
        roots.append(parent)
    seen = set()
    for base in roots:
        for folder in (_store(base), os.path.join(base, '.reticuli', 'deps')):
            if not os.path.isdir(folder): continue
            for name in sorted(os.listdir(folder)):
                path = os.path.join(folder, name)
                real = os.path.realpath(path)
                if real not in seen and os.path.isdir(path):
                    seen.add(real)
                    yield path

def _resolve(directory, link, ws=None):
    for path in _candidates(directory, ws):
        try:
            manifest = kernel.read_manifest(path)
            if manifest['root'] == link['root'] and manifest['name'] == link['component']:
                return path
        except (kernel.ClaimError, OSError): pass
    return None

def _links(directory):
    links = kernel.read_manifest(directory).get('components', [])
    if links: return links
    # A plain kernel reseal replaces the manifest. Recover locally staged
    # data dependencies by their declared names so their content is re-earned.
    parsed = kernel.load_recipe(directory)
    recovered = []
    for name in declared_inputs(parsed, directory):
        for component in _candidates(directory):
            try:
                manifest = kernel.read_manifest(component)
                if any(s['output'] == name for s in kernel.load_recipe(component).get('step', [])):
                    recovered.append({'input': name, 'output': name,
                                      'component': manifest['name'], 'root': manifest['root']})
            except kernel.ClaimError: pass
    return recovered

def seal_with(directory, *, components=None, proof=None):
    old = None
    try: old = kernel.read_manifest(directory)
    except kernel.ClaimError: pass
    manifest = kernel.seal(directory)
    if components is None and old: components = old.get('components')
    if proof is None and old: proof = old.get('proof')
    if components is not None: manifest['components'] = components
    if proof is not None: manifest['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest

def detect_components(ws, inputs):
    links = []
    for name in inputs:
        source = safe_path(ws, name)
        if not os.path.isfile(source): continue
        digest = kernel._hash_file(source)
        for component in _candidates(ws):
            try:
                manifest = kernel.read_manifest(component)
                parsed = kernel.load_recipe(component)
                for step in parsed.get('step', []):
                    out = step['output']
                    path = safe_path(component, out)
                    if os.path.isfile(path) and kernel._hash_file(path) == digest:
                        links.append({'input': name, 'component': manifest['name'],
                                      'root': manifest['root'], 'output': out})
                        break
            except kernel.ClaimError: pass
    return links

def claims(ws):
    rows = []
    for path in _candidates(ws):
        if os.path.dirname(path) != _store(ws): continue
        try:
            manifest = kernel.read_manifest(path)
            rows.append({'name': manifest['name'], 'root': manifest['root'],
                         'phase': kernel.phase(path)})
        except kernel.ClaimError: pass
    return rows

def deps(ws):
    rows = []
    for path in _candidates(ws):
        if os.path.dirname(path) != _store(ws): continue
        manifest = kernel.read_manifest(path)
        links = []
        for link in manifest.get('components', []):
            found = _resolve(path, link, ws)
            links.append(dict(link, status='ok' if found else 'unresolved'))
        rows.append({'name': manifest['name'], 'root': manifest['root'],
                     'phase': kernel.phase(path), 'depends_on': links})
    return {'claims': rows}

def _closure(directory, ws=None):
    seen = set()
    def visit(path):
        for link in _links(path):
            key = (link['component'], link['root'])
            if key in seen: continue
            found = _resolve(path, link, ws or directory)
            if not found: raise kernel.ClaimError('missing declared component: ' + link['component'])
            seen.add(key)
            yield from visit(found)
            yield found
    yield from visit(directory)

def _stage(source, target, ws=None):
    store = _store(target)
    os.makedirs(store, exist_ok=True)
    for component in _closure(source, ws):
        name = kernel.read_manifest(component)['name']
        dest = os.path.join(store, name)
        if not os.path.exists(dest):
            shutil.copytree(component, dest, symlinks=False, ignore=shutil.ignore_patterns('sealed'))

def pull(source, ws):
    parsed = kernel.load_recipe(source)
    name = parsed['claim']['name']
    dest = os.path.join(_store(ws), name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest): shutil.rmtree(dest)
    shutil.copytree(source, dest, symlinks=False, ignore=shutil.ignore_patterns('sealed'))
    _stage(source, dest)
    for item in [os.path.basename(kr.recipe_path(source)), *declared_inputs(parsed, source),
                 *[s['output'] for s in parsed.get('step', [])]]:
        path = safe_path(dest, item)
        if os.path.isfile(path): copy_into(path, safe_path(ws, item))
    return {'materialized': True, 'root': kernel.read_manifest(dest)['root'], 'name': name}

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    comps = kernel.read_manifest(directory).get('components', [])
    rebuilt = []
    # The source claim's component output is already the byte-for-byte reuse
    # input for a `from` step; the kernel copies it into the room.
    if not reuse:
        for component in _closure(directory, ws):
            rebuilt.append({'component': kernel.read_manifest(component)['name'],
                            'root': kernel.read_manifest(component)['root']})
    result = kernel.rebuild(directory, producer, into)
    seal_with(into, components=comps)
    _stage(directory, into, ws)
    result['rebuilt_components'] = rebuilt
    return result

def sign_root(directory, ws=None):
    memo = {}
    def fold(path):
        manifest = kernel.read_manifest(path)
        if manifest['root'] in memo: return memo[manifest['root']]
        if not kernel.verify(path)['ok']: raise kernel.ClaimError('component identity mismatch')
        links = []
        for link in manifest.get('components', []):
            found = _resolve(path, link, ws)
            if not found: raise kernel.ClaimError('missing declared component: ' + link['component'])
            node = fold(found)
            if node not in links: links.append(node)
        value = kernel.sign_node(manifest['root'], kernel.build_digest(path), links)
        memo[manifest['root']] = value
        return value
    return fold(directory)

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers, visited = [], set()
    def walk(path, supplied):
        for link in _links(path):
            key = (link['component'], link['root'])
            if key in visited: continue
            found = _resolve(path, link, ws or directory)
            if not found:
                layers.append({'name': link['component'], 'root': link['root'],
                               'ok': False, 'status': 'unresolved', 'bytes_from': []})
                visited.add(key)
                continue
            parsed = kernel.load_recipe(path)
            code = any(s.get('from') == link['component'] and s['output'] == link['input']
                       for s in parsed.get('step', []))
            source = supplied.get(link['input'], safe_path(path, link['input']))
            component_out = safe_path(found, link['output'])
            attribution = True
            if not code:
                attribution = os.path.isfile(source) and os.path.isfile(component_out) and kernel._hash_file(source) == kernel._hash_file(component_out)
            mappings = {link['output']: source} if code else {}
            # Collect all outputs attributed to the same component before judging.
            for other in kernel.read_manifest(path).get('components', []):
                if other['root'] == link['root'] and other['component'] == link['component']:
                    if any(s.get('from') == other['component'] and s['output'] == other['input'] for s in parsed.get('step', [])):
                        mappings[other['output']] = supplied.get(other['input'], safe_path(path, other['input']))
            visited.add(key)
            try:
                check = kernel.audit(found, produce_from=mappings or None)
                row = {'name': link['component'], 'root': link['root'], 'ok': check['ok'] and attribution,
                       'status': 'ok' if check['ok'] and attribution else ('attribution mismatch' if not attribution else 'failed'),
                       'bytes_from': sorted(mappings)}
            except kernel.ClaimError:
                row = {'name': link['component'], 'root': link['root'], 'ok': False,
                       'status': 'failed', 'bytes_from': sorted(mappings)}
            layers.append(row)
            walk(found, {**supplied, **mappings})
    walk(directory, {})
    return {'ok': own['ok'] and all(r['ok'] for r in layers), 'root': own.get('root'),
            'gates': own.get('gates', []), 'layers': layers}

def crosscheck_deep(m1, m2, m3, **kwargs):
    result = kernel.crosscheck(m1, m2, m3, **kwargs)
    deep = {role: audit_deep(path) for role, path in zip(('M1','M2','M3'), (m1,m2,m3))}
    if not all(x['ok'] for x in deep.values()):
        result['satisfied'] = False
        result['verdict'] = 'reject'
        result['rejected'].append('deep audit')
    result['deep'] = deep
    return result

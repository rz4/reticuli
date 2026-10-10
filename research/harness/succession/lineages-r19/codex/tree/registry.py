"""Stored claims, content links, and composed auditing."""
import os
import shutil
import tempfile
from . import kernel, _util

SEALED = '.reticuli/sealed'
DEPS = '.reticuli/deps'

def _store_dirs(root):
    seen = set()
    for base in (root, os.path.dirname(root), os.path.dirname(os.path.dirname(os.path.dirname(root)))):
        for folder in (os.path.join(base, SEALED), os.path.join(base, DEPS)):
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    path = os.path.join(folder, name)
                    if os.path.isdir(path) and os.path.realpath(path) not in seen:
                        seen.add(os.path.realpath(path)); yield path

def _find(root, link, ws=None):
    candidates = list(_store_dirs(root))
    if ws: candidates += list(_store_dirs(ws))
    for path in candidates:
        try:
            m = kernel.read_manifest(path)
            if m['root'] == link['root'] and m['name'] == link['component']: return path
        except kernel.ClaimError: pass
    return None

def _links(directory):
    links = kernel.read_manifest(directory).get('components')
    if links is not None: return links
    path = os.path.join(directory, '.reticuli', 'components.json')
    return _util.read_json(path) if os.path.isfile(path) else []

def seal_with(directory, *, components=None, proof=None):
    old = None
    try: old = kernel.read_manifest(directory)
    except kernel.ClaimError: pass
    manifest = kernel.seal(directory)
    if components is None and old: components = old.get('components')
    if components:
        manifest['components'] = components
        _util.write_json(os.path.join(directory, '.reticuli', 'components.json'), components)
    if proof: manifest['proof'] = proof
    _util.write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest

def claims(ws):
    rows = []
    folder = os.path.join(ws, SEALED)
    if not os.path.isdir(folder): return rows
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isdir(path): continue
        try:
            m = kernel.read_manifest(path)
            rows.append({'name': m['name'], 'root': m['root'], 'path': path, 'phase': kernel.phase(path)})
        except kernel.ClaimError: pass
    return rows

def detect_components(ws, inputs):
    links = []
    for name in inputs:
        source = _util.safe_path(ws, name)
        if not os.path.isfile(source): continue
        digest = kernel._hash_file(source)
        for row in claims(ws):
            path = row['path']; parsed = kernel.load_recipe(path)
            for step in parsed.get('step', []):
                output = step['output']; target = os.path.join(path, output)
                if os.path.isfile(target) and kernel._hash_file(target) == digest:
                    links.append({'input': name, 'component': row['name'], 'root': row['root'], 'output': output})
    return links

def deps(ws):
    rows = []
    for row in claims(ws):
        edges = []
        for link in _links(row['path']):
            edge = dict(link); edge['status'] = 'ok' if _find(row['path'], link, ws) else 'unresolved'; edges.append(edge)
        rows.append(dict(row, depends_on=edges))
    return {'claims': rows}

def sign_root(directory, ws=None, _seen=None):
    _seen = set() if _seen is None else _seen
    root = kernel.verify(directory)['root']
    if root in _seen: raise kernel.ClaimError('component cycle')
    _seen.add(root)
    nodes = []
    for link in _links(directory):
        child = _find(directory, link, ws)
        if child is None: raise kernel.ClaimError('unresolved component: ' + link['component'])
        node = sign_root(child, ws, _seen)
        if node not in nodes: nodes.append(node)
    _seen.remove(root)
    return kernel.sign_node(root, kernel.build_digest(directory), nodes)

def _closure(source, ws=None):
    found = {}; visiting = set()
    def visit(path):
        root = kernel.read_manifest(path)['root']
        if root in found: return
        if root in visiting: raise kernel.ClaimError('component cycle')
        visiting.add(root)
        for link in _links(path):
            child = _find(source, link, ws) or _find(path, link, ws)
            if child is None: raise kernel.ClaimError('unresolved component: ' + link['component'])
            visit(child)
        visiting.remove(root); found[root] = path
    visit(source)
    found.pop(kernel.read_manifest(source)['root'], None)
    return found

def _copy_claim(source, target):
    from . import transfer
    transfer._copy_declared(source, target, blind=False, dependencies=False)

def pull(source, ws):
    parsed = kernel.load_recipe(source); name = parsed['claim']['name']
    target = os.path.join(ws, SEALED, name)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if not os.path.exists(target): _copy_claim(source, target)
    for path in _closure(source).values():
        dep = os.path.join(target, SEALED, kernel.read_manifest(path)['name'])
        if not os.path.exists(dep): _copy_claim(path, dep)
    for item in _util.declared_inputs(parsed, source) + [s['output'] for s in parsed.get('step', [])]:
        src = os.path.join(source, item)
        if os.path.isfile(src): _util.copy_into(src, os.path.join(ws, item))
    return {'materialized': True, 'path': target, 'root': kernel.read_manifest(source)['root']}

def rebuild_chain(source, producer, into, *, ws=None, reuse=False):
    closure = _closure(source, ws)
    rebuilt = []
    available = {}
    if reuse:
        available = closure
    else:
        for root, path in closure.items():
            with tempfile.TemporaryDirectory(prefix='reticuli-component-') as temp:
                # A component can rebuild from its sealed source; the top claim receives its products.
                result = kernel.rebuild(path, producer, temp)
                if not result['ok']: raise kernel.ClaimError('component rebuild failed')
                keep = tempfile.mkdtemp(prefix='reticuli-rebuilt-')
                shutil.copytree(temp, keep, dirs_exist_ok=True)
                available[root] = keep
                rebuilt.append({'component': kernel.read_manifest(path)['name'], 'root': root})
    parsed = kernel.load_recipe(source)
    produce_from = {}
    for link in _links(source):
        if any(s.get('from') == link['component'] and s['output'] == link['input'] for s in parsed.get('step', [])):
            child = available.get(link['root']) or closure.get(link['root'])
            if child: produce_from[link['input']] = os.path.join(child, link['output'])
    result = kernel.rebuild(source, producer, into, produce_from=produce_from or None)
    if not result['ok']: raise kernel.ClaimError('chain rebuild failed')
    seal_with(into, components=_links(source))
    # Flat staging provides one copy per dependency.
    for root, path in closure.items():
        dep = os.path.join(into, SEALED, kernel.read_manifest(path)['name'])
        if not os.path.exists(dep): _copy_claim(path, dep)
    result['rebuilt_components'] = rebuilt
    return result

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers = []; seen = set()
    def visit(path):
        for root in dict.fromkeys(link['root'] for link in _links(path)):
            links = [link for link in _links(path) if link['root'] == root]
            if root in seen: continue
            seen.add(root)
            link = links[0]; child = _find(directory, link, ws) or _find(path, link, ws)
            row = {'name': link['component'], 'root': root, 'bytes_from': [x['input'] for x in links], 'ok': False}
            if child is None:
                row['status'] = 'unresolved'; layers.append(row); continue
            try:
                with tempfile.TemporaryDirectory(prefix='reticuli-deep-') as temp:
                    _copy_claim(child, temp)
                    cparsed = kernel.load_recipe(child)
                    parent_parsed = kernel.load_recipe(path)
                    code_inputs = {s['output'] for s in parent_parsed.get('step', []) if s.get('kind') == 'produce' and s.get('from') == link['component']}
                    bad = False
                    for edge in links:
                        src = os.path.join(directory, edge['input'])
                        if edge['input'] in code_inputs:
                            if not os.path.isfile(src): bad = True; continue
                            _util.copy_into(src, os.path.join(temp, edge['output']))
                        else:
                            if not os.path.isfile(src) or not os.path.isfile(os.path.join(child, edge['output'])) or kernel._hash_file(src) != kernel._hash_file(os.path.join(child, edge['output'])): bad = True
                    if bad: row['status'] = 'attribution mismatch'
                    else:
                        result = kernel.audit(temp)
                        row['ok'] = result['ok']; row['status'] = 'ok' if result['ok'] else 'broken'
                    layers.append(row)
            except kernel.ClaimError:
                row['status'] = 'broken'; layers.append(row)
            visit(child)
    visit(directory)
    return {'ok': own['ok'] and all(r['ok'] for r in layers), 'root': own.get('root'), 'gates': own.get('gates', []), 'layers': layers}

def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    deep = [audit_deep(p) for p in (m1, m2, m3)]
    result['deep'] = deep
    result['satisfied'] = result['satisfied'] and all(r['ok'] for r in deep)
    return result

def record_proof_deep(m1, m2, m3):
    result = crosscheck_deep(m1, m2, m3)
    if result['satisfied']: return kernel.record_proof(m1, m2, m3)
    return {'proof_recorded': False, 'crosscheck': result}

def structure(directory, ws=None): return {'root': kernel.verify(directory)['root'], 'layers': audit_deep(directory, ws)['layers']}

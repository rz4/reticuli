"""Local claim registry and composition of sealed claims."""
import hashlib
import os
import shutil
import tempfile

from . import kernel
from ._util import declared_inputs, safe_path, copy_into, write_json, read_json

SEALED = '.reticuli/sealed'
DEPS = '.reticuli/deps'

def _manifest(directory):
    manifest = kernel.read_manifest(directory)
    sidecar = os.path.join(directory, '.reticuli', 'components.json')
    if 'components' not in manifest and os.path.isfile(sidecar):
        manifest['components'] = read_json(sidecar)
    return manifest

def _files(directory, generated=True):
    parsed = kernel.load_recipe(directory)
    recipe_name = 'reticuli.toml' if os.path.isfile(os.path.join(directory, 'reticuli.toml')) else 'claim.toml'
    names = [recipe_name] + declared_inputs(parsed, directory)
    for step in parsed.get('step', []):
        if generated or step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned') not in ('generated', 'free'):
            names.append(step['output'])
    return list(dict.fromkeys(n for n in names if os.path.isfile(os.path.join(directory, n))))

def _copy_claim(source, target, generated=True):
    os.makedirs(target, exist_ok=True)
    for name in _files(source, generated):
        copy_into(safe_path(source, name), safe_path(target, name))
    if os.path.isfile(os.path.join(source, kernel.MANIFEST)):
        copy_into(os.path.join(source, kernel.MANIFEST), os.path.join(target, kernel.MANIFEST))

def _stores(directory, ws=None):
    roots = [directory]
    if ws:
        roots.append(ws)
    current = os.path.realpath(directory)
    for _ in range(4):
        roots.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    result = []
    for root in roots:
        for folder in (SEALED, DEPS):
            store = os.path.join(root, folder)
            if os.path.isdir(store):
                result.extend(os.path.join(store, n) for n in sorted(os.listdir(store)))
    return list(dict.fromkeys(result))

def _resolve(directory, link, ws=None):
    for candidate in _stores(directory, ws):
        try:
            if _manifest(candidate)['root'] == link['root']:
                return candidate
        except (OSError, kernel.ClaimError):
            continue
    return None

def seal_with(directory, *, components=None, proof=None):
    old = {}
    try:
        old = _manifest(directory)
    except kernel.ClaimError:
        pass
    result = kernel.seal(directory)
    if components is None:
        components = old.get('components')
    if proof is None:
        proof = old.get('proof')
    if components:
        result['components'] = components
        write_json(os.path.join(directory, '.reticuli', 'components.json'), components)
    if proof:
        result['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), result)
    return result

def claims(ws):
    store = os.path.join(ws, SEALED)
    rows = []
    if os.path.isdir(store):
        for name in sorted(os.listdir(store)):
            path = os.path.join(store, name)
            try:
                manifest = _manifest(path)
                rows.append({'name': manifest['name'], 'root': manifest['root'],
                             'path': path, 'phase': kernel.phase(path)})
            except (kernel.ClaimError, OSError):
                continue
    return rows

def detect_components(ws, inputs):
    links = []
    for row in claims(ws):
        source = row['path']
        parsed = kernel.load_recipe(source)
        for step in parsed.get('step', []):
            output = step['output']
            path = os.path.join(source, output)
            if not os.path.isfile(path):
                continue
            digest = _sha(path)
            for name in inputs:
                ipath = os.path.join(ws, name)
                if os.path.isfile(ipath) and _sha(ipath) == digest:
                    links.append({'input': name, 'component': row['name'], 'root': row['root'], 'output': output})
    return links

def _sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()

def deps(ws):
    rows = []
    for row in claims(ws):
        manifest = _manifest(row['path'])
        edges = []
        for link in manifest.get('components', []):
            found = _resolve(row['path'], link, ws)
            edges.append(dict(link, status='ok' if found else 'unresolved'))
        rows.append(dict(row, depends_on=edges))
    return {'claims': rows}

def _closure(source, ws=None):
    found = {}
    def visit(path):
        for link in _manifest(path).get('components', []):
            root = link['root']
            if root in found:
                continue
            comp = _resolve(source, link, ws) or _resolve(path, link, ws)
            if comp is None:
                raise kernel.ClaimError('missing declared component: ' + link['component'])
            found[root] = comp
            visit(comp)
    visit(source)
    return found

def _stage_closure(source, target, ws=None, generated=True):
    for path in _closure(source, ws).values():
        name = _manifest(path)['name']
        _copy_claim(path, os.path.join(target, SEALED, name), generated=generated)

def pull(source, ws):
    name = _manifest(source)['name']
    target = os.path.join(ws, SEALED, name)
    _copy_claim(source, target)
    _stage_closure(source, target, generated=True)
    _stage_closure(source, ws, generated=True)
    for filename in _files(source):
        copy_into(os.path.join(source, filename), os.path.join(ws, filename))
    return {'materialized': True, 'root': _manifest(source)['root'], 'path': target}

def sign_root(directory, ws=None):
    visited = set()
    def fold(path):
        manifest = _manifest(path)
        if manifest['root'] in visited:
            raise kernel.ClaimError('component cycle')
        visited.add(manifest['root'])
        children = []
        for link in manifest.get('components', []):
            comp = _resolve(directory, link, ws) or _resolve(path, link, ws)
            if not comp:
                raise kernel.ClaimError('missing declared component: ' + link['component'])
            children.append(fold(comp))
        visited.remove(manifest['root'])
        return kernel.sign_node(kernel.verify(path)['root'], kernel.build_digest(path), children)
    return fold(directory)

def rebuild_chain(source, producer, into, *, ws=None, reuse=False):
    links = _manifest(source).get('components', [])
    # The kernel copies outputs declared as `from` from the sealed source.
    result = kernel.rebuild(source, producer, into)
    if links:
        seal_with(into, components=links)
        _stage_closure(source, into, ws, generated=True)
    result['rebuilt_components'] = [dict(component=_manifest(p)['name'], root=root)
                                    for root, p in _closure(source, ws).items()]
    return result

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    rows = []
    seen = set()
    top = directory
    def visit(path, manifest):
        for link in manifest.get('components', []):
            root = link['root']
            if root in seen:
                continue
            seen.add(root)
            source = _resolve(top, link, ws) or _resolve(path, link, ws)
            row = {'name': link['component'], 'root': root, 'bytes_from': [], 'ok': False}
            if source is None:
                row['status'] = 'unresolved'
                rows.append(row)
                continue
            parsed = kernel.load_recipe(source)
            produced = {s['output'] for s in parsed.get('step', []) if s['kind'] == 'produce'}
            with tempfile.TemporaryDirectory(prefix='reticuli-component-') as room:
                _copy_claim(source, room)
                for candidate in parsed.get('step', []):
                    name = candidate['output']
                    if name in produced and os.path.isfile(os.path.join(top, name)):
                        copy_into(os.path.join(top, name), os.path.join(room, name))
                        row['bytes_from'].append(name)
                # A data attribution must match the stored component output.
                parent_file = os.path.join(top, link['input'])
                source_file = os.path.join(source, link['output'])
                if link['input'] not in produced and os.path.isfile(parent_file) and os.path.isfile(source_file) and _sha(parent_file) != _sha(source_file):
                    row['status'] = 'attribution mismatch'
                else:
                    check = kernel.audit(room)
                    row['ok'] = check['ok']
                    row['status'] = 'ok' if check['ok'] else 'broken'
            rows.append(row)
            visit(source, _manifest(source))
    visit(directory, _manifest(directory))
    return {'ok': own['ok'] and all(row['ok'] for row in rows), 'root': own.get('root'),
            'gates': own.get('gates', []), 'layers': rows}

def crosscheck_deep(m1, m2, m3, *, mutants=None):
    result = kernel.crosscheck(m1, m2, m3, mutants=mutants)
    deep = [audit_deep(path) for path in (m1, m2, m3)]
    result['deep'] = deep
    if not all(row['ok'] for row in deep):
        result['satisfied'] = False
        result['verdict'] = 'reject'
        result.setdefault('rejected', []).append('composed audit')
    return result

def record_proof_deep(m1, m2, m3, *, mutants=None):
    result = crosscheck_deep(m1, m2, m3, mutants=mutants)
    if result['satisfied']:
        kernel.record_proof(m1, m2, m3, mutants=mutants)
    return result

def structure(directory, ws=None):
    return {'name': _manifest(directory)['name'], 'root': _manifest(directory)['root'],
            'phase': kernel.phase(directory), 'components': _manifest(directory).get('components', [])}

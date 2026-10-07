"""Content-addressed component links and composed claim operations."""
import os
import shutil
import tempfile

from . import kernel
from ._kernel import core, recipe

def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')

def _component_path(directory, name, ws=None):
    candidates = [os.path.join(directory, '.reticuli', 'sealed', name),
                  os.path.join(directory, '.reticuli', 'deps', name)]
    if ws:
        candidates.append(os.path.join(_store(ws), name))
    for path in candidates:
        if os.path.isdir(path):
            return path
    raise kernel.ClaimError('missing declared component: ' + name)

def seal_with(directory, *, components=None, proof=None):
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    core._write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest

def detect_components(ws, inputs):
    links = []
    for name in inputs:
        wanted = kernel._hash_file(core._safe(ws, name))
        if not os.path.isdir(_store(ws)):
            continue
        for component in sorted(os.listdir(_store(ws))):
            path = os.path.join(_store(ws), component)
            try:
                manifest = kernel.read_manifest(path)
                parsed = kernel.load_recipe(path)
                for step in parsed.get('step', []):
                    output = step['output']
                    try:
                        matching = kernel._hash_file(core._safe(path, output)) == wanted
                    except kernel.ClaimError:
                        matching = False
                    if matching:
                        links.append({'input': name, 'component': component,
                                      'root': manifest['root'], 'output': output})
            except kernel.ClaimError:
                continue
    return links

def claims(ws):
    result = []
    if os.path.isdir(_store(ws)):
        for name in sorted(os.listdir(_store(ws))):
            path = os.path.join(_store(ws), name)
            if os.path.isdir(path):
                try:
                    manifest = kernel.read_manifest(path)
                    result.append({'name': manifest['name'], 'root': manifest['root'],
                                   'phase': kernel.phase(path), 'path': path})
                except kernel.ClaimError:
                    pass
    return result

def deps(ws):
    result = []
    for row in claims(ws):
        manifest = kernel.read_manifest(row['path'])
        edges = []
        for link in manifest.get('components', []):
            try:
                component = _component_path(row['path'], link['component'], ws)
                status = 'ok' if kernel.read_manifest(component)['root'] == link['root'] else 'mismatch'
            except kernel.ClaimError:
                status = 'missing'
            edges.append(dict(link, status=status))
        result.append(dict(row, depends_on=edges))
    return {'claims': result}

def pull(directory, ws):
    parsed = kernel.load_recipe(directory)
    names = [os.path.basename(recipe.recipe_path(directory))]
    names += recipe._inputs(parsed, directory)
    names += [step['output'] for step in parsed.get('step', [])]
    for name in dict.fromkeys(names):
        source = core._safe(directory, name)
        if os.path.isfile(source):
            core._copy_into(source, core._safe(ws, name))
    return {'materialized': True, 'root': kernel.verify(directory)['root']}

def _links(directory):
    return kernel.read_manifest(directory).get('components', [])

def sign_root(directory, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    real = os.path.realpath(directory)
    if real in seen:
        raise kernel.ClaimError('component cycle')
    seen.add(real)
    links = []
    for name in sorted({link['component'] for link in _links(directory)}):
        sub = _component_path(directory, name, ws)
        declared = next(link['root'] for link in _links(directory) if link['component'] == name)
        if kernel.read_manifest(sub)['root'] != declared:
            raise kernel.ClaimError('component root mismatch: ' + name)
        links.append(sign_root(sub, ws, seen))
    seen.remove(real)
    return kernel.sign_node(kernel.verify(directory)['root'], kernel.build_digest(directory), links)

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    links = _links(directory)
    component_dirs = {}
    rebuilt = []
    with tempfile.TemporaryDirectory(prefix='reticuli-components-') as temporary:
        for name in sorted({link['component'] for link in links}):
            source = _component_path(directory, name, ws)
            if reuse:
                component_dirs[name] = source
            else:
                target = os.path.join(temporary, name)
                rebuild_chain(source, producer, target, ws=ws, reuse=False)
                component_dirs[name] = target
            rebuilt.append({'component': name, 'root': kernel.read_manifest(source)['root']})
        from_map = {}
        for link in links:
            parsed = kernel.load_recipe(directory)
            if any(s.get('output') == link['input'] and s.get('from') == link['component']
                   for s in parsed.get('step', [])):
                from_map[link['input']] = core._safe(component_dirs[link['component']], link['output'])
        result = kernel.rebuild(directory, producer, into, produce_from=from_map)
        manifest = kernel.read_manifest(into)
        manifest['components'] = links
        core._write_json(os.path.join(into, kernel.MANIFEST), manifest)
        for name, source in component_dirs.items():
            shutil.copytree(source, os.path.join(_store(into), name), dirs_exist_ok=True)
    result['rebuilt_components'] = rebuilt
    return result

def _audit_component(source, shipped, overrides):
    with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
        shutil.copytree(source, room, dirs_exist_ok=True)
        parsed = kernel.load_recipe(source)
        for step in recipe.produces(parsed):
            name = step['output']
            if name in overrides:
                core._copy_into(overrides[name], core._safe(room, name))
        return kernel.audit(room)

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers = []
    visited = set()
    def walk(parent, supplied):
        for name in sorted({link['component'] for link in _links(parent)}):
            links = [x for x in _links(parent) if x['component'] == name]
            try:
                source = _component_path(parent, name, ws)
                overrides = dict(supplied)
                for link in links:
                    overrides[link['output']] = core._safe(directory, link['input'])
                key = (name, os.path.realpath(source))
                if key in visited:
                    continue
                visited.add(key)
                audit = _audit_component(source, directory, overrides)
                row = {'name': name, 'root': kernel.read_manifest(source)['root'],
                       'ok': audit['ok'], 'status': 'ok' if audit['ok'] else 'failed',
                       'bytes_from': [x['input'] for x in links]}
                layers.append(row)
                walk(source, overrides)
            except (kernel.ClaimError, OSError) as exc:
                layers.append({'name': name, 'ok': False, 'status': 'unresolved',
                               'detail': str(exc), 'bytes_from': [x['input'] for x in links]})
    walk(directory, {})
    return {'ok': own['ok'] and all(x['ok'] for x in layers), 'root': own.get('root'),
            'gates': own.get('gates', []), 'layers': layers}

def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    audits = {key: audit_deep(path) for key, path in zip(('M1','M2','M3'), (m1,m2,m3))}
    result['deep_audits'] = audits
    if not all(row['ok'] for row in audits.values()):
        result['satisfied'] = False
        result['verdict'] = 'reject'
    return result

def structure(directory, ws=None):
    return {'root': kernel.verify(directory)['root'], 'phase': kernel.phase(directory),
            'components': _links(directory)}

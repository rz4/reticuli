"""Claim stores, component links, and composed verification."""
import json
import os
import shutil
import tempfile

from . import kernel
from ._util import safe_path, copy_into, declared_inputs, write_json


def _workspace(directory):
    directory = os.path.abspath(directory)
    while True:
        if os.path.basename(os.path.dirname(os.path.dirname(directory))) == '.reticuli':
            return os.path.dirname(os.path.dirname(os.path.dirname(directory)))
        parent = os.path.dirname(directory)
        if parent == directory:
            return directory
        directory = parent


def _stored(ws):
    base = os.path.join(ws, '.reticuli', 'sealed')
    if not os.path.isdir(base):
        return []
    return [os.path.join(base, n) for n in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, n))]


def _resolve(directory, name, ws=None):
    paths = [os.path.join(directory, '.reticuli', 'sealed', name),
             os.path.join(directory, '.reticuli', 'deps', name)]
    if ws:
        paths.append(os.path.join(ws, '.reticuli', 'sealed', name))
    for path in paths:
        if os.path.isfile(os.path.join(path, kernel.MANIFEST)):
            return path
    raise kernel.ClaimError(f'missing component {name}')


def detect_components(ws, inputs):
    result = []
    for name in inputs:
        target = safe_path(ws, name)
        if not os.path.isfile(target):
            continue
        digest = kernel._hash_file(target)
        for component in _stored(ws):
            recipe = kernel.load_recipe(component)
            for step in recipe.get('step', []):
                output = step['output']
                path = safe_path(component, output)
                if os.path.isfile(path) and kernel._hash_file(path) == digest:
                    result.append({'input': name, 'component': recipe['claim']['name'],
                                   'root': kernel.verify(component)['root'], 'output': output})
    return result


def seal_with(directory, *, components=None, proof=None):
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest


def claims(ws):
    result = []
    for path in _stored(ws):
        manifest = kernel.read_manifest(path)
        result.append({'name': manifest['name'], 'root': manifest['root'],
                       'phase': kernel.phase(path), 'path': path})
    return result


def deps(ws):
    rows = []
    for item in claims(ws):
        manifest = kernel.read_manifest(item['path'])
        links = []
        for link in manifest.get('components', []):
            try:
                component = _resolve(item['path'], link['component'], ws)
                status = 'ok' if kernel.verify(component)['root'] == link['root'] else 'mismatch'
            except kernel.ClaimError:
                status = 'unresolved'
            links.append(dict(link, status=status))
        rows.append(dict(item, depends_on=links))
    return {'claims': rows}


def _component_names(manifest):
    return list(dict.fromkeys(x['component'] for x in manifest.get('components', [])))


def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    directory = os.path.abspath(directory)
    ws = ws or _workspace(directory)
    manifest = kernel.read_manifest(directory)
    components = manifest.get('components', [])
    rebuilt = []
    supplied = {}
    temporary = tempfile.mkdtemp(prefix='reticuli-chain-')
    try:
        for name in _component_names(manifest):
            component = _resolve(directory, name, ws)
            checked = kernel.verify(component)
            if not checked['ok']:
                raise kernel.ClaimError(f'component identity mismatch: {name}')
            if reuse:
                built = component
            else:
                built = os.path.join(temporary, name)
                result = rebuild_chain(component, producer, built, ws=ws)
                rebuilt.append({'component': name, 'root': result['root']})
                rebuilt.extend(result.get('rebuilt_components', []))
            for link in components:
                if link['component'] == name and 'from' in next((s for s in kernel.load_recipe(directory).get('step', []) if s['output'] == link['input']), {}):
                    supplied[link['input']] = safe_path(built, link['output'])
        command = producer
        if supplied:
            own = [s['output'] for s in kernel.load_recipe(directory).get('step', [])
                   if s['kind'] == 'produce' and 'from' not in s]
            if own:
                import shlex
                command = 'RETICULI_OUTPUT=' + shlex.quote(os.path.join(os.path.abspath(into), own[0])) + '; ' + producer
        result = kernel.rebuild(directory, command, into, produce_from=supplied or None)
        out_manifest = kernel.read_manifest(into)
        if components:
            out_manifest['components'] = components
            write_json(os.path.join(into, kernel.MANIFEST), out_manifest)
            for name in _component_names(manifest):
                source = _resolve(directory, name, ws)
                target = os.path.join(into, '.reticuli', 'sealed', name)
                shutil.copytree(source, target, dirs_exist_ok=True)
        result['rebuilt_components'] = rebuilt
        return result
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def pull(directory, ws):
    recipe = kernel.load_recipe(directory)
    os.makedirs(ws, exist_ok=True)
    names = [os.path.basename(_recipe_path(directory))] + declared_inputs(recipe, directory)
    names += [s['output'] for s in recipe.get('step', []) if os.path.isfile(safe_path(directory, s['output']))]
    for name in dict.fromkeys(names):
        copy_into(safe_path(directory, name), safe_path(ws, name))
    return {'materialized': True, 'root': kernel.verify(directory)['root']}


def _recipe_path(directory):
    for name in ('reticuli.toml', 'claim.toml'):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    raise kernel.ClaimError('missing recipe')


def sign_root(directory, ws=None, _seen=None):
    directory = os.path.abspath(directory)
    ws = ws or _workspace(directory)
    _seen = set() if _seen is None else _seen
    if directory in _seen:
        raise kernel.ClaimError('component cycle')
    _seen.add(directory)
    manifest = kernel.read_manifest(directory)
    links = []
    for name in _component_names(manifest):
        component = _resolve(directory, name, ws)
        if kernel.verify(component)['root'] != next(x['root'] for x in manifest['components'] if x['component'] == name):
            raise kernel.ClaimError('component root mismatch')
        links.append(sign_root(component, ws, _seen.copy()))
    return kernel.sign_node(kernel.verify(directory)['root'], kernel.build_digest(directory), links)


def audit_deep(directory, *, ws=None):
    directory = os.path.abspath(directory)
    own = kernel.audit(directory)
    layers = []
    visited = set()
    def walk(current, shipped):
        manifest = kernel.read_manifest(current)
        for name in _component_names(manifest):
            links = [x for x in manifest.get('components', []) if x['component'] == name]
            bytes_from = [x['input'] for x in links if 'from' in next((s for s in kernel.load_recipe(current).get('step', []) if s['output'] == x['input']), {})]
            key = (name, manifest['root'])
            if key in visited:
                continue
            visited.add(key)
            try:
                component = _resolve(current, name, ws)
                with tempfile.TemporaryDirectory(prefix='reticuli-deep-') as room:
                    shutil.copytree(component, room, dirs_exist_ok=True)
                    for link in links:
                        source = safe_path(shipped, link['input'])
                        if os.path.isfile(source):
                            copy_into(source, safe_path(room, link['output']))
                    judged = kernel.audit(room)
                    row = {'name': name, 'root': kernel.read_manifest(component)['root'],
                           'ok': judged['ok'], 'status': 'ok' if judged['ok'] else 'failed',
                           'bytes_from': bytes_from}
                    layers.append(row)
                    walk(component, room)
            except (kernel.ClaimError, OSError):
                layers.append({'name': name, 'root': links[0].get('root'), 'ok': False,
                               'status': 'unresolved', 'bytes_from': bytes_from})
    walk(directory, directory)
    return {'ok': own['ok'] and all(x['ok'] for x in layers), 'root': own.get('root'),
            'gates': own['gates'], 'layers': layers}


def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    deep = {name: audit_deep(path) for name, path in [('M1', m1), ('M2', m2), ('M3', m3)]}
    result['deep'] = deep
    result['satisfied'] = result['satisfied'] and all(x['ok'] for x in deep.values())
    return result


def record_proof_deep(m1, m2, m3):
    result = crosscheck_deep(m1, m2, m3)
    if result['satisfied']:
        kernel.record_proof(m1, m2, m3)
    return result


def structure(directory):
    manifest = kernel.read_manifest(directory)
    return {'name': manifest['name'], 'root': manifest['root'], 'phase': kernel.phase(directory),
            'components': manifest.get('components', [])}

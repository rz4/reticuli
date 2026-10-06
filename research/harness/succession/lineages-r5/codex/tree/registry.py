"""Content-addressed component registry and recursive claim operations."""
import hashlib
import json
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, write_json


def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')


def _component_path(directory, name, ws=None):
    for base in (os.path.join(directory, '.reticuli', 'sealed'),
                 os.path.join(directory, '.reticuli', 'deps'),
                 _store(ws) if ws else ''):
        if base and os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


def _components(directory):
    return kernel.read_manifest(directory).get('components', [])


def _groups(links):
    result = {}
    for link in links:
        result.setdefault(link['component'], []).append(link)
    return result


def detect_components(ws, inputs):
    found = []
    base = _store(ws)
    if not os.path.isdir(base):
        return found
    for input_name in inputs:
        needle = kernel._hash_file(os.path.join(ws, input_name))
        for component in sorted(os.listdir(base)):
            path = os.path.join(base, component)
            try:
                manifest = kernel.read_manifest(path)
                parsed = kernel.load_recipe(path)
                for step in parsed.get('step', []):
                    output = step['output']
                    candidate = os.path.join(path, output)
                    if os.path.isfile(candidate) and kernel._hash_file(candidate) == needle:
                        found.append({'input': input_name, 'component': component,
                                      'root': manifest['root'], 'output': output})
            except kernel.ClaimError:
                continue
    return found


def seal_with(directory, *, components=None, proof=None):
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest


def claims(ws):
    base = _store(ws)
    if not os.path.isdir(base):
        return []
    rows = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            try:
                m = kernel.read_manifest(path)
                rows.append({'name': m['name'], 'root': m['root'], 'phase': kernel.phase(path), 'path': path})
            except kernel.ClaimError:
                pass
    return rows


def deps(ws):
    rows = []
    available = {r['name']: r for r in claims(ws)}
    for row in available.values():
        links = []
        for item in _components(row['path']):
            linked = available.get(item['component'])
            links.append(dict(item, status='ok' if linked and linked['root'] == item['root'] else 'missing'))
        rows.append(dict(row, depends_on=links))
    return {'claims': rows}


def structure(directory, ws=None):
    return {'name': kernel.read_manifest(directory)['name'], 'root': kernel.verify(directory)['root'],
            'phase': kernel.phase(directory), 'components': _components(directory)}


def sign_root(directory, ws=None, _seen=None):
    _seen = set() if _seen is None else _seen
    name = os.path.realpath(directory)
    if name in _seen:
        raise kernel.ClaimError('component cycle')
    _seen.add(name)
    children = []
    for component, links in _groups(_components(directory)).items():
        path = _component_path(directory, component, ws)
        if path is None:
            raise kernel.ClaimError('missing declared component: ' + component)
        if kernel.verify(path)['root'] != links[0]['root']:
            raise kernel.ClaimError('component root mismatch: ' + component)
        children.append(sign_root(path, ws, _seen))
    _seen.remove(name)
    return kernel.sign_node(kernel.verify(directory)['root'], kernel.build_digest(directory), children)


def _copy_dependencies(source, target):
    for base_name in ('sealed', 'deps'):
        base = os.path.join(source, '.reticuli', base_name)
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            dst = os.path.join(target, '.reticuli', 'sealed', name)
            if not os.path.exists(dst):
                shutil.copytree(os.path.join(base, name), dst)


def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    groups = _groups(_components(directory))
    rebuilt = []
    with tempfile.TemporaryDirectory(prefix='reticuli-chain-') as stage:
        produce_from = {}
        for name, links in groups.items():
            component = _component_path(directory, name, ws)
            if component is None:
                raise kernel.ClaimError('missing component: ' + name)
            if reuse:
                child = component
                rebuilt.append({'component': name, 'root': kernel.verify(child)['root'], 'reused': True})
            else:
                child = os.path.join(stage, name)
                result = rebuild_chain(component, producer, child, ws=ws)
                rebuilt.extend(result.get('rebuilt_components', []))
                rebuilt.append({'component': name, 'root': result['root']})
            for link in links:
                produce_from[link['input']] = os.path.join(child, link['output'])
        parsed = kernel.load_recipe(directory)
        pinned = set(declared_inputs(parsed, directory))
        input_from = {name: path for name, path in produce_from.items() if name in pinned}
        result = kernel.rebuild(directory, producer, into,
                                produce_from=produce_from or None,
                                input_from=input_from or None)
        seal_with(into, components=_components(directory))
        for name in groups:
            source = _component_path(directory, name, ws)
            destination = os.path.join(into, '.reticuli', 'sealed', name)
            if source and not os.path.exists(destination):
                shutil.copytree(source, destination)
        _copy_dependencies(directory, into)
        result['rebuilt_components'] = rebuilt
        return result

def pull(directory, ws):
    parsed = kernel.load_recipe(directory)
    os.makedirs(ws, exist_ok=True)
    source_recipe = 'reticuli.toml' if os.path.isfile(os.path.join(directory, 'reticuli.toml')) else 'claim.toml'
    names = [source_recipe] + declared_inputs(parsed, directory) + [s['output'] for s in parsed.get('step', [])]
    for name in names:
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            copy_into(path, os.path.join(ws, name))
    return {'materialized': True, 'root': kernel.verify(directory)['root']}


def _audit_layer(directory, root, outputs, source):
    with tempfile.TemporaryDirectory(prefix='reticuli-deep-') as tmp:
        shutil.copytree(directory, tmp, dirs_exist_ok=True)
        for output in outputs:
            shipped = os.path.join(source, output)
            if os.path.isfile(shipped):
                copy_into(shipped, os.path.join(tmp, output))
        try:
            result = kernel.audit(tmp)
            return result['ok'], result
        except kernel.ClaimError as exc:
            return False, {'error': str(exc)}


def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers = []
    visited = set()
    def walk(node, top):
        for name, links in _groups(_components(node)).items():
            if name in visited:
                continue
            visited.add(name)
            path = _component_path(node, name, ws) or _component_path(top, name, ws)
            if path is None:
                layers.append({'name': name, 'ok': False, 'status': 'unresolved', 'bytes_from': [l['input'] for l in links]})
                continue
            outputs = [l['output'] for l in links]
            # The top claim carries the concrete bytes for every ancestor output.
            with tempfile.TemporaryDirectory(prefix='reticuli-overlay-') as tmp:
                shutil.copytree(path, tmp, dirs_exist_ok=True)
                for link in links:
                    shipped = os.path.join(top, link['input'])
                    if os.path.isfile(shipped):
                        copy_into(shipped, os.path.join(tmp, link['output']))
                try:
                    judged = kernel.audit(tmp)
                    ok = judged['ok'] and kernel.verify(tmp)['root'] == links[0]['root']
                except kernel.ClaimError:
                    ok = False
                layers.append({'name': name, 'root': links[0]['root'], 'ok': ok,
                               'status': 'ok' if ok else 'failed',
                               'bytes_from': [l['input'] for l in links]})
            walk(path, top)
    walk(directory, directory)
    return {'ok': own['ok'] and all(r['ok'] for r in layers), 'root': own.get('root'), 'layers': layers, 'audit': own}


def crosscheck_deep(m1, m2, m3):
    shallow = kernel.crosscheck(m1, m2, m3)
    deep = [audit_deep(x) for x in (m1, m2, m3)]
    shallow['deep'] = deep
    shallow['satisfied'] = shallow['satisfied'] and all(x['ok'] for x in deep)
    return shallow


def record_proof_deep(m1, m2, m3):
    result = crosscheck_deep(m1, m2, m3)
    if result['satisfied']:
        kernel.record_proof(m1, m2, m3)
    return result

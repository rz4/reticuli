"""Claim store, component graph, and composed verification."""
import os
import shutil
import tempfile
from . import kernel
from ._kernel import recipe as kr
from ._util import copy_into, declared_inputs, write_json


def _workspace(directory):
    p = os.path.realpath(directory)
    while p != os.path.dirname(p):
        if os.path.basename(os.path.dirname(p)) == 'sealed' and os.path.basename(os.path.dirname(os.path.dirname(p))) == '.reticuli':
            return os.path.dirname(os.path.dirname(os.path.dirname(p)))
        p = os.path.dirname(p)
    return directory


def _component(source, name, ws=None):
    candidates = [os.path.join(source, '.reticuli', 'sealed', name),
                  os.path.join(source, '.reticuli', 'deps', name)]
    if ws:
        candidates.append(os.path.join(ws, '.reticuli', 'sealed', name))
    candidates.append(os.path.join(_workspace(source), '.reticuli', 'sealed', name))
    for p in candidates:
        if os.path.isdir(p):
            return p
    raise kernel.ClaimError('missing declared component: ' + name)


def _links(directory):
    return kernel.read_manifest(directory).get('components', [])


def seal_with(directory, *, components=None, proof=None):
    result = kernel.seal(directory)
    manifest = kernel.read_manifest(directory)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest


def claims(ws):
    base = os.path.join(ws, '.reticuli', 'sealed')
    rows = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if os.path.isdir(path):
                try:
                    row = kernel.verify(path)
                    rows.append({'name': row['name'], 'root': row['root'], 'phase': kernel.phase(path), 'path': path})
                except kernel.ClaimError:
                    pass
    return rows


def detect_components(ws, inputs):
    result = []
    for name in inputs:
        source = os.path.join(ws, name)
        if not os.path.isfile(source):
            continue
        digest = kernel._hash_file(source)
        for row in claims(ws):
            claim = row['path']
            parsed = kernel.load_recipe(claim)
            for step in parsed.get('step', []):
                out = step['output']
                target = os.path.join(claim, out)
                if os.path.isfile(target) and kernel._hash_file(target) == digest:
                    result.append({'input': name, 'component': row['name'], 'root': row['root'], 'output': out})
    return result


def deps(ws):
    result = []
    for row in claims(ws):
        edges = []
        for link in _links(row['path']):
            try:
                child = _component(row['path'], link['component'], ws)
                ok = kernel.verify(child)['root'] == link['root']
            except (kernel.ClaimError, KeyError):
                ok = False
            edges.append(dict(link, status='ok' if ok else 'unresolved'))
        result.append(dict(row, depends_on=edges))
    return {'claims': result}


def sign_root(directory, ws=None, _seen=None):
    _seen = set() if _seen is None else _seen
    path = os.path.realpath(directory)
    if path in _seen:
        raise kernel.ClaimError('component cycle')
    _seen.add(path)
    checked = kernel.verify(path)
    if not checked['ok']:
        raise kernel.ClaimError('component identity mismatch')
    children = []
    for name in sorted({x['component'] for x in _links(path)}):
        child = _component(path, name, ws)
        if kernel.verify(child)['root'] != next(x['root'] for x in _links(path) if x['component'] == name):
            raise kernel.ClaimError('component root mismatch: ' + name)
        children.append(sign_root(child, ws, _seen))
    _seen.remove(path)
    return kernel.sign_node(checked['root'], kernel.build_digest(path), children)


def rebuild_chain(source, producer, into, *, ws=None, reuse=False):
    links = _links(source)
    supplied = {}
    rebuilt = []
    with tempfile.TemporaryDirectory(prefix='reticuli-components-') as temp:
        child_paths = {}
        for name in sorted({x['component'] for x in links}):
            child = _component(source, name, ws)
            if reuse:
                child_paths[name] = child
            else:
                target = os.path.join(temp, name)
                rebuild_chain(child, producer, target, ws=ws)
                child_paths[name] = target
            rebuilt.append({'component': name, 'root': kernel.verify(child_paths[name])['root']})
        for link in links:
            child_file = os.path.join(child_paths[link['component']], link['output'])
            supplied[link['input']] = child_file
        result = kernel.rebuild(source, producer, into, produce_from=supplied or None)
        if links:
            sealed = os.path.join(into, '.reticuli', 'sealed')
            for name, child in child_paths.items():
                shutil.copytree(child, os.path.join(sealed, name), dirs_exist_ok=True)
            seal_with(into, components=links)
        result['rebuilt_components'] = rebuilt
        return result


def pull(source, ws):
    parsed = kernel.load_recipe(source)
    names = [os.path.basename(kr.recipe_path(source)), *declared_inputs(parsed, source)]
    names += [step['output'] for step in parsed.get('step', []) if os.path.isfile(os.path.join(source, step['output']))]
    for name in dict.fromkeys(names):
        copy_into(os.path.join(source, name), os.path.join(ws, name))
    return {'materialized': True, 'root': kernel.verify(source)['root']}


def audit_deep(directory):
    own = kernel.audit(directory)
    layers = []
    seen = set()
    def visit(source, overrides):
        for name in sorted({x['component'] for x in _links(source)}):
            related = [x for x in _links(source) if x['component'] == name]
            if name in seen:
                continue
            seen.add(name)
            try:
                child = _component(source, name)
                with tempfile.TemporaryDirectory(prefix='reticuli-deep-') as room:
                    shutil.copytree(child, room, dirs_exist_ok=True)
                    child_overrides = dict(overrides)
                    for link in related:
                        child_overrides[link['output']] = overrides.get(link['input'], os.path.join(source, link['input']))
                    parsed = kernel.load_recipe(child)
                    generated = {s['output'] for s in kr.produces(parsed) if s.get('class', 'generated') == 'generated'}
                    for output, path in child_overrides.items():
                        if output in generated and os.path.isfile(path):
                            copy_into(path, os.path.join(room, output))
                    audit = kernel.audit(room)
                    row = {'name': name, 'root': kernel.verify(child)['root'], 'ok': audit['ok'],
                           'status': 'ok' if audit['ok'] else 'failed',
                           'bytes_from': sorted(x['input'] for x in related)}
                    layers.append(row)
                    visit(child, child_overrides)
            except kernel.ClaimError:
                layers.append({'name': name, 'root': related[0].get('root'), 'ok': False,
                               'status': 'unresolved', 'bytes_from': sorted(x['input'] for x in related)})
    visit(directory, {})
    return {'ok': own['ok'] and all(r['ok'] for r in layers), 'audit': own, 'layers': layers}


def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    deep = {key: audit_deep(path) for key, path in zip(('M1','M2','M3'), (m1,m2,m3))}
    result['deep'] = deep
    result['satisfied'] = result['satisfied'] and all(x['ok'] for x in deep.values())
    return result


def structure(directory):
    return {'root': kernel.verify(directory)['root'], 'phase': kernel.phase(directory), 'components': _links(directory)}


def record_proof_deep(m1, m2, m3):
    result = crosscheck_deep(m1, m2, m3)
    if result['satisfied']:
        seal_with(m1, components=_links(m1), proof={'kind':'crosscheck','roots':result['roots']})
    return result

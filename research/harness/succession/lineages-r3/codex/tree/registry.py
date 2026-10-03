"""Content-addressed links between sealed claims and their rebuilds."""
from __future__ import annotations

import os
import shutil
import tempfile

from . import kernel
from ._kernel import core, recipe
from ._util import write_json

def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')

def _workspace(directory):
    path = os.path.abspath(directory)
    while True:
        if os.path.isdir(_store(path)):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return os.path.abspath(directory)
        path = parent

def _component(directory, name, ws=None):
    places = [os.path.join(directory, '.reticuli', 'deps', name),
              os.path.join(directory, '.reticuli', 'sealed', name),
              os.path.join(_store(ws or _workspace(directory)), name)]
    return next((p for p in places if os.path.isfile(os.path.join(p, kernel.MANIFEST))), None)

def seal_with(directory, *, components=None, proof=None):
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest

def detect_components(ws, inputs):
    found = []
    base = _store(ws)
    if not os.path.isdir(base):
        return found
    for input_name in inputs:
        target = core._hash_file(core._safe(ws, input_name))
        for name in sorted(os.listdir(base)):
            claim = os.path.join(base, name)
            if not os.path.isdir(claim):
                continue
            parsed = kernel.load_recipe(claim)
            for step in recipe._steps(parsed):
                output = step['output']
                path = core._safe(claim, output)
                if os.path.isfile(path) and core._hash_file(path) == target:
                    found.append({'input': input_name, 'component': name,
                                  'root': kernel.verify(claim)['root'], 'output': output})
    return found

def claims(ws):
    base = _store(ws)
    if not os.path.isdir(base):
        return []
    rows = []
    for name in sorted(os.listdir(base)):
        directory = os.path.join(base, name)
        if os.path.isdir(directory) and os.path.isfile(os.path.join(directory, kernel.MANIFEST)):
            manifest = kernel.read_manifest(directory)
            rows.append({'name': manifest['name'], 'root': manifest['root'],
                         'phase': kernel.phase(directory), 'path': directory})
    return rows

def deps(ws):
    rows = []
    for row in claims(ws):
        links = kernel.read_manifest(row['path']).get('components', [])
        edges = []
        for link in links:
            source = _component(row['path'], link['component'], ws)
            status = 'ok' if source and kernel.verify(source)['root'] == link['root'] else 'unresolved'
            edges.append(dict(link, status=status))
        rows.append(dict(row, depends_on=edges))
    return {'claims': rows}

def sign_root(directory, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    path = os.path.realpath(directory)
    if path in seen:
        raise kernel.ClaimError('component cycle')
    seen.add(path)
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('component identity mismatch')
    links = []
    for link in kernel.read_manifest(directory).get('components', []):
        child = _component(directory, link['component'], ws)
        if not child or kernel.verify(child)['root'] != link['root']:
            raise kernel.ClaimError('missing declared component: ' + link['component'])
        links.append(sign_root(child, ws, seen))
    seen.remove(path)
    return kernel.sign_node(checked['root'], kernel.build_digest(directory), links)

def _copy_claim(source, target):
    parsed = kernel.load_recipe(source)
    os.makedirs(target, exist_ok=True)
    name = os.path.basename(recipe.recipe_path(source))
    paths = [name, *recipe._inputs(parsed, source)]
    paths += [s['output'] for s in recipe._steps(parsed)
              if s.get('class', 'generated' if s['kind'] == 'produce' else 'pinned') not in ('generated', 'free')]
    for item in paths:
        core._copy_into(core._safe(source, item), core._safe(target, item))
    core._copy_into(os.path.join(source, kernel.MANIFEST), os.path.join(target, kernel.MANIFEST))

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    manifest = kernel.read_manifest(directory)
    links = manifest.get('components', [])
    generated, inputs, rebuilt = {}, {}, []
    with tempfile.TemporaryDirectory(prefix='reticuli-chain-') as scratch:
        for link in links:
            source = _component(directory, link['component'], ws)
            if not source or kernel.verify(source)['root'] != link['root']:
                raise kernel.ClaimError('missing declared component: ' + link['component'])
            if reuse:
                child = source
            else:
                child = os.path.join(scratch, link['component'])
                rebuild_chain(source, producer, child, ws=ws)
                rebuilt.append({'component': link['component'], 'root': kernel.verify(child)['root']})
            path = core._safe(child, link['output'])
            if link['input'] in recipe._inputs(kernel.load_recipe(directory), directory):
                inputs[link['input']] = path
            else:
                generated[link['input']] = path
        result = kernel.rebuild(directory, producer, into, produce_from=generated, input_from=inputs)
        if links:
            result = seal_with(into, components=links)
            dep_base = os.path.join(into, '.reticuli', 'sealed')
            for link in links:
                child = _component(directory, link['component'], ws)
                dest = os.path.join(dep_base, link['component'])
                if not os.path.exists(dest):
                    shutil.copytree(child, dest)
    return dict(result, rebuilt_components=rebuilt)

def pull(directory, ws):
    parsed = kernel.load_recipe(directory)
    os.makedirs(ws, exist_ok=True)
    name = os.path.basename(recipe.recipe_path(directory))
    paths = [name, *recipe._inputs(parsed, directory), *(s['output'] for s in recipe._steps(parsed))]
    for item in paths:
        source = core._safe(directory, item)
        if os.path.isfile(source):
            core._copy_into(source, core._safe(ws, item))
    return {'materialized': True, 'root': kernel.verify(directory)['root']}

def audit_deep(directory):
    own = kernel.audit(directory)
    layers = []
    for link in kernel.read_manifest(directory).get('components', []):
        source = _component(directory, link['component'])
        if source is None:
            layers.append({'name': link['component'], 'status': 'unresolved', 'ok': False})
            continue
        with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
            _copy_claim(source, room)
            used = [x for x in kernel.read_manifest(directory).get('components', [])
                    if x['component'] == link['component']]
            for item in used:
                core._copy_into(core._safe(directory, item['input']), core._safe(room, item['output']))
            try:
                judged = kernel.audit(room)
                good = judged['ok']
            except kernel.ClaimError:
                good = False
            layers.append({'name': link['component'], 'root': link['root'],
                           'bytes_from': sorted(x['input'] for x in used),
                           'status': 'ok' if good else 'failed', 'ok': good})
    return {'ok': own['ok'] and all(x['ok'] for x in layers), 'root': own.get('root'),
            'layers': layers, 'audit': own}

def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    deep = {name: audit_deep(path) for name, path in zip(('M1', 'M2', 'M3'), (m1, m2, m3))}
    result['deep'] = deep
    result['satisfied'] = result['satisfied'] and all(x['ok'] for x in deep.values())
    return result

"""Content-addressed component links and composed claim operations."""
from __future__ import annotations

import os
import shutil
import tempfile
from . import kernel
from ._kernel import recipe
from ._util import copy_into, write_json

def _workspace(path):
    path = os.path.realpath(path)
    marker = os.sep + '.reticuli' + os.sep + 'sealed' + os.sep
    return path.split(marker)[0] if marker in path else path

def _links(directory):
    return kernel.read_manifest(directory).get('components', [])

def _resolve(directory, link, ws=None):
    name = link['component']
    candidates = [os.path.join(directory, '.reticuli', 'sealed', name),
                  os.path.join(directory, '.reticuli', 'deps', name)]
    if ws:
        candidates.append(os.path.join(ws, '.reticuli', 'sealed', name))
    candidates.append(os.path.join(_workspace(directory), '.reticuli', 'sealed', name))
    for path in candidates:
        if os.path.isfile(os.path.join(path, kernel.MANIFEST)):
            if kernel.verify(path)['root'] != link['root'] or not kernel.verify(path)['ok']:
                raise kernel.ClaimError('component identity mismatch: ' + name)
            return path
    raise kernel.ClaimError('missing declared component: ' + name)

def detect_components(ws, inputs):
    base = os.path.join(ws, '.reticuli', 'sealed')
    found = []
    if not os.path.isdir(base):
        return found
    for inp in inputs:
        input_path = kernel._safe(ws, inp)
        if not os.path.isfile(input_path):
            continue
        digest = kernel._hash_file(input_path)
        for name in sorted(os.listdir(base)):
            claim = os.path.join(base, name)
            try:
                checked = kernel.verify(claim)
                parsed = kernel.load_recipe(claim)
                if not checked['ok']:
                    continue
                for step in parsed.get('step', []):
                    out = step['output']
                    path = kernel._safe(claim, out)
                    if os.path.isfile(path) and kernel._hash_file(path) == digest:
                        found.append({'input': inp, 'component': name,
                                      'root': checked['root'], 'output': out})
            except kernel.ClaimError:
                continue
    return found

def seal_with(directory, *, components=None, proof=None):
    prior = None
    try:
        prior = kernel.read_manifest(directory)
    except kernel.ClaimError:
        pass
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    elif prior and 'components' in prior:
        manifest['components'] = prior['components']
    if proof is not None:
        manifest['proof'] = proof
    elif prior and 'proof' in prior:
        manifest['proof'] = prior['proof']
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest

def claims(ws):
    base = os.path.join(ws, '.reticuli', 'sealed')
    if not os.path.isdir(base):
        return []
    rows = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if not os.path.isdir(path):
            continue
        try:
            v = kernel.verify(path)
            rows.append({'name': v['name'], 'root': v['root'], 'ok': v['ok'],
                         'phase': kernel.phase(path) if v['ok'] else 'sealed', 'path': path})
        except kernel.ClaimError:
            continue
    return rows

def deps(ws):
    rows = []
    for row in claims(ws):
        path = row['path']
        edges = []
        for link in _links(path):
            edge = dict(link)
            try:
                _resolve(path, link, ws)
                edge['status'] = 'ok'
            except kernel.ClaimError:
                edge['status'] = 'unresolved'
            edges.append(edge)
        rows.append({**row, 'depends_on': edges})
    return {'claims': rows}

def structure(ws):
    return deps(ws)

def sign_root(directory, ws=None, _seen=None):
    real = os.path.realpath(directory)
    seen = set() if _seen is None else _seen
    if real in seen:
        raise kernel.ClaimError('component cycle')
    seen.add(real)
    checked = kernel.verify(real)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    links = []
    for link in _links(real):
        links.append(sign_root(_resolve(real, link, ws), ws, seen.copy()))
    return kernel.sign_node(checked['root'], kernel.build_digest(real), links)

def pull(directory, ws):
    checked = kernel.verify(directory)
    if not checked['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    parsed = kernel.load_recipe(directory)
    names = [os.path.basename(recipe.recipe_path(directory))]
    names += recipe._inputs(parsed, directory)
    names += [s['output'] for s in parsed.get('step', [])]
    os.makedirs(ws, exist_ok=True)
    for name in dict.fromkeys(names):
        source = kernel._safe(directory, name)
        if os.path.isfile(source):
            copy_into(source, kernel._safe(ws, name))
    return {'materialized': True, 'root': checked['root']}

def _snapshot(source, target):
    from . import transfer
    transfer._copy_claim(source, target, generated=False, residue=False)

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    source = os.path.realpath(directory)
    links = _links(source)
    rebuilt = []
    component_paths = {}
    if links and not reuse:
        with tempfile.TemporaryDirectory(prefix='reticuli-chain-') as temp:
            for link in links:
                name = link['component']
                if name in component_paths:
                    continue
                component = _resolve(source, link, ws)
                dest = os.path.join(temp, name)
                result = rebuild_chain(component, producer, dest, ws=ws)
                rebuilt.extend(result.get('rebuilt_components', []))
                rebuilt.append({'component': name, 'root': result['root']})
                component_paths[name] = dest
            return _rebuild_parent(source, producer, into, links, component_paths, rebuilt)
    if links:
        for link in links:
            name = link['component']
            if name not in component_paths:
                component_paths[name] = _resolve(source, link, ws)
                rebuilt.append({'component': name, 'root': link['root'], 'reused': True})
    return _rebuild_parent(source, producer, into, links, component_paths, rebuilt)

def _rebuild_parent(source, producer, into, links, components, rebuilt):
    # The kernel copies `from` outputs from the source. For a rebuilt child,
    # substitute its new outputs in a temporary source with the same root.
    with tempfile.TemporaryDirectory(prefix='reticuli-source-') as staging:
        from . import transfer
        transfer._copy_claim(source, staging, generated=True, residue=False)
        for link in links:
            if link['component'] in components:
                output = os.path.join(components[link['component']], link['output'])
                if os.path.isfile(output):
                    copy_into(output, kernel._safe(staging, link['input']))
        result = kernel.rebuild(staging, producer, into)
    seal_with(into, components=links)
    for name, path in components.items():
        _snapshot(path, os.path.join(into, '.reticuli', 'sealed', name))
    result['rebuilt_components'] = rebuilt
    return result

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    rows = []
    active = set()
    def visit(source, overrides):
        real = os.path.realpath(source)
        if real in active:
            rows.append({'name': os.path.basename(real), 'ok': False, 'status': 'cycle'})
            return
        active.add(real)
        grouped = {}
        for link in _links(source):
            grouped.setdefault(link['component'], []).append(link)
        for name, group in grouped.items():
            try:
                component = _resolve(source, group[0], ws)
                with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
                    from . import transfer
                    transfer._copy_claim(component, room, generated=True, residue=False)
                    for link in group:
                        shipped = overrides.get(link['input'], os.path.join(source, link['input']))
                        copy_into(shipped, kernel._safe(room, link['output']))
                    verdict = kernel.audit(room)
                    row = {'name': name, 'root': group[0]['root'], 'ok': verdict['ok'],
                           'status': 'ok' if verdict['ok'] else 'failed',
                           'bytes_from': [x['input'] for x in group]}
                    rows.append(row)
                    child_overrides = {x['output']: os.path.join(room, x['output']) for x in group}
                    visit(component, child_overrides)
            except (kernel.ClaimError, OSError) as exc:
                rows.append({'name': name, 'root': group[0].get('root'), 'ok': False,
                             'status': 'unresolved', 'detail': str(exc)})
        active.remove(real)
    visit(directory, {})
    return {'ok': bool(own['ok'] and all(r['ok'] for r in rows)),
            'root': own.get('root'), 'layers': rows, 'audit': own}

def crosscheck_deep(m1, m2, m3):
    shallow = kernel.crosscheck(m1, m2, m3)
    audits = [audit_deep(p) for p in (m1, m2, m3)]
    shallow['deep'] = audits
    shallow['satisfied'] = bool(shallow['satisfied'] and all(a['ok'] for a in audits))
    if not shallow['satisfied']:
        shallow['verdict'] = 'reject'
    return shallow

def record_proof_deep(m1, m2, m3):
    result = crosscheck_deep(m1, m2, m3)
    if result['satisfied']:
        seal_with(m1, proof={'kind': 'crosscheck', 'm2': result['roots']['M2'],
                             'm3': result['roots']['M3']})
    return result

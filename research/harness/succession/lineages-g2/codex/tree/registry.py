"""Content-addressed component registry and composed judgments."""
import os
import shutil
import tempfile
from . import kernel
from ._kernel import core, recipe

def _store(ws):
    return os.path.join(os.fspath(ws), '.reticuli', 'sealed')

def _workspace(path):
    path = os.path.realpath(path)
    parent = os.path.dirname(path)
    if os.path.basename(parent) == 'sealed' and os.path.basename(os.path.dirname(parent)) == '.reticuli':
        return os.path.dirname(os.path.dirname(parent))
    return path

def _candidates(source, ws=None):
    roots = [source, _workspace(source)]
    if ws:
        roots.append(ws)
    seen = set()
    for base in roots:
        for folder in (_store(base), os.path.join(base, '.reticuli', 'deps')):
            if os.path.isdir(folder):
                for name in sorted(os.listdir(folder)):
                    path = os.path.join(folder, name)
                    real = os.path.realpath(path)
                    if os.path.isdir(path) and real not in seen:
                        seen.add(real)
                        yield path

def _resolve(source, link, ws=None):
    for path in _candidates(source, ws):
        try:
            m = kernel.read_manifest(path)
            if m['root'] == link['root'] and m['name'] == link['component']:
                return path
        except kernel.ClaimError:
            pass
    return None

def _links(path):
    manifest = kernel.read_manifest(path)
    if manifest.get('components'):
        return manifest['components']
    backup = os.path.join(path, '.reticuli', 'components.json')
    if os.path.isfile(backup):
        import json
        with open(backup, encoding='utf-8') as stream:
            return json.load(stream)
    return []

def seal_with(directory, *, components=None, proof=None):
    previous = None
    try:
        previous = kernel.read_manifest(directory)
    except kernel.ClaimError:
        pass
    manifest = kernel.seal(directory)
    if components is not None:
        manifest['components'] = components
    elif previous and 'components' in previous:
        manifest['components'] = previous['components']
    if proof is not None:
        manifest['proof'] = proof
    elif previous and 'proof' in previous:
        manifest['proof'] = previous['proof']
    core._write_json(core._safe(directory, kernel.MANIFEST), manifest)
    if manifest.get('components'):
        core._write_json(core._safe(directory, '.reticuli/components.json'), manifest['components'])
    return manifest

def detect_components(ws, inputs):
    result = []
    for name in inputs:
        target = core._hash_file(core._safe(ws, name))
        for path in _candidates(ws):
            try:
                manifest = kernel.read_manifest(path)
                parsed = kernel.load_recipe(path)
                for step in parsed.get('step', []):
                    output = step['output']
                    candidate = core._safe(path, output)
                    if os.path.isfile(candidate) and core._hash_file(candidate) == target:
                        result.append({'input': name, 'component': manifest['name'],
                                       'root': manifest['root'], 'output': output})
            except kernel.ClaimError:
                pass
    return result

def claims(ws):
    rows = []
    for path in _candidates(ws):
        try:
            m = kernel.read_manifest(path)
            rows.append({'name': m['name'], 'root': m['root'], 'phase': kernel.phase(path), 'path': path})
        except kernel.ClaimError:
            pass
    return rows

def deps(ws):
    rows = []
    for item in claims(ws):
        path = item['path']
        links = []
        for link in _links(path):
            links.append({**link, 'status': 'ok' if _resolve(path, link, ws) else 'unresolved'})
        rows.append({**item, 'depends_on': links})
    return {'claims': rows}

def sign_root(directory, ws=None, _seen=None):
    _seen = set() if _seen is None else _seen
    manifest = kernel.read_manifest(directory)
    if manifest['root'] in _seen:
        raise kernel.ClaimError('component cycle')
    _seen.add(manifest['root'])
    children = []
    for link in _links(directory):
        path = _resolve(directory, link, ws)
        if path is None:
            raise kernel.ClaimError('missing declared component: ' + link['component'])
        children.append(sign_root(path, ws or directory, _seen))
    _seen.remove(manifest['root'])
    return kernel.sign_node(kernel.verify(directory)['root'], kernel.build_digest(directory), children)

def _closure(source, ws=None, *, strict=True):
    found = {}
    def visit(path):
        for link in _links(path):
            root = link['root']
            if root in found:
                continue
            child = _resolve(source, link, ws)
            if child is None:
                if strict:
                    raise kernel.ClaimError('missing declared component: ' + link['component'])
                continue
            found[root] = child
            visit(child)
    visit(source)
    return found

def _copy_claim(source, target, *, generated=True):
    parsed = kernel.load_recipe(source)
    names = {os.path.basename(recipe.recipe_path(source)), kernel.MANIFEST}
    names.update(recipe._inputs(parsed, source))
    for step in parsed.get('step', []):
        if generated or step.get('class', 'pinned') not in ('generated', 'free'):
            names.add(step['output'])
    for name in sorted(names):
        src = core._safe(source, name)
        if os.path.isfile(src):
            dst = core._safe(target, name)
            core._copy_into(src, dst)

def pull(source, ws):
    closure = _closure(source)
    target = os.path.join(_store(ws), kernel.read_manifest(source)['name'])
    _copy_claim(source, target)
    for child in closure.values():
        dest = os.path.join(_store(ws), kernel.read_manifest(child)['name'])
        if os.path.realpath(dest) != os.path.realpath(target):
            _copy_claim(child, dest)
    parsed = kernel.load_recipe(source)
    for name in {os.path.basename(recipe.recipe_path(source)), *recipe._inputs(parsed, source),
                 *(s['output'] for s in parsed.get('step', []))}:
        src = os.path.join(target, name)
        if os.path.isfile(src):
            core._copy_into(src, core._safe(ws, name))
    return {'materialized': True, 'root': kernel.read_manifest(source)['root'], 'path': target}

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers = []
    closure = _closure(directory, ws, strict=False) if _links(directory) else {}
    visited = set()
    def judge(path, links, shipped=None):
        shipped = shipped or {}
        for link in links:
            root = link['root']
            if root in visited:
                continue
            visited.add(root)
            child = closure.get(root)
            if child is None:
                layers.append({'name': link['component'], 'root': root, 'ok': False,
                               'status': 'unresolved', 'bytes_from': [link['input']]})
                continue
            related = [x for x in links if x['root'] == root]
            code = set()
            parsed = kernel.load_recipe(path)
            for step in parsed.get('step', []):
                if step.get('from') == link['component']:
                    code.add(step['output'])
            attribution_ok = True
            forwarded = {}
            for item in related:
                supplied = shipped.get(item['input'], core._safe(path, item['input']))
                if item['input'] not in code:
                    try:
                        attribution_ok &= (core._hash_file(supplied) ==
                                           core._hash_file(core._safe(child, item['output'])))
                    except kernel.ClaimError:
                        attribution_ok = False
                else:
                    forwarded[item['output']] = supplied
            with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
                _copy_claim(child, room)
                for item in related:
                    if item['input'] in code:
                        src = forwarded[item['output']]
                        if os.path.isfile(src):
                            core._copy_into(src, core._safe(room, item['output']))
                try:
                    aud = kernel.audit(room)
                    ok = aud['ok'] and attribution_ok
                except kernel.ClaimError:
                    ok = False
            row = {'name': link['component'], 'root': root, 'ok': ok,
                   'status': 'ok' if ok else ('attribution mismatch' if not attribution_ok else 'failed'),
                   'bytes_from': sorted(code)}
            layers.append(row)
            judge(child, _links(child), forwarded)
    judge(directory, _links(directory))
    return {'ok': own['ok'] and all(row['ok'] for row in layers), 'root': own['root'],
            'layers': layers, 'audit': own}

def rebuild_chain(source, producer, into, *, ws=None, reuse=False):
    links = _links(source)
    closure = _closure(source, ws) if links else {}
    rebuilt = []
    mappings_input, mappings_produce = {}, {}
    parsed = kernel.load_recipe(source)
    from_outputs = {s['output'] for s in parsed.get('step', []) if s.get('from')}
    for link in links:
        child = closure[link['root']]
        output_path = core._safe(child, link['output'])
        if not reuse:
            rebuilt.append({'component': link['component'], 'root': link['root']})
        if link['input'] in from_outputs:
            mappings_produce[link['input']] = output_path
        else:
            mappings_input[link['input']] = output_path
    result = kernel.rebuild(source, producer, into,
                            input_from=mappings_input or None,
                            produce_from=mappings_produce or None)
    seal_with(into, components=links)
    for child in closure.values():
        dest = os.path.join(_store(into), kernel.read_manifest(child)['name'])
        _copy_claim(child, dest)
    result['rebuilt_components'] = rebuilt or [{'component': x['component']} for x in links]
    return result

def crosscheck_deep(m1, m2, m3, **kwargs):
    result = kernel.crosscheck(m1, m2, m3, **kwargs)
    audits = [audit_deep(path) for path in (m1, m2, m3)]
    if not all(x['ok'] for x in audits):
        result['satisfied'] = False
        result['verdict'] = 'reject'
        result['rejected'].append('deep audit')
    result['deep'] = audits
    return result

def record_proof_deep(m1, m2, m3, **kwargs):
    deep = crosscheck_deep(m1, m2, m3, **kwargs)
    return kernel.record_proof(m1, m2, m3, **kwargs) if deep['satisfied'] else {'proof_recorded': False, 'crosscheck': deep}

def structure(directory, ws=None):
    return {'name': kernel.read_manifest(directory)['name'], 'root': kernel.verify(directory)['root'],
            'phase': kernel.phase(directory), 'depends_on': _links(directory)}

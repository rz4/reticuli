"""Content-addressed component links and recursive claim operations."""
import json
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, safe_path, write_json


def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')


def _components(path):
    return kernel.read_manifest(path).get('components', [])


def _find(path, name, ws=None):
    places = [os.path.join(path, '.reticuli', 'sealed', name),
              os.path.join(path, '.reticuli', 'deps', name)]
    if ws:
        places.append(os.path.join(_store(ws), name))
    for place in places:
        if os.path.isdir(place):
            return place
    raise kernel.ClaimError('missing declared component: ' + name)


def detect_components(ws, inputs):
    found = []
    if not os.path.isdir(_store(ws)):
        return found
    for name in sorted(os.listdir(_store(ws))):
        component = os.path.join(_store(ws), name)
        try:
            checked = kernel.verify(component)
            if not checked['ok']:
                continue
            doc = kernel.load_recipe(component)
            outputs = [s['output'] for s in doc.get('step', [])]
            for inp in inputs:
                for out in outputs:
                    try:
                        if kernel._hash_file(safe_path(ws, inp)) == kernel._hash_file(safe_path(component, out)):
                            found.append({'input': inp, 'component': name, 'root': checked['root'], 'output': out})
                    except kernel.ClaimError:
                        pass
        except kernel.ClaimError:
            pass
    return found


def seal_with(path, *, components=None, proof=None):
    manifest = kernel.seal(path)
    if components is not None:
        manifest['components'] = components
    if proof is not None:
        manifest['proof'] = proof
    write_json(os.path.join(path, kernel.MANIFEST), manifest)
    return manifest


def claims(ws):
    rows = []
    if os.path.isdir(_store(ws)):
        for name in sorted(os.listdir(_store(ws))):
            path = os.path.join(_store(ws), name)
            if os.path.isdir(path):
                checked = kernel.verify(path)
                rows.append({'name': name, 'root': checked['root'], 'ok': checked['ok'], 'phase': kernel.phase(path)})
    return rows


def deps(ws):
    rows = []
    for item in claims(ws):
        path = os.path.join(_store(ws), item['name'])
        links = []
        for link in _components(path):
            try:
                source = _find(path, link['component'], ws)
                status = 'ok' if kernel.verify(source)['root'] == link['root'] else 'mismatch'
            except kernel.ClaimError:
                status = 'missing'
            links.append(dict(link, status=status))
        rows.append(dict(item, depends_on=links))
    return {'claims': rows}


def structure(path, ws=None):
    return {'name': kernel.read_manifest(path)['name'], 'root': kernel.verify(path)['root'],
            'phase': kernel.phase(path), 'components': _components(path)}


def pull(path, ws):
    checked = kernel.verify(path)
    if not checked['ok']:
        raise kernel.ClaimError('source claim identity mismatch')
    doc = kernel.load_recipe(path)
    name = 'reticuli.toml' if os.path.isfile(os.path.join(path, 'reticuli.toml')) else 'claim.toml'
    files = [name, *declared_inputs(path), *[s['output'] for s in doc.get('step', [])]]
    os.makedirs(ws, exist_ok=True)
    for file in files:
        src = safe_path(path, file)
        if os.path.isfile(src):
            copy_into(src, safe_path(ws, file))
    return {'materialized': True, 'root': checked['root']}


def rebuild_chain(path, producer, into, *, ws=None, reuse=False):
    links = _components(path)
    sources = {}
    rebuilt = []
    temporary = []
    try:
        for link in links:
            name = link['component']
            if name in sources:
                continue
            src = _find(path, name, ws)
            if reuse:
                sources[name] = src
            else:
                room = tempfile.mkdtemp(prefix='reticuli-component-')
                temporary.append(room)
                # The kernel requires an empty destination.
                shutil.rmtree(room)
                rebuild_chain(src, producer, room, ws=ws)
                sources[name] = room
                rebuilt.append({'component': name, 'root': kernel.verify(room)['root']})
        produce_from = {}
        for link in links:
            src = safe_path(sources[link['component']], link['output'])
            if not os.path.isfile(src):
                raise kernel.ClaimError('component output missing: ' + link['output'])
            produce_from[link['input']] = src
        generated = {s['output'] for s in kernel.load_recipe(path).get('step', []) if s.get('class') == 'generated'}
        output_sources = {k:v for k,v in produce_from.items() if k in generated}
        input_sources = {k:v for k,v in produce_from.items() if k not in generated}
        result = kernel.rebuild(path, producer, into, produce_from=output_sources or None, input_from=input_sources or None)
        if not result['ok']:
            raise kernel.ClaimError('component rebuild failed: ' + repr(result))
        manifest = kernel.read_manifest(into)
        if links:
            manifest['components'] = links
            write_json(os.path.join(into, kernel.MANIFEST), manifest)
            for name, src in sources.items():
                dest = os.path.join(_store(into), name)
                shutil.copytree(src, dest, ignore=shutil.ignore_patterns('sealed', 'deps', 'ledger.jsonl'), dirs_exist_ok=True)
        result['rebuilt_components'] = rebuilt
        return result
    finally:
        for room in temporary:
            shutil.rmtree(room, ignore_errors=True)


def sign_root(path, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    root = kernel.verify(path)['root']
    if not kernel.verify(path)['ok']:
        raise kernel.ClaimError('component identity mismatch')
    if root in seen:
        raise kernel.ClaimError('component cycle')
    seen.add(root)
    children = []
    for name in sorted({x['component'] for x in _components(path)}):
        source = _find(path, name, ws)
        children.append(sign_root(source, ws, seen.copy()))
    return kernel.sign_node(root, kernel.build_digest(path), children)


def _audit_layers(path, ws, seen, overrides):
    rows = []
    for name in sorted({x['component'] for x in _components(path)}):
        links = [x for x in _components(path) if x['component'] == name]
        if name in seen:
            continue
        seen.add(name)
        try:
            source = _find(path, name, ws)
            with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
                shutil.copytree(source, room, dirs_exist_ok=True)
                supplied = {}
                for link in links:
                    target = safe_path(path, link['input'])
                    if os.path.isfile(target):
                        supplied[link['output']] = target
                        copy_into(target, safe_path(room, link['output']))
                for out, source_file in overrides.items():
                    if out in [s['output'] for s in kernel.load_recipe(room).get('step', [])]:
                        copy_into(source_file, safe_path(room, out))
                audit = kernel.audit(room)
                rows.append({'name': name, 'root': kernel.verify(room)['root'], 'ok': audit['ok'],
                             'status': 'ok' if audit['ok'] else 'failed',
                             'bytes_from': sorted(supplied)})
                child_overrides = dict(overrides, **supplied)
                rows.extend(_audit_layers(room, ws, seen, child_overrides))
        except (kernel.ClaimError, OSError) as exc:
            rows.append({'name': name, 'root': links[0].get('root'), 'ok': False,
                         'status': 'unresolved', 'bytes_from': [], 'detail': str(exc)})
    return rows


def audit_deep(path, ws=None):
    own = kernel.audit(path)
    layers = _audit_layers(path, ws, set(), {})
    return {'ok': own['ok'] and all(x['ok'] for x in layers), 'root': own['root'],
            'gates': own['gates'], 'layers': layers}


def crosscheck_deep(m1, m2, m3, *, mutants=None):
    return kernel.crosscheck(m1, m2, m3, mutants=mutants) if all(audit_deep(p)['ok'] for p in (m1,m2,m3)) else dict(kernel.crosscheck(m1,m2,m3,mutants=mutants), satisfied=False, verdict='reject')


def record_proof_deep(m1, m2, m3, *, mutants=None):
    result = crosscheck_deep(m1,m2,m3,mutants=mutants)
    if result['satisfied']:
        kernel.record_proof(m1,m2,m3,mutants=mutants)
    return result

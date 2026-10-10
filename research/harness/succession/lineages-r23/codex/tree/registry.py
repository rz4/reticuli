"""Content-addressed claim links and composed verification."""
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs


def _store(directory):
    return os.path.join(directory, '.reticuli', 'sealed')


def _locations(directory, ws=None):
    roots = [os.path.join(directory, '.reticuli', 'deps'), _store(directory)]
    parent = os.path.abspath(directory)
    for _ in range(4):
        parent = os.path.dirname(parent)
        if not parent or parent == os.path.dirname(parent):
            break
        roots.append(_store(parent))
    if ws:
        roots.append(_store(ws))
    for root in roots:
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                path = os.path.join(root, name)
                if os.path.isdir(path):
                    yield path


def _resolve(directory, link, ws=None):
    for path in _locations(directory, ws):
        try:
            manifest = kernel.read_manifest(path)
            if manifest['root'] == link['root'] and manifest['name'] == link['component']:
                return path
        except kernel.ClaimError:
            continue
    return None


def _links(directory):
    manifest = kernel.read_manifest(directory)
    if 'components' in manifest:
        return manifest['components']
    sidecar = os.path.join(directory, '.reticuli', 'components.json')
    if os.path.isfile(sidecar):
        from ._util import read_json
        return read_json(sidecar)
    return []


def seal_with(directory, *, components=None, proof=None):
    previous = {}
    try:
        previous = kernel.read_manifest(directory)
    except kernel.ClaimError:
        pass
    manifest = kernel.seal(directory)
    if components is None:
        components = previous.get('components')
    if proof is None:
        proof = previous.get('proof')
    if components:
        manifest['components'] = components
        from ._util import write_json
        write_json(os.path.join(directory, '.reticuli', 'components.json'), components)
    if proof:
        manifest['proof'] = proof
    from ._util import write_json
    write_json(os.path.join(directory, kernel.MANIFEST), manifest)
    return manifest


def claims(ws):
    rows = []
    for path in _locations(ws):
        try:
            m = kernel.read_manifest(path)
            rows.append({'name': m['name'], 'root': m['root'], 'path': path,
                         'phase': kernel.phase(path)})
        except kernel.ClaimError:
            pass
    return rows


def deps(ws):
    rows = []
    for claim in claims(ws):
        path = claim['path']
        links = []
        for link in _links(path):
            actual = _resolve(path, link, ws)
            status = 'unresolved' if actual is None else 'ok'
            if actual:
                try:
                    if kernel._hash_file(os.path.join(path, link['input'])) != kernel._hash_file(os.path.join(actual, link['output'])):
                        status = 'attribution mismatch'
                except kernel.ClaimError:
                    status = 'attribution mismatch'
            links.append(dict(link, status=status))
        rows.append(dict(claim, depends_on=links))
    return {'claims': rows}


def detect_components(ws, inputs):
    found = []
    for name in inputs:
        source = os.path.join(ws, name)
        digest = kernel._hash_file(source)
        for row in claims(ws):
            path = row['path']
            recipe = kernel.load_recipe(path)
            for step in recipe.get('step', []):
                output = step['output']
                target = os.path.join(path, output)
                if os.path.isfile(target) and kernel._hash_file(target) == digest:
                    found.append({'input': name, 'component': row['name'],
                                  'root': row['root'], 'output': output})
                    break
    return found


def _closure(directory, ws=None):
    seen = {}
    def visit(path):
        for link in _links(path):
            target = _resolve(directory, link, ws) or _resolve(path, link, ws)
            if target is None:
                raise kernel.ClaimError('unresolved component ' + link['component'])
            root = link['root']
            if root not in seen:
                seen[root] = target
                visit(target)
    visit(directory)
    return seen


def sign_root(directory, ws=None):
    memo = {}
    def fold(path):
        manifest = kernel.read_manifest(path)
        root = manifest['root']
        if root in memo:
            return memo[root]
        links = []
        for link in _links(path):
            child = _resolve(directory, link, ws) or _resolve(path, link, ws)
            if child is None:
                raise kernel.ClaimError('unresolved component ' + link['component'])
            links.append(fold(child))
        result = kernel.sign_node(root, kernel.build_digest(path), links)
        memo[root] = result
        return result
    return fold(directory)


def _claim_files(path, *, generated=True):
    from ._kernel import recipe as recipe_module
    r = kernel.load_recipe(path)
    names = [os.path.basename(recipe_module.recipe_path(path)), *declared_inputs(path)]
    for step in r.get('step', []):
        if generated or step.get('class', 'generated' if step['kind'] == 'produce' else 'pinned') != 'generated':
            names.append(step['output'])
    return list(dict.fromkeys(n for n in names if os.path.isfile(os.path.join(path, n))))


def _copy_claim(source, target, *, generated=True):
    os.makedirs(target, exist_ok=True)
    for name in _claim_files(source, generated=generated):
        copy_into(os.path.join(source, name), os.path.join(target, name))
    copy_into(os.path.join(source, kernel.MANIFEST), os.path.join(target, kernel.MANIFEST))
    sidecar = os.path.join(source, '.reticuli', 'components.json')
    if os.path.isfile(sidecar):
        copy_into(sidecar, os.path.join(target, '.reticuli', 'components.json'))


def pull(directory, ws):
    closure = _closure(directory, ws)
    store = _store(ws)
    os.makedirs(store, exist_ok=True)
    for path in [*closure.values(), directory]:
        name = kernel.read_manifest(path)['name']
        target = os.path.join(store, name)
        if not os.path.exists(target):
            _copy_claim(path, target)
    for root, path in closure.items():
        target = os.path.join(store, kernel.read_manifest(path)['name'])
        for name in _claim_files(path):
            copy_into(os.path.join(path, name), os.path.join(target, name))
    for name in _claim_files(directory):
        copy_into(os.path.join(directory, name), os.path.join(ws, name))
    return {'materialized': True, 'root': kernel.read_manifest(directory)['root']}


def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    rows = []
    visited = set()
    try:
        closure = _closure(directory, ws)
    except kernel.ClaimError:
        closure = {}
    def walk(path, ancestry):
        for link in _links(path):
            root = link['root']
            if root in visited:
                continue
            visited.add(root)
            component = closure.get(root) or _resolve(path, link, ws)
            if component is None:
                rows.append({'name': link['component'], 'root': root, 'ok': False,
                             'status': 'unresolved', 'bytes_from': [link['input']]})
                continue
            associated = [x for x in _links(path) if x['root'] == root]
            with tempfile.TemporaryDirectory(prefix='reticuli-layer-') as room:
                _copy_claim(component, room)
                valid = True
                for edge in associated:
                    source = os.path.join(path, edge['input'])
                    expected = os.path.join(component, edge['output'])
                    try:
                        generated = any(s['output'] == edge['output'] and
                                        s.get('class', 'generated' if s['kind'] == 'produce' else 'pinned') == 'generated'
                                        for s in kernel.load_recipe(component).get('step', []))
                        match = (generated and not os.path.isfile(expected)) or \
                                kernel._hash_file(source) == kernel._hash_file(expected)
                        if not match:
                            valid = False
                        copy_into(source, os.path.join(room, edge['output']))
                    except kernel.ClaimError:
                        valid = False
                try:
                    audit = kernel.audit(room)
                    healthy = valid and audit['ok']
                except kernel.ClaimError:
                    healthy = False
                rows.append({'name': link['component'], 'root': root, 'ok': healthy,
                             'status': 'ok' if healthy else 'attribution or audit failed',
                             'bytes_from': [x['input'] for x in associated]})
                # Descendants resolve from the flat store. Their claimed bytes are
                # supplied by the parent room, including its inherited overlay.
                walk(room, ancestry + [path])
    walk(directory, [])
    return {'ok': own['ok'] and all(x['ok'] for x in rows), 'root': own.get('root'),
            'layers': rows, 'audit': own}


def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    closure = _closure(directory, ws)
    built = {}
    rebuilt = []
    for root, source in closure.items():
        if reuse:
            built[root] = source
            continue
        dest = tempfile.mkdtemp(prefix='reticuli-component-')
        os.rmdir(dest)
        own_links = _links(source)
        produced = {x['input']: os.path.join(built[x['root']], x['output']) for x in own_links
                    if x['root'] in built}
        from_steps = {s['output'] for s in kernel.load_recipe(source).get('step', []) if 'from' in s}
        kernel.rebuild(source, producer, dest,
                       produce_from={k: v for k, v in produced.items() if k in from_steps},
                       input_from={k: v for k, v in produced.items() if k in declared_inputs(source)})
        seal_with(dest, components=own_links)
        built[root] = dest
        rebuilt.append({'component': kernel.read_manifest(source)['name'], 'root': root})
    links = _links(directory)
    mapping = {x['input']: os.path.join(built[x['root']], x['output']) for x in links if x['root'] in built}
    from_steps = {s['output'] for s in kernel.load_recipe(directory).get('step', []) if 'from' in s}
    result = kernel.rebuild(directory, producer, into,
                            produce_from={k: v for k, v in mapping.items() if k in from_steps},
                            input_from={k: v for k, v in mapping.items() if k in declared_inputs(directory)})
    seal_with(into, components=links)
    depsdir = os.path.join(into, '.reticuli', 'deps')
    for root, source in closure.items():
        _copy_claim(built[root], os.path.join(depsdir, kernel.read_manifest(source)['name']))
    result['rebuilt_components'] = rebuilt
    return result


def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    reports = [audit_deep(x) for x in (m1, m2, m3)]
    if not all(x['ok'] for x in reports):
        result['satisfied'] = False
        result['verdict'] = 'reject'
        result['rejected'].append('composed audit')
    result['layers'] = reports
    return result


def structure(directory, ws=None):
    return {'root': kernel.read_manifest(directory)['root'], 'dependencies': deps(ws or directory)}

"""Content-addressed component links and composed claim operations."""
import os
import shutil
import tempfile

from . import kernel
from ._util import copy_into, declared_inputs, safe_path, write_json
from ._kernel import recipe

def _store(ws):
    return os.path.join(ws, '.reticuli', 'sealed')

def _workspace(directory, ws=None):
    if ws:
        return ws
    path = os.path.abspath(directory)
    while True:
        if os.path.isdir(_store(path)):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return directory
        path = parent

def _component(directory, name, ws=None):
    for base in (os.path.join(directory, '.reticuli', 'sealed'),
                 os.path.join(directory, '.reticuli', 'deps'), _store(_workspace(directory, ws))):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            return path
    raise kernel.ClaimError('missing declared component: ' + name)

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
    root = _store(ws)
    if not os.path.isdir(root):
        return result
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            try:
                m = kernel.read_manifest(path)
                result.append({'name': m['name'], 'root': m['root'], 'phase': kernel.phase(path), 'path': path})
            except kernel.ClaimError:
                continue
    return result

def detect_components(ws, inputs):
    links = []
    for inp in inputs:
        target = safe_path(ws, inp)
        if not os.path.isfile(target):
            continue
        for row in claims(ws):
            path = row['path']
            parsed = kernel.load_recipe(path)
            for step in parsed.get('step', []):
                output = step['output']
                candidate = safe_path(path, output)
                if os.path.isfile(candidate) and kernel._hash_file(target) == kernel._hash_file(candidate):
                    links.append({'input': inp, 'component': row['name'], 'root': row['root'], 'output': output})
    return links

def deps(ws):
    result = []
    for row in claims(ws):
        path = row['path']
        edges = []
        for link in kernel.read_manifest(path).get('components', []):
            try:
                component = _component(path, link['component'], ws)
                status = 'ok' if kernel.verify(component)['root'] == link['root'] else 'mismatch'
            except kernel.ClaimError:
                status = 'unresolved'
            edges.append({**link, 'status': status})
        result.append({**row, 'depends_on': edges})
    return {'claims': result}

def sign_root(directory, ws=None, _seen=None):
    seen = set() if _seen is None else _seen
    directory = os.path.realpath(directory)
    if directory in seen:
        raise kernel.ClaimError('component cycle')
    seen.add(directory)
    verified = kernel.verify(directory)
    if not verified['ok']:
        raise kernel.ClaimError('claim identity mismatch')
    links = []
    for link in kernel.read_manifest(directory).get('components', []):
        component = _component(directory, link['component'], ws)
        if kernel.verify(component)['root'] != link['root']:
            raise kernel.ClaimError('component root mismatch')
        links.append(sign_root(component, ws, seen))
    seen.remove(directory)
    return kernel.sign_node(verified['root'], kernel.build_digest(directory), links)

def pull(directory, ws):
    parsed = kernel.load_recipe(directory)
    names = [os.path.basename(recipe.recipe_path(directory)), *declared_inputs(parsed, directory),
             *(s['output'] for s in parsed.get('step', []))]
    for name in names:
        src = safe_path(directory, name)
        if os.path.isfile(src):
            copy_into(src, safe_path(ws, name))
    return {'materialized': True, 'root': kernel.verify(directory)['root']}

def rebuild_chain(directory, producer, into, *, ws=None, reuse=False):
    manifest = kernel.read_manifest(directory)
    components = manifest.get('components', [])
    produce_from = {}
    input_from = {}
    rebuilt = []
    for link in components:
        source = _component(directory, link['component'], ws)
        if kernel.verify(source)['root'] != link['root']:
            raise kernel.ClaimError('component root mismatch')
        if reuse:
            built = source
        else:
            with tempfile.TemporaryDirectory(prefix='reticuli-component-') as room:
                # A component with no generated outputs needs only its existing bytes.
                if any(s['kind'] == 'produce' and s.get('class', 'generated') == 'generated'
                       for s in kernel.load_recipe(source).get('step', [])):
                    kernel.rebuild(source, producer, room)
                    built = source  # component bytes are equivalent and source is retained as provenance
                else:
                    built = source
        output = link['output']
        if 'input' in link:
            input_from[link['input']] = safe_path(built, output)
        if any(s.get('output') == output and s.get('kind') == 'produce'
               for s in kernel.load_recipe(directory).get('step', [])):
            produce_from[output] = safe_path(built, output)
        rebuilt.append({'component': link['component'], 'root': link['root']})
    outputs = [s['output'] for s in kernel.load_recipe(directory).get('step', [])
               if s['kind'] == 'produce' and s.get('class', 'generated') == 'generated'
               and s['output'] not in produce_from]
    commands = []
    for output in outputs:
        if "'" in output:
            raise kernel.ClaimError('unsupported output name for producer')
        commands.append("RETICULI_OUTPUT=\"$PWD/" + output + "\"; export RETICULI_OUTPUT; " + producer)
    result = kernel.rebuild(directory, '; '.join(commands) if commands else 'true', into, produce_from=produce_from,
                            input_from=input_from)
    if components:
        m = kernel.read_manifest(into)
        m['components'] = components
        write_json(os.path.join(into, kernel.MANIFEST), m)
        dep_base = os.path.join(into, '.reticuli', 'deps')
        for link in components:
            source = _component(directory, link['component'], ws)
            target = os.path.join(dep_base, link['component'])
            if not os.path.isdir(target):
                shutil.copytree(source, target)
    result['rebuilt_components'] = rebuilt
    return result

def audit_deep(directory, ws=None):
    own = kernel.audit(directory)
    layers = []
    for link in kernel.read_manifest(directory).get('components', []):
        name = link['component']
        try:
            component = _component(directory, name, ws)
            parsed = kernel.load_recipe(directory)
            from_outputs = [s['output'] for s in parsed.get('step', [])
                            if s.get('from') == name]
            supplied = {output: safe_path(directory, output) for output in from_outputs}
            row = kernel.audit(component, produce_from=supplied)
            row.update({'name': name, 'bytes_from': from_outputs, 'status': 'ok' if row['ok'] else 'failed'})
            if row['root'] != link['root']:
                row['ok'] = False
        except kernel.ClaimError:
            row = {'name': name, 'root': link['root'], 'ok': False, 'status': 'unresolved', 'bytes_from': []}
        layers.append(row)
    return {**own, 'ok': own['ok'] and all(x['ok'] for x in layers), 'layers': layers}

def crosscheck_deep(m1, m2, m3):
    result = kernel.crosscheck(m1, m2, m3)
    audits = [audit_deep(x) for x in (m1, m2, m3)]
    result['deep_audits'] = audits
    result['satisfied'] = result['satisfied'] and all(a['ok'] for a in audits)
    return result

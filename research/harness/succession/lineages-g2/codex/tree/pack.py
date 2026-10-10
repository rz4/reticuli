"""Turn a project into a claim whose implementation is generated."""
from __future__ import annotations
import glob
import os
import shutil
from . import kernel, registry, render
from ._kernel import core


def _expand(directory, patterns):
    found = set()
    for pattern in patterns:
        # Glob expansion is an authoring operation; the resulting recipe has fixed paths.
        for path in glob.glob(os.path.join(directory, pattern), recursive=True):
            if os.path.isfile(path):
                name = os.path.relpath(path, directory).replace(os.sep, '/')
                core._safe(directory, name)
                found.add(name)
    return sorted(found)


def _warm_gate(directory, recipe, command, output):
    bad = kernel.vacuous_gates(recipe)
    if bad:
        raise kernel.ClaimError('vacuous gate: ' + ', '.join(bad))
    result = kernel.run_gate(command, directory, recipe)
    if result['status'] != 'ok':
        raise kernel.ClaimError('gate failed: ' + result.get('stderr', ''))
    core._hash_file(core._safe(directory, output))


def _carry(directory, component):
    if not component:
        return [], {}
    name, source = component['name'], os.path.realpath(component['claim'])
    manifest = kernel.read_manifest(source)
    if manifest['name'] != name or not kernel.verify(source)['ok']:
        raise kernel.ClaimError('invalid component claim')
    target_store = os.path.join(directory, kernel.STORE, 'sealed')
    target = os.path.join(target_store, name)
    os.makedirs(target_store, exist_ok=True)
    if os.path.lexists(target):
        if os.path.islink(target): os.unlink(target)
        else: shutil.rmtree(target)
    registry._copy_claim(source, target)
    # Ancestors are shared by reference, so growth follows the number of layers.
    source_store = os.path.join(source, kernel.STORE, 'sealed')
    if os.path.isdir(source_store):
        for ancestor in os.listdir(source_store):
            link = os.path.join(target_store, ancestor)
            if not os.path.lexists(link):
                os.symlink(os.path.realpath(os.path.join(source_store, ancestor)), link)
    links = []
    supplied = {}
    for output in component.get('outputs', []):
        core._safe(directory, output)
        core._safe(source, output)
        if core._hash_file(core._safe(directory, output)) != core._hash_file(core._safe(source, output)):
            raise kernel.ClaimError('component output differs: ' + output)
        links.append({'input': output, 'component': name, 'output': output, 'root': manifest['root']})
        supplied[output] = name
    return links, supplied


def pack(directory, name, generated, inputs, gate, gate_output, *, envelope=None,
         claim_format=3, component=None, mutation_floor=None, requires=None,
         by=None, inputs_manifest=None, environment=None):
    directory = os.path.realpath(os.fspath(directory))
    generated_files = _expand(directory, generated)
    input_files = _expand(directory, inputs)
    links, supplied = _carry(directory, component)
    claim = {'name': name}
    if claim_format != 1: claim['format'] = claim_format
    if inputs_manifest is not None:
        core._safe(directory, inputs_manifest)
        listing = ''.join(core._hash_file(core._safe(directory, path)) + '  ' + path + '\n' for path in input_files)
        with open(core._safe(directory, inputs_manifest), 'w', encoding='utf-8') as stream:
            stream.write(listing)
    else:
        claim['inputs'] = input_files
    if envelope is not None: claim['envelope'] = envelope
    if mutation_floor is not None: claim['mutation_floor'] = mutation_floor
    if requires is not None: claim['requires'] = requires
    if inputs_manifest is not None: claim['inputs_manifest'] = inputs_manifest
    if environment is not None:
        core._hash_file(core._safe(directory, environment))
        claim['environment'] = environment
    guidance_key = 'request' if claim_format == 1 else 'guidance'
    steps = []
    for path in generated_files:
        step = {'kind': 'produce', 'output': path, 'class': 'generated'}
        if path in supplied: step['from'] = supplied[path]
        else: step[guidance_key] = 'regenerate ' + path + ' to pass the gate'
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output, 'class': 'validated', 'run': gate})
    recipe = {'claim': claim, 'step': steps}
    with open(core._safe(directory, kernel.RECIPE), 'w', encoding='utf-8') as stream:
        stream.write(render.dump_recipe(recipe))
    _warm_gate(directory, recipe, gate, gate_output)
    sealed = registry.seal_with(directory, components=links)
    if by is not None:
        kernel.ledger(directory, {'event': 'producer', 'model': by})
    return {'ok': True, 'root': sealed['root'], 'path': directory}

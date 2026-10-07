"""Turn a project into a self-claim: checks are inputs, code is generated."""
import glob
import os
import shutil

from . import kernel, render, registry
from ._kernel import core


def _expand(directory, patterns):
    found = []
    for pattern in patterns or []:
        # Expand only existing files. The names written into identity are exact
        # directory entries, including case, on every host.
        for path in sorted(glob.glob(os.path.join(directory, pattern), recursive=True)):
            if os.path.isfile(path):
                name = os.path.relpath(path, directory).replace(os.sep, '/')
                core._safe(directory, name)
                if name not in found:
                    found.append(name)
    return found


def pack(root, name, generated, inputs, gate, gate_output,
         *, envelope=None, claim_format=3, component=None, mutation_floor=None,
         requires=None, by=None, inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    generated_names = _expand(root, generated)
    input_names = _expand(root, inputs)
    if environment is not None:
        core._hash_file(core._safe(root, environment))
    for name_in in input_names:
        core._hash_file(core._safe(root, name_in))
    generated_names = [n for n in generated_names if n not in input_names]
    component_names = set(component.get('outputs', [])) if component else set()
    if component:
        source = component['claim']
        if not kernel.verify(source)['ok']:
            raise kernel.ClaimError('component identity mismatch')
        target = os.path.join(root, kernel.STORE, 'sealed', component['name'])
        if os.path.realpath(source) != os.path.realpath(target):
            shutil.copytree(source, target, dirs_exist_ok=True)
        for output in component_names:
            core._safe(root, output)
            if output not in generated_names:
                generated_names.append(output)
    claim = {'name': name}
    if claim_format != 1:
        claim['format'] = claim_format
    if inputs_manifest:
        manifest = core._safe(root, inputs_manifest)
        os.makedirs(os.path.dirname(manifest), exist_ok=True)
        with open(manifest, 'w', encoding='utf-8') as stream:
            for path in input_names:
                stream.write(kernel._hash_file(core._safe(root, path)) + '  ' + path + '\n')
        claim['inputs_manifest'] = inputs_manifest
    else:
        claim['inputs'] = input_names
    if envelope is not None:
        claim['envelope'] = envelope
    if mutation_floor is not None:
        claim['mutation_floor'] = mutation_floor
    if requires is not None:
        claim['requires'] = requires
    if environment is not None:
        claim['environment'] = environment
    hint_key = 'request' if claim_format < 3 else 'guidance'
    steps = []
    for output in generated_names:
        step = {'kind': 'produce', 'output': output, 'class': 'generated'}
        if output in component_names:
            step['from'] = component['name']
        else:
            step[hint_key] = f'regenerate {output} to pass the gate'
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output, 'class': 'validated', 'run': gate})
    parsed = {'claim': claim, 'step': steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    with open(os.path.join(root, kernel.RECIPE), 'w', encoding='utf-8') as stream:
        stream.write(render.dump_recipe(parsed))
    result = kernel.run_gate(gate, root, parsed)
    if result['status'] != 'ok':
        raise kernel.ClaimError('gate failed: ' + result.get('stderr', ''))
    core._hash_file(core._safe(root, gate_output))
    links = None
    if component:
        source = component['claim']
        source_recipe = kernel.load_recipe(source)
        links = []
        for output in component_names:
            links.append({'input': output, 'component': component['name'],
                          'root': kernel.verify(source)['root'], 'output': output})
    manifest = registry.seal_with(root, components=links) if links is not None else kernel.seal(root)
    if by:
        kernel.ledger(root, {'event': 'producer', 'model': by})
    return {'ok': True, 'root': manifest['root']}

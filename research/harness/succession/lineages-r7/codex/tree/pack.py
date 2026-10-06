"""Make an existing project into a claim whose implementation is generated."""
from __future__ import annotations

import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path


def _expand(root, patterns):
    names = []
    for pattern in patterns:
        safe_path(root, pattern)
        matches = glob.glob(os.path.join(root, pattern), recursive=True)
        for path in matches:
            name = os.path.relpath(path, root).replace(os.sep, '/')
            if os.path.isfile(path):
                safe_path(root, name)
                names.append(name)
    return list(dict.fromkeys(sorted(names)))


def _write_recipe(root, recipe):
    with open(os.path.join(root, kernel.RECIPE), 'w', encoding='utf-8') as target:
        target.write(render.dump_recipe(recipe))


def pack(root, name, generated, inputs, gate, gate_output,
         *, envelope=None, claim_format=3, component=None,
         mutation_floor=None, requires=None, by=None, inputs_manifest=None,
         environment=None):
    root = os.path.abspath(root)
    generated_names = _expand(root, generated)
    input_names = _expand(root, inputs)
    if environment is not None:
        path = safe_path(root, environment)
        if not os.path.isfile(path):
            raise kernel.ClaimError(f'missing environment file: {environment}')
    if not generated_names:
        raise kernel.ClaimError('no generated files matched')
    for filename in input_names:
        if filename in generated_names:
            raise kernel.ClaimError(f'file is both input and generated: {filename}')
    safe_path(root, gate_output)
    claim = {'name': name}
    if claim_format != 1:
        claim['format'] = claim_format
    if inputs_manifest:
        if claim_format < 2:
            raise kernel.ClaimError('inputs_manifest requires format 2')
        manifest = safe_path(root, inputs_manifest)
        with open(manifest, 'w', encoding='utf-8') as target:
            for filename in input_names:
                target.write(f'{kernel._hash_file(safe_path(root, filename))}  {filename}\n')
        claim['inputs_manifest'] = inputs_manifest
    else:
        claim['inputs'] = input_names
    if environment is not None:
        claim['environment'] = environment
    if envelope is not None:
        claim['envelope'] = envelope
    if mutation_floor is not None:
        claim['mutation_floor'] = mutation_floor
    if requires is not None:
        claim['requires'] = requires
    component_outputs = set(component.get('outputs', [])) if component else set()
    steps = []
    for filename in generated_names:
        step = {'kind': 'produce', 'output': filename, 'class': 'generated'}
        if filename in component_outputs:
            step['from'] = component['name']
        else:
            hint = f'regenerate {filename} to pass the gate'
            step['request' if claim_format == 1 else 'guidance'] = hint
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output,
                  'class': 'validated', 'run': gate})
    recipe = {'claim': claim, 'step': steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    _write_recipe(root, recipe)
    result = kernel.run_gate(gate, root, recipe)
    if result['status'] != 'ok':
        raise kernel.ClaimError('gate did not pass: ' + result.get('stderr', result['status']))
    if not os.path.isfile(safe_path(root, gate_output)):
        raise kernel.ClaimError(f'gate did not write verdict: {gate_output}')
    if component:
        comp_name = component['name']
        source = os.path.abspath(component['claim'])
        target = os.path.join(root, kernel.STORE, 'sealed', comp_name)
        if os.path.realpath(source) != os.path.realpath(target):
            shutil.copytree(source, target, dirs_exist_ok=True)
        links = [{'input': filename, 'component': comp_name,
                  'root': kernel.verify(source)['root'], 'output': filename}
                 for filename in component_outputs]
        manifest = registry.seal_with(root, components=links)
    else:
        manifest = kernel.seal(root)
    if by:
        kernel.ledger(root, {'event': 'producer', 'model': by})
    return {'ok': True, 'root': manifest['root'], 'name': name}

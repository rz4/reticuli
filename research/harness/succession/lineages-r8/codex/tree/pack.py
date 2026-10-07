"""Make a project into a claim with its implementation generated."""
from __future__ import annotations

import glob
import os
import shutil
from . import kernel, registry, render
from ._util import safe_path, ledger_add


def _names(root, patterns):
    found = []
    for pattern in patterns:
        safe_path(root, pattern)
        for path in sorted(glob.glob(os.path.join(root, pattern), recursive=True)):
            name = os.path.relpath(path, root).replace(os.sep, '/')
            if os.path.isfile(path) and name not in found:
                safe_path(root, name)
                found.append(name)
    return found


def pack(root, name, generated, inputs, gate, gate_output, *, envelope=None,
         claim_format=3, component=None, mutation_floor=None, requires=None,
         by=None, inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    produced = _names(root, generated)
    pinned = _names(root, inputs)
    if environment is not None:
        path = safe_path(root, environment)
        if not os.path.isfile(path):
            raise kernel.ClaimError(f'missing environment: {environment}')
    safe_path(root, gate_output)
    if set(produced) & set(pinned):
        raise kernel.ClaimError('generated and pinned paths overlap')
    if component:
        component_name = component['name']
        source = os.path.abspath(component['claim'])
        verified = kernel.verify(source)
        if not verified['ok']:
            raise kernel.ClaimError('component identity mismatch')
        outputs = set(component.get('outputs', []))
    else:
        component_name = None
        outputs = set()
    claim = {'name': name}
    if claim_format != 1:
        claim['format'] = claim_format
    if inputs_manifest:
        manifest_path = safe_path(root, inputs_manifest)
        lines = [f'{kernel._hash_file(safe_path(root, item))}  {item}' for item in pinned]
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as stream:
            stream.write('\n'.join(lines) + ('\n' if lines else ''))
        claim['inputs_manifest'] = inputs_manifest
    elif pinned:
        claim['inputs'] = pinned
    if envelope is not None:
        claim['envelope'] = envelope
    if mutation_floor is not None:
        claim['mutation_floor'] = float(mutation_floor)
    if requires is not None:
        claim['requires'] = requires
    if environment is not None:
        claim['environment'] = environment
    steps = []
    for item in produced:
        step = {'kind': 'produce', 'output': item, 'class': 'generated'}
        if item in outputs:
            step['from'] = component_name
        else:
            step['request' if claim_format == 1 else 'guidance'] = f'regenerate {item} to pass the gate'
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output, 'class': 'validated', 'run': gate})
    recipe = {'claim': claim, 'step': steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    with open(os.path.join(root, kernel.RECIPE), 'w', encoding='utf-8') as stream:
        stream.write(render.dump_recipe(recipe))
    result = kernel.run_gate(gate, root, recipe)
    if result['status'] != 'ok' or not os.path.isfile(safe_path(root, gate_output)):
        raise kernel.ClaimError(f'gate failed: {result["status"]}: {result["stderr"]}')
    links = []
    if component:
        destination = os.path.join(root, kernel.STORE, 'sealed', component_name)
        if os.path.realpath(destination) != os.path.realpath(source):
            if os.path.exists(destination):
                shutil.rmtree(destination)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copytree(source, destination)
        for item in produced:
            if item in outputs:
                links.append({'input': item, 'component': component_name,
                              'root': verified['root'], 'output': item})
    sealed = registry.seal_with(root, components=links) if links else kernel.seal(root)
    if not kernel.audit(root)['ok']:
        raise kernel.ClaimError('gate verdict cannot be re-earned cold')
    if by:
        ledger_add(root, {'event': 'producer', 'model': by})
    return {'ok': True, 'root': sealed['root'], 'name': name}

"""Declare a project's checks as a claim and its implementation as generated."""
import glob
import os
import shutil

from . import kernel, registry, render
from ._util import safe_path


def _expand(workspace, patterns):
    names = []
    for pattern in patterns:
        safe_path(workspace, pattern)
        matches = glob.glob(os.path.join(workspace, pattern), recursive=True)
        for path in matches:
            if os.path.isfile(path):
                name = os.path.relpath(path, workspace).replace(os.sep, '/')
                safe_path(workspace, name)
                if name not in names:
                    names.append(name)
    return sorted(names)


def pack(workspace, name, generated, inputs, gate, gate_output, *,
         envelope=None, claim_format=3, component=None, mutation_floor=None,
         requires=None, by=None, inputs_manifest=None, environment=None):
    made = _expand(workspace, generated)
    pinned = _expand(workspace, inputs)
    if environment is not None:
        path = safe_path(workspace, environment)
        kernel._hash_file(path)
    if gate_output in made or gate_output in pinned:
        raise kernel.ClaimError('gate output overlaps a declared file')
    safe_path(workspace, gate_output)
    if inputs_manifest:
        safe_path(workspace, inputs_manifest)
        with open(os.path.join(workspace, inputs_manifest), 'w', encoding='utf-8') as stream:
            for path in pinned:
                stream.write(f'{kernel._hash_file(safe_path(workspace, path))}  {path}\n')
    claim = {'name': name}
    if claim_format != 1:
        claim['format'] = claim_format
    if inputs_manifest:
        claim['inputs_manifest'] = inputs_manifest
    else:
        claim['inputs'] = pinned
    if envelope is not None:
        claim['envelope'] = envelope
    if mutation_floor is not None:
        claim['mutation_floor'] = mutation_floor
    if requires is not None:
        claim['requires'] = requires
    if environment is not None:
        claim['environment'] = environment
    supplied = set(component.get('outputs', [])) if component else set()
    steps = []
    for path in made:
        step = {'kind': 'produce', 'output': path, 'class': 'generated'}
        if path in supplied:
            step['from'] = component['name']
        else:
            key = 'request' if claim_format == 1 else 'guidance'
            step[key] = f'regenerate {path} to pass the gate'
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output, 'class': 'validated', 'run': gate})
    parsed = {'claim': claim, 'step': steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    if os.path.exists(os.path.join(workspace, gate_output)):
        os.unlink(os.path.join(workspace, gate_output))
    result = kernel.run_gate(gate, workspace, parsed)
    if result['status'] != 'ok':
        raise kernel.ClaimError('gate failed: ' + result.get('stderr', ''))
    kernel._hash_file(safe_path(workspace, gate_output))
    with open(os.path.join(workspace, kernel.RECIPE), 'w', encoding='utf-8') as stream:
        stream.write(render.dump_recipe(parsed))
    links = []
    if component:
        source = component['claim']
        checked = kernel.verify(source)
        if not checked['ok']:
            raise kernel.ClaimError('component identity mismatch')
        for path in supplied:
            if path not in made:
                raise kernel.ClaimError('component output is not declared generated')
            links.append({'input': path, 'component': component['name'],
                          'root': checked['root'], 'output': path})
        destination = os.path.join(workspace, kernel.STORE, 'sealed', component['name'])
        if os.path.exists(destination):
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    sealed = registry.seal_with(workspace, components=links if component else None)
    if by is not None:
        kernel.ledger(workspace, {'event': 'producer', 'model': by})
    return {'ok': True, 'root': sealed['root']}

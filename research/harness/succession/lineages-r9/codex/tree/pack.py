"""Pack a project as a self-claim: implementation generated, check pinned."""
from __future__ import annotations
import glob
import os
import shutil
from . import kernel, render, registry


def _expand(directory, patterns):
    names = []
    for pattern in patterns:
        if not isinstance(pattern, str) or os.path.isabs(pattern) or '..' in pattern.replace('\\', '/').split('/'):
            raise kernel.ClaimError('unsafe pack pattern: ' + repr(pattern))
        matches = glob.glob(pattern, root_dir=directory, recursive=True)
        if not matches and not glob.has_magic(pattern):
            matches = [pattern]
        for name in sorted(matches):
            full = os.path.join(directory, name)
            if not os.path.isfile(full) or os.path.islink(full):
                raise kernel.ClaimError('missing or unsafe pack file: ' + name)
            if name not in names:
                names.append(name)
    return names


def pack(root, name, generated, inputs, gate, gate_output, *, envelope=None,
         claim_format=3, component=None, mutation_floor=None, requires=None,
         by=None, inputs_manifest=None, environment=None):
    root = os.path.abspath(root)
    generated_names = _expand(root, generated)
    pinned = _expand(root, inputs)
    if environment is not None:
        env_name = _expand(root, [environment])
        if not env_name:
            raise kernel.ClaimError('missing environment file: ' + environment)
    if set(generated_names) & set(pinned):
        raise kernel.ClaimError('a file cannot be both generated and pinned')
    if not pinned:
        deciders = kernel.gate_deciders(gate)
        if deciders and all(d in generated_names for d in deciders):
            raise kernel.ClaimError('vacuous gate: every decider is generated')
    if inputs_manifest:
        if os.path.isabs(inputs_manifest) or '..' in inputs_manifest.split('/'):
            raise kernel.ClaimError('unsafe inputs manifest path')
        manifest_path = os.path.join(root, inputs_manifest)
        os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
        with open(manifest_path, 'w', encoding='utf-8') as dest:
            for path in sorted(pinned):
                dest.write(f'{kernel._hash_file(os.path.join(root, path))}  {path}\n')
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
    supplied = set()
    links = []
    if component:
        cname = component['name']
        child = component['claim']
        checked = kernel.verify(child)
        if not checked['ok']:
            raise kernel.ClaimError('component identity mismatch')
        for path in component['outputs']:
            if path not in generated_names:
                raise kernel.ClaimError('component output is not declared generated: ' + path)
            source = os.path.join(child, path)
            target = os.path.join(root, path)
            if kernel._hash_file(source) != kernel._hash_file(target):
                raise kernel.ClaimError('component output differs: ' + path)
            supplied.add(path)
            links.append({'component': cname, 'root': checked['root'],
                          'input': path, 'output': path})
    guidance_key = 'request' if claim_format == 1 else 'guidance'
    steps = []
    for path in generated_names:
        step = {'kind': 'produce', 'output': path, 'class': 'generated'}
        if path in supplied:
            step['from'] = component['name']
        else:
            step[guidance_key] = f'regenerate {path} to pass the gate'
        steps.append(step)
    steps.append({'kind': 'gate', 'output': gate_output,
                  'class': 'validated', 'run': gate})
    parsed = {'claim': claim, 'step': steps}
    # The warm gate may read its recipe. Write it before asking for a verdict.
    recipe_path = os.path.join(root, kernel.RECIPE)
    with open(recipe_path, 'w', encoding='utf-8') as dest:
        dest.write(render.dump_recipe(parsed))
    result = kernel.run_gate(gate, root, parsed)
    if result['status'] != 'ok':
        raise kernel.ClaimError('pack gate failed: ' + repr(result))
    output = os.path.join(root, gate_output)
    if not os.path.isfile(output):
        raise kernel.ClaimError('pack gate did not write verdict: ' + gate_output)
    sealed = kernel.seal(root)
    if component:
        target = os.path.join(root, kernel.STORE, 'sealed', component['name'])
        shutil.copytree(component['claim'], target, dirs_exist_ok=True)
        registry.seal_with(root, components=links)
    if by:
        kernel.ledger(root, {'event': 'producer', 'model': by, 'blind': False})
    return {'ok': True, **sealed}

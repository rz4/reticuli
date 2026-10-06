"""Turn a traced work session into a cold-certified claim."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path

TRACE = '.reticuli/draft.jsonl'


def _events(workspace):
    path = os.path.join(workspace, TRACE)
    try:
        with open(path, encoding='utf-8') as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError) as error:
        raise kernel.ClaimError(f'cannot read session trace: {error}') from error


def _exact_file(workspace, name):
    """Check directory entries literally, including case on folded filesystems."""
    try:
        safe_path(workspace, name)
    except kernel.ClaimError:
        return False
    current = workspace
    for part in name.split('/'):
        if part not in os.listdir(current):
            return False
        current = os.path.join(current, part)
    return os.path.isfile(current)


def propose(workspace, outputs, name=None, *, claim=None, generated=None):
    workspace = os.path.abspath(workspace)
    events = _events(workspace)
    commands = [event['cmd'] for event in events if event.get('event') == 'bash' and isinstance(event.get('cmd'), str)]
    if not commands:
        raise kernel.ClaimError('session has no gate command')
    for output in outputs:
        safe_path(workspace, output)
    traced_writes = [event['path'] for event in events if event.get('event') == 'write' and isinstance(event.get('path'), str)]
    generated_names = list(dict.fromkeys(traced_writes + list(generated or [])))
    claimed = set(claim or [])
    generated_names = [item for item in generated_names if item not in claimed and item not in outputs]
    inputs = list(claim or [])
    inputs += [event['path'] for event in events if event.get('event') == 'read' and isinstance(event.get('path'), str)]
    for command in commands:
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        for token in tokens:
            if token not in generated_names and token not in outputs and _exact_file(workspace, token):
                inputs.append(token)
    inputs = list(dict.fromkeys(inputs))
    for filename in inputs + generated_names:
        safe_path(workspace, filename)
    steps = [{'kind': 'produce', 'output': item, 'class': 'generated',
              'guidance': f'regenerate {item} to pass the gate'} for item in generated_names]
    steps += [{'kind': 'gate', 'output': item, 'class': 'validated',
               'run': commands[-1]} for item in outputs]
    recipe = {'claim': {'name': name or os.path.basename(workspace), 'format': 3,
                        'inputs': inputs}, 'step': steps}
    return recipe


def _copy(source, target, name):
    from_path = safe_path(source, name)
    if not os.path.isfile(from_path):
        raise kernel.ClaimError(f'missing declared file: {name}')
    to_path = safe_path(target, name)
    os.makedirs(os.path.dirname(to_path), exist_ok=True)
    shutil.copy2(from_path, to_path)


def build_claim(workspace, outputs, into, *, name=None, claim=None, generated=None):
    workspace = os.path.abspath(workspace)
    recipe = propose(workspace, outputs, name, claim=claim, generated=generated)
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    # Validate every trace-derived path before any copy enters the destination.
    for filename in recipe['claim']['inputs'] + [step['output'] for step in recipe['step']]:
        safe_path(workspace, filename)
    into = os.path.abspath(into)
    os.makedirs(into, exist_ok=True)
    with open(os.path.join(into, kernel.RECIPE), 'w', encoding='utf-8') as target:
        target.write(render.dump_recipe(recipe))
    files = recipe['claim']['inputs'] + [step['output'] for step in recipe['step']]
    for filename in dict.fromkeys(files):
        _copy(workspace, into, filename)
    with tempfile.TemporaryDirectory(prefix='reticuli-authoring-') as room:
        shutil.copy2(os.path.join(into, kernel.RECIPE), os.path.join(room, kernel.RECIPE))
        for filename in recipe['claim']['inputs'] + [step['output'] for step in recipe['step'] if step['kind'] == 'produce']:
            _copy(into, room, filename)
        for step in recipe['step']:
            if step['kind'] != 'gate':
                continue
            result = kernel.run_gate(step['run'], room, recipe)
            if result['status'] != 'ok':
                raise kernel.ClaimError('cold gate did not pass: ' + result.get('stderr', result['status']))
            output = step['output']
            if kernel._hash_file(safe_path(room, output)) != kernel._hash_file(safe_path(into, output)):
                raise kernel.ClaimError(f'cold verdict did not reproduce: {output}')
    manifest = kernel.seal(into)
    events = _events(workspace)
    timestamps = [event['ts'] for event in events if isinstance(event.get('ts'), (int, float))]
    calls = sum(event.get('event') == 'prompt' for event in events)
    kernel.ledger(into, {'event': 'producer', 'calls': calls,
                         'seconds': max(timestamps) - min(timestamps) if timestamps else 0.0})
    return {'ok': True, 'root': manifest['root'], 'name': recipe['claim']['name']}

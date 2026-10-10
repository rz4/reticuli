"""Propose a claim from a session trace, then certify it cold."""
from __future__ import annotations
import json
import os
import shlex
import shutil
import tempfile
from . import kernel, render
from ._kernel import core

TRACE = '.reticuli/draft.jsonl'


def _events(directory):
    try:
        with open(os.path.join(directory, TRACE), encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError('cannot read session trace: ' + str(exc)) from exc


def _real_file(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name): return False
    try: path = core._safe(directory, name)
    except kernel.ClaimError: return False
    if not os.path.isfile(path): return False
    parent, base = os.path.dirname(path), os.path.basename(path)
    return base in os.listdir(parent)  # exact entry, even on a folding host


def _candidates(directory, command):
    try: words = shlex.split(command)
    except ValueError: return []
    return [word for word in words if _real_file(directory, word)]


def propose(directory, outputs, name=None, *, claim=None, generated=None):
    directory = os.path.realpath(os.fspath(directory))
    events = _events(directory)
    gates = [event['cmd'] for event in events if event.get('event') == 'bash' and isinstance(event.get('cmd'), str)]
    if not gates: raise kernel.ClaimError('session has no gate')
    command = gates[-1]
    output_set = set(outputs)
    written = set(generated or [])
    inputs = set(claim or [])
    for event in events:
        path = event.get('path')
        if event.get('event') in ('read', 'write') and isinstance(path, str):
            core._safe(directory, path)  # refuse escapes before any copying
            if event['event'] == 'read': inputs.add(path)
            else: written.add(path)
    for path in _candidates(directory, command):
        if path not in written and path not in output_set:
            inputs.add(path)
    inputs.difference_update(output_set)
    written.difference_update(output_set)
    written.difference_update(inputs)
    for path in inputs | written | output_set:
        core._safe(directory, path)
    if name is None: name = os.path.basename(directory)
    recipe = {'claim': {'name': name, 'format': 3, 'inputs': sorted(inputs)},
              'step': [{'kind': 'produce', 'output': path, 'class': 'generated',
                        'guidance': 'regenerate ' + path + ' to pass the gate'}
                       for path in sorted(written)] +
                      [{'kind': 'gate', 'output': path, 'class': 'validated', 'run': command}
                       for path in outputs]}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError('vacuous gate: all deciders are generated')
    return recipe


def build_claim(directory, outputs, into, name=None, *, claim=None, generated=None):
    directory = os.path.realpath(os.fspath(directory))
    recipe = propose(directory, outputs, name, claim=claim, generated=generated)
    into = os.path.realpath(os.fspath(into))
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError('claim destination is not empty')
    with tempfile.TemporaryDirectory(prefix='reticuli-author-') as room:
        with open(core._safe(room, kernel.RECIPE), 'w', encoding='utf-8') as stream:
            stream.write(render.dump_recipe(recipe))
        names = set(recipe['claim']['inputs']) | {s['output'] for s in recipe['step'] if s['kind'] == 'produce'}
        for path in names:
            core._copy_into(core._safe(directory, path), core._safe(room, path))
        for step in recipe['step']:
            if step['kind'] != 'gate': continue
            result = kernel.run_gate(step['run'], room, recipe)
            if result['status'] != 'ok':
                raise kernel.ClaimError('cold gate failed: ' + result.get('stderr', ''))
            source = core._safe(directory, step['output'])
            cold = core._safe(room, step['output'])
            if core._hash_file(source) != core._hash_file(cold):
                raise kernel.ClaimError('cold verdict differs: ' + step['output'])
        os.makedirs(into, exist_ok=True)
        for path in names | {s['output'] for s in recipe['step'] if s['kind'] == 'gate'}:
            core._copy_into(core._safe(room, path), core._safe(into, path))
        core._copy_into(core._safe(room, kernel.RECIPE), core._safe(into, kernel.RECIPE))
    sealed = kernel.seal(into)
    events = _events(directory)
    times = [e['ts'] for e in events if type(e.get('ts')) in (int, float)]
    kernel.ledger(into, {'event': 'session', 'calls': sum(e.get('event') == 'prompt' for e in events),
                         'seconds': max(times) - min(times) if times else 0.0})
    return {'ok': True, 'root': sealed['root'], 'path': into}

"""Turn a declared session boundary into a cold-certified claim."""
import json
import os
import shlex
import shutil
import tempfile

from . import kernel, render
from ._util import safe_path

TRACE = '.reticuli/draft.jsonl'


def _events(workspace):
    try:
        with open(os.path.join(workspace, TRACE), encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f'cannot read session trace: {exc}') from exc


def _exists_exact(workspace, name):
    try:
        path = safe_path(workspace, name)
        current = workspace
        for part in name.split('/'):
            if part not in os.listdir(current):
                return False
            current = os.path.join(current, part)
        return os.path.isfile(path)
    except (OSError, kernel.ClaimError):
        return False


def _tokens(command):
    try:
        return shlex.split(command)
    except ValueError:
        return []


def propose(workspace, outputs, name=None, *, claim=None, generated=None):
    events = _events(workspace)
    gates = [e['cmd'] for e in events if e.get('event') == 'bash' and isinstance(e.get('cmd'), str)]
    if not gates:
        raise kernel.ClaimError('session has no gate')
    outputs = list(dict.fromkeys(outputs))
    explicit_claim = set(claim or [])
    writes = {e['path'] for e in events if e.get('event') == 'write' and isinstance(e.get('path'), str)}
    produced = (writes | set(generated or [])) - explicit_claim - set(outputs)
    candidates = {e['path'] for e in events if e.get('event') == 'read' and isinstance(e.get('path'), str)}
    candidates.update(explicit_claim)
    for command in gates:
        for token in _tokens(command):
            if _exists_exact(workspace, token):
                candidates.add(token)
    inputs = sorted(candidates - produced - set(outputs))
    steps = [{'kind': 'produce', 'output': path, 'class': 'generated',
              'guidance': f'regenerate {path} to pass the gate'} for path in sorted(produced)]
    steps.extend({'kind': 'gate', 'output': path, 'class': 'validated', 'run': gates[-1]}
                 for path in outputs)
    return {'claim': {'name': name or os.path.basename(os.path.abspath(workspace)),
                      'format': 3, 'inputs': inputs}, 'step': steps}


def build_claim(workspace, outputs, into, *, name=None, claim=None, generated=None):
    proposed = propose(workspace, outputs, name, claim=claim, generated=generated)
    paths = proposed['claim']['inputs'] + [step['output'] for step in proposed['step']]
    # Validate every trace-derived path before any copy takes place.
    for path in paths:
        safe_path(workspace, path)
    vacuous = kernel.vacuous_gates(proposed)
    if vacuous:
        raise kernel.ClaimError('vacuous gate: ' + ', '.join(vacuous))
    for output in outputs:
        kernel._hash_file(safe_path(workspace, output))
    with tempfile.TemporaryDirectory(prefix='reticuli-authoring-') as room:
        for path in proposed['claim']['inputs'] + [s['output'] for s in proposed['step'] if s['kind'] == 'produce']:
            source = safe_path(workspace, path)
            kernel._hash_file(source)
            dest = safe_path(room, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(source, dest)
        with open(os.path.join(room, kernel.RECIPE), 'w', encoding='utf-8') as stream:
            stream.write(render.dump_recipe(proposed))
        for step in proposed['step']:
            if step['kind'] != 'gate':
                continue
            earned = kernel.run_gate(step['run'], room, proposed)
            if earned['status'] != 'ok':
                raise kernel.ClaimError('cold gate failed: ' + earned.get('stderr', ''))
            if kernel._hash_file(safe_path(room, step['output'])) != kernel._hash_file(safe_path(workspace, step['output'])):
                raise kernel.ClaimError('cold gate verdict mismatch')
        os.makedirs(into, exist_ok=True)
        for path in paths:
            source = safe_path(workspace, path)
            dest = safe_path(into, path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(source, dest)
        shutil.copy2(os.path.join(room, kernel.RECIPE), os.path.join(into, kernel.RECIPE))
    sealed = kernel.seal(into)
    events = _events(workspace)
    prompts = sum(e.get('event') == 'prompt' for e in events)
    times = [e['ts'] for e in events if type(e.get('ts')) in (int, float)]
    kernel.ledger(into, {'event': 'oracle', 'calls': prompts,
                         'seconds': max(times) - min(times) if times else 0.0})
    return {'ok': True, 'root': sealed['root']}

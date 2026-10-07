"""Turn a session trace and explicit claim boundary into a sealed claim."""
from __future__ import annotations
import json
import os
import re
import shlex
import shutil
from . import kernel, render

TRACE = '.reticuli/draft.jsonl'


def _events(ws):
    try:
        with open(os.path.join(ws, TRACE), encoding='utf-8') as source:
            return [json.loads(line) for line in source if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError('cannot read session trace: ' + str(exc)) from exc


def _safe_name(ws, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or '..' in name.replace('\\', '/').split('/'):
        raise kernel.ClaimError('unsafe session path: ' + repr(name))
    parts = name.split('/')
    current = ws
    for part in parts:
        if not part or part == '.':
            raise kernel.ClaimError('unsafe session path: ' + repr(name))
        try:
            if part not in os.listdir(current):
                return None
        except OSError:
            return None
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise kernel.ClaimError('symlink session path: ' + repr(name))
    return current if os.path.isfile(current) else None


def _tokens(command):
    try:
        return shlex.split(command.replace('&&', ' ').replace('||', ' '))
    except ValueError:
        return []


def propose(ws, outputs, name=None, *, claim=None, generated=None):
    events = _events(ws)
    writes = {e['path'] for e in events if e.get('event') == 'write' and isinstance(e.get('path'), str)}
    reads = {e['path'] for e in events if e.get('event') == 'read' and isinstance(e.get('path'), str)}
    gates = [e['cmd'] for e in events if e.get('event') == 'bash' and e.get('cmd')]
    if not gates:
        raise kernel.ClaimError('session has no gate')
    outs = set(outputs)
    pinned = set(claim or [])
    generated_names = (writes | set(generated or [])) - pinned - outs
    candidates = set(reads) | pinned
    for command in gates:
        candidates.update(_tokens(command))
    for candidate in candidates:
        if candidate in outs or candidate in generated_names:
            continue
        if not isinstance(candidate, str) or candidate.startswith('-'):
            continue
        if _safe_name(ws, candidate):
            pinned.add(candidate)
    for candidate in reads | set(claim or []) | set(generated or []):
        if _safe_name(ws, candidate) is None:
            raise kernel.ClaimError('unsafe or missing declared session path: ' + repr(candidate))
    claim_table = {'name': name or os.path.basename(os.path.abspath(ws)), 'format': 3,
                   'inputs': sorted(pinned)}
    steps = [{'kind': 'produce', 'output': path, 'class': 'generated',
              'guidance': f'regenerate {path} to pass the gate'}
             for path in sorted(generated_names) if _safe_name(ws, path)]
    for i, output in enumerate(outputs):
        steps.append({'kind': 'gate', 'output': output, 'class': 'validated',
                      'run': gates[min(i, len(gates)-1)]})
    return {'claim': claim_table, 'step': steps}


def build_claim(ws, outputs, into, *, name=None, claim=None, generated=None):
    parsed = propose(ws, outputs, name, claim=claim, generated=generated)
    generated_names = {s['output'] for s in parsed['step'] if s['kind'] == 'produce'}
    pinned = set(parsed['claim']['inputs'])
    for step in parsed['step']:
        if step['kind'] != 'gate':
            continue
        deciders = kernel.gate_deciders(step['run'])
        if deciders and all(d in generated_names for d in deciders) and not any(
                d in pinned for d in _tokens(step['run'])):
            raise kernel.ClaimError('vacuous gate: every decider is generated')
    for path in [*parsed['claim']['inputs'], *generated_names, *outputs]:
        if _safe_name(ws, path) is None:
            raise kernel.ClaimError('unsafe or missing session path: ' + path)
    if os.path.exists(into):
        shutil.rmtree(into)
    os.makedirs(into)
    with open(os.path.join(into, kernel.RECIPE), 'w', encoding='utf-8') as target:
        target.write(render.dump_recipe(parsed))
    for path in [*parsed['claim']['inputs'], *generated_names]:
        target = os.path.join(into, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(ws, path), target)
    for step in parsed['step']:
        if step['kind'] != 'gate':
            continue
        result = kernel.run_gate(step['run'], into, parsed)
        if result['status'] != 'ok':
            raise kernel.ClaimError('cold gate failed: ' + repr(result))
        output = step['output']
        cold = _safe_name(into, output)
        warm = _safe_name(ws, output)
        if not cold or not warm or kernel._hash_file(cold) != kernel._hash_file(warm):
            raise kernel.ClaimError('cold gate verdict did not reproduce: ' + output)
    sealed = kernel.seal(into)
    events = _events(ws)
    prompts = [e for e in events if e.get('event') == 'prompt']
    times = [e['ts'] for e in events if type(e.get('ts')) in (int, float)]
    event = {'event': 'oracle', 'calls': len(prompts)}
    if times:
        event['seconds'] = max(times) - min(times)
    kernel.ledger(into, event)
    return {'ok': True, **sealed}

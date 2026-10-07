"""Turn a trace into a cold-certified, content-addressed claim."""
import json
import os
import re
import shlex
import shutil
import tempfile

from . import kernel, render
from ._kernel import core

TRACE = '.reticuli/draft.jsonl'


def _events(workspace):
    try:
        with open(os.path.join(workspace, TRACE), encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError('cannot read session trace') from exc


def _exact_file(workspace, name):
    """Accept only an exact directory-entry spelling, independent of host case rules."""
    try:
        core._safe(workspace, name)
    except kernel.ClaimError:
        return False
    directory = workspace
    for part in name.split('/'):
        try:
            if part not in os.listdir(directory):
                return False
        except OSError:
            return False
        directory = os.path.join(directory, part)
    return os.path.isfile(directory)


def _candidate_tokens(command):
    try:
        tokens = shlex.split(command.replace('&&', ' && ').replace(';', ' ; '))
    except ValueError:
        tokens = command.split()
    for token in tokens:
        if token.startswith('./'):
            token = token[2:]
        if re.fullmatch(r'[A-Za-z0-9_./-]+', token):
            yield token


def propose(workspace, outputs, name=None, *, claim=None, generated=None):
    events = _events(workspace)
    commands = [e['cmd'] for e in events if e.get('event') == 'bash' and isinstance(e.get('cmd'), str)]
    if not commands:
        raise kernel.ClaimError('session has no gate')
    gate = commands[-1]
    outputs = list(outputs)
    written = {e['path'] for e in events if e.get('event') == 'write' and isinstance(e.get('path'), str)}
    claimed = set(claim or [])
    produced = set(generated or []) | (written - claimed)
    candidates = {e['path'] for e in events if e.get('event') == 'read' and isinstance(e.get('path'), str)}
    candidates.update(_candidate_tokens(gate))
    candidates.update(claimed)
    candidates -= set(outputs)
    candidates -= produced
    for path in candidates | produced | set(outputs):
        core._safe(workspace, path)  # confinement before any copy
    inputs = sorted(p for p in candidates if _exact_file(workspace, p))
    produced = sorted(p for p in produced if _exact_file(workspace, p) and p not in outputs)
    steps = [{'kind': 'produce', 'output': p, 'class': 'generated',
              'guidance': f'regenerate {p} to pass the gate'} for p in produced]
    for output in outputs:
        steps.append({'kind': 'gate', 'output': output, 'class': 'validated', 'run': gate})
    parsed = {'claim': {'name': name or os.path.basename(os.path.abspath(workspace)),
                        'format': 3, 'inputs': inputs}, 'step': steps}
    if kernel.vacuous_gates(parsed):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    return parsed


def build_claim(workspace, outputs, destination, *, name=None, claim=None, generated=None):
    parsed = propose(workspace, outputs, name, claim=claim, generated=generated)
    events = _events(workspace)
    gate = parsed['step'][-1]['run']
    needed = parsed['claim']['inputs'] + [s['output'] for s in parsed['step'] if s['kind'] == 'produce']
    # Certify in a fresh room. Copy only declared bytes, and compare every
    # verdict with the warm session's verdict before publishing a claim.
    with tempfile.TemporaryDirectory(prefix='reticuli-author-') as room:
        for path in needed:
            core._copy_into(core._safe(workspace, path), core._safe(room, path))
        with open(os.path.join(room, kernel.RECIPE), 'w', encoding='utf-8') as stream:
            stream.write(render.dump_recipe(parsed))
        outcome = kernel.run_gate(gate, room, parsed)
        if outcome['status'] != 'ok':
            raise kernel.ClaimError('cold gate failed: ' + outcome.get('stderr', ''))
        for output in outputs:
            if kernel._hash_file(core._safe(room, output)) != kernel._hash_file(core._safe(workspace, output)):
                raise kernel.ClaimError('cold verdict did not reproduce: ' + output)
        if os.path.exists(destination):
            shutil.rmtree(destination)
        shutil.copytree(room, destination)
    sealed = kernel.seal(destination)
    prompts = [e for e in events if e.get('event') == 'prompt']
    times = [e['ts'] for e in events if type(e.get('ts')) in (int, float)]
    seconds = max(times) - min(times) if times else 0.0
    kernel.ledger(destination, {'event': 'producer', 'calls': len(prompts), 'seconds': float(seconds)})
    return {'ok': True, 'root': sealed['root']}

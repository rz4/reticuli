"""Propose a claim from a session, then certify its verdict cold."""
import json
import os
import re
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
        raise kernel.ClaimError('cannot read session trace: ' + str(exc)) from exc


def _exact_file(workspace, name):
    """Require every spelling to match a real directory entry exactly."""
    try:
        safe_path(workspace, name)
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


def propose(workspace, verdicts, name, *, claim=None, generated=None):
    events = _events(workspace)
    writes = {event['path'] for event in events if event.get('event') == 'write' and isinstance(event.get('path'), str)}
    reads = {event['path'] for event in events if event.get('event') == 'read' and isinstance(event.get('path'), str)}
    for path in writes | reads:
        safe_path(workspace, path)
    commands = [event['cmd'] for event in events if event.get('event') == 'bash' and isinstance(event.get('cmd'), str)]
    if not commands:
        raise kernel.ClaimError('session has no gate')
    command = commands[-1]
    tokens = []
    try:
        tokens = shlex.split(command)
    except ValueError:
        pass
    candidates = set(reads)
    for token in tokens:
        token = token.strip(';,|&()')
        if _exact_file(workspace, token):
            candidates.add(token)
    explicit_claim = set(claim or [])
    explicit_generated = set(generated or [])
    for path in explicit_claim | explicit_generated:
        safe_path(workspace, path)
        if not _exact_file(workspace, path):
            raise kernel.ClaimError('declared file missing: ' + path)
    outputs = set(verdicts)
    for path in outputs:
        safe_path(workspace, path)
    produced = (writes | explicit_generated) - explicit_claim - outputs
    inputs = (candidates | explicit_claim) - produced - outputs
    inputs = sorted(path for path in inputs if _exact_file(workspace, path))
    produced = sorted(path for path in produced if _exact_file(workspace, path))
    steps = [{"kind": "produce", "output": path, "class": "generated",
              "guidance": f"regenerate {path} to pass the gate"} for path in produced]
    steps.extend({"kind": "gate", "output": path, "class": "validated", "run": command} for path in verdicts)
    return {"claim": {"name": name, "format": 3, "inputs": inputs}, "step": steps}


def build_claim(workspace, verdicts, destination, *, name=None, claim=None, generated=None):
    workspace = os.fspath(workspace)
    destination = os.fspath(destination)
    document = propose(workspace, verdicts, name or os.path.basename(destination),
                       claim=claim, generated=generated)
    if kernel.vacuous_gates(document):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    events = _events(workspace)
    with tempfile.TemporaryDirectory(prefix='reticuli-author-') as room:
        with open(os.path.join(room, kernel.RECIPE), 'w', encoding='utf-8') as stream:
            stream.write(render.dump_recipe(document))
        names = set(document['claim']['inputs']) | {s['output'] for s in document['step']}
        for path in sorted(names):
            source = safe_path(workspace, path)
            if not os.path.isfile(source):
                raise kernel.ClaimError('declared file missing: ' + path)
            target = safe_path(room, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        manifest = kernel.seal(room)
        audit = kernel.audit(room)
        if not audit['ok']:
            raise kernel.ClaimError('cold gate did not reproduce pinned verdict')
        if os.path.exists(destination):
            raise kernel.ClaimError('claim destination already exists')
        os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
        shutil.copytree(room, destination)
    prompts = [event for event in events if event.get('event') == 'prompt']
    times = [event['ts'] for event in events if type(event.get('ts')) in (int, float)]
    kernel.ledger(destination, {'event': 'oracle', 'calls': len(prompts),
                                'seconds': max(times) - min(times) if times else 0.0})
    return {'ok': True, 'root': manifest['root'], 'name': document['claim']['name']}

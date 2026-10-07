"""Turn a traced working session into a cold-certified claim."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
from . import kernel, render
from ._util import safe_path, copy_into, ledger_add

TRACE = '.reticuli/draft.jsonl'


def _events(directory):
    try:
        with open(os.path.join(directory, TRACE), encoding='utf-8') as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f'cannot read session trace: {exc}') from exc


def _exact_file(directory, name):
    """Use directory entries, not case-folding host path lookup."""
    try:
        parts = name.split('/')
        if not parts or any(part in ('', '.', '..') for part in parts):
            return False
        cursor = directory
        for part in parts:
            if part not in os.listdir(cursor):
                return False
            cursor = os.path.join(cursor, part)
        safe_path(directory, name)
        return os.path.isfile(cursor)
    except (OSError, kernel.ClaimError):
        return False


def _tokens(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|><')
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        words = command.split()
    for word in words:
        word = word.strip('"\'()')
        if word.startswith('./'):
            word = word[2:]
        if word and not word.startswith('-'):
            yield word


def propose(directory, verdicts, name, *, claim=None, generated=None,
            claim_format=3):
    directory = os.path.abspath(directory)
    events = _events(directory)
    claimed = list(dict.fromkeys(claim or []))
    written = list(dict.fromkeys(generated or []))
    read = []
    commands = []
    for event in events:
        kind = event.get('event')
        path = event.get('path')
        if kind in ('write', 'read') and isinstance(path, str):
            safe_path(directory, path)  # Confine trace paths before any copy.
            if kind == 'write' and path not in written:
                written.append(path)
            if kind == 'read' and path not in read:
                read.append(path)
        if kind == 'bash' and isinstance(event.get('cmd'), str):
            commands.append(event['cmd'])
            for token in _tokens(event['cmd']):
                if token not in read and _exact_file(directory, token):
                    read.append(token)
    for path in claimed + written + list(verdicts):
        safe_path(directory, path)
    verdicts = list(dict.fromkeys(verdicts))
    inputs = [path for path in claimed if _exact_file(directory, path)]
    for path in read:
        if (path not in written and path not in verdicts and path not in inputs
                and not path.startswith('.reticuli/') and _exact_file(directory, path)):
            inputs.append(path)
    produced = [path for path in written if path not in inputs and path not in verdicts
                and _exact_file(directory, path)]
    steps = [{'kind': 'produce', 'output': path, 'class': 'generated',
              'guidance' if claim_format != 1 else 'request': f'regenerate {path} to pass the gate'}
             for path in produced]
    if not commands:
        raise kernel.ClaimError('session has no gate command')
    for output in verdicts:
        if not _exact_file(directory, output):
            raise kernel.ClaimError(f'missing gate verdict: {output}')
        steps.append({'kind': 'gate', 'output': output, 'class': 'validated',
                      'run': commands[-1]})
    info = {'name': name}
    if claim_format != 1:
        info['format'] = claim_format
    if inputs:
        info['inputs'] = inputs
    recipe = {'claim': info, 'step': steps}
    if kernel.vacuous_gates(recipe):
        raise kernel.ClaimError('vacuous gate: every decider is generated')
    return {'claim': info, 'step': steps, 'recipe': recipe,
            'generated': produced, 'inputs': inputs, 'gates': commands}


def build_claim(directory, verdicts, into, *, name=None, claim=None,
                generated=None, claim_format=3):
    directory = os.path.abspath(directory)
    proposed = propose(directory, verdicts, name or os.path.basename(directory),
                       claim=claim, generated=generated, claim_format=claim_format)
    recipe = proposed['recipe']
    into = os.path.abspath(into)
    if os.path.exists(into) and os.listdir(into):
        raise kernel.ClaimError(f'claim destination is not empty: {into}')
    os.makedirs(into, exist_ok=True)
    # Paths were confined in propose, before the first copy.
    for path in list(dict.fromkeys(proposed['inputs'] + proposed['generated'] + list(verdicts))):
        copy_into(safe_path(directory, path), safe_path(into, path))
    with open(os.path.join(into, kernel.RECIPE), 'w', encoding='utf-8') as stream:
        stream.write(render.dump_recipe(recipe))
    sealed = kernel.seal(into)
    audited = kernel.audit(into)
    if not audited['ok']:
        raise kernel.ClaimError('gate verdict cannot be re-earned cold')
    events = _events(directory)
    prompts = sum(event.get('event') == 'prompt' for event in events)
    timestamps = [event['ts'] for event in events
                  if type(event.get('ts')) in (int, float)]
    seconds = max(timestamps) - min(timestamps) if timestamps else 0.0
    ledger_add(into, {'event': 'oracle', 'calls': prompts, 'seconds': seconds})
    return {'ok': True, 'root': sealed['root'], 'path': into}

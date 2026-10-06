"""Small filesystem and ledger helpers shared by higher layers."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'


def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError(f'unsafe path: {name!r}')
    base = os.path.realpath(directory)
    path = base
    for part in name.split('/'):
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise kernel.ClaimError(f'symlink path: {name!r}')
    if not os.path.realpath(path).startswith(base + os.sep):
        raise kernel.ClaimError(f'path escapes claim: {name!r}')
    return path


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    with open(path, encoding='utf-8') as source:
        return json.load(source)


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as target:
        json.dump(value, target, sort_keys=True)
        target.write('\n')


def copy_into(source, destination):
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def declared_inputs(recipe, directory=None):
    claim = recipe.get('claim', {})
    names = list(claim.get('inputs', []))
    if claim.get('inputs_manifest'):
        manifest = claim['inputs_manifest']
        if directory is None:
            raise kernel.ClaimError('inputs manifest needs a directory')
        with open(safe_path(directory, manifest), encoding='utf-8') as source:
            for line in source:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.append(line.split('  ', 1)[-1])
        names.append(manifest)
    if claim.get('environment'):
        names.append(claim['environment'])
    return list(dict.fromkeys(names))


def step_output(step):
    return step['output']


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def locked_append(path, entry):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as target:
        target.write(json.dumps(entry, sort_keys=True) + '\n')


def ledger_add(directory, entry):
    kernel.ledger(directory, entry)


def trace_append(directory, entry):
    locked_append(safe_path(directory, '.reticuli/trace.jsonl'), entry)

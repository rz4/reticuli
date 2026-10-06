"""Shared, public filesystem and ledger helpers for layers above the kernel."""
import datetime
import hashlib
import json
import os
import shutil

from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'


def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError('unsafe claim path: ' + repr(name))
    path = os.path.join(directory, name)
    if os.path.commonpath((os.path.realpath(directory), os.path.realpath(path))) != os.path.realpath(directory):
        raise kernel.ClaimError('claim path escapes directory')
    for part in name.split('/'):
        directory = os.path.join(directory, part)
        if os.path.islink(directory):
            raise kernel.ClaimError('symlink in claim path')
    return path


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f'cannot read {path}: {exc}') from exc


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True)
        f.write('\n')


def copy_into(source, destination):
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    return shutil.copy2(source, destination)


def declared_inputs(parsed, directory):
    from ._kernel import recipe
    return recipe._inputs(parsed, directory)


def step_output(step):
    return step['output']


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def locked_append(path, entry):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, sort_keys=True) + '\n')


def ledger_add(directory, entry):
    locked_append(os.path.join(directory, LEDGER), entry)


def trace_append(directory, entry):
    locked_append(os.path.join(directory, STORE, 'trace.jsonl'), entry)

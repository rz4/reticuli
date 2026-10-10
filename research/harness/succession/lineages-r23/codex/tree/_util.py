"""Small public file and bookkeeping helpers shared by exchange layers."""
import datetime
import hashlib
import json
import os
import shutil

from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(
            x in ('', '.', '..') for x in name.replace('\\', '/').split('/')):
        raise kernel.ClaimError(f'invalid claim path: {name!r}')
    base = os.path.realpath(directory)
    path = os.path.join(base, name)
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise kernel.ClaimError(f'path escapes claim: {name}')
    return path


def copy_into(source, target):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)
    return target


def declared_inputs(directory):
    from ._kernel import recipe
    return recipe._inputs(kernel.load_recipe(directory), directory)


def step_output(step):
    return step['output']


def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(value)


def trace_append(directory, event):
    locked_append(os.path.join(directory, STORE, 'trace.jsonl'), json.dumps(event, sort_keys=True) + '\n')


def ledger_add(directory, event):
    kernel.ledger(directory, event)

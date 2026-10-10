"""Small public helpers shared by layers above the claim kernel."""
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
    from ._kernel.core import _safe
    return _safe(directory, name)

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def copy_into(source, destination):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)

def declared_inputs(parsed, directory=None):
    from ._kernel.recipe import _inputs
    return _inputs(parsed, directory)

def step_output(step):
    return step['output']

def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)

def write_json(path, value):
    from ._kernel.core import _write_json
    _write_json(path, value)

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(value)

def trace_append(directory, event):
    locked_append(os.path.join(directory, LEDGER), json.dumps(event, sort_keys=True) + '\n')

def ledger_add(directory, event):
    kernel.ledger(directory, event)

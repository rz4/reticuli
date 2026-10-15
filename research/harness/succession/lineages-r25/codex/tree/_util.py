"""Small public filesystem and ledger helpers shared by exchange modules."""
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
    from ._kernel.core import _safe
    return _safe(directory, name)

def copy_into(source, destination):
    from ._kernel.core import _copy_into
    return _copy_into(source, destination)

def declared_inputs(directory):
    from ._kernel.recipe import _inputs
    return _inputs(kernel.load_recipe(directory), directory)

def step_output(step):
    return step['output']

def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)

def write_json(path, value):
    from ._kernel.core import _write_json
    return _write_json(path, value)

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(value)

def trace_append(directory, event):
    locked_append(os.path.join(directory, LEDGER), json.dumps(event, sort_keys=True)+'\n')

def ledger_add(directory, event):
    kernel.ledger(directory, event)

def stamp():
    from ._kernel.core import _now
    return _now()

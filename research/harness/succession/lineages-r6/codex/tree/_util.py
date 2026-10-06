"""Small filesystem and bookkeeping helpers shared by upper layers."""
from __future__ import annotations

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
    return kernel._safe(directory, name)

def copy_into(source, destination):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)

def declared_inputs(directory):
    from ._kernel import recipe
    return recipe._inputs(kernel.load_recipe(directory), directory)

def step_output(step):
    return step['output']

def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def write_json(path, value):
    from ._kernel import core
    core._write_json(path, value)

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(value, sort_keys=True) + '\n')

def ledger_add(directory, event):
    kernel.ledger(directory, event)

def trace_append(directory, event):
    locked_append(safe_path(directory, '.reticuli/trace.jsonl'), event)

def stamp():
    from ._kernel import core
    return core._now()

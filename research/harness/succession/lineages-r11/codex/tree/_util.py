"""Small public filesystem and bookkeeping helpers shared by upper layers."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

from . import kernel
from ._kernel import core, recipe

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(directory, name):
    return core._safe(directory, name)

def copy_into(source, destination):
    return core._copy_into(source, destination)

def declared_inputs(parsed, directory=None):
    return recipe._inputs(parsed, directory)

def step_output(step):
    return step['output']

def read_json(path):
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)

def write_json(path, value):
    core._write_json(path, value)

def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(value)

def trace_append(directory, event):
    locked_append(os.path.join(directory, LEDGER), json.dumps(event, sort_keys=True) + '\n')

def ledger_add(directory, event):
    kernel.ledger(directory, event)

"""Small shared helpers for exchange layers."""
import hashlib
import json
import os
from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def safe_path(directory, name):
    return kernel._kernel.core._safe(directory, name) if hasattr(kernel, '_kernel') else os.path.join(directory, name)

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(value, f, sort_keys=True)
        f.write('\n')

def copy_into(source, destination):
    import shutil
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)

def declared_inputs(parsed, directory):
    from ._kernel import recipe
    return recipe._inputs(parsed, directory)

def step_output(step):
    return step['output']

def stamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(value)

def ledger_add(directory, event):
    kernel.ledger(directory, event)

def trace_append(directory, event):
    locked_append(os.path.join(directory, STORE, 'trace.jsonl'), json.dumps(event, sort_keys=True) + '\n')

"""Small public filesystem and ledger helpers shared by exchange layers."""
from __future__ import annotations

import datetime
import hashlib
import json
import os

from . import kernel
from ._kernel import core, recipe

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(directory, name):
    return core._safe(directory, name)

def copy_into(source, target):
    return core._copy_into(source, target)

def declared_inputs(parsed, directory):
    return recipe._inputs(parsed, directory)

def step_output(step):
    return step['output']

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def write_json(path, value):
    core._write_json(path, value)

def read_json(path):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(str(exc)) from exc

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, sort_keys=True) + '\n')

def ledger_add(directory, event):
    kernel.ledger(directory, event)

def trace_append(directory, event):
    locked_append(os.path.join(directory, STORE, 'trace.jsonl'), event)

"""Shared filesystem and bookkeeping helpers for exchange layers."""
from __future__ import annotations
import datetime
import hashlib
import json
import os
import shutil
from pathlib import Path
from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def safe_path(root, name):
    return kernel._safe(root, name)

def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()

def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise kernel.ClaimError(f'cannot read JSON: {exc}') from exc

def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')

def copy_into(source, destination):
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)

def declared_inputs(data):
    return kernel._inputs(data)

def step_output(step):
    return step['output']

def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def locked_append(path, line):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(line)

def ledger_add(directory, event):
    locked_append(safe_path(directory, LEDGER), json.dumps(event, sort_keys=True) + '\n')

def trace_append(directory, event):
    ledger_add(directory, event)

# Exchange compatibility for the kernel facade's optional bookkeeping names.
kernel.ledger = ledger_add

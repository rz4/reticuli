"""Small public helpers shared by the exchange layer."""
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
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError('unsafe path: ' + repr(name))
    base = os.path.realpath(directory)
    path = base
    for part in name.split('/'):
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise kernel.ClaimError('symlink path: ' + name)
    return path

def copy_into(source, dest):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    shutil.copyfile(source, dest)
    return dest

def read_json(path):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except (OSError, ValueError) as e: raise kernel.ClaimError(str(e)) from e

def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: json.dump(obj, f, sort_keys=True)

def declared_inputs(parsed, directory=None):
    names = list(parsed['claim'].get('inputs', []))
    if parsed['claim'].get('inputs_manifest'):
        name = parsed['claim']['inputs_manifest']; names.append(name)
        with open(safe_path(directory, name), encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.append(line.split('  ', 1)[-1])
    if parsed['claim'].get('environment'): names.append(parsed['claim']['environment'])
    return names

def step_output(step): return step['output']
def stamp(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def locked_append(path, row):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f: f.write(json.dumps(row, sort_keys=True) + '\n')
def trace_append(directory, row): locked_append(os.path.join(directory, STORE, 'trace.jsonl'), row)
def ledger_add(directory, row): kernel.ledger(directory, row)

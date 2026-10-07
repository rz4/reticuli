"""Small filesystem and bookkeeping helpers shared by exchange modules."""
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError(f'unsafe path: {name!r}')
    base = os.path.realpath(directory)
    path = os.path.join(base, name)
    cur = base
    for part in name.split('/'):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise kernel.ClaimError(f'symlink path: {name!r}')
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise kernel.ClaimError(f'unsafe path: {name!r}')
    return path

def copy_into(source, destination):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)

def read_json(path):
    try:
        with open(path, encoding='utf-8') as f: return json.load(f)
    except (OSError, ValueError) as e:
        raise kernel.ClaimError(f'cannot read {path}: {e}') from e

def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: json.dump(value, f, sort_keys=True); f.write('\n')

def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f: f.write(value)

def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def ledger_add(directory, event):
    locked_append(safe_path(directory, LEDGER), json.dumps(event, sort_keys=True)+'\n')

def trace_append(directory, event):
    ledger_add(directory, event)

def declared_inputs(directory):
    claim = kernel.load_recipe(directory)['claim']
    names = list(claim.get('inputs', []))
    if claim.get('inputs_manifest'):
        manifest = claim['inputs_manifest']; names.append(manifest)
        with open(safe_path(directory, manifest), encoding='utf-8') as f:
            for line in f:
                line=line.strip()
                if line and not line.startswith('#'):
                    names.append(line.split('  ',1)[-1])
    if claim.get('environment'): names.append(claim['environment'])
    return list(dict.fromkeys(names))

def step_output(step):
    return step['output']

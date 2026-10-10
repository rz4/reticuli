"""Small public helpers shared by layers above the kernel."""
import datetime
import hashlib
import json
import os
import shutil

from . import kernel

STORE = '.reticuli'
LEDGER = '.reticuli/ledger.jsonl'
RECIPE = 'claim.toml'

def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()

def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError(f'invalid path: {name!r}')
    base = os.path.realpath(directory)
    path = base
    for part in name.split('/'):
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise kernel.ClaimError(f'symlink in path: {name}')
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise kernel.ClaimError(f'path escapes claim: {name}')
    return path

def copy_into(source, target):
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)
    return target

def declared_inputs(parsed, directory=None):
    claim = parsed.get('claim', {})
    names = list(claim.get('inputs', []))
    manifest = claim.get('inputs_manifest')
    if manifest:
        names.append(manifest)
        with open(safe_path(directory, manifest), encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.append(line.split('  ', 1)[-1])
    if claim.get('environment'):
        names.append(claim['environment'])
    return list(dict.fromkeys(names))

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

def ledger_add(directory, event):
    locked_append(os.path.join(directory, LEDGER), json.dumps(event, sort_keys=True) + '\n')
    return event

def trace_append(directory, event):
    return ledger_add(directory, event)

"""Shared public filesystem and ledger helpers for layers above the kernel."""
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


def safe_path(base, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or any(p in ('', '.', '..') for p in name.split('/')):
        raise kernel.ClaimError('unsafe claim path: ' + repr(name))
    root = os.path.realpath(base)
    path = root
    for part in name.split('/'):
        path = os.path.join(path, part)
        if os.path.islink(path):
            raise kernel.ClaimError('symlink in claim path: ' + name)
    if os.path.commonpath((root, os.path.realpath(path))) != root:
        raise kernel.ClaimError('claim path escapes directory')
    return path


def copy_into(source, destination):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def declared_inputs(path):
    doc = kernel.load_recipe(path)
    names = list(doc['claim'].get('inputs', []))
    manifest = doc['claim'].get('inputs_manifest')
    if manifest:
        names.append(manifest)
        with open(safe_path(path, manifest), encoding='utf-8') as stream:
            for line in stream:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.append(line.split('  ', 1)[-1])
    env = doc['claim'].get('environment')
    if env:
        names.append(env)
    return names


def step_output(step):
    return step['output']


def read_json(path):
    try:
        with open(path, encoding='utf-8') as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError('cannot read JSON: ' + str(exc)) from exc


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write('\n')


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(value)


def ledger_add(path, event):
    locked_append(os.path.join(path, LEDGER), json.dumps(event, sort_keys=True) + '\n')


def trace_append(path, event):
    ledger_add(path, event)

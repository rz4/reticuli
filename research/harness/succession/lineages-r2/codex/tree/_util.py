"""Small public helpers shared by exchange-layer modules."""
from __future__ import annotations

import hashlib
import json
import os
import shutil

from . import kernel

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(directory, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or ".." in name.split("/"):
        raise kernel.ClaimError(f"invalid claim path: {name!r}")
    base = os.path.realpath(directory)
    path = os.path.join(base, name)
    if os.path.commonpath((base, os.path.realpath(path))) != base:
        raise kernel.ClaimError(f"path escapes claim: {name}")
    cur = base
    for part in name.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise kernel.ClaimError(f"symlink in claim path: {name}")
    return path


def copy_into(source, destination):
    kernel._hash_file(source)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def read_json(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as exc:
        raise kernel.ClaimError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")


def locked_append(path, value):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def ledger_add(directory, event):
    locked_append(safe_path(directory, LEDGER), event)


def trace_append(directory, event):
    locked_append(safe_path(directory, ".reticuli/trace.jsonl"), event)


def stamp():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def declared_inputs(directory, recipe=None):
    from ._kernel import recipe as recipes
    return recipes._inputs(recipe or kernel.load_recipe(directory), directory)


def step_output(step):
    return step["output"]

"""Small standard-library helpers shared by the exchange modules."""
from __future__ import annotations
import datetime, hashlib, json, os, shutil, tempfile

STORE = ".reticuli"
LEDGER = ".reticuli/ledger.jsonl"
RECIPE = "claim.toml"


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def safe_path(root, name):
    if not isinstance(name, str) or not name or os.path.isabs(name) or "\0" in name:
        raise ValueError("unsafe relative path")
    bits = name.replace("\\", "/").split("/")
    if ".." in bits:
        raise ValueError("path escapes root")
    root = os.path.abspath(os.fspath(root))
    path = os.path.abspath(os.path.join(root, name))
    if os.path.commonpath((root, path)) != root or path == root:
        raise ValueError("path escapes root")
    return path


def copy_into(source, target):
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    shutil.copyfile(source, target)
    return os.fspath(target)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    path = os.path.abspath(os.fspath(path)); os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".json-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, sort_keys=True); f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return path


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def locked_append(path, line):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # One append-mode write is atomic for the small records used here.
    data = line if isinstance(line, str) else line.decode("utf-8")
    with open(path, "a", encoding="utf-8") as f:
        f.write(data); f.flush()
    return path


def ledger_add(d, event):
    item = dict(event); item.setdefault("when", stamp())
    locked_append(os.path.join(d, LEDGER), json.dumps(item, sort_keys=True) + "\n")
    return item


def trace_append(d, event):
    return ledger_add(d, event)


def declared_inputs(recipe):
    claim = recipe.get("claim", {}) if isinstance(recipe, dict) else {}
    return list(claim.get("inputs", []))


def step_output(step):
    return step.get("output") if isinstance(step, dict) else None

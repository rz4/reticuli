import os, json, hashlib
from ._kernel.core import _safe, _copy_into, _write_json, _read_json, _now
from ._kernel.recipe import _inputs
from ._kernel.run import ledger
STORE='.reticuli'
LEDGER='.reticuli/ledger.jsonl'
RECIPE='claim.toml'
safe_path=_safe
copy_into=_copy_into
write_json=_write_json
read_json=_read_json
stamp=_now
ledger_add=ledger
def hash_bytes(b):return hashlib.sha256(b).hexdigest()
def declared_inputs(r,d=None):return _inputs(r,d)
def step_output(s):return s['output']
def locked_append(p,event):
    import fcntl
    os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
    with open(p,'a') as f:
        fcntl.flock(f,fcntl.LOCK_EX);f.write(json.dumps(event)+'\n');f.flush();fcntl.flock(f,fcntl.LOCK_UN)
def trace_append(d,event):locked_append(os.path.join(d,STORE,'draft.jsonl'),event)

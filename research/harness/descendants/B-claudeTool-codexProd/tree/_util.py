import os,json,time,hashlib
from ._kernel.core import _safe as safe_path,_copy_into as copy_into,_write_json as write_json
from ._kernel.recipe import _inputs as declared_inputs
STORE='.reticuli'
LEDGER='.reticuli/ledger.jsonl'
RECIPE='claim.toml'
def hash_bytes(b): return hashlib.sha256(b).hexdigest()
def read_json(p):
    with open(p) as f: return json.load(f)
def stamp(): return time.time()
def step_output(s): return s['output']
def locked_append(p,v):
    os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
    with open(p,'a') as f: f.write(json.dumps(v)+'\n')
def ledger_add(d,v): locked_append(os.path.join(d,LEDGER),v)
def trace_append(d,v): locked_append(os.path.join(d,STORE,'draft.jsonl'),v)

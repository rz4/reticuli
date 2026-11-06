import os,json,glob
from .. import kernel

def _read_residue(d,n):
    try: return json.load(open(os.path.join(d,kernel.STORE,n)))
    except (OSError,ValueError): return None
def _signatures(d): return len(glob.glob(os.path.join(d,kernel.STORE,'attest','*.json')))+len(glob.glob(os.path.join(d,kernel.SIGN_DIR,'*.sign.json')))
def _next_step(v):
    if not v.get('ok'): return 'restore pinned bytes'
    if not v.get('audited'): return 'ret audit'
    if not v.get('deciding'): return 'ret assess'
    if not v.get('proof'): return 'ret crosscheck'
    return 'ret sign'
def _claim_view(d):
    v=kernel.verify(d); v.update(phase=kernel.phase(d),audited=_read_residue(d,'audit.json'),deciding=_read_residue(d,'assess.json'),proof=kernel.read_manifest(d).get('proof'),signatures=_signatures(d),cost=kernel.cost(d)); v['next']=_next_step(v); return v
def _phase(d): return kernel.phase(d)
def _verified(d): return kernel.verify(d)
def _verdict(v): return v.get('verdict','earned' if v.get('ok') else 'failed')
def _gate_ok(g): return g.get('status')=='ok'
def _deciding_words(v): return str(v)

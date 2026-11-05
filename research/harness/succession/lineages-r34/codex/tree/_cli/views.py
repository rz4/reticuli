import os, glob
from .. import kernel
from .._kernel.core import _read_json

def _read_residue(d,name,root=None):
    p=os.path.join(d,kernel.STORE,name)
    try:r=_read_json(p)
    except kernel.ClaimError:return None
    return r if root is None or r.get('root')==root else None

def _signatures(d):return len(glob.glob(os.path.join(d,kernel.STORE,'attest','*.attest.json')))+len(glob.glob(os.path.join(d,kernel.SIGN_DIR,'*.sign.json')))
def _next_step(v):
    if not v.get('ok',True):return 'restore the pinned bytes'
    if not v.get('audited'):return 'ret audit '+v.get('path','.')
    if not v.get('deciding'):return 'ret assess '+v.get('path','.')
    if not v.get('proof'):return 'ret crosscheck with an independent rebuild'
    return 'ret sign to authorize'
def _claim_view(d):
    v=kernel.verify(d);v.update(path=d,phase=kernel.phase(d),audited=_read_residue(d,'audit.json',v['root']),deciding=_read_residue(d,'assess.json',v['root']),proof=kernel.read_manifest(d).get('proof'),signatures=_signatures(d),cost=kernel.cost(d))
    v['next']=_next_step(v);return v

def _gate_ok(g):return g.get('status')=='ok'
def _phase(d):return kernel.phase(d)
def _verified(d):return kernel.verify(d)
def _verdict(x):return x.get('verdict',x.get('status'))
def _deciding_words(x):return 'measured' if x else 'unknown'

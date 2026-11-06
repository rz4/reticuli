import re, os, json, hashlib, datetime
from .core import ClaimError, canonical
from .recipe import number, obligations
from .build import _ssh_verify
RECORD_NAMESPACE='reticuli.record'
RECORD_FORMAT=2
_RECORD_ENVIRONMENT=frozenset({'platform','runtime','machine'})
_RECORD_GATE=frozenset({'status','sandbox','output'})
_RECORD_MEMBERS=frozenset({'when','cost','gates','producer','environment','name','root','record','build_digest','tool'})
_RECORD_PRODUCER=frozenset({'blind','model','cutoff','vendor'})
_RECORD_REQUIRED=frozenset({'build_digest','when','environment','record','name','root','gates'})
_RECORD_SANDBOXES=frozenset({'none','seatbelt','inherited','bubblewrap'})
_RECORD_STATUSES=frozenset({'timeout','ok','environment','failed','mismatch'})
_RECORD_HEX=re.compile(r'^[0-9a-f]{64}$')
_RECORD_WHEN=re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
def record_validate(x):
    def need(v,msg):
        if not v:raise ClaimError('record: '+msg)
    need(isinstance(x,dict),'must be an object')
    v=x.get('record');need(type(v)==int and v in (1,2),'unsupported record version '+str(v))
    required=_RECORD_REQUIRED|({'claim'} if v==2 else set());members=_RECORD_MEMBERS|({'claim'} if v==2 else set())
    need(required<=x.keys() and x.keys()<=members,'missing or unknown member')
    for k in ('root','build_digest'):need(isinstance(x[k],str) and _RECORD_HEX.fullmatch(x[k]),'invalid '+k)
    need(isinstance(x['name'],str),'name')
    need(isinstance(x['when'],str) and _RECORD_WHEN.fullmatch(x['when']),'when')
    need(isinstance(x['environment'],dict) and set(x['environment'])==_RECORD_ENVIRONMENT and all(isinstance(v,str) for v in x['environment'].values()),'environment')
    need(isinstance(x['gates'],list),'gates')
    for g in x['gates']:
        need(isinstance(g,dict) and set(g)==_RECORD_GATE,'gate members')
        need(isinstance(g['output'],str) and g['status'] in _RECORD_STATUSES and g['sandbox'] in _RECORD_SANDBOXES,'gate vocabulary')
    if 'cost' in x:
        need(isinstance(x['cost'],dict),'cost')
        need(all(k in ('usd','tokens','calls','seconds') and number(v) for k,v in x['cost'].items()),'cost value')
    if v==2:
        need(isinstance(x['claim'],dict) and set(x['claim'])<={'envelope','tolerance','mutation_floor'},'claim obligations')
        obligations(x['claim'],record=True)
    if 'producer' in x:
        p=x['producer'];need(isinstance(p,dict) and set(p)<=_RECORD_PRODUCER,'producer')
        for k,v in p.items():need(type(v)==bool if k=='blind' else isinstance(v,str),'producer '+k)
    if 'tool' in x:need(isinstance(x['tool'],str),'tool')
    return x

def record_canonical(doc):record_validate(doc);return canonical(doc)
def record_digest(doc):return hashlib.sha256(record_canonical(doc)).hexdigest()
def record_read(p):
    try:
        b=open(p,'rb').read();doc=json.loads(b)
    except (OSError,ValueError,UnicodeError) as e:raise ClaimError('record: '+str(e))
    if record_canonical(doc)!=b:raise ClaimError('record is not canonical bytes')
    return doc

def record_signer(p,anchor=None):
    try:record_read(p)
    except ClaimError:return None
    return _ssh_verify(p,RECORD_NAMESPACE,anchor) if anchor else None

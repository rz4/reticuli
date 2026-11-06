import json,re,os,hashlib,datetime
from .core import ClaimError,COST_KEYS
from .recipe import number
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
_RECORD_WHEN=re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
def record_validate(v):
    def require(x,msg):
        if not x: raise ClaimError('invalid record: '+msg)
    require(isinstance(v,dict),'expected object')
    ver=v.get('record'); require(type(ver)==int and ver in (1,2),f'version {ver}')
    req=_RECORD_REQUIRED | ({'claim'} if ver==2 else set()); allowed=_RECORD_MEMBERS | ({'claim'} if ver==2 else set())
    require(req<=v.keys() and v.keys()<=allowed,'member set')
    for k in ('name','when','root','build_digest'): require(isinstance(v[k],str),k)
    for k in ('root','build_digest'): require(_RECORD_HEX.fullmatch(v[k]),k)
    require(_RECORD_WHEN.fullmatch(v['when']),'when')
    require(isinstance(v['environment'],dict) and v['environment'].keys()==_RECORD_ENVIRONMENT and all(isinstance(x,str) for x in v['environment'].values()),'environment')
    require(isinstance(v['gates'],list),'gates')
    for g in v['gates']:
        require(isinstance(g,dict) and g.keys()==_RECORD_GATE,'gate members')
        require(isinstance(g['output'],str) and g['status'] in _RECORD_STATUSES and g['sandbox'] in _RECORD_SANDBOXES,'gate vocabulary')
    if 'cost' in v:
        require(isinstance(v['cost'],dict),'cost')
        require(all(k in COST_KEYS and number(x) for k,x in v['cost'].items()),'cost value')
    if 'producer' in v:
        p=v['producer']; require(isinstance(p,dict) and p.keys()<=_RECORD_PRODUCER,'producer')
        require(all(type(x)==bool if k=='blind' else isinstance(x,str) for k,x in p.items()),'producer type')
    if ver==2:
        c=v['claim']; require(isinstance(c,dict) and c.keys()<={'tolerance','envelope','mutation_floor'},'claim')
        for k in ('tolerance','mutation_floor'):
            if k in c: require(number(c[k]),k)
        if 'envelope' in c: require(isinstance(c['envelope'],dict) and bool(c['envelope']) and all(k in COST_KEYS and number(x,0,True) for k,x in c['envelope'].items()),'envelope')
    if 'tool' in v: require(isinstance(v['tool'],str),'tool')
    return v

def record_canonical(v): record_validate(v); return json.dumps(v,sort_keys=True).encode()
def record_digest(v): return hashlib.sha256(record_canonical(v)).hexdigest()
def record_read(p):
    try:
        raw=open(p,'rb').read(); v=json.loads(raw)
        if record_canonical(v)!=raw: raise ClaimError('record file is not canonical')
        return v
    except (OSError,ValueError) as e: raise ClaimError(str(e)) from e
def record_signer(p,anchor=None):
    try:
        record_read(p); anchor=anchor or os.environ.get('RETICULI_SIGNERS')
        if not anchor: return None
        for line in open(anchor):
            if line.strip() and not line.startswith('#'):
                name=line.split()[0]
                if _ssh_verify(p,RECORD_NAMESPACE,name,anchor): return name
    except (OSError,ClaimError): pass
    return None

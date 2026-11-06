import os, json, hashlib, stat, shutil, datetime, platform, sys, tempfile
NAMESPACE = 'reticuli'
DIGEST = 'sha256'
FORMAT = 6
STORE = '.reticuli'
MANIFEST = '.reticuli/manifest.json'
RECIPE = 'reticuli.toml'
LEGACY_RECIPE = 'claim.toml'
LEDGER = '.reticuli/ledger.jsonl'
USAGE = '.reticuli/usage.json'
MUTATION_RESIDUE = '.reticuli/mutation_score.json'
SIGN_DIR = '.reticuli/mint'
SIGN_NAMESPACE = 'reticuli.mint'
_JAILED = 'RETICULI_JAILED'
_ENV_CACHE = 'RETICULI_ENV_CACHE'
_ENV_CLAIM = 'RETICULI_CLAIM'
_ENV_MODEL = 'RETICULI_MODEL'
_ENV_OUTPUT = 'RETICULI_OUTPUT'
_ENV_OUTPUTS = 'RETICULI_OUTPUTS'
_ENV_REQUEST = 'RETICULI_REQUEST'
_ENV_SIGNERS = 'RETICULI_SIGNERS'
_ENV_TIMEOUT = 'RETICULI_GATE_TIMEOUT'
_ENV_TOLERANCE = 'RETICULI_TOLERANCE'
_ENV_USAGE = 'RETICULI_USAGE'
_ENV_VENDOR = 'RETICULI_VENDOR'
_KEEP_ENV = ('PATH','HOME','TMPDIR','LANG','LC_ALL','TZ','RETICULI_JAILED')
GATE_TIMEOUT = 120
FURNISH_TIMEOUT = 120
PRODUCER_TIMEOUT = 3600
TOLERANCE = 2.0
MUTANT_CEILING = 30
MUTANT_FLOOR = 1
MUTANT_HEADROOM = 3
COST_KEYS = COST_LADDER = COST_UNITS = ('usd','tokens','calls','seconds')
GUIDANCE_KEYS = ('guidance','request')
KINDS = frozenset({'produce','gate'})
_SHELL = '/bin/sh'
class ClaimError(Exception): pass

def _now(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _safe(d, name):
    if not isinstance(name,str) or not name or os.path.isabs(name) or '..' in name.split('/'):
        raise ClaimError('unsafe claim path: '+str(name))
    base=os.path.realpath(d); p=base
    for part in name.split('/'):
        p=os.path.join(p,part)
        if os.path.islink(p): raise ClaimError('symlink in claim path: '+name)
    p=os.path.abspath(p)
    if not p.startswith(base+os.sep): raise ClaimError('unsafe claim path: '+name)
    return p

def _hash_file(p):
    try:
        s=os.lstat(p)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1: raise ClaimError('not a regular single-link file: '+str(p))
        with open(p,'rb') as f: return hashlib.sha256(f.read()).hexdigest()
    except OSError as e: raise ClaimError(str(e)) from e

def _write_json(p,doc):
    os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(p)))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(doc,f,sort_keys=True)
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def _read_json(p):
    try:
        with open(p,encoding='utf-8') as f:return json.load(f)
    except (OSError,ValueError,UnicodeError) as e: raise ClaimError(str(e)) from e

def _copy_into(src,d,name):
    _hash_file(src); dst=_safe(d,name)
    os.makedirs(os.path.dirname(dst),exist_ok=True); shutil.copy2(src,dst)
    return dst

def _judging_host(): return {'python':sys.version.split()[0], 'platform':sys.platform, 'machine':platform.machine()}
def canonical(x): return json.dumps(x,sort_keys=True).encode('utf-8')
def digest(x): return hashlib.sha256(canonical(x)).hexdigest()

def toml_value(v):
    if isinstance(v,str): return json.dumps(v,ensure_ascii=False)
    if isinstance(v,bool): return str(v).lower()
    if isinstance(v,(int,float)): return repr(v)
    if isinstance(v,list): return '['+', '.join(toml_value(x) for x in v)+']'
    if isinstance(v,dict):return '{ '+', '.join(json.dumps(k)+' = '+toml_value(x) for k,x in v.items())+' }'
    raise ClaimError('no canonical TOML value: '+repr(v))
def dump_recipe(r):
    lines=[]
    for k,v in r.items():
        if k=='step':continue
        if isinstance(v,dict):
            lines.append('['+k+']')
            lines.extend(json.dumps(a)+' = '+toml_value(b) for a,b in v.items())
        else:lines.append(json.dumps(k)+' = '+toml_value(v))
    for s in r.get('step',[]):
        lines.append('\n[[step]]'); lines.extend(json.dumps(k)+' = '+toml_value(v) for k,v in s.items())
    return '\n'.join(lines)+'\n'

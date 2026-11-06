import os, json, hashlib, stat, shutil, tempfile, datetime, platform, sys
class ClaimError(Exception): pass
NAMESPACE='reticuli'
DIGEST='sha256'
FORMAT=6
STORE='.reticuli'
MANIFEST=STORE+'/manifest.json'
RECIPE='reticuli.toml'
LEGACY_RECIPE='claim.toml'
LEDGER=STORE+'/ledger.jsonl'
USAGE=STORE+'/usage.json'
MUTATION_RESIDUE=STORE+'/mutation_score.json'
SIGN_DIR=STORE+'/mint'
SIGN_NAMESPACE='reticuli.mint'
_JAILED='RETICULI_JAILED'
_ENV_CACHE='RETICULI_ENV_CACHE'
_ENV_CLAIM='RETICULI_CLAIM'
_ENV_MODEL='RETICULI_MODEL'
_ENV_OUTPUT='RETICULI_OUTPUT'
_ENV_OUTPUTS='RETICULI_OUTPUTS'
_ENV_REQUEST='RETICULI_REQUEST'
_ENV_SIGNERS='RETICULI_SIGNERS'
_ENV_TIMEOUT='RETICULI_GATE_TIMEOUT'
_ENV_TOLERANCE='RETICULI_TOLERANCE'
_ENV_USAGE='RETICULI_USAGE'
_ENV_VENDOR='RETICULI_VENDOR'
_KEEP_ENV=('PATH','HOME','TMPDIR','LANG','LC_ALL','TZ','RETICULI_JAILED')
GATE_TIMEOUT=120
FURNISH_TIMEOUT=120
PRODUCER_TIMEOUT=3600
TOLERANCE=2.0
MUTANT_CEILING=10
MUTANT_FLOOR=1
MUTANT_HEADROOM=3
COST_KEYS=COST_LADDER=COST_UNITS=('usd','tokens','calls','seconds')
GUIDANCE_KEYS=('guidance','request')
KINDS=frozenset({'produce','gate'})
_SHELL='/bin/sh'
def _now(): return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _safe(d,p):
    if not isinstance(p,str) or not p or os.path.isabs(p) or '..' in p.split('/'): raise ClaimError(f'unsafe path: {p!r}')
    base=os.path.realpath(d); cur=base
    for bit in p.split('/'):
        cur=os.path.join(cur,bit)
        if os.path.islink(cur): raise ClaimError(f'symlink path: {p}')
    return os.path.abspath(cur)
def _hash_file(p):
    try:
        s=os.lstat(p)
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1: raise ClaimError(f'not a single-link regular file: {p}')
        with open(p,'rb') as f: return hashlib.sha256(f.read()).hexdigest()
    except OSError as e: raise ClaimError(str(e)) from e
def _write_json(p,v):
    os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(p)))
    try:
        with os.fdopen(fd,'w') as f: json.dump(v,f,sort_keys=True)
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def _copy_into(src,d,p):
    dest=_safe(d,p); _hash_file(src)
    os.makedirs(os.path.dirname(dest),exist_ok=True); shutil.copy2(src,dest)
    return dest
def _judging_host(): return {'python':sys.version,'platform':sys.platform,'machine':platform.machine()}
def canonical(v):
    try: return json.dumps(v,sort_keys=True)
    except (TypeError,ValueError) as e: raise ClaimError(f'noncanonical recipe: {e}') from e
def digest(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def dump_toml(v):
    def value(x):
        if isinstance(x,dict): return '{'+', '.join(json.dumps(k)+' = '+value(w) for k,w in x.items())+'}'
        if isinstance(x,list): return '['+', '.join(value(w) for w in x)+']'
        return json.dumps(x,ensure_ascii=False)
    lines=[]
    for k,x in v.items():
        if isinstance(x,dict):
            lines+=['['+k+']']+[json.dumps(a)+' = '+value(b) for a,b in x.items()]+['']
        elif isinstance(x,list) and all(isinstance(w,dict) for w in x):
            for w in x: lines+=['[['+k+']]']+[json.dumps(a)+' = '+value(b) for a,b in w.items()]+['']
        else: lines+=[json.dumps(k)+' = '+value(x)]
    return '\n'.join(lines)+'\n'
